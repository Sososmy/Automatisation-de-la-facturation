"""Journal d'audit SQLite append-only."""
from __future__ import annotations

import hashlib
import json
import sqlite3
from datetime import datetime, timezone
from pathlib import Path
from threading import RLock
from typing import Any, Iterator

from src.config import settings


class ErreurAudit(Exception):
    """Erreur liée au journal d'audit."""


def _chemin_sqlite(database_url: str) -> str:
    if database_url.startswith("sqlite:///"):
        chemin = database_url[len("sqlite:///"):]
    elif "://" not in database_url:
        chemin = database_url
    else:
        raise ValueError("JournalAudit prend en charge les URL SQLite uniquement.")
    if not chemin:
        raise ValueError("Le chemin de la base SQLite est vide.")
    if chemin == ":memory:":
        return chemin
    fichier = Path(chemin).expanduser().resolve()
    fichier.parent.mkdir(parents=True, exist_ok=True)
    return str(fichier)


class JournalAudit:
    """Écrit des événements immuables et chaînés par empreinte cryptographique."""

    def __init__(self, database_url: str | None = None) -> None:
        self._connexion = sqlite3.connect(
            _chemin_sqlite(database_url or settings.database_url),
            timeout=30,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connexion.row_factory = sqlite3.Row
        self._verrou = RLock()
        self._initialiser()

    def _initialiser(self) -> None:
        with self._verrou:
            self._connexion.executescript(
                """
                CREATE TABLE IF NOT EXISTS journal_audit (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    horodatage TEXT NOT NULL,
                    acteur TEXT NOT NULL,
                    action TEXT NOT NULL,
                    facture_id TEXT,
                    details TEXT NOT NULL,
                    empreinte_precedente TEXT NOT NULL,
                    empreinte TEXT NOT NULL
                );
                CREATE INDEX IF NOT EXISTS idx_journal_audit_facture
                    ON journal_audit(facture_id, id);
                """
            )

    def _derniere_empreinte(self) -> str:
        ligne = self._connexion.execute(
            "SELECT empreinte FROM journal_audit ORDER BY id DESC LIMIT 1"
        ).fetchone()
        return ligne["empreinte"] if ligne else "GENESIS"

    @staticmethod
    def _calculer_empreinte(
        horodatage: str,
        acteur: str,
        action: str,
        facture_id: str | None,
        details: str,
        precedente: str,
    ) -> str:
        contenu = "|".join(
            (horodatage, acteur, action, facture_id or "", details, precedente)
        )
        return hashlib.sha256(contenu.encode("utf-8")).hexdigest()

    def enregistrer(
        self,
        *,
        acteur: str,
        action: str,
        facture_id: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        acteur = acteur.strip()
        action = action.strip()
        if not acteur or not action:
            raise ErreurAudit("L'acteur et l'action sont obligatoires.")

        horodatage = datetime.now(timezone.utc).isoformat(timespec="seconds")
        details_json = json.dumps(
            details or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":")
        )
        with self._verrou:
            self._connexion.execute("BEGIN IMMEDIATE")
            try:
                precedente = self._derniere_empreinte()
                empreinte = self._calculer_empreinte(
                    horodatage,
                    acteur,
                    action,
                    facture_id,
                    details_json,
                    precedente,
                )
                curseur = self._connexion.execute(
                    """
                    INSERT INTO journal_audit (
                        horodatage, acteur, action, facture_id, details,
                        empreinte_precedente, empreinte
                    ) VALUES (?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        horodatage,
                        acteur,
                        action,
                        facture_id,
                        details_json,
                        precedente,
                        empreinte,
                    ),
                )
            except BaseException:
                self._connexion.rollback()
                raise
            else:
                self._connexion.commit()
                return self._charger(curseur.lastrowid)

    def _charger(self, identifiant: int) -> dict[str, Any]:
        ligne = self._connexion.execute(
            "SELECT * FROM journal_audit WHERE id = ?", (identifiant,)
        ).fetchone()
        if ligne is None:
            raise ErreurAudit("Événement d'audit introuvable.")
        return dict(ligne)

    def lister(self, facture_id: str | None = None) -> list[dict[str, Any]]:
        with self._verrou:
            if facture_id is None:
                lignes = self._connexion.execute(
                    "SELECT * FROM journal_audit ORDER BY id"
                ).fetchall()
            else:
                lignes = self._connexion.execute(
                    "SELECT * FROM journal_audit "
                    "WHERE facture_id = ? ORDER BY id",
                    (facture_id,),
                ).fetchall()
            return [dict(ligne) for ligne in lignes]

    def verifier_chaine(self) -> bool:
        with self._verrou:
            evenements = self._connexion.execute(
                "SELECT * FROM journal_audit ORDER BY id"
            ).fetchall()
        precedente = "GENESIS"
        for evenement in evenements:
            if evenement["empreinte_precedente"] != precedente:
                return False
            attendue = self._calculer_empreinte(
                evenement["horodatage"],
                evenement["acteur"],
                evenement["action"],
                evenement["facture_id"],
                evenement["details"],
                precedente,
            )
            if evenement["empreinte"] != attendue:
                return False
            precedente = attendue
        return True

    def reinitialiser_demo(self) -> None:
        """Efface le journal avec les données fictives lors d'une réinitialisation locale."""
        with self._verrou:
            self._connexion.execute("BEGIN IMMEDIATE")
            try:
                self._connexion.execute("DELETE FROM journal_audit")
            except BaseException:
                self._connexion.rollback()
                raise
            else:
                self._connexion.commit()

    def fermer(self) -> None:
        with self._verrou:
            self._connexion.close()

    def __enter__(self) -> "JournalAudit":
        return self

    def __exit__(self, exc_type: object, exc_value: object, traceback: object) -> None:
        self.fermer()
