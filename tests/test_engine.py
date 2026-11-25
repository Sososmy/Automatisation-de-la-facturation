from decimal import Decimal

import pytest

from src.engine import calculer_facture
from src.schemas import (
    Article,
    ChampExtrait,
    CodeAnomalie,
    DossierExtrait,
    LigneExtraite,
)


def champ(valeur: str | None = None) -> ChampExtrait:
    return ChampExtrait(valeur=valeur, source=valeur, confiance=1.0)


def dossier(
    *,
    quantite: str = "10",
    prix: str = "6500",
    remise: str | None = None,
    total_ht: str | None = None,
    total_ttc: str | None = None,
) -> DossierExtrait:
    return DossierExtrait(
        lignes=[
            LigneExtraite(
                designation=champ("Ciment 50 kg"),
                quantite=champ(quantite),
                prix_unitaire=champ(prix),
                remise=champ(remise),
            )
        ],
        total_ht_declare=champ(total_ht),
        total_ttc_declare=champ(total_ttc),
    )


def test_calculer_facture_applique_remise_avant_tva_et_verifie_totaux() -> None:
    facture, anomalies = calculer_facture(
        dossier(remise="5%", total_ht="61750", total_ttc="72865"),
        [Article(id="ART-001", designation="Ciment 50 kg", prix_reference=Decimal("6500"))],
        facture_id="facture-1",
        client_id="client-1",
        taux_taxe=Decimal("0.18"),
    )

    assert facture.total_ht == Decimal("61750")
    assert facture.total_taxe == Decimal("11115")
    assert facture.total_ttc == Decimal("72865")
    assert facture.lignes[0].remise_pct == Decimal("5")
    assert anomalies == []


def test_calculer_facture_absence_remise_et_article_non_taxable() -> None:
    facture, anomalies = calculer_facture(
        dossier(quantite="2", prix="1000"),
        [
            Article(
                id="ART-EXO",
                designation="Article exonéré",
                prix_reference=Decimal("1000"),
                taxable=False,
            )
        ],
        facture_id="facture-2",
        client_id="client-1",
        taux_taxe=Decimal("0.18"),
    )

    assert facture.total_ht == Decimal("2000")
    assert facture.total_taxe == Decimal("0")
    assert facture.total_ttc == Decimal("2000")
    assert facture.lignes[0].remise_pct == Decimal("0")
    assert anomalies == []


def test_calculer_facture_signale_un_total_declare_different() -> None:
    _, anomalies = calculer_facture(
        dossier(total_ht="65000", total_ttc="76701"),
        [Article(id="ART-001", designation="Ciment 50 kg", prix_reference=Decimal("6500"))],
        facture_id="facture-3",
        client_id="client-1",
        taux_taxe=Decimal("0.18"),
    )

    assert [anomalie.code for anomalie in anomalies] == [CodeAnomalie.ECART_MONTANT]


def test_calculer_facture_arrondit_les_montants_xof_a_unite() -> None:
    facture, _ = calculer_facture(
        dossier(quantite="1", prix="3"),
        [Article(id="ART-001", designation="Ciment 50 kg", prix_reference=Decimal("3"))],
        facture_id="facture-arrondi",
        client_id="client-1",
        taux_taxe=Decimal("0.18"),
    )

    assert facture.total_ht == Decimal("3")
    assert facture.total_taxe == Decimal("1")
    assert facture.total_ttc == Decimal("4")


def test_calculer_facture_refuse_une_remise_superieure_a_100_pourcents() -> None:
    with pytest.raises(ValueError, match="remise"):
        calculer_facture(
            dossier(remise="101%"),
            [Article(id="ART-001", designation="Ciment 50 kg", prix_reference=Decimal("6500"))],
            facture_id="facture-4",
            client_id="client-1",
            taux_taxe=Decimal("0.18"),
        )
