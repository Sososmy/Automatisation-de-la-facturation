"""Contrat de données commun à tous les modules.

Règles :
- Les montants et quantités sont des Decimal, jamais des float.
- Une donnée absente reste None : on ne l'invente jamais.
- Toute modification de ce fichier se décide à plusieurs.
"""
from __future__ import annotations

import re
import unicodedata
from decimal import Decimal, InvalidOperation
from enum import Enum
from typing import Optional

from pydantic import BaseModel, Field


# --------------------------------------------------------------------------
# Statuts et anomalies
# --------------------------------------------------------------------------
class Statut(str, Enum):
    BROUILLON = "BROUILLON"
    VALIDEE = "VALIDEE"
    EMISE = "EMISE"
    AVOIR = "AVOIR"


class CodeAnomalie(str, Enum):
    CHAMP_MANQUANT = "CHAMP_MANQUANT"
    CHAMP_INVALIDE = "CHAMP_INVALIDE"
    CONFIANCE_FAIBLE = "CONFIANCE_FAIBLE"
    CLIENT_MANQUANT = "CLIENT_MANQUANT"
    CLIENT_INCONNU = "CLIENT_INCONNU"
    CLIENT_INCERTAIN = "CLIENT_INCERTAIN"
    ARTICLE_INCONNU = "ARTICLE_INCONNU"
    PRIX_INHABITUEL = "PRIX_INHABITUEL"
    DOUBLON = "DOUBLON"
    ECART_LIVRAISON = "ECART_LIVRAISON"
    INCOHERENCE_PIECES = "INCOHERENCE_PIECES"
    TAXE_INCOHERENTE = "TAXE_INCOHERENTE"
    ECART_MONTANT = "ECART_MONTANT"  # utilisé par engine.py


class Anomalie(BaseModel):
    code: CodeAnomalie
    message: str
    bloquante: bool = True
    resolue: bool = False  # passe à True quand un humain l'a traitée
    ligne: Optional[int] = None  # numéro de ligne (à partir de 1) si concerné


# --------------------------------------------------------------------------
# Référentiels
# --------------------------------------------------------------------------
class Client(BaseModel):
    id: str
    nom: str
    email: Optional[str] = None
    ifu: Optional[str] = None


class Article(BaseModel):
    id: str
    designation: str
    prix_reference: Decimal
    taxable: bool = True


# --------------------------------------------------------------------------
# Sortie de l'extraction (module extraction.py -> controls.py)
# --------------------------------------------------------------------------
class ChampExtrait(BaseModel):
    valeur: Optional[str] = None  # None si absent de la source
    source: Optional[str] = None  # extrait d'origine, pour vérification
    confiance: float = 0.0  # entre 0 et 1


class LigneExtraite(BaseModel):
    designation: ChampExtrait = Field(default_factory=ChampExtrait)
    quantite: ChampExtrait = Field(default_factory=ChampExtrait)
    prix_unitaire: ChampExtrait = Field(default_factory=ChampExtrait)
    remise: ChampExtrait = Field(default_factory=ChampExtrait)  # en pourcentage


class LigneLivree(BaseModel):
    """Ligne d'une pièce de livraison (facultative)."""

    designation: str
    quantite: Decimal


class DossierExtrait(BaseModel):
    """Ce que l'extraction a lu dans la source.

    Totaux : une source peut afficher le HT, le TTC, les deux ou aucun.
    On extrait ce qui est présent ; le moteur compare uniquement ce qui existe.

    Taxe : `taux_taxe` est la mention de la source (« TVA 18 % », « exonéré »).
    Elle sert à détecter une incohérence, jamais au calcul : le moteur utilise
    le taux paramétré et les statuts du référentiel.

    Traçabilité : `source_hash` et `nom_fichier_source` sont renseignés par
    l'application à l'import, pas par l'IA.
    """

    client: ChampExtrait = Field(default_factory=ChampExtrait)
    numero_commande: ChampExtrait = Field(default_factory=ChampExtrait)
    date: ChampExtrait = Field(default_factory=ChampExtrait)
    conditions_paiement: ChampExtrait = Field(default_factory=ChampExtrait)
    lignes: list[LigneExtraite] = Field(default_factory=list)
    total_ht_declare: ChampExtrait = Field(default_factory=ChampExtrait)
    total_ttc_declare: ChampExtrait = Field(default_factory=ChampExtrait)
    taux_taxe: ChampExtrait = Field(default_factory=ChampExtrait)
    livraison: list[LigneLivree] = Field(default_factory=list)  # vide = non fournie
    source_hash: Optional[str] = None  # empreinte du fichier importé (application)
    nom_fichier_source: Optional[str] = None  # nom du fichier importé (application)


# --------------------------------------------------------------------------
# Sortie du moteur de calcul (engine.py -> documents.py)
# --------------------------------------------------------------------------
class LigneCalculee(BaseModel):
    article_id: str
    designation: str
    quantite: Decimal
    prix_unitaire: Decimal
    remise_pct: Decimal = Decimal("0")
    base_ht: Decimal
    taxe: Decimal
    total_ttc: Decimal


class Facture(BaseModel):
    id: str  # identifiant stable (idempotence)
    numero: Optional[str] = None  # attribué seulement à la validation
    statut: Statut = Statut.BROUILLON
    client_id: str
    lignes: list[LigneCalculee] = Field(default_factory=list)
    total_ht: Decimal = Decimal("0")
    total_taxe: Decimal = Decimal("0")
    total_ttc: Decimal = Decimal("0")
    facture_origine_id: Optional[str] = None  # renseigné pour un avoir lié
    version: int = 1  # verrou optimiste (validations concurrentes)


# --------------------------------------------------------------------------
# Utilitaires partagés
# --------------------------------------------------------------------------
def normaliser(texte: Optional[str]) -> str:
    """Minuscules, sans accents, espaces simplifiés (pour comparer des noms)."""
    if not texte:
        return ""
    sans_accents = unicodedata.normalize("NFKD", texte)
    sans_accents = "".join(c for c in sans_accents if not unicodedata.combining(c))
    return re.sub(r"\s+", " ", sans_accents.lower()).strip()


def en_decimal(texte: Optional[str]) -> Optional[Decimal]:
    """Convertit '6 500 FCFA', '6500,50' ou '10%' en Decimal. None si illisible.

    Convention : un séparateur suivi d'exactement 3 chiffres ('1.250', '1,250')
    est un séparateur de milliers (le FCFA n'a pas de centimes).
    """
    if texte is None:
        return None
    s = str(texte).replace("\u00a0", " ").replace(" ", "")
    s = re.sub(r"[^\d,.\-]", "", s)
    if not re.search(r"\d", s):
        return None
    if "," in s and "." in s:
        decimal = "," if s.rfind(",") > s.rfind(".") else "."
        milliers = "." if decimal == "," else ","
        s = s.replace(milliers, "").replace(decimal, ".")
    elif "," in s:
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+", s):
            s = s.replace(",", "")
        else:
            s = s.replace(",", ".")
    elif "." in s and re.fullmatch(r"-?\d{1,3}(\.\d{3})+", s):
        s = s.replace(".", "")
    try:
        return Decimal(s)
    except InvalidOperation:
        return None


def en_taux(texte: Optional[str]) -> Optional[Decimal]:
    """Convertit une mention de taxe en fraction : '18 %' -> 0.18, '0,18' -> 0.18,
    'exonéré' -> 0. None si illisible.

    Convention : un nombre contenant '%' ou supérieur à 1 est un pourcentage ;
    un nombre entre 0 et 1 sans '%' est déjà une fraction.
    """
    n = normaliser(texte)
    if not n:
        return None
    if "exon" in n:
        return Decimal("0")
    v = en_decimal(texte)
    if v is None or v < 0:
        return None
    if "%" in texte or v > 1:
        v = v / 100
    return v
