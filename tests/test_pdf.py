from datetime import date
from decimal import Decimal
from io import BytesIO

import pdfplumber
import pytest

from src.pdf import InformationsVendeur, generer_pdf
from src.schemas import Client, Facture, LigneCalculee


def test_pdf_maquette_affiche_avertissement_et_totaux():
    facture = Facture(
        id="fac-pdf",
        client_id="client-1",
        lignes=[
            LigneCalculee(
                article_id="article-1",
                designation="Aciers & tubes",
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
    pdf = generer_pdf(
        facture,
        Client(id="client-1", nom="Société Exemple", ifu="1234567890123"),
        InformationsVendeur(
            nom="Boutique Test",
            adresse="Cotonou",
            telephone="+229 00 00 00 00",
        ),
        date_document=date(2026, 5, 1),
        conditions_paiement="Paiement à réception",
    )

    assert pdf.startswith(b"%PDF-")
    with pdfplumber.open(BytesIO(pdf)) as document:
        texte = "\n".join(page.extract_text() or "" for page in document.pages)

    assert "NON NORMALISEE DGI" in texte
    assert "Boutique Test" in texte
    assert "Société Exemple" in texte
    assert "Aciers & tubes" in texte
    assert "2 360 F CFA" in texte

    with pytest.raises(ValueError, match="client fourni"):
        generer_pdf(
            facture,
            Client(id="autre-client", nom="Autre client"),
            InformationsVendeur(nom="Boutique Test"),
            date_document=date(2026, 5, 1),
        )
