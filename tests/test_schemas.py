from decimal import Decimal

import pytest

from src.schemas import DossierExtrait, en_decimal, en_taux, normaliser


@pytest.mark.parametrize("texte, attendu", [
    ("6500", Decimal("6500")),
    ("6 500 FCFA", Decimal("6500")),
    ("6\u00a0500", Decimal("6500")),
    ("6.500", Decimal("6500")),
    ("1,250", Decimal("1250")),
    ("1.250.000", Decimal("1250000")),
    ("1 250,50", Decimal("1250.50")),
    ("1,5", Decimal("1.5")),
    ("12.5", Decimal("12.5")),
    ("10%", Decimal("10")),
    ("-3", Decimal("-3")),
])
def test_en_decimal_formats_lisibles(texte, attendu):
    assert en_decimal(texte) == attendu


@pytest.mark.parametrize("texte", [None, "", "abc", "FCFA", "-"])
def test_en_decimal_illisible_donne_none(texte):
    assert en_decimal(texte) is None


def test_normaliser_retire_accents_casse_et_espaces():
    assert normaliser("  Société   EXEMPLE ") == "societe exemple"
    assert normaliser(None) == ""


@pytest.mark.parametrize("texte, attendu", [
    ("18 %", Decimal("0.18")),
    ("18%", Decimal("0.18")),
    ("18", Decimal("0.18")),
    ("0,18", Decimal("0.18")),
    ("TVA 18 %", Decimal("0.18")),
    ("1 %", Decimal("0.01")),
    ("0", Decimal("0")),
    ("Exonéré", Decimal("0")),
    ("exonération de TVA", Decimal("0")),
])
def test_en_taux_formats_lisibles(texte, attendu):
    assert en_taux(texte) == attendu


@pytest.mark.parametrize("texte", [None, "", "abc", "-5 %"])
def test_en_taux_illisible_donne_none(texte):
    assert en_taux(texte) is None


def test_dossier_a_deux_totaux_facultatifs_et_champs_techniques_vides():
    d = DossierExtrait()
    assert d.total_ht_declare.valeur is None
    assert d.total_ttc_declare.valeur is None
    assert d.taux_taxe.valeur is None
    assert d.source_hash is None and d.nom_fichier_source is None
    assert not hasattr(d, "total_declare")
