"""Moteur déterministe de calcul des montants de facture."""
from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP
from typing import Sequence

from src.config import settings
from src.schemas import (
    Anomalie,
    Article,
    CodeAnomalie,
    DossierExtrait,
    Facture,
    LigneCalculee,
    en_decimal,
)

_UNITE_XOF = Decimal("1")


def _arrondir(montant: Decimal) -> Decimal:
    return montant.quantize(_UNITE_XOF, rounding=ROUND_HALF_UP)


def _montant_declare(
    valeur: str | None,
    libelle: str,
    montant_calcule: Decimal,
) -> Anomalie | None:
    if valeur is None or not valeur.strip():
        return None

    declare = en_decimal(valeur)
    if declare is None:
        return Anomalie(
            code=CodeAnomalie.CHAMP_INVALIDE,
            message=f"{libelle} déclaré illisible (« {valeur} »).",
        )

    declare = _arrondir(declare)
    if declare != montant_calcule:
        return Anomalie(
            code=CodeAnomalie.ECART_MONTANT,
            message=(
                f"{libelle} déclaré {declare} F CFA, "
                f"mais le montant recalculé est {montant_calcule} F CFA."
            ),
        )
    return None


def calculer_facture(
    dossier: DossierExtrait,
    articles: Sequence[Article],
    *,
    facture_id: str,
    client_id: str,
    taux_taxe: Decimal | None = None,
) -> tuple[Facture, list[Anomalie]]:
    """Calcule une facture à partir de lignes extraites et d'articles confirmés.

    `articles` doit contenir l'article confirmé correspondant à chaque ligne,
    dans le même ordre. Les données manquantes ou invalides empêchent le calcul.
    """
    if not facture_id.strip():
        raise ValueError("facture_id ne peut pas être vide.")
    if not client_id.strip():
        raise ValueError("client_id ne peut pas être vide.")
    if not dossier.lignes:
        raise ValueError("Le dossier doit contenir au moins une ligne.")
    if len(articles) != len(dossier.lignes):
        raise ValueError("Il faut un article confirmé pour chaque ligne extraite.")

    taux = settings.tax_rate if taux_taxe is None else taux_taxe
    if not taux.is_finite() or taux < 0:
        raise ValueError("Le taux de taxe doit être un Decimal fini positif ou nul.")

    lignes_calculees: list[LigneCalculee] = []
    for numero, (ligne, article) in enumerate(zip(dossier.lignes, articles), start=1):
        quantite = en_decimal(ligne.quantite.valeur)
        prix_unitaire = en_decimal(ligne.prix_unitaire.valeur)
        if quantite is None or quantite <= 0:
            raise ValueError(f"Ligne {numero} : quantité absente, illisible ou non positive.")
        if prix_unitaire is None or prix_unitaire < 0:
            raise ValueError(f"Ligne {numero} : prix unitaire absent, illisible ou négatif.")

        remise_texte = ligne.remise.valeur
        remise_pct = (
            Decimal("0")
            if remise_texte is None or not remise_texte.strip()
            else en_decimal(remise_texte)
        )
        if remise_pct is None or not Decimal("0") <= remise_pct <= Decimal("100"):
            raise ValueError(f"Ligne {numero} : la remise doit être comprise entre 0 et 100 %.")

        base_ht = _arrondir(
            quantite * prix_unitaire * (Decimal("1") - remise_pct / Decimal("100"))
        )
        taxe = _arrondir(base_ht * taux) if article.taxable else Decimal("0")
        lignes_calculees.append(
            LigneCalculee(
                article_id=article.id,
                designation=article.designation,
                quantite=quantite,
                prix_unitaire=prix_unitaire,
                remise_pct=remise_pct,
                base_ht=base_ht,
                taxe=taxe,
                total_ttc=base_ht + taxe,
            )
        )

    total_ht = sum((ligne.base_ht for ligne in lignes_calculees), Decimal("0"))
    total_taxe = sum((ligne.taxe for ligne in lignes_calculees), Decimal("0"))
    total_ttc = sum((ligne.total_ttc for ligne in lignes_calculees), Decimal("0"))
    facture = Facture(
        id=facture_id,
        client_id=client_id,
        lignes=lignes_calculees,
        total_ht=total_ht,
        total_taxe=total_taxe,
        total_ttc=total_ttc,
    )

    anomalies = [
        anomalie
        for anomalie in (
            _montant_declare(
                dossier.total_ht_declare.valeur,
                "Total HT",
                total_ht,
            ),
            _montant_declare(
                dossier.total_ttc_declare.valeur,
                "Total TTC",
                total_ttc,
            ),
        )
        if anomalie is not None
    ]
    return facture, anomalies
