from decimal import Decimal

import pytest

from src.documents import (
    AvoirDejaCree,
    ConflitIdempotence,
    ConflitVersion,
    DepotDocuments,
    ValidationBloquee,
)
from src.schemas import Anomalie, CodeAnomalie, Facture, LigneCalculee, Statut


def nouvelle_facture(facture_id: str = "fac-1") -> Facture:
    return Facture(
        id=facture_id,
        client_id="client-1",
        lignes=[
            LigneCalculee(
                article_id="article-1",
                designation="Sac de ciment",
                quantite=Decimal("2"),
                prix_unitaire=Decimal("1000"),
                base_ht=Decimal("2000"),
                taxe=Decimal("360"),
                total_ttc=Decimal("2360"),
            )
        ],
        total_ht=Decimal("2000"),
        total_taxe=Decimal("360"),
        total_ttc=Decimal("2360"),
    )


def test_creation_brouillon_idempotente_et_conflit(tmp_path):
    with DepotDocuments(str(tmp_path / "documents.db")) as depot:
        facture = nouvelle_facture()
        assert depot.creer_brouillon(facture) == facture
        assert depot.creer_brouillon(facture) == facture

        modifiee = facture.model_copy(update={"total_ttc": Decimal("2400")})
        with pytest.raises(ConflitIdempotence):
            depot.creer_brouillon(modifiee)


def test_modification_versionnee_et_validation_des_anomalies(tmp_path):
    with DepotDocuments(str(tmp_path / "documents.db")) as depot:
        depot.creer_brouillon(nouvelle_facture())
        correction = nouvelle_facture().model_copy(
            update={"total_ttc": Decimal("2361")}
        )
        corrigee = depot.modifier_brouillon(correction, version_attendue=1)
        assert corrigee.version == 2
        with pytest.raises(ConflitVersion):
            depot.modifier_brouillon(correction, version_attendue=1)

        anomalie = Anomalie(
            code=CodeAnomalie.CHAMP_MANQUANT,
            message="Information à confirmer",
        )
        with pytest.raises(ValidationBloquee):
            depot.valider("fac-1", [anomalie], version_attendue=2)

        validee = depot.valider(
            "fac-1",
            [anomalie.model_copy(update={"resolue": True})],
            version_attendue=2,
            annee=2026,
        )
        assert validee.statut == Statut.VALIDEE
        assert validee.numero == "SIM-FACTURE-2026-000001"
        assert validee.version == 3
        assert depot.valider("fac-1", version_attendue=999) == validee


def test_emission_simulee_et_avoir_total_unique(tmp_path):
    with DepotDocuments(str(tmp_path / "documents.db")) as depot:
        depot.creer_brouillon(nouvelle_facture())
        validee = depot.valider("fac-1", version_attendue=1, annee=2026)
        emise = depot.emettre("fac-1", version_attendue=validee.version)
        assert emise.statut == Statut.EMISE
        assert emise.version == 3

        avoir = depot.creer_avoir_total(
            "avoir-1",
            "fac-1",
            version_attendue=emise.version,
            annee=2026,
        )
        assert avoir.statut == Statut.AVOIR
        assert avoir.facture_origine_id == "fac-1"
        assert avoir.total_ttc == Decimal("-2360")
        assert avoir.lignes[0].quantite == Decimal("-2")
        assert depot.creer_avoir_total(
            "avoir-1", "fac-1", version_attendue=999, annee=2026
        ) == avoir
        with pytest.raises(AvoirDejaCree):
            depot.creer_avoir_total(
                "avoir-2", "fac-1", version_attendue=emise.version, annee=2026
            )
