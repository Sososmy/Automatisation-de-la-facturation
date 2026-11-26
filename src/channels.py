"""Émission locale simulée pour les canaux courriel, SMS et WhatsApp."""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


@dataclass(frozen=True)
class ResultatEmission:
    canal: str
    destinataire: str
    sujet: str | None
    contenu: str
    simule: bool = True
    horodatage: str = ""


class CanauxSimules:
    """Produit des résultats d'émission sans effectuer d'appel externe."""

    _CANAUX = ("courriel", "sms", "whatsapp")

    def emettre(
        self,
        canal: str,
        destinataire: str,
        contenu: str,
        *,
        sujet: str | None = None,
    ) -> ResultatEmission:
        canal_normalise = canal.strip().lower()
        if canal_normalise not in self._CANAUX:
            raise ValueError("Canal non pris en charge.")
        destinataire = destinataire.strip()
        if not destinataire:
            raise ValueError("Le destinataire est obligatoire.")
        if not contenu.strip():
            raise ValueError("Le contenu est obligatoire.")
        if canal_normalise == "courriel" and "@" not in destinataire:
            raise ValueError("Adresse courriel invalide.")

        return ResultatEmission(
            canal=canal_normalise,
            destinataire=destinataire,
            sujet=sujet.strip() if sujet and sujet.strip() else None,
            contenu=contenu.strip(),
            horodatage=datetime.now(timezone.utc).isoformat(timespec="seconds"),
        )
