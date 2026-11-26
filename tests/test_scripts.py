import subprocess
import sys
from pathlib import Path

from src.audit import JournalAudit
from src.documents import DepotDocuments
from src.schemas import ChampExtrait, DossierExtrait


ROOT = Path(__file__).resolve().parents[1]


def test_reset_requires_explicit_confirmation(tmp_path):
    base = tmp_path / "demo.db"
    resultat = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.reset_data",
            "--database-url",
            str(base),
        ],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert resultat.returncode == 2
    assert "--confirm" in resultat.stderr
    assert not base.exists()


def test_reset_clears_only_the_selected_demo_database(tmp_path):
    base = str(tmp_path / "demo.db")
    dossier = DossierExtrait(
        source_hash="source-1",
        client=ChampExtrait(valeur="Client fictif"),
    )
    with DepotDocuments(base) as depot:
        depot.enregistrer_source("source-1", "commande.txt", "Texte fictif", dossier)
    with JournalAudit(base) as journal:
        journal.enregistrer(acteur="admin", action="SOURCE_IMPORTEE")

    resultat = subprocess.run(
        [
            sys.executable,
            "-m",
            "scripts.reset_data",
            "--database-url",
            base,
            "--confirm",
        ],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    assert "réinitialisée" in resultat.stdout
    with DepotDocuments(base) as depot:
        assert depot.lister_sources() == []
    with JournalAudit(base) as journal:
        assert journal.lister() == []
        assert journal.verifier_chaine()
