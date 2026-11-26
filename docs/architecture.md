# Architecture — cas 2 BWAI 2026

## Parcours

`source locale -> proposition d'extraction -> revue humaine -> contrôles ->
moteur déterministe -> brouillon SQLite -> validation versionnée -> émission
simulée -> règlements simulés`

Le parcours est orchestré par `src/app.py`. Une source texte, PDF textuel, TXT
ou MD est lue en mémoire, puis conservée localement dans SQLite afin de pouvoir
reprendre une revue après interruption. Les référentiels fictifs clients et
articles restent des fichiers JSON versionnés dans `data/referentiels/`.
L'interface permet aussi de saisir une pièce de livraison facultative au format
`désignation;quantité`.

## Frontières de confiance

Ollama local (modèle par défaut `qwen2.5:3b`) peut proposer des champs extraits.
`src/extraction.py` cherche chaque valeur dans le texte source, calcule sa
propre confiance et conserve un extrait explicatif. Les valeurs non retrouvées
sont rejetées. Aucun calcul de facture n'est demandé au modèle. S'il est absent
ou en échec, un mode dégradé explicite permet une revue et une saisie humaine.

`src/controls.py` rapproche les clients et articles, signale les doublons, les
écarts de prix, de taxe, de livraison et les champs à confirmer. Les anomalies
bloquantes non résolues empêchent la validation. Le contrôle des quantités
livrées n'est exécuté que si cette pièce facultative est fournie.

`src/engine.py` utilise `Decimal` pour appliquer la remise, le taux de taxe
configuré et l'arrondi XOF `ROUND_HALF_UP`, puis compare le HT/TTC déclaré aux
totaux recalculés. Ce résultat déterministe ne dépend pas du modèle.

## Persistance, transitions et audit

`src/documents.py` utilise directement SQLite :

- `sources_commerciales` conserve l'empreinte, la source locale, le dossier
  initial, le dossier corrigé et les associations confirmées pour la reprise et
  la détection des doublons ;
- `factures` conserve brouillons, factures et avoirs liés ;
- `sequences_documents` attribue des numéros internes `SIM-*` ;
- `reglements` conserve les règlements fictifs et leurs références uniques.

Les transitions métier utilisent `BEGIN IMMEDIATE`, une version optimiste et
des contraintes d'unicité. Une facture validée ou émise ne peut plus être
modifiée ; sa correction passe par un avoir total lié et, au besoin, une
nouvelle facture. Les règlements sont réservés aux factures émises, ne peuvent
pas dépasser le solde et sont idempotents par référence.

`src/audit.py` écrit les imports, corrections champ par champ, validations,
émissions et règlements dans le journal SQLite. Chaque événement inclut
l'empreinte précédente ; les écritures concurrentes sont sérialisées et la
chaîne peut être vérifiée. Le journal est local et ne constitue pas un registre
comptable certifié.

## Interface et sorties

`src/app.py` fournit le parcours Streamlit, un compte local protégé par
`APP_PASSWORD`, la sélection d'un modèle Ollama local, l'aperçu d'émission et
l'historique. `src/channels.py` valide et prépare un message sans appel réseau.
`src/pdf.py` exporte un document de démonstration portant explicitement la
mention « non normalisé DGI ». Aucune émission e-MECEF, aucun courriel, SMS ou
paiement réel n'est réalisé.

## Vérification

- `python -m pytest -q` : tests unitaires, contrôles de concurrence et parcours
  Streamlit en mode dégradé.
- `python -m scripts.run_scenarios` : six scénarios fictifs reproductibles,
  sans Ollama ni réseau.
- `python -m scripts.evaluate_extraction` : mesures séparées de l'extraction
  sur les jeux JSONL annotés.

Voir le [rapport de hackathon](rapport_hackathon.md) et la [fiche IA](fiche_ia.md).
