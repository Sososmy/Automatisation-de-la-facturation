from decimal import Decimal

import pytest

from src.controls import (
    controler, controle_client, controle_confiance, controle_doublon,
    controle_livraison, controle_lignes, controle_taxe, empreinte, peut_valider,
)
from src.schemas import (
    Article, ChampExtrait, Client, CodeAnomalie, DossierExtrait,
    LigneExtraite, LigneLivree,
)

CLIENTS = [
    Client(id="CLI-001", nom="Société Exemple SARL"),
    Client(id="CLI-002", nom="Boutique Test"),
]
ARTICLES = [
    Article(id="ART-001", designation="Ciment 50 kg", prix_reference=Decimal("6500")),
    Article(id="ART-002", designation="Fer à béton 10 mm", prix_reference=Decimal("4200")),
]


def champ(valeur, confiance=0.95):
    return ChampExtrait(valeur=valeur, source="test", confiance=confiance)


def ligne(designation="Ciment 50 kg", quantite="10", prix="6500", remise=None, confiance=0.95):
    return LigneExtraite(
        designation=champ(designation, confiance),
        quantite=champ(quantite, confiance),
        prix_unitaire=champ(prix, confiance),
        remise=champ(remise, confiance) if remise else ChampExtrait(),
    )


def dossier(client="Société Exemple SARL", lignes=None, **kw):
    return DossierExtrait(
        client=champ(client),
        date=champ("2026-11-20"),
        lignes=lignes if lignes is not None else [ligne()],
        **kw,
    )


def codes(anomalies):
    return [a.code for a in anomalies]


# ---------------------------- dossier propre ----------------------------
def test_dossier_propre_sans_anomalie_et_validable():
    anomalies = controler(dossier(), CLIENTS, ARTICLES)
    assert anomalies == []
    assert peut_valider(anomalies)


# ------------------------------- client ---------------------------------
def test_client_exact_ou_sans_accent_est_accepte():
    assert controle_client(dossier(client="Societe exemple sarl"), CLIENTS) == []


def test_client_proche_est_a_confirmer():
    a = controle_client(dossier(client="Societe Exemple"), CLIENTS)
    assert codes(a) == [CodeAnomalie.CLIENT_INCERTAIN]
    assert a[0].bloquante


def test_client_inconnu():
    a = controle_client(dossier(client="Zzz Quincaillerie"), CLIENTS)
    assert codes(a) == [CodeAnomalie.CLIENT_INCONNU]


def test_client_absent():
    d = dossier()
    d.client = ChampExtrait()
    assert codes(controle_client(d, CLIENTS)) == [CodeAnomalie.CLIENT_MANQUANT]


# ------------------------------- lignes ---------------------------------
def test_aucune_ligne():
    a = controle_lignes(dossier(lignes=[]), ARTICLES)
    assert codes(a) == [CodeAnomalie.CHAMP_MANQUANT]


def test_champs_manquants_ne_sont_pas_inventes():
    l = LigneExtraite(designation=champ("Ciment 50 kg"))
    a = controle_lignes(dossier(lignes=[l]), ARTICLES)
    assert codes(a).count(CodeAnomalie.CHAMP_MANQUANT) == 2  # quantité et prix
    assert all(x.ligne == 1 for x in a)


def test_quantite_invalide_ou_negative():
    for q in ("abc", "0", "-2"):
        a = controle_lignes(dossier(lignes=[ligne(quantite=q)]), ARTICLES)
        assert CodeAnomalie.CHAMP_INVALIDE in codes(a), q


def test_remise_hors_bornes():
    a = controle_lignes(dossier(lignes=[ligne(remise="150")]), ARTICLES)
    assert CodeAnomalie.CHAMP_INVALIDE in codes(a)
    assert controle_lignes(dossier(lignes=[ligne(remise="10%")]), ARTICLES) == []


def test_article_inconnu():
    a = controle_lignes(dossier(lignes=[ligne(designation="Sable fin")]), ARTICLES)
    assert codes(a) == [CodeAnomalie.ARTICLE_INCONNU]


def test_designation_ecrite_autrement_reste_reconnue():
    assert controle_lignes(dossier(lignes=[ligne(designation="ciment 50kg")]), ARTICLES) == []


def test_prix_inhabituel_au_dela_du_seuil():
    assert controle_lignes(dossier(lignes=[ligne(prix="6700")]), ARTICLES) == []  # +3 %
    a = controle_lignes(dossier(lignes=[ligne(prix="9000")]), ARTICLES)  # +38 %
    assert codes(a) == [CodeAnomalie.PRIX_INHABITUEL]


def test_seuil_de_prix_est_parametrable():
    d = dossier(lignes=[ligne(prix="7200")])  # +11 %
    assert controle_lignes(d, ARTICLES, seuil_prix=0.30) == []
    assert codes(controle_lignes(d, ARTICLES, seuil_prix=0.10)) == [CodeAnomalie.PRIX_INHABITUEL]


# ------------------------------ confiance -------------------------------
def test_confiance_faible_signalee_mais_non_bloquante():
    d = dossier(lignes=[ligne(confiance=0.5)])
    a = controle_confiance(d)
    assert a and all(x.code == CodeAnomalie.CONFIANCE_FAIBLE and not x.bloquante for x in a)
    assert peut_valider(a)


def test_champ_absent_nest_pas_compte_en_confiance_faible():
    d = dossier()
    d.conditions_paiement = ChampExtrait(valeur=None, confiance=0.0)
    assert controle_confiance(d) == []


# ------------------------------- doublon --------------------------------
def test_doublon_meme_contenu():
    assert codes(controle_doublon(dossier(), [dossier()])) == [CodeAnomalie.DOUBLON]


def test_doublon_meme_numero_de_commande_meme_client():
    ancien = dossier(numero_commande=champ("BC-77"), lignes=[ligne(quantite="3")])
    nouveau = dossier(numero_commande=champ("bc-77"), lignes=[ligne(quantite="5")])
    assert codes(controle_doublon(nouveau, [ancien])) == [CodeAnomalie.DOUBLON]


def test_pas_de_doublon_si_contenu_different():
    autre = dossier(lignes=[ligne(quantite="99")])
    assert controle_doublon(dossier(), [autre]) == []


def test_empreinte_stable_malgre_ecritures_differentes():
    a = dossier(lignes=[ligne(quantite="10", prix="6 500")])
    b = dossier(client="societe exemple sarl", lignes=[ligne(quantite="10", prix="6500")])
    assert empreinte(a) == empreinte(b)


# ------------------------------ livraison -------------------------------
def test_sans_livraison_pas_de_controle():
    assert controle_livraison(dossier()) == []


def test_livraison_conforme():
    d = dossier(livraison=[LigneLivree(designation="Ciment 50kg", quantite=Decimal("10"))])
    assert controle_livraison(d) == []


def test_livraison_partielle_bloque():
    d = dossier(livraison=[LigneLivree(designation="Ciment 50 kg", quantite=Decimal("8"))])
    a = controle_livraison(d)
    assert codes(a) == [CodeAnomalie.ECART_LIVRAISON]
    assert not peut_valider(a)


def test_livraison_en_plusieurs_bons_additionnes():
    d = dossier(livraison=[
        LigneLivree(designation="Ciment 50 kg", quantite=Decimal("6")),
        LigneLivree(designation="Ciment 50 kg", quantite=Decimal("4")),
    ])
    assert controle_livraison(d) == []


def test_article_livre_mais_non_commande():
    d = dossier(livraison=[
        LigneLivree(designation="Ciment 50 kg", quantite=Decimal("10")),
        LigneLivree(designation="Sable fin", quantite=Decimal("2")),
    ])
    assert codes(controle_livraison(d)) == [CodeAnomalie.INCOHERENCE_PIECES]


def test_article_commande_non_livre():
    d = dossier(livraison=[LigneLivree(designation="Sable fin", quantite=Decimal("2"))])
    assert CodeAnomalie.ECART_LIVRAISON in codes(controle_livraison(d))


# --------------------------- validation humaine --------------------------
def test_anomalie_bloquante_resolue_debloque_la_validation():
    anomalies = controler(dossier(client="Zzz Quincaillerie"), CLIENTS, ARTICLES)
    assert not peut_valider(anomalies)
    for a in anomalies:
        a.resolue = True
    assert peut_valider(anomalies)


def test_cumul_des_controles():
    d = dossier(
        client="Zzz Quincaillerie",
        lignes=[ligne(prix="9000"), ligne(designation="Sable fin")],
    )
    c = codes(controler(d, CLIENTS, ARTICLES, historique=[d]))
    assert {CodeAnomalie.CLIENT_INCONNU, CodeAnomalie.PRIX_INHABITUEL,
            CodeAnomalie.ARTICLE_INCONNU, CodeAnomalie.DOUBLON} <= set(c)


# -------------------------------- taxe ----------------------------------
def test_taxe_absente_aucune_anomalie():
    assert controle_taxe(dossier()) == []


@pytest.mark.parametrize("mention", ["18 %", "TVA 18%", "0,18", "18"])
def test_taxe_conforme_au_taux_parametre(mention):
    assert controle_taxe(dossier(taux_taxe=champ(mention))) == []


def test_taxe_differente_est_signalee_et_bloquante():
    a = controle_taxe(dossier(taux_taxe=champ("20 %")))
    assert codes(a) == [CodeAnomalie.TAXE_INCOHERENTE]
    assert a[0].bloquante and "20" in a[0].message and "18" in a[0].message


def test_source_exoneree_alors_que_le_taux_parametre_est_18():
    a = controle_taxe(dossier(taux_taxe=champ("Exonéré")))
    assert codes(a) == [CodeAnomalie.TAXE_INCOHERENTE]


def test_taux_attendu_parametrable():
    d = dossier(taux_taxe=champ("Exonéré"))
    assert controle_taxe(d, taux_attendu=Decimal("0")) == []
    assert controle_taxe(dossier(taux_taxe=champ("18 %")), taux_attendu=Decimal("0")) != []


def test_mention_de_taxe_illisible_avertit_sans_bloquer():
    a = controle_taxe(dossier(taux_taxe=champ("abc")))
    assert codes(a) == [CodeAnomalie.CHAMP_INVALIDE]
    assert not a[0].bloquante


def test_controler_transmet_le_taux_attendu():
    d = dossier(taux_taxe=champ("18 %"))
    assert controler(d, CLIENTS, ARTICLES) == []
    assert CodeAnomalie.TAXE_INCOHERENTE in codes(
        controler(d, CLIENTS, ARTICLES, taux_taxe_attendu=Decimal("0.20")))


# ------------------------- totaux HT et TTC -----------------------------
def test_totaux_declares_facultatifs_ne_creent_pas_danomalie():
    assert controler(dossier(), CLIENTS, ARTICLES) == []
    d = dossier(total_ht_declare=champ("145 750"), total_ttc_declare=champ("171 985"))
    assert controler(d, CLIENTS, ARTICLES) == []


def test_confiance_faible_sur_totaux_et_taxe():
    d = dossier(
        total_ht_declare=champ("145750", 0.4),
        total_ttc_declare=champ("171985", 0.5),
        taux_taxe=champ("18 %", 0.6),
    )
    a = controle_confiance(d)
    messages = " ".join(x.message for x in a)
    assert "total HT déclaré" in messages
    assert "total TTC déclaré" in messages
    assert "taux de taxe" in messages
    assert peut_valider(a)


# -------------------------- doublon par fichier -------------------------
def test_doublon_meme_fichier_meme_si_contenu_different():
    ancien = dossier(source_hash="abc123", lignes=[ligne(quantite="3")])
    nouveau = dossier(source_hash="abc123", lignes=[ligne(quantite="99")])
    a = controle_doublon(nouveau, [ancien])
    assert codes(a) == [CodeAnomalie.DOUBLON]
    assert "fichier" in a[0].message


def test_hash_differents_et_contenus_differents_pas_de_doublon():
    ancien = dossier(source_hash="aaa", lignes=[ligne(quantite="3")])
    nouveau = dossier(source_hash="bbb", lignes=[ligne(quantite="99")])
    assert controle_doublon(nouveau, [ancien]) == []


def test_hash_absent_ou_vide_ne_declenche_pas_de_doublon():
    ancien = dossier(source_hash="", lignes=[ligne(quantite="3")])
    nouveau = dossier(source_hash="", lignes=[ligne(quantite="99")])
    assert controle_doublon(nouveau, [ancien]) == []


def test_meme_contenu_avec_fichiers_differents_reste_un_doublon():
    ancien = dossier(source_hash="pdf-1")
    nouveau = dossier(source_hash="photo-2")
    a = controle_doublon(nouveau, [ancien])
    assert codes(a) == [CodeAnomalie.DOUBLON]
    assert "contenu" in a[0].message


# ------------------- rapprochement des articles (désignations) -------------------
@pytest.mark.parametrize("designation", [
    "sacs de ciment 50kg",              # mots descriptifs en plus
    "Ciment 50 kg",
    "ciment 50KG",
    "barres de fer à béton 10 mm",
    "12 barres de fer a beton 10mm",    # quantité restée dans la désignation
    "Cimnt 50 kg",                      # faute de frappe
])
def test_designations_reconnues(designation):
    assert controle_lignes(dossier(lignes=[ligne(designation=designation, prix="6500" if "iment" in designation.lower() or "cimnt" in designation.lower() else "4200")]), ARTICLES) == []


@pytest.mark.parametrize("designation", [
    "fer à béton 12 mm",    # autre article : le nombre diffère
    "barres de fer 8 mm",
    "ciment 35 kg",
    "fer à béton",          # trop vague : plusieurs articles possibles
    "ciment",
])
def test_designations_non_reconnues_sont_signalees(designation):
    a = controle_lignes(dossier(lignes=[ligne(designation=designation)]), ARTICLES)
    assert codes(a) == [CodeAnomalie.ARTICLE_INCONNU]
