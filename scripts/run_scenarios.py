"""Rejoue les scénarios du cas 2 avec données fictives et sans appel au modèle."""
from __future__ import annotations

import hashlib
import json
import sys
import tempfile
from decimal import Decimal
from pathlib import Path

from src.controls import controler
from src.documents import DepotDocuments, ValidationBloquee
from src.engine import calculer_facture
from src.schemas import (
    Article,
    ChampExtrait,
    Client,
    DossierExtrait,
    LigneExtraite,
    LigneLivree,
)

ROOT = Path(__file__).resolve().parents[1]


def _champ(valeur: str | None) -> ChampExtrait:
    return ChampExtrait(
        valeur=valeur,
        source=f"Scénario fictif : {valeur}" if valeur is not None else None,
        confiance=1.0 if valeur is not None else 0.0,
    )


def _dossier(donnees: dict, texte: str) -> DossierExtrait:
    lignes = [
        LigneExtraite(
            designation=_champ(ligne.get("designation")),
            quantite=_champ(ligne.get("quantite")),
            prix_unitaire=_champ(ligne.get("prix_unitaire")),
            remise=_champ(ligne.get("remise")),
        )
        for ligne in donnees["lignes"]
    ]
    livraison = [
        LigneLivree(
            designation=ligne["designation"],
            quantite=Decimal(ligne["quantite"]),
            source=f"Scénario fictif : {ligne['designation']};{ligne['quantite']}",
        )
        for ligne in donnees.get("livraison", [])
    ]
    source_hash = hashlib.sha256(texte.encode("utf-8")).hexdigest()
    return DossierExtrait(
        client=_champ(donnees.get("client")),
        numero_commande=_champ(donnees.get("numero_commande")),
        date=_champ(donnees.get("date")),
        conditions_paiement=_champ(donnees.get("conditions_paiement")),
        lignes=lignes,
        total_ht_declare=_champ(donnees.get("total_ht_declare")),
        total_ttc_declare=_champ(donnees.get("total_ttc_declare")),
        taux_taxe=_champ(donnees.get("taux_taxe")),
        livraison=livraison,
        source_hash=source_hash,
    )


def _charger_referentiels() -> tuple[list[Client], list[Article]]:
    clients = [
        Client.model_validate(item)
        for item in json.loads(
            (ROOT / "data" / "referentiels" / "clients.json").read_text(
                encoding="utf-8"
            )
        )
    ]
    articles = [
        Article.model_validate(item)
        for item in json.loads(
            (ROOT / "data" / "referentiels" / "articles.json").read_text(
                encoding="utf-8"
            )
        )
    ]
    return clients, articles


def _executer_scenario(
    scenario: dict,
    database_url: str,
    clients: list[Client],
    articles: list[Article],
) -> dict:
    dossier = _dossier(scenario["dossier"], scenario["source"])
    facture_id = f"scenario-{scenario['id']}"
    with DepotDocuments(database_url) as depot:
        anomalies = controler(
            dossier,
            clients,
            articles,
            historique=depot.lister_dossiers_originaux(),
            taux_taxe_attendu=Decimal("0.18"),
        )
        facture = None
        anomalies_calcul = []
        if not any(a.code.value == "DOUBLON" for a in anomalies):
            selection = [
                next(a for a in articles if a.id == ligne["article_id"])
                for ligne in scenario["dossier"]["lignes"]
            ]
            facture, anomalies_calcul = calculer_facture(
                dossier,
                selection,
                facture_id=facture_id,
                client_id=next(
                    client.id
                    for client in clients
                    if client.nom == dossier.client.valeur
                ),
                taux_taxe=Decimal("0.18"),
            )
        anomalies.extend(anomalies_calcul)
        codes = sorted(anomalie.code.value for anomalie in anomalies)
        action = scenario["action"]
        resultat = "DOUBLON" if "DOUBLON" in codes else "BROUILLON"

        depot.enregistrer_source(
            dossier.source_hash,
            scenario["id"] + ".txt",
            scenario["source"],
            dossier,
        )
        if action in ("facture", "bloquee", "avoir", "reprise"):
            if facture is None:
                raise AssertionError(f"{scenario['id']} : facture non calculable.")
            brouillon = depot.creer_brouillon(facture)
            if action == "bloquee":
                try:
                    depot.valider(
                        facture_id,
                        anomalies,
                        version_attendue=brouillon.version,
                        annee=2026,
                    )
                except ValidationBloquee:
                    resultat = "BLOQUEE"
                else:
                    raise AssertionError(
                        f"{scenario['id']} : la validation aurait dû être bloquée."
                    )
            elif action in ("facture", "avoir"):
                validee = depot.valider(
                    facture_id,
                    anomalies,
                    version_attendue=brouillon.version,
                    annee=2026,
                )
                emise = depot.emettre(
                    facture_id, version_attendue=validee.version
                )
                resultat = emise.statut.value
                if action == "avoir":
                    avoir = depot.creer_avoir_total(
                        f"avoir-{facture_id}",
                        facture_id,
                        version_attendue=emise.version,
                        annee=2026,
                    )
                    resultat = avoir.statut.value
            elif action == "reprise":
                depot.fermer()
                with DepotDocuments(database_url) as repris:
                    facture_reprise = repris.obtenir(facture_id)
                    source_reprise = repris.obtenir_source(dossier.source_hash)
                    if (
                        facture_reprise.id != facture_id
                        or source_reprise["dossier"].source_hash != dossier.source_hash
                    ):
                        raise AssertionError(
                            f"{scenario['id']} : la reprise locale a échoué."
                        )
                resultat = "REPRISE"

    attendu = scenario["attendu"]
    if codes != sorted(attendu["anomalies"]):
        raise AssertionError(
            f"{scenario['id']} : anomalies {codes}, attendues {attendu['anomalies']}."
        )
    if resultat != attendu["resultat"]:
        raise AssertionError(
            f"{scenario['id']} : résultat {resultat}, attendu {attendu['resultat']}."
        )
    if facture is not None and "total_ttc" in attendu:
        if str(facture.total_ttc) != attendu["total_ttc"]:
            raise AssertionError(
                f"{scenario['id']} : TTC {facture.total_ttc}, "
                f"attendu {attendu['total_ttc']}."
            )
    return {
        "id": scenario["id"],
        "description": scenario["description"],
        "anomalies": codes,
        "resultat": resultat,
        "total_ttc": str(facture.total_ttc) if facture is not None else None,
    }


def executer() -> list[dict]:
    clients, articles = _charger_referentiels()
    scenarios = [
        json.loads(chemin.read_text(encoding="utf-8"))
        for chemin in sorted((ROOT / "data" / "scenarios").glob("*.json"))
    ]
    if not scenarios:
        raise RuntimeError("Aucun scénario de démonstration n'est disponible.")
    with tempfile.TemporaryDirectory(prefix="bwai-scenarios-") as temporaire:
        base = str(Path(temporaire) / "scenarios.db")
        return [
            _executer_scenario(scenario, base, clients, articles)
            for scenario in scenarios
        ]


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    print(json.dumps(executer(), ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
