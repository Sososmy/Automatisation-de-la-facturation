"""Contrôles du dossier extrait avant calcul et validation.

Chaque contrôle renvoie des Anomalie. Une anomalie bloquante non résolue
empêche la validation (voir peut_valider). Aucun contrôle ne corrige ni
n'invente de donnée : il signale, un humain décide.
"""
from __future__ import annotations

import hashlib
import json
import re
from decimal import Decimal
from typing import Iterable, Iterator, Optional

from rapidfuzz import fuzz

from src.schemas import (
    Anomalie,
    Article,
    ChampExtrait,
    Client,
    CodeAnomalie,
    DossierExtrait,
    en_decimal,
    en_taux,
    normaliser,
)

SCORE_SUR = 95  # au moins : correspondance considérée comme certaine
SCORE_POSSIBLE = 80  # entre les deux : correspondance à confirmer par un humain


# --------------------------------------------------------------------------
# Rapprochement avec les référentiels
# --------------------------------------------------------------------------
def _score(a: str, b: str) -> float:
    """Similarité de 0 à 100, insensible à la casse, aux accents et aux espaces
    (« Ciment 50kg » et « Ciment 50 kg » sont considérés comme identiques)."""
    na, nb = normaliser(a), normaliser(b)
    return max(
        fuzz.token_sort_ratio(na, nb),
        fuzz.ratio(na.replace(" ", ""), nb.replace(" ", "")),
    )


def trouver_client(nom: str, clients: Iterable[Client]) -> tuple[Optional[Client], float]:
    """Client le plus proche et son score (0 à 100)."""
    meilleur, score_max = None, 0.0
    for c in clients:
        s = _score(nom, c.nom)
        if s > score_max:
            meilleur, score_max = c, s
    return meilleur, score_max


def _jetons(texte: str) -> set[str]:
    """Mots comparables ; chiffres et lettres séparés : « 50kg » -> {50, kg}."""
    n = re.sub(r"[^a-z0-9 ]", " ", normaliser(texte))
    n = re.sub(r"(?<=\d)(?=[a-z])|(?<=[a-z])(?=\d)", " ", n)
    return set(n.split())


def _score_article(ligne: str, article: str) -> float:
    """Similarité entre la désignation d'une ligne et celle d'un article du référentiel.

    - Mots en plus dans la ligne (« sacs de ciment 50kg » pour « Ciment 50 kg ») : acceptés.
    - Nombres de l'article absents de la ligne (« fer 12 mm » pour « Fer 10 mm ») : deux articles
      différents, score 0.
    - Ligne plus vague que l'article (nombres absents) : jamais reconnue d'office (plafond 79).
    """
    jl, ja = _jetons(ligne), _jetons(article)
    nl = {j for j in jl if j.isdigit()}
    na = {j for j in ja if j.isdigit()}
    if na and nl and not na <= nl:
        return 0.0
    score = 100.0 if ja and ja <= jl else _score(ligne, article)
    if na and not nl:
        score = min(score, 79.0)
    return score


def trouver_article(designation: str, articles: Iterable[Article]) -> tuple[Optional[Article], float]:
    """Article le plus proche et son score (0 à 100)."""
    meilleur, score_max = None, 0.0
    for a in articles:
        s = _score_article(designation, a.designation)
        if s > score_max:
            meilleur, score_max = a, s
    return meilleur, score_max


# --------------------------------------------------------------------------
# Outils internes
# --------------------------------------------------------------------------
def _vide(champ: ChampExtrait) -> bool:
    return champ.valeur is None or not champ.valeur.strip()


def _champs(dossier: DossierExtrait) -> Iterator[tuple[str, ChampExtrait, Optional[int]]]:
    """Tous les champs extraits : (libellé, champ, numéro de ligne ou None)."""
    yield "client", dossier.client, None
    yield "date", dossier.date, None
    yield "conditions de paiement", dossier.conditions_paiement, None
    yield "total HT déclaré", dossier.total_ht_declare, None
    yield "total TTC déclaré", dossier.total_ttc_declare, None
    yield "taux de taxe", dossier.taux_taxe, None
    for i, ligne in enumerate(dossier.lignes, start=1):
        yield "désignation", ligne.designation, i
        yield "quantité", ligne.quantite, i
        yield "prix unitaire", ligne.prix_unitaire, i
        yield "remise", ligne.remise, i


def empreinte(dossier: DossierExtrait) -> str:
    """Empreinte du contenu métier, pour repérer un même dossier soumis deux fois."""
    contenu = {
        "client": normaliser(dossier.client.valeur),
        "date": (dossier.date.valeur or "").strip(),
        "lignes": [
            [
                normaliser(l.designation.valeur),
                str(en_decimal(l.quantite.valeur)),
                str(en_decimal(l.prix_unitaire.valeur)),
                str(en_decimal(l.remise.valeur) or 0),
            ]
            for l in dossier.lignes
        ],
    }
    brut = json.dumps(contenu, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(brut.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------
# Contrôles
# --------------------------------------------------------------------------
def controle_client(dossier: DossierExtrait, clients: list[Client]) -> list[Anomalie]:
    if _vide(dossier.client):
        return [Anomalie(code=CodeAnomalie.CLIENT_MANQUANT, message="Client absent de la source.")]
    client, score = trouver_client(dossier.client.valeur, clients)
    if client is not None and score >= SCORE_SUR:
        return []
    if client is not None and score >= SCORE_POSSIBLE:
        return [Anomalie(
            code=CodeAnomalie.CLIENT_INCERTAIN,
            message=f"Client « {dossier.client.valeur} » proche de « {client.nom} » ({score:.0f} %) : à confirmer.",
        )]
    return [Anomalie(
        code=CodeAnomalie.CLIENT_INCONNU,
        message=f"Client « {dossier.client.valeur} » absent du référentiel.",
    )]


def controle_lignes(dossier: DossierExtrait, articles: list[Article],
                    seuil_prix: float = 0.30) -> list[Anomalie]:
    anomalies: list[Anomalie] = []
    if not dossier.lignes:
        return [Anomalie(code=CodeAnomalie.CHAMP_MANQUANT, message="Aucune ligne à facturer dans la source.")]

    for i, ligne in enumerate(dossier.lignes, start=1):
        def signaler(code: CodeAnomalie, message: str) -> None:
            anomalies.append(Anomalie(code=code, message=f"Ligne {i} : {message}", ligne=i))

        # Désignation
        if _vide(ligne.designation):
            signaler(CodeAnomalie.CHAMP_MANQUANT, "désignation absente.")

        # Quantité
        if _vide(ligne.quantite):
            signaler(CodeAnomalie.CHAMP_MANQUANT, "quantité absente.")
        else:
            q = en_decimal(ligne.quantite.valeur)
            if q is None or q <= 0:
                signaler(CodeAnomalie.CHAMP_INVALIDE, f"quantité illisible ou non positive (« {ligne.quantite.valeur} »).")

        # Prix unitaire
        prix = None
        if _vide(ligne.prix_unitaire):
            signaler(CodeAnomalie.CHAMP_MANQUANT, "prix unitaire absent.")
        else:
            prix = en_decimal(ligne.prix_unitaire.valeur)
            if prix is None or prix < 0:
                signaler(CodeAnomalie.CHAMP_INVALIDE, f"prix illisible ou négatif (« {ligne.prix_unitaire.valeur} »).")
                prix = None

        # Remise (facultative)
        if not _vide(ligne.remise):
            r = en_decimal(ligne.remise.valeur)
            if r is None or not (0 <= r <= 100):
                signaler(CodeAnomalie.CHAMP_INVALIDE, f"remise invalide (« {ligne.remise.valeur} »), attendu entre 0 et 100 %.")

        # Article et prix par rapport au référentiel
        if not _vide(ligne.designation):
            article, score = trouver_article(ligne.designation.valeur, articles)
            if article is None or score < SCORE_POSSIBLE:
                signaler(CodeAnomalie.ARTICLE_INCONNU, f"article « {ligne.designation.valeur} » absent du référentiel.")
            elif prix is not None and article.prix_reference > 0:
                ecart = abs(prix - article.prix_reference) / article.prix_reference
                if ecart > Decimal(str(seuil_prix)):
                    signaler(
                        CodeAnomalie.PRIX_INHABITUEL,
                        f"prix {prix} très différent du prix de référence {article.prix_reference} ({ecart:.0%} d'écart).",
                    )
    return anomalies


def controle_confiance(dossier: DossierExtrait, seuil: float = 0.80) -> list[Anomalie]:
    """Champs lus avec une confiance faible : revue conseillée, non bloquante."""
    anomalies = []
    for libelle, champ, ligne in _champs(dossier):
        if not _vide(champ) and champ.confiance < seuil:
            lieu = f"Ligne {ligne} : " if ligne else ""
            anomalies.append(Anomalie(
                code=CodeAnomalie.CONFIANCE_FAIBLE,
                message=f"{lieu}{libelle} lu avec une confiance de {champ.confiance:.0%}, à vérifier.",
                bloquante=False,
                ligne=ligne,
            ))
    return anomalies


def controle_doublon(dossier: DossierExtrait, historique: Iterable[DossierExtrait]) -> list[Anomalie]:
    """Même fichier, même contenu, ou même numéro de commande pour le même client."""
    mon_empreinte = empreinte(dossier)
    mon_client = normaliser(dossier.client.valeur)
    ma_commande = (dossier.numero_commande.valeur or "").strip().lower()
    mon_hash = (dossier.source_hash or "").strip()
    for ancien in historique:
        meme_fichier = bool(mon_hash) and mon_hash == (ancien.source_hash or "").strip()
        meme_contenu = empreinte(ancien) == mon_empreinte
        meme_commande = (
            bool(ma_commande)
            and ma_commande == (ancien.numero_commande.valeur or "").strip().lower()
            and mon_client == normaliser(ancien.client.valeur)
        )
        if meme_fichier:
            return [Anomalie(
                code=CodeAnomalie.DOUBLON,
                message="Ce fichier a déjà été importé (même empreinte de fichier).",
            )]
        if meme_contenu or meme_commande:
            return [Anomalie(
                code=CodeAnomalie.DOUBLON,
                message="Ce dossier a déjà été traité (même contenu ou même commande pour ce client).",
            )]
    return []


def controle_taxe(dossier: DossierExtrait, taux_attendu: Decimal = Decimal("0.18")) -> list[Anomalie]:
    """Compare la taxe mentionnée par la source au taux paramétré.

    La mention de la source ne sert jamais au calcul : elle sert à alerter.
    Absente, elle ne produit aucune anomalie (information facultative).
    """
    champ = dossier.taux_taxe
    if _vide(champ):
        return []
    taux = en_taux(champ.valeur)
    if taux is None:
        return [Anomalie(
            code=CodeAnomalie.CHAMP_INVALIDE,
            message=f"Mention de taxe illisible (« {champ.valeur} »).",
            bloquante=False,
        )]
    if abs(taux - taux_attendu) > Decimal("0.0001"):
        lu = f"{(taux * 100).normalize():f} %"
        attendu = f"{(taux_attendu * 100).normalize():f} %"
        return [Anomalie(
            code=CodeAnomalie.TAXE_INCOHERENTE,
            message=f"La source indique une taxe de {lu} (« {champ.valeur} »), le taux paramétré est {attendu} : à vérifier.",
        )]
    return []


def controle_livraison(dossier: DossierExtrait) -> list[Anomalie]:
    """Compare quantités commandées et livrées, seulement si la livraison est fournie."""
    if not dossier.livraison:
        return []
    anomalies: list[Anomalie] = []
    livre = {i: Decimal(0) for i in range(1, len(dossier.lignes) + 1)}

    for ligne_livree in dossier.livraison:
        cible, score_max = None, 0.0
        for i, ligne in enumerate(dossier.lignes, start=1):
            if _vide(ligne.designation):
                continue
            s = _score(ligne_livree.designation, ligne.designation.valeur)
            if s > score_max:
                cible, score_max = i, s
        if cible is None or score_max < SCORE_POSSIBLE:
            anomalies.append(Anomalie(
                code=CodeAnomalie.INCOHERENCE_PIECES,
                message=f"« {ligne_livree.designation} » figure sur la livraison mais pas sur la commande.",
            ))
        else:
            livre[cible] += ligne_livree.quantite

    for i, ligne in enumerate(dossier.lignes, start=1):
        commande = en_decimal(ligne.quantite.valeur)
        if commande is None:
            continue  # déjà signalé par controle_lignes
        if livre[i] != commande:
            anomalies.append(Anomalie(
                code=CodeAnomalie.ECART_LIVRAISON,
                message=f"Ligne {i} : commandé {commande}, livré {livre[i]}.",
                ligne=i,
            ))
    return anomalies


# --------------------------------------------------------------------------
# Point d'entrée
# --------------------------------------------------------------------------
def controler(
    dossier: DossierExtrait,
    clients: list[Client],
    articles: list[Article],
    historique: Iterable[DossierExtrait] = (),
    *,
    seuil_prix: float = 0.30,
    seuil_confiance: float = 0.80,
    taux_taxe_attendu: Decimal = Decimal("0.18"),
) -> list[Anomalie]:
    """Lance tous les contrôles et renvoie la liste des anomalies."""
    return (
        controle_client(dossier, clients)
        + controle_lignes(dossier, articles, seuil_prix)
        + controle_confiance(dossier, seuil_confiance)
        + controle_doublon(dossier, historique)
        + controle_taxe(dossier, taux_taxe_attendu)
        + controle_livraison(dossier)
    )


def peut_valider(anomalies: Iterable[Anomalie]) -> bool:
    """Vrai si aucune anomalie bloquante n'est restée non résolue."""
    return not any(a.bloquante and not a.resolue for a in anomalies)
