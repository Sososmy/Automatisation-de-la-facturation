# Facturation automatisée — prototype BWAI 2026

Prototype d'aide au traitement de documents commerciaux pour le Bénin. Il
sépare l'extraction assistée par IA des contrôles et des calculs déterministes.
Il ne constitue pas un logiciel de comptabilité certifié et ne produit pas de
facture normalisée par la DGI.

## État du projet

### Déjà réalisé

- **Contrats de données** dans `src/schemas.py` : clients, articles, champs
  extraits, anomalies et factures.
- **Extraction** dans `src/extraction.py` : lecture de documents, proposition
  de champs par modèle, vérification des valeurs dans le texte source et mode
  de repli limité si le modèle est indisponible.
- **Contrôles** dans `src/controls.py` : rapprochement avec les clients et
  articles, détection d'anomalies, sans correction automatique des données.
- **Calcul** dans `src/engine.py` : montants en `Decimal`, remise facultative,
  taxe configurée sur les articles taxables et arrondi XOF.
- **Évaluation** dans `src/evaluation.py` : mesure des erreurs, omissions,
  inventions, citations et latences. Le jeu annoté
  `data/eval/exemple.jsonl` contient actuellement six exemples fictifs; il
  sert de premier jeu de test, pas de validation à grande échelle.
- **Cycle documentaire** dans `src/documents.py` : stockage SQLite des
  documents, brouillons, validation avec contrôle de version, émission
  simulée et avoir total. Les numéros `SIM-*` sont internes au prototype.
- **Export PDF** dans `src/pdf.py` : aperçu contenant une mention visible de
  non-normalisation DGI.
- Six scénarios de démonstration sont présents dans `data/scenarios/`.
- Vérification locale du 25 novembre 2026 : `python -m pytest -q` — **129 tests
  réussis, 1 ignoré**.

### En cours ou restant à faire

- **Base de données des référentiels** : SQLite est configuré et le dépôt de
  documents crée les tables `factures` et `sequences_documents`. Les clients,
  articles et règles restent dans des fichiers JSON; leur chargement et leur
  consultation depuis SQLite ne sont pas encore reliés.
- **Parcours complet** : les modules existent séparément, mais ils ne sont pas
  encore orchestrés dans une chaîne extraction → contrôles → calcul →
  correction humaine → validation → enregistrement et PDF.
- **Validation humaine** : les contrôles signalent les anomalies et les
  documents bloquent la validation lorsqu'on leur transmet des anomalies
  bloquantes non résolues. Le parcours de revue/correction et la persistance
  complète de ces décisions restent à intégrer.
- **Évaluation plus large** : enrichir le jeu avec des documents variés,
  annotés et anonymisés, puis définir des critères d'acceptation avant de
  considérer l'extraction suffisamment fiable.
- **Interface** : `src/app.py` affiche actuellement une page Streamlit minimale;
  l'import, la revue humaine, la validation et le téléchargement PDF restent à
  construire.
- **Audit et canaux** : `src/audit.py` et `src/channels.py` sont des
  emplacements prévus, pas des fonctions d'audit ou d'envoi opérationnelles.
- **Production et conformité** : sécurité, gestion des accès, sauvegardes,
  déploiement et éventuelle intégration officielle e-MECEF/DGI ne sont pas
  implémentés. Aucun courriel, SMS ou WhatsApp n'est réellement envoyé.

## Prochaines étapes convenues

1. Rendre SQLite utilisable pour les référentiels clients et articles, en
   important les données initiales de `data/referentiels/`.
2. Relier les modules pour exécuter le parcours complet et permettre la revue
   humaine des champs et anomalies.
3. Élargir le jeu de données et mesurer les résultats avant de développer
   l'interface.
4. Construire l'interface Streamlit pour importer les documents, vérifier et
   corriger les résultats, valider, puis récupérer le PDF.

## Installation et commandes

Depuis la racine du dépôt, avec Python 3.11 ou supérieur :

```powershell
python -m pip install -r requirements.txt
python -m pytest -q
streamlit run src/app.py
```

Le lancement Streamlit ouvre actuellement la page minimale du prototype; le
parcours utilisateur complet n'est pas encore connecté.

La configuration se trouve dans `.env.example`. `DATABASE_URL` vaut par défaut
`sqlite:///./data/app.db`. Ne placez jamais de clés API ou d'autres secrets dans
le dépôt.

## Structure

- `src/` : schémas, extraction, contrôles, calcul, documents, PDF et interface.
- `data/referentiels/` : fichiers JSON de clients, articles et règles de calcul.
- `data/eval/` : jeu annoté d'évaluation de l'extraction.
- `data/scenarios/` : scénarios de démonstration.
- `tests/` : tests unitaires des modules.
- `scripts/` : scripts de scénarios, de réinitialisation et d'évaluation.
- `docs/` : architecture, fiche IA et licences.
