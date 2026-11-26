"""Efface les factures, sources et événements d'une base locale de démonstration."""
from __future__ import annotations

import argparse
import sys

from src.audit import JournalAudit
from src.config import settings
from src.documents import DepotDocuments


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--database-url",
        default=settings.database_url,
        help="URL SQLite ciblée (par défaut : DATABASE_URL).",
    )
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Confirme l'effacement irréversible des données de démonstration.",
    )
    arguments = parser.parse_args()
    if not arguments.confirm:
        parser.error("ajoutez --confirm après avoir vérifié la base ciblée")

    with DepotDocuments(arguments.database_url) as depot:
        depot.reinitialiser_demo()
    with JournalAudit(arguments.database_url) as journal:
        journal.reinitialiser_demo()
    print("Base de démonstration réinitialisée.")


if __name__ == "__main__":
    main()
