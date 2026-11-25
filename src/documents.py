"""Cycle de vie persistant des brouillons de facture."""
from __future__ import annotations

import sqlite3
from contextlib import contextmanager
from datetime import date
from pathlib import Path
from threading import RLock
from typing import Iterable, Iterator

from src.config import settings
from src.schemas import Anomalie, Facture, LigneCalculee, Statut


class ErreurDocument(Exception):
    """Erreur métier liée au cycle de vie d'un document."""


class FactureIntrouvable(ErreurDocument):
    pass


class TransitionInvalide(ErreurDocument):
    pass


class ConflitVersion(ErreurDocument):
    pass


class ConflitIdempotence(ErreurDocument):
    pass


class ValidationBloquee(ErreurDocument):
    pass


class AvoirDejaCree(ErreurDocument):
    pass


def _chemin_sqlite(database_url: str) -> str:
    if database_url.startswith("sqlite:///"):
        chemin = database_url[len("sqlite:///"):]
    elif "://" not in database_url:
        chemin = database_url
    else:
        raise ValueError("DepotDocuments prend en charge les URL SQLite uniquement.")

    if not chemin:
        raise ValueError("Le chemin de la base SQLite est vide.")
    if chemin == ":memory:":
        return chemin

    fichier = Path(chemin).expanduser().resolve()
    fichier.parent.mkdir(parents=True, exist_ok=True)
    return str(fichier)


class DepotDocuments:
    """Stockage SQLite avec transitions atomiques et numérotation de démonstration.

    Les numéros SIM-* sont internes au prototype et ne sont pas des numéros
    délivrés ou validés par la DGI.
    """

    def __init__(self, database_url: str | None = None) -> None:
        self._connexion = sqlite3.connect(
            _chemin_sqlite(database_url or settings.database_url),
            timeout=30,
            check_same_thread=False,
            isolation_level=None,
        )
        self._connexion.row_factory = sqlite3.Row
        self._connexion.execute("PRAGMA foreign_keys = ON")
        self._verrou = RLock()
        self._initialiser()

    def _initialiser(self) -> None:
        with self._verrou:
            self._connexion.executescript(
                """
                CREATE TABLE IF NOT EXISTS factures (
                    id TEXT PRIMARY KEY,
                    numero TEXT UNIQUE,
                    statut TEXT NOT NULL,
                    version INTEGER NOT NULL,
                    facture_origine_id TEXT REFERENCES factures(id),
                    contenu TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS sequences_documents (
                    type_document TEXT NOT NULL,
                    annee INTEGER NOT NULL,
                    derniere_valeur INTEGER NOT NULL,
                    PRIMARY KEY (type_document, annee)
                );
                CREATE UNIQUE INDEX IF NOT EXISTS un_avoir_integral_par_facture
                    ON factures(facture_origine_id)
                    WHERE statut = 'AVOIR';
                """
            )

    @contextmanager
    def _transaction(self) -> Iterator[sqlite3.Connection]:
        with self._verrou:
            self._connexion.execute("BEGIN IMMEDIATE")
            try:
                yield self._connexion
            except BaseException:
                self._connexion.rollback()
                raise
            else:
                self._connexion.commit()

    @staticmethod
    def _charger(ligne: sqlite3.Row | None) -> Facture:
        if ligne is None:
            raise FactureIntrouvable("Facture introuvable.")
        return Facture.model_validate_json(ligne["contenu"])

    @staticmethod
    def _contenu_metier_identique(a: Facture, b: Facture) -> bool:
        return (
            a.id == b.id
            and a.client_id == b.client_id
            and a.lignes == b.lignes
            and a.total_ht == b.total_ht
            and a.total_taxe == b.total_taxe
            and a.total_ttc == b.total_ttc
            and a.facture_origine_id == b.facture_origine_id
        )

    @staticmethod
    def _inserer(connexion: sqlite3.Connection, facture: Facture) -> None:
        connexion.execute(
            """
            INSERT INTO factures (id, numero, statut, version, facture_origine_id, contenu)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                facture.id,
                facture.numero,
                facture.statut.value,
                facture.version,
                facture.facture_origine_id,
                facture.model_dump_json(),
            ),
        )

    @staticmethod
    def _prochain_numero(
        connexion: sqlite3.Connection,
        type_document: str,
        annee: int,
    ) -> str:
        ligne = connexion.execute(
            """
            SELECT derniere_valeur FROM sequences_documents
            WHERE type_document = ? AND annee = ?
            """,
            (type_document, annee),
        ).fetchone()
        valeur = 1 if ligne is None else ligne["derniere_valeur"] + 1
        connexion.execute(
            """
            INSERT INTO sequences_documents (type_document, annee, derniere_valeur)
            VALUES (?, ?, ?)
            ON CONFLICT(type_document, annee)
            DO UPDATE SET derniere_valeur = excluded.derniere_valeur
            """,
            (type_document, annee, valeur),
        )
        return f"SIM-{type_document}-{annee}-{valeur:06d}"

    def _enregistrer_transition(
        self,
        connexion: sqlite3.Connection,
        facture: Facture,
        version_precedente: int,
    ) -> Facture:
        resultat = connexion.execute(
            """
            UPDATE factures
            SET numero = ?, statut = ?, version = ?, contenu = ?
            WHERE id = ? AND version = ?
            """,
            (
                facture.numero,
                facture.statut.value,
                facture.version,
                facture.model_dump_json(),
                facture.id,
                version_precedente,
            ),
        )
        if resultat.rowcount != 1:
            raise ConflitVersion("La facture a été modifiée par une autre opération.")
        return facture

    def creer_brouillon(self, facture: Facture) -> Facture:
        if facture.statut != Statut.BROUILLON or facture.numero is not None:
            raise TransitionInvalide("Un nouveau document doit être un brouillon sans numéro.")

        with self._transaction() as connexion:
            existante = connexion.execute(
                "SELECT contenu FROM factures WHERE id = ?", (facture.id,)
            ).fetchone()
            if existante is not None:
                facture_existante = self._charger(existante)
                if self._contenu_metier_identique(facture_existante, facture):
                    return facture_existante
                raise ConflitIdempotence(
                    f"L'identifiant « {facture.id} » existe déjà avec un autre contenu."
                )
            self._inserer(connexion, facture)
            return facture

    def obtenir(self, facture_id: str) -> Facture:
        with self._verrou:
            ligne = self._connexion.execute(
                "SELECT contenu FROM factures WHERE id = ?", (facture_id,)
            ).fetchone()
            return self._charger(ligne)

    def modifier_brouillon(
        self,
        facture_corrigee: Facture,
        *,
        version_attendue: int,
    ) -> Facture:
        if facture_corrigee.statut != Statut.BROUILLON or facture_corrigee.numero is not None:
            raise TransitionInvalide("Seul un brouillon sans numéro peut être modifié.")

        with self._transaction() as connexion:
            actuelle = self._charger(
                connexion.execute(
                    "SELECT contenu FROM factures WHERE id = ?",
                    (facture_corrigee.id,),
                ).fetchone()
            )
            if actuelle.statut != Statut.BROUILLON:
                raise TransitionInvalide("Une facture validée ou émise est immuable.")
            if actuelle.version != version_attendue:
                raise ConflitVersion("Le brouillon a changé; rechargez-le avant de le modifier.")

            mise_a_jour = facture_corrigee.model_copy(
                update={"version": actuelle.version + 1}
            )
            return self._enregistrer_transition(connexion, mise_a_jour, actuelle.version)

    def valider(
        self,
        facture_id: str,
        anomalies: Iterable[Anomalie] = (),
        *,
        version_attendue: int,
        annee: int | None = None,
    ) -> Facture:
        annee_numero = date.today().year if annee is None else annee
        if annee_numero < 1:
            raise ValueError("L'année de numérotation doit être positive.")

        with self._transaction() as connexion:
            actuelle = self._charger(
                connexion.execute(
                    "SELECT contenu FROM factures WHERE id = ?", (facture_id,)
                ).fetchone()
            )
            if actuelle.statut in (Statut.VALIDEE, Statut.EMISE):
                return actuelle
            if actuelle.statut != Statut.BROUILLON:
                raise TransitionInvalide("Seul un brouillon peut être validé.")
            if actuelle.version != version_attendue:
                raise ConflitVersion("Le brouillon a changé; rechargez-le avant de le valider.")
            non_resolues = [a for a in anomalies if a.bloquante and not a.resolue]
            if non_resolues:
                raise ValidationBloquee(
                    f"Validation bloquée : {len(non_resolues)} anomalie(s) bloquante(s) restent à traiter."
                )

            numero = self._prochain_numero(connexion, "FACTURE", annee_numero)
            validee = actuelle.model_copy(
                update={
                    "numero": numero,
                    "statut": Statut.VALIDEE,
                    "version": actuelle.version + 1,
                }
            )
            return self._enregistrer_transition(connexion, validee, actuelle.version)

    def emettre(self, facture_id: str, *, version_attendue: int) -> Facture:
        """Enregistre l'émission simulée; aucun envoi ni appel à la DGI n'est effectué."""
        with self._transaction() as connexion:
            actuelle = self._charger(
                connexion.execute(
                    "SELECT contenu FROM factures WHERE id = ?", (facture_id,)
                ).fetchone()
            )
            if actuelle.statut == Statut.EMISE:
                return actuelle
            if actuelle.statut != Statut.VALIDEE:
                raise TransitionInvalide("Seule une facture validée peut être émise.")
            if actuelle.version != version_attendue:
                raise ConflitVersion("La facture a changé; rechargez-la avant l'émission.")

            emise = actuelle.model_copy(
                update={"statut": Statut.EMISE, "version": actuelle.version + 1}
            )
            return self._enregistrer_transition(connexion, emise, actuelle.version)

    def creer_avoir_total(
        self,
        avoir_id: str,
        facture_origine_id: str,
        *,
        version_attendue: int,
        annee: int | None = None,
    ) -> Facture:
        """Crée un avoir total négatif lié à une facture validée ou émise."""
        if not avoir_id.strip() or avoir_id == facture_origine_id:
            raise ValueError("L'identifiant de l'avoir doit être distinct et non vide.")
        annee_numero = date.today().year if annee is None else annee
        if annee_numero < 1:
            raise ValueError("L'année de numérotation doit être positive.")

        with self._transaction() as connexion:
            existant = connexion.execute(
                "SELECT contenu FROM factures WHERE id = ?", (avoir_id,)
            ).fetchone()
            if existant is not None:
                avoir_existant = self._charger(existant)
                if (
                    avoir_existant.statut == Statut.AVOIR
                    and avoir_existant.facture_origine_id == facture_origine_id
                ):
                    return avoir_existant
                raise ConflitIdempotence(
                    f"L'identifiant « {avoir_id} » existe déjà avec un autre document."
                )

            origine = self._charger(
                connexion.execute(
                    "SELECT contenu FROM factures WHERE id = ?",
                    (facture_origine_id,),
                ).fetchone()
            )
            if origine.statut not in (Statut.VALIDEE, Statut.EMISE):
                raise TransitionInvalide(
                    "Un avoir ne peut être créé que pour une facture validée ou émise."
                )
            if origine.version != version_attendue:
                raise ConflitVersion("La facture d'origine a changé; rechargez-la.")

            avoir_existant = connexion.execute(
                """
                SELECT id FROM factures
                WHERE facture_origine_id = ? AND statut = ?
                """,
                (facture_origine_id, Statut.AVOIR.value),
            ).fetchone()
            if avoir_existant is not None:
                raise AvoirDejaCree("Un avoir total existe déjà pour cette facture.")

            lignes = [
                LigneCalculee(
                    article_id=ligne.article_id,
                    designation=ligne.designation,
                    quantite=-abs(ligne.quantite),
                    prix_unitaire=ligne.prix_unitaire,
                    remise_pct=ligne.remise_pct,
                    base_ht=-abs(ligne.base_ht),
                    taxe=-abs(ligne.taxe),
                    total_ttc=-abs(ligne.total_ttc),
                )
                for ligne in origine.lignes
            ]
            numero = self._prochain_numero(connexion, "AVOIR", annee_numero)
            avoir = Facture(
                id=avoir_id,
                numero=numero,
                statut=Statut.AVOIR,
                client_id=origine.client_id,
                lignes=lignes,
                total_ht=-abs(origine.total_ht),
                total_taxe=-abs(origine.total_taxe),
                total_ttc=-abs(origine.total_ttc),
                facture_origine_id=origine.id,
            )
            self._inserer(connexion, avoir)
            return avoir

    def fermer(self) -> None:
        with self._verrou:
            self._connexion.close()

    def __enter__(self) -> DepotDocuments:
        return self

    def __exit__(self, exc_type, exc_value, traceback) -> None:
        self.fermer()
