"""Notation d'une extraction par rapport à la réponse attendue (jeu annoté).

Sert à comparer des modèles (scripts/comparer_modeles.py) et à alimenter la
fiche IA. Aucune dépendance réseau : tout est testable avec un faux modèle.
"""
from __future__ import annotations

import json
import re
import statistics
import time
from collections import Counter
from typing import Callable, Optional

from rapidfuzz import fuzz

from src.extraction import ExtractionError, ResultatExtraction, lire_json, normaliser_date  # noqa: F401
from src.schemas import DossierExtrait, en_decimal, en_taux, normaliser

CHAMPS = ["client", "numero_commande", "date", "conditions_paiement",
          "total_ht_declare", "total_ttc_declare", "taux_taxe"]
CHAMPS_LIGNE = ["designation", "quantite", "prix_unitaire", "remise"]
CRITIQUES = {"client", "quantite", "prix_unitaire"}  # une erreur ici fausse la facture
NUMERIQUES = {"quantite", "prix_unitaire", "remise", "total_ht_declare", "total_ttc_declare"}
SEUIL_TEXTE = {"client": 90, "designation": 85, "conditions_paiement": 80, "numero_commande": 100}
_DUREE_PAIEMENT = re.compile(r"\b(\d+)\s*(jours?|semaines?|mois|ans?|annees?)\b")

# --------------------------------------------------------------------------
# Lecture d'une extraction (dict) et conversion d'un DossierExtrait
# --------------------------------------------------------------------------
def _valeur(champ) -> Optional[str]:
    v = champ.get("valeur") if isinstance(champ, dict) else champ
    if v is None:
        return None
    v = str(v).strip()
    return v or None


def _source(champ) -> Optional[str]:
    s = champ.get("source") if isinstance(champ, dict) else None
    return str(s).strip() if s else None


# --------------------------------------------------------------------------
# Comparaison de valeurs
# --------------------------------------------------------------------------
def egal(champ: str, attendu: str, predit: str) -> bool:
    if champ in NUMERIQUES:
        return en_decimal(attendu) is not None and en_decimal(attendu) == en_decimal(predit)
    if champ == "taux_taxe":
        return en_taux(attendu) is not None and en_taux(attendu) == en_taux(predit)
    if champ == "date":
        da, dp = normaliser_date(attendu), normaliser_date(predit)
        return da == dp if da and dp else normaliser(attendu) == normaliser(predit)
    a, p = normaliser(attendu).replace(" ", ""), normaliser(predit).replace(" ", "")
    if champ == "conditions_paiement":
        duree_attendue = _DUREE_PAIEMENT.search(normaliser(attendu))
        duree_predite = _DUREE_PAIEMENT.search(normaliser(predit))
        if duree_attendue and duree_predite:
            return duree_attendue.groups() == duree_predite.groups()
    return fuzz.ratio(a, p) >= SEUIL_TEXTE.get(champ, 90)


def _compter(c: Counter, champ: str, attendu, predit, source, texte_norm: str,
             journal: Optional[list] = None, id_cas=None) -> None:
    cite = bool(source) and normaliser(source) in texte_norm

    def noter(type_: str) -> None:
        c[f"{type_}:{champ}"] += 1
        if journal is not None:
            journal.append({"id": id_cas, "type": type_, "champ": champ,
                            "attendu": attendu, "predit": predit, "source": source})

    if attendu is not None:
        c["attendus"] += 1
        critique = champ in CRITIQUES
        c["critiques_attendus"] += critique
        if predit is None:
            c["omissions"] += 1
            noter("omission")
        elif egal(champ, attendu, predit):
            c["corrects"] += 1
            c["critiques_corrects"] += critique
        else:
            c["faux"] += 1
            noter("faux")
    else:
        c["absents"] += 1
        if predit is not None:
            c["inventions"] += 1
            c["inventions_citees"] += cite  # invention dont la citation est pourtant dans le texte
            noter("invention")
    if predit is not None:
        c["citations"] += 1
        c["citations_ok"] += cite


def evaluer_cas(attendu: dict, brut: Optional[dict], texte: str,
                journal: Optional[list] = None, id_cas=None) -> Counter:
    """Compte les bonnes réponses, erreurs, omissions et inventions d'un cas."""
    c: Counter = Counter()
    brut = brut or {}
    tn = normaliser(texte)

    for champ in CHAMPS:
        _compter(c, champ, attendu.get(champ), _valeur(brut.get(champ)), _source(brut.get(champ)), tn, journal, id_cas)

    gold = attendu.get("lignes") or []
    pred = [l for l in (brut.get("lignes") or []) if isinstance(l, dict)]
    c["lignes_attendues"] += len(gold)
    libres = list(range(len(pred)))
    for g in gold:
        meilleur, score_max = None, 0.0
        for i in libres:
            p = _valeur(pred[i].get("designation")) or ""
            s = fuzz.ratio(normaliser(g.get("designation", "")).replace(" ", ""), normaliser(p).replace(" ", ""))
            if s > score_max:
                meilleur, score_max = i, s
        if meilleur is None or score_max < 70:
            for champ in CHAMPS_LIGNE:  # ligne non trouvée : tout ce qui était attendu est omis
                _compter(c, champ, g.get(champ), None, None, tn, journal, id_cas)
            continue
        libres.remove(meilleur)
        c["lignes_trouvees"] += 1
        for champ in CHAMPS_LIGNE:
            _compter(c, champ, g.get(champ), _valeur(pred[meilleur].get(champ)),
                     _source(pred[meilleur].get(champ)), tn, journal, id_cas)
    c["lignes_en_trop"] += len(libres)
    return c


# --------------------------------------------------------------------------
# Évaluation d'un modèle sur tout le jeu
# --------------------------------------------------------------------------
def charger_jeu(chemin) -> list[dict]:
    with open(chemin, encoding="utf-8") as f:
        return [json.loads(l) for l in f if l.strip()]


def _champ_dict(c) -> dict:
    return {"valeur": c.valeur, "source": c.source}


def dossier_vers_dict(d: DossierExtrait) -> dict:
    """DossierExtrait -> dict {champ: {valeur, source}} comparable à la réponse attendue."""
    sortie = {nom: _champ_dict(getattr(d, nom)) for nom in CHAMPS}
    sortie["lignes"] = [{nom: _champ_dict(getattr(l, nom)) for nom in CHAMPS_LIGNE} for l in d.lignes]
    return sortie


def evaluer_pipeline(cas: list[dict], extraire_fn: Callable[[str], ResultatExtraction],
                     journal: Optional[list] = None) -> dict:
    """Note le pipeline complet (modèle + vérification dans le code) sur le jeu annoté.

    `extraire_fn(texte)` renvoie un ResultatExtraction ou lève ExtractionError.
    """
    total: Counter = Counter()
    latences: list[float] = []
    for un_cas in cas:
        t0 = time.perf_counter()
        try:
            res = extraire_fn(un_cas["texte"])
            brut = dossier_vers_dict(res.dossier)
            total["rejets"] += len(res.rejets)
            total["mode_degrade"] += res.mode == "degrade"
        except ExtractionError as erreur:
            brut = None
            total["erreurs_extraction"] += 1
            if journal is not None:
                journal.append(
                    {
                        "id": un_cas.get("id"),
                        "type": "erreur_extraction",
                        "message": str(erreur),
                    }
                )
        latences.append(time.perf_counter() - t0)
        total += evaluer_cas(un_cas["attendu"], brut, un_cas["texte"], journal, un_cas.get("id"))
    return resume(total, latences, len(cas))


def _taux(a: float, b: float) -> Optional[float]:
    return round(a / b, 3) if b else None


def resume(c: Counter, latences: list[float], nb_cas: int) -> dict:
    ls = sorted(latences)
    return {
        "cas": nb_cas,
        "erreurs_extraction": c["erreurs_extraction"],
        "mode_degrade": c["mode_degrade"],
        "valeurs_rejetees": c["rejets"],
        "exactitude": _taux(c["corrects"], c["attendus"]),
        "exactitude_critique": _taux(c["critiques_corrects"], c["critiques_attendus"]),
        "erreurs": _taux(c["faux"], c["attendus"]),
        "omissions": _taux(c["omissions"], c["attendus"]),
        "invention": _taux(c["inventions"], c["absents"]),
        "inventions_nb": c["inventions"],
        "inventions_citation_valide": c["inventions_citees"],
        "lignes_trouvees": _taux(c["lignes_trouvees"], c["lignes_attendues"]),
        "lignes_en_trop": c["lignes_en_trop"],
        "citations_verifiees": _taux(c["citations_ok"], c["citations"]),
        "latence_moy_s": round(statistics.mean(ls), 2) if ls else None,
        "latence_p95_s": round(ls[min(len(ls) - 1, int(0.95 * len(ls)))], 2) if ls else None,
        "par_champ": par_champ(c),
    }


def par_champ(c: Counter) -> dict:
    """Inventions, erreurs et omissions décomposées par champ."""
    detail: dict = {}
    for cle, n in c.items():
        if ":" in cle and cle.split(":")[0] in ("invention", "faux", "omission"):
            type_, champ = cle.split(":", 1)
            detail.setdefault(champ, {})[type_] = n
    return dict(sorted(detail.items()))
