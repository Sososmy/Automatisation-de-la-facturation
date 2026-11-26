import json
import subprocess
import sys
from pathlib import Path

from src.evaluation import (charger_jeu, dossier_vers_dict, egal, evaluer_cas,
                            evaluer_pipeline)
from src.extraction import ExtractionError, extraire, lire_json, lire_texte

JEU = Path(__file__).resolve().parents[1] / "data" / "eval" / "exemple.jsonl"
JEUX_ANNOTES = (
    JEU,
    Path(__file__).resolve().parents[1] / "data" / "eval" / "bwai2026_developpement.jsonl",
    Path(__file__).resolve().parents[1] / "data" / "eval" / "bwai2026_test.jsonl",
)


def reponse_parfaite(attendu, texte):
    """Fabrique la réponse idéale du modèle à partir de la réponse attendue."""
    def champ(v):
        # la citation est ici le texte entier : toujours une citation fidèle du document
        return {"valeur": v, "source": None if v is None else texte}
    rep = {k: champ(attendu.get(k)) for k in
           ["client", "numero_commande", "date", "conditions_paiement",
            "total_ht_declare", "total_ttc_declare", "taux_taxe"]}
    rep["lignes"] = [{k: champ(l.get(k)) for k in ["designation", "quantite", "prix_unitaire", "remise"]}
                     for l in attendu["lignes"]]
    return rep


def test_lire_json_tolerant():
    assert lire_json('```json\n{"a": 1}\n```') == {"a": 1}
    assert lire_json('Voici : {"a": 1} merci') == {"a": 1}
    assert lire_json("pas de json") is None
    assert lire_json('{"a": ') is None
    assert lire_json("") is None


def test_egal_formats():
    assert egal("date", "2026-11-18", "18/11/2026")
    assert egal("quantite", "6500", "6 500")
    assert egal("taux_taxe", "18 %", "0,18")
    assert egal("conditions_paiement", "7 jours", "sous 7 jours")
    assert egal("client", "Société Exemple", "societe exemple")
    assert not egal("prix_unitaire", "6500", "9000")
    assert not egal("numero_commande", "BC-2026-045", "BC-2026")


def test_reponse_parfaite_donne_score_parfait():
    for jeu in JEUX_ANNOTES:
        for cas in charger_jeu(jeu):
            c = evaluer_cas(
                cas["attendu"],
                reponse_parfaite(cas["attendu"], cas["texte"]),
                cas["texte"],
            )
            assert c["faux"] == 0 and c["omissions"] == 0 and c["inventions"] == 0
            assert c["corrects"] == c["attendus"]
            assert c["lignes_en_trop"] == 0


def test_invention_detectee():
    cas = charger_jeu(JEU)[1]  # le client est absent du message
    rep = reponse_parfaite(cas["attendu"], cas["texte"])
    rep["client"] = {"valeur": "Société Exemple", "source": "Société Exemple"}
    c = evaluer_cas(cas["attendu"], rep, cas["texte"])
    assert c["inventions"] == 1
    assert c["citations_ok"] < c["citations"]  # la citation n'est pas dans le texte


def test_erreur_de_prix_et_omission():
    cas = charger_jeu(JEU)[0]
    rep = reponse_parfaite(cas["attendu"], cas["texte"])
    rep["lignes"][0]["prix_unitaire"] = {"valeur": "50", "source": "50"}
    rep["client"] = {"valeur": None, "source": None}
    c = evaluer_cas(cas["attendu"], rep, cas["texte"])
    assert c["faux"] == 1
    assert c["omissions"] == 1


def test_ligne_en_trop_et_ligne_manquante():
    cas = charger_jeu(JEU)[0]
    rep = reponse_parfaite(cas["attendu"], cas["texte"])
    rep["lignes"].append({"designation": {"valeur": "du", "source": "du"},
                          "quantite": {"valeur": "45", "source": "45"},
                          "prix_unitaire": {"valeur": "20", "source": "20"}})
    c = evaluer_cas(cas["attendu"], rep, cas["texte"])
    assert c["lignes_en_trop"] == 1
    rep["lignes"] = rep["lignes"][:1]
    c = evaluer_cas(cas["attendu"], rep, cas["texte"])
    assert c["lignes_trouvees"] == 1 and c["omissions"] >= 3


def test_json_invalide_compte_comme_omissions():
    cas = charger_jeu(JEU)[0]
    c = evaluer_cas(cas["attendu"], None, cas["texte"])
    assert c["corrects"] == 0 and c["omissions"] == c["attendus"]


def test_journal_et_detail_par_champ():
    cas = charger_jeu(JEU)[1]  # client absent du message
    rep = reponse_parfaite(cas["attendu"], cas["texte"])
    rep["client"] = {"valeur": "Société Exemple", "source": "inventé"}
    rep["lignes"][0]["prix_unitaire"] = {"valeur": "6500", "source": cas["texte"]}  # prix absent du message
    journal = []
    evaluer_cas(cas["attendu"], rep, cas["texte"], journal, "ex02")
    types = {(e["champ"], e["type"]) for e in journal}
    assert ("client", "invention") in types and ("prix_unitaire", "invention") in types
    assert all(e["id"] == "ex02" for e in journal)


def test_invention_avec_citation_valide_est_comptee_a_part():
    cas = charger_jeu(JEU)[1]
    rep = reponse_parfaite(cas["attendu"], cas["texte"])
    rep["client"] = {"valeur": "Société Exemple", "source": "inventé"}            # attrapée par la vérification
    rep["lignes"][0]["prix_unitaire"] = {"valeur": "5", "source": "5 sacs de ciment"}  # citation réelle, valeur fausse
    c = evaluer_cas(cas["attendu"], rep, cas["texte"])
    assert c["inventions"] == 2 and c["inventions_citees"] == 1


# ---------------- pipeline complet avec un faux modèle ----------------
class ClientFaux:
    nom = "faux-modele"

    def __init__(self, reponses, erreur=None):
        self.reponses, self.erreur = reponses, erreur

    def completer(self, systeme, utilisateur):
        if self.erreur:
            raise self.erreur
        texte = utilisateur.split("<document>\n")[1].split("\n</document>")[0]
        return self.reponses(texte)


def llm_parfait(cas):
    """Réponse idéale du modèle : seulement les valeurs attendues non nulles."""
    par_texte = {c["texte"]: c["attendu"] for c in cas}

    def reponses(texte):
        a = par_texte[texte]
        sortie = {k: v for k, v in a.items() if k != "lignes" and v is not None}
        sortie["lignes"] = [{k: v for k, v in l.items() if v is not None} for l in a["lignes"]]
        return json.dumps(sortie)
    return reponses


def test_pipeline_avec_modele_parfait_donne_un_score_parfait():
    for jeu in JEUX_ANNOTES:
        cas = charger_jeu(jeu)
        client = ClientFaux(llm_parfait(cas))
        r = evaluer_pipeline(cas, lambda texte: extraire(lire_texte(texte), client))
        assert r["exactitude"] == 1.0 and r["invention"] == 0.0
        assert r["erreurs_extraction"] == 0 and r["valeurs_rejetees"] == 0
        assert r["citations_verifiees"] == 1.0


def test_pipeline_rejette_les_inventions_du_modele():
    cas = charger_jeu(JEU)
    parfait = llm_parfait(cas)

    def menteur(texte):
        d = json.loads(parfait(texte))
        d["client"] = "Société Inventée"       # absent du message
        d["lignes"][0]["remise"] = "0"         # absent du message
        return json.dumps(d)
    journal = []
    r = evaluer_pipeline(cas, lambda t: extraire(lire_texte(t), ClientFaux(menteur)), journal)
    assert r["invention"] == 0.0               # la vérification a tout écarté
    assert r["valeurs_rejetees"] >= 3
    assert all(e["type"] != "invention" for e in journal)


def test_pipeline_modele_illisible_ou_en_panne():
    cas = charger_jeu(JEU)
    r = evaluer_pipeline(cas, lambda t: extraire(lire_texte(t), ClientFaux(lambda x: "désolé")))
    assert r["erreurs_extraction"] == len(cas) and r["exactitude"] == 0.0
    panne = ClientFaux(None, erreur=ExtractionError("réseau"))
    r = evaluer_pipeline(cas, lambda t: extraire(lire_texte(t), panne))
    assert r["erreurs_extraction"] == len(cas)


def test_pipeline_journalise_les_erreurs_d_extraction():
    cas = [charger_jeu(JEU)[0]]
    journal = []
    panne = ClientFaux(None, erreur=ExtractionError("réponse illisible"))
    resultats = evaluer_pipeline(
        cas,
        lambda texte: extraire(lire_texte(texte), panne),
        journal,
    )

    assert resultats["erreurs_extraction"] == 1
    assert journal[0] == {
        "id": cas[0]["id"],
        "type": "erreur_extraction",
        "message": "réponse illisible",
    }


def test_resume_expose_le_detail_par_champ():
    cas = charger_jeu(JEU)
    r = evaluer_pipeline(cas, lambda t: extraire(lire_texte(t), ClientFaux(lambda x: "{}")))
    assert r["par_champ"]["client"]["omission"] >= 1


def test_dossier_vers_dict_garde_valeur_et_source():
    cas = charger_jeu(JEU)[0]
    res = extraire(lire_texte(cas["texte"]), ClientFaux(llm_parfait([cas])))
    d = dossier_vers_dict(res.dossier)
    assert d["client"]["valeur"] == "Société Exemple" and d["client"]["source"]
    assert len(d["lignes"]) == 2


def test_cli_baseline_degrade_ecrit_un_rapport(tmp_path):
    racine = Path(__file__).resolve().parents[1]
    sortie = tmp_path / "rapport.json"
    execution = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.evaluate_extraction",
            "--mode",
            "degrade",
            "--output",
            str(sortie),
        ],
        cwd=racine,
        check=True,
        capture_output=True,
    )

    rapport = json.loads(sortie.read_text(encoding="utf-8"))
    assert execution.stdout.startswith(b"{")
    assert rapport["resultats"]["cas"] == len(charger_jeu(JEU))
    assert rapport["resultats"]["erreurs_extraction"] == 0
