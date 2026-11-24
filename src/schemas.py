"""Contrat de données partagé entre tous les modules (à figer en premier).

Règle : montants en Decimal (jamais float). Le FCFA n'a pas de centimes.
"""
from decimal import Decimal
from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


class Statut(str, Enum):
    BROUILLON = "BROUILLON"
    VALIDEE = "VALIDEE"
    EMISE = "EMISE"
    AVOIR = "AVOIR"


class ChampExtrait(BaseModel):
    valeur: Optional[str] = None      # None si donnée absente : on n'invente jamais
    source: Optional[str] = None      # extrait / page / ligne d'origine
    confiance: float = 0.0            # 0..1


class LigneExtraite(BaseModel):
    designation: ChampExtrait
    quantite: ChampExtrait
    prix_unitaire: ChampExtrait
    remise: ChampExtrait = ChampExtrait()


class DossierExtrait(BaseModel):
    client: ChampExtrait
    date: ChampExtrait = ChampExtrait()
    conditions_paiement: ChampExtrait = ChampExtrait()
    lignes: list[LigneExtraite] = Field(default_factory=list)
    total_declare: ChampExtrait = ChampExtrait()


class Anomalie(BaseModel):
    code: str                         # CLIENT_INCONNU, DOUBLON, PRIX_INHABITUEL, ...
    message: str
    bloquante: bool = True
    resolue: bool = False


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
    id: str                           # identifiant stable (idempotence)
    numero: Optional[str] = None      # attribué seulement à la validation
    statut: Statut = Statut.BROUILLON
    client_id: str
    lignes: list[LigneCalculee] = Field(default_factory=list)
    total_ht: Decimal = Decimal("0")
    total_taxe: Decimal = Decimal("0")
    total_ttc: Decimal = Decimal("0")
    facture_origine_id: Optional[str] = None   # pour les avoirs liés
    version: int = 1                  # verrou optimiste (concurrence)
