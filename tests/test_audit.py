import sqlite3
from concurrent.futures import ThreadPoolExecutor

from src.audit import ErreurAudit, JournalAudit


def test_journal_append_only_chaine_et_filtre(tmp_path):
    chemin = str(tmp_path / "audit.db")
    with JournalAudit(chemin) as journal:
        premier = journal.enregistrer(
            acteur="admin",
            action="BROUILLON_CREE",
            facture_id="fac-1",
            details={"version": 1},
        )
        second = journal.enregistrer(
            acteur="admin",
            action="FACTURE_VALIDEE",
            facture_id="fac-1",
            details={"numero": "SIM-FACTURE-2026-000001"},
        )

        assert premier["empreinte_precedente"] == "GENESIS"
        assert second["empreinte_precedente"] == premier["empreinte"]
        assert len(journal.lister("fac-1")) == 2
        assert journal.lister("autre")[0:] == []
        assert journal.verifier_chaine()


def test_journal_refuse_acteur_action_vides(tmp_path):
    with JournalAudit(str(tmp_path / "audit.db")) as journal:
        try:
            journal.enregistrer(acteur="", action="TEST")
        except ErreurAudit:
            return
        raise AssertionError("L'acteur vide aurait dû être refusé.")


def test_ecritures_concurrentes_conservent_une_chaine_valide(tmp_path):
    chemin = str(tmp_path / "audit.db")

    def ecrire(index):
        with JournalAudit(chemin) as journal:
            journal.enregistrer(acteur="admin", action=f"EVENEMENT_{index}")

    with ThreadPoolExecutor(max_workers=4) as travailleurs:
        list(travailleurs.map(ecrire, range(16)))

    with JournalAudit(chemin) as journal:
        assert len(journal.lister()) == 16
        assert journal.verifier_chaine()


def test_verification_detecte_une_modification_du_journal(tmp_path):
    chemin = str(tmp_path / "audit.db")
    with JournalAudit(chemin) as journal:
        journal.enregistrer(acteur="admin", action="SOURCE_IMPORTEE")

    with sqlite3.connect(chemin) as connexion:
        connexion.execute(
            "UPDATE journal_audit SET action = 'ACTION_MODIFIEE' WHERE id = 1"
        )

    with JournalAudit(chemin) as journal:
        assert not journal.verifier_chaine()
