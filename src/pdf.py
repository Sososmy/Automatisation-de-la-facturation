"""Génération d'un aperçu PDF non normalisé pour le prototype."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal, ROUND_HALF_UP
from io import BytesIO
from xml.sax.saxutils import escape

from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_RIGHT
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.units import mm
from reportlab.pdfgen.canvas import Canvas
from reportlab.platypus import Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from src.schemas import Client, Facture, Statut


@dataclass(frozen=True)
class InformationsVendeur:
    nom: str
    ifu: str | None = None
    adresse: str | None = None
    telephone: str | None = None
    email: str | None = None


def _texte(value: str, style: ParagraphStyle) -> Paragraph:
    return Paragraph(escape(value), style)


def _montant(value: Decimal) -> str:
    entier = value.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
    return f"{entier:,.0f}".replace(",", " ") + " F CFA"


def _nombre(value: Decimal) -> str:
    return format(value.normalize(), "f").replace(".", ",")


def _titre(facture: Facture) -> str:
    if facture.statut == Statut.BROUILLON:
        return "BROUILLON DE FACTURE"
    if facture.statut == Statut.AVOIR:
        return "AVOIR DE DEMONSTRATION"
    return "FACTURE DE DEMONSTRATION"


def generer_pdf(
    facture: Facture,
    client: Client,
    vendeur: InformationsVendeur,
    *,
    date_document: date,
    conditions_paiement: str | None = None,
) -> bytes:
    """Retourne un PDF de démonstration; il n'est pas validé par la DGI."""
    if not vendeur.nom.strip():
        raise ValueError("Le nom du vendeur ne peut pas être vide.")
    if facture.client_id != client.id:
        raise ValueError("Le client fourni ne correspond pas à celui de la facture.")

    sortie = BytesIO()
    document = SimpleDocTemplate(
        sortie,
        pagesize=A4,
        leftMargin=16 * mm,
        rightMargin=16 * mm,
        topMargin=15 * mm,
        bottomMargin=18 * mm,
        title=f"{_titre(facture)} - {facture.numero or facture.id}",
        author=vendeur.nom,
    )
    styles = getSampleStyleSheet()
    titre_style = ParagraphStyle(
        "TitreFacture",
        parent=styles["Title"],
        fontName="Helvetica-Bold",
        fontSize=18,
        leading=22,
        alignment=TA_RIGHT,
        textColor=colors.HexColor("#18324B"),
    )
    avertissement_style = ParagraphStyle(
        "AvertissementDGI",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=9,
        leading=12,
        alignment=TA_CENTER,
        textColor=colors.HexColor("#8B1E1E"),
    )
    etiquette_style = ParagraphStyle(
        "Etiquette",
        parent=styles["Normal"],
        fontName="Helvetica-Bold",
        fontSize=8,
        leading=10,
        textColor=colors.HexColor("#18324B"),
    )
    normal_style = ParagraphStyle(
        "TexteFacture",
        parent=styles["Normal"],
        fontName="Helvetica",
        fontSize=8,
        leading=11,
    )
    cell_style = ParagraphStyle(
        "Cellule",
        parent=normal_style,
        fontSize=7,
        leading=9,
    )
    cell_right_style = ParagraphStyle(
        "CelluleDroite",
        parent=cell_style,
        alignment=TA_RIGHT,
    )

    vendeur_lignes = [vendeur.nom]
    for libelle, valeur in (
        ("IFU", vendeur.ifu),
        ("Adresse", vendeur.adresse),
        ("Téléphone", vendeur.telephone),
        ("E-mail", vendeur.email),
    ):
        if valeur:
            vendeur_lignes.append(f"{libelle} : {valeur}")

    client_lignes = [client.nom]
    for libelle, valeur in (("IFU", client.ifu), ("E-mail", client.email)):
        if valeur:
            client_lignes.append(f"{libelle} : {valeur}")

    meta = [
        f"Référence interne : {facture.numero or 'en attente de validation'}",
        f"Date du document : {date_document.strftime('%d/%m/%Y')}",
    ]
    if conditions_paiement:
        meta.append(f"Conditions de paiement : {conditions_paiement}")
    if facture.facture_origine_id:
        meta.append(f"Avoir lié à la facture : {facture.facture_origine_id}")

    parties = Table(
        [
            [
                _texte("VENDEUR", etiquette_style),
                _texte("CLIENT", etiquette_style),
            ],
            [
                Paragraph("<br/>".join(escape(ligne) for ligne in vendeur_lignes), normal_style),
                Paragraph("<br/>".join(escape(ligne) for ligne in client_lignes), normal_style),
            ],
        ],
        colWidths=[(A4[0] - 32 * mm) / 2] * 2,
    )
    parties.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#EAF0F5")),
                ("BOX", (0, 0), (-1, -1), 0.5, colors.HexColor("#B7C4D0")),
                ("INNERGRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#D2DAE1")),
                ("VALIGN", (0, 0), (-1, -1), "TOP"),
                ("LEFTPADDING", (0, 0), (-1, -1), 8),
                ("RIGHTPADDING", (0, 0), (-1, -1), 8),
                ("TOPPADDING", (0, 0), (-1, -1), 6),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
            ]
        )
    )

    entetes = ["Désignation", "Qté", "Prix unit.", "Remise", "Base HT", "Taxe", "Total TTC"]
    donnees = [[_texte(entete, etiquette_style) for entete in entetes]]
    for ligne in facture.lignes:
        donnees.append(
            [
                _texte(ligne.designation, cell_style),
                _texte(_nombre(ligne.quantite), cell_right_style),
                _texte(_montant(ligne.prix_unitaire), cell_right_style),
                _texte(f"{_nombre(ligne.remise_pct)} %", cell_right_style),
                _texte(_montant(ligne.base_ht), cell_right_style),
                _texte(_montant(ligne.taxe), cell_right_style),
                _texte(_montant(ligne.total_ttc), cell_right_style),
            ]
        )

    tableau_lignes = Table(
        donnees,
        colWidths=[151, 32, 57, 48, 69, 57, 80],
        repeatRows=1,
        hAlign="LEFT",
    )
    tableau_lignes.setStyle(
        TableStyle(
            [
                ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#18324B")),
                ("TEXTCOLOR", (0, 0), (-1, 0), colors.white),
                ("GRID", (0, 0), (-1, -1), 0.35, colors.HexColor("#B7C4D0")),
                ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
                ("ALIGN", (1, 1), (-1, -1), "RIGHT"),
                ("LEFTPADDING", (0, 0), (-1, -1), 4),
                ("RIGHTPADDING", (0, 0), (-1, -1), 4),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    totaux = Table(
        [
            ["Total HT", _montant(facture.total_ht)],
            ["Total taxe", _montant(facture.total_taxe)],
            ["TOTAL TTC", _montant(facture.total_ttc)],
        ],
        colWidths=[95 * mm, 55 * mm],
        hAlign="RIGHT",
    )
    totaux.setStyle(
        TableStyle(
            [
                ("ALIGN", (1, 0), (1, -1), "RIGHT"),
                ("FONTNAME", (0, 0), (-1, 1), "Helvetica"),
                ("FONTNAME", (0, 2), (-1, 2), "Helvetica-Bold"),
                ("FONTSIZE", (0, 0), (-1, -1), 9),
                ("LINEABOVE", (0, 2), (-1, 2), 1, colors.HexColor("#18324B")),
                ("TOPPADDING", (0, 0), (-1, -1), 5),
                ("BOTTOMPADDING", (0, 0), (-1, -1), 5),
            ]
        )
    )

    contenu = [
        _texte("MAQUETTE DE DEMONSTRATION | NON NORMALISEE DGI", avertissement_style),
        Spacer(1, 5 * mm),
        Table(
            [[
                Paragraph("<br/>".join(escape(ligne) for ligne in vendeur_lignes), normal_style),
                _texte(_titre(facture), titre_style),
            ]],
            colWidths=[(A4[0] - 32 * mm) * 0.55, (A4[0] - 32 * mm) * 0.45],
        ),
        Spacer(1, 4 * mm),
        Paragraph("<br/>".join(escape(ligne) for ligne in meta), normal_style),
        Spacer(1, 5 * mm),
        parties,
        Spacer(1, 7 * mm),
        tableau_lignes,
        Spacer(1, 5 * mm),
        totaux,
        Spacer(1, 4 * mm),
    ]
    document.build(contenu, onFirstPage=_pied_de_page, onLaterPages=_pied_de_page)
    return sortie.getvalue()


def _pied_de_page(canvas: Canvas, document: SimpleDocTemplate) -> None:
    canvas.saveState()
    canvas.setStrokeColor(colors.HexColor("#B7C4D0"))
    canvas.line(16 * mm, 13 * mm, A4[0] - 16 * mm, 13 * mm)
    canvas.setFont("Helvetica", 7)
    canvas.setFillColor(colors.HexColor("#555555"))
    canvas.drawCentredString(
        A4[0] / 2,
        8 * mm,
        "APERÇU DE DEMONSTRATION - NON VALABLE COMME FACTURE NORMALISEE DGI",
    )
    canvas.drawRightString(A4[0] - 16 * mm, 8 * mm, str(document.page))
    canvas.restoreState()
