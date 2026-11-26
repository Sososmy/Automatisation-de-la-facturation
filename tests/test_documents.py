from decimal import Decimal

import pytest

from src.documents import (
    AvoirDejaCree,
    ConflitReglement,
    ConflitIdempotence,
    ConflitVersion,
    DepotDocuments,
    ErreurDocument,
    TransitionInvalide,
    ValidationBloquee,
)
from src.schemas import (
    Anomalie,
    ChampExtrait,
    CodeAnomalie,
    DossierExtrait,
    Facture,
    LigneCalculee,
    Statut,
)


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


def test_source_reprise_conserve_le_dossier_corrige_et_l_original(tmp_path):
    with DepotDocuments(str(tmp_path / "documents.db")) as depot:
        original = DossierExtrait(
            source_hash="empreinte-source",
            client=ChampExtrait(valeur="Client extrait"),
        )
        depot.enregistrer_source(
            "empreinte-source",
            "commande.txt",
            "Texte source local",
            original,
        )
        corrige = original.model_copy(deep=True)
        corrige.client = ChampExtrait(
            valeur="Client confirmé",
            source="Correction humaine",
            confiance=1.0,
        )
        depot.mettre_a_jour_dossier_source(
            "empreinte-source",
            corrige,
            client_id_revu="CLI-001",
            articles_ids_revus=["ART-001"],
        )

        reprise = depot.obtenir_source("empreinte-source")
        assert reprise["texte"] == "Texte source local"
        assert reprise["dossier"].client.valeur == "Client confirmé"
        assert reprise["client_id_revu"] == "CLI-001"
        assert reprise["articles_ids_revus"] == ["ART-001"]
        assert depot.lister_dossiers_originaux()[0].client.valeur == "Client extrait"

        with pytest.raises(ErreurDocument, match="introuvable"):
            depot.obtenir_source("inconnu")


def test_reglements_simules_idempotents_et_sans_depassement(tmp_path):
    with DepotDocuments(str(tmp_path / "documents.db")) as depot:
        depot.creer_brouillon(nouvelle_facture())
        validee = depot.valider("fac-1", version_attendue=1, annee=2026)
        emise = depot.emettre("fac-1", version_attendue=validee.version)

        premier = depot.enregistrer_reglement(
            "fac-1", "MM-001", Decimal("1000"), "Mobile Money simulé"
        )
        assert depot.enregistrer_reglement(
            "fac-1", "MM-001", Decimal("1000"), "Mobile Money simulé"
        ) == premier
        assert depot.solde_restant("fac-1") == Decimal("1360")
        assert len(depot.lister_reglements("fac-1")) == 1

        with pytest.raises(ConflitReglement):
            depot.enregistrer_reglement(
                "fac-1", "MM-001", Decimal("900"), "Mobile Money simulé"
            )
        with pytest.raises(ValueError, match="solde restant"):
            depot.enregistrer_reglement(
                "fac-1", "MM-002", Decimal("1400"), "Espèces simulées"
            )

        second = depot.enregistrer_reglement(
            "fac-1", "MM-002", Decimal("1360"), "Espèces simulées"
        )
        assert second.facture_id == "fac-1"
        assert depot.solde_restant("fac-1") == Decimal("0")


def test_reglement_refuse_un_document_non_emis_et_montant_invalide(tmp_path):
    with DepotDocuments(str(tmp_path / "documents.db")) as depot:
        depot.creer_brouillon(nouvelle_facture())
        with pytest.raises(TransitionInvalide, match="facture émise"):
            depot.enregistrer_reglement(
                "fac-1", "MM-001", Decimal("1"), "Mobile Money simulé"
            )
        with pytest.raises(ValueError, match="positif"):
            depot.enregistrer_reglement(
                "fac-1", "MM-001", Decimal("0"), "Mobile Money simulé"
            )
