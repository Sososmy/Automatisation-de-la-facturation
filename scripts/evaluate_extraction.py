"""Évalue le pipeline d'extraction sur un jeu JSONL annoté."""
from __future__ import annotations

import argparse
import json
from pathlib import Path

from src.evaluation import charger_jeu, evaluer_pipeline
from src.extraction import (
    MODELE_DEFAUT,
    ClientOllama,
    extraire,
    extraire_degrade,
    lire_texte,
)


ROOT = Path(__file__).resolve().parents[1]
JEU_DEFAUT = ROOT / "data" / "eval" / "exemple.jsonl"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--dataset", type=Path, default=JEU_DEFAUT)
    parser.add_argument(
        "--mode",
        choices=("degrade", "ollama"),
        default="degrade",
        help="Baseline locale sans IA, ou évaluation du modèle Ollama local.",
    )
    parser.add_argument("--model", default=MODELE_DEFAUT)
    parser.add_argument(
        "--timeout",
        type=int,
        default=30,
        help="Délai maximal en secondes par appel Ollama.",
    )
    parser.add_argument("--output", type=Path, help="Fichier JSON de rapport facultatif.")
    args = parser.parse_args(argv)
    if args.timeout <= 0:
        parser.error("--timeout doit être supérieur à zéro.")

    cas = charger_jeu(args.dataset)
    if not cas:
        parser.error(f"Le jeu d'évaluation est vide : {args.dataset}")

    client = ClientOllama(modele=args.model, delai=args.timeout)

    def extraire_cas(texte: str):
        source = lire_texte(texte)
        if args.mode == "degrade":
            return extraire_degrade(source, raison="Baseline sans modèle IA.")
        return extraire(source, client)

    journal: list[dict] = []
    resultats = evaluer_pipeline(cas, extraire_cas, journal)
    rapport = {
        "jeu": str(args.dataset),
        "mode": args.mode,
        "modele": args.model if args.mode == "ollama" else None,
        "resultats": resultats,
        "journal": journal,
    }
    rendu = json.dumps(rapport, ensure_ascii=False, indent=2)
    if args.output:
        args.output.write_text(rendu + "\n", encoding="utf-8")
    print(rendu)
    return 1 if resultats["erreurs_extraction"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
