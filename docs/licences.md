# Bibliothèques, modèles et licences

Les versions exactes des dépendances Python sont résolues à l'installation à
partir des bornes minimales de `requirements.txt`. Vérifier les licences des
versions effectivement déployées avant toute redistribution.

| Composant direct | Usage | Licence du projet |
|---|---|---|
| Pydantic | Modèles et validation de données | MIT |
| pydantic-settings | Configuration par variables d'environnement | MIT |
| Streamlit | Interface locale | Apache-2.0 |
| pdfplumber | Lecture de PDF textuels | MIT |
| RapidFuzz | Rapprochement de texte | MIT |
| ReportLab | Génération d'aperçus PDF | BSD-3-Clause |
| pytest | Tests automatisés | MIT |
| SQLite / bibliothèque standard Python | Persistance locale et stockage | Domaine public SQLite / PSF |

Ollama est un exécutable local facultatif, non installé par `requirements.txt`.
Le modèle par défaut est `qwen2.5:3b` (Qwen2.5 Instruct, licence Apache-2.0).
Le modèle doit être obtenu auprès de sa source officielle et sa licence de
redistribution doit être vérifiée pour tout produit dérivé.

Aucun code de fournisseur de messagerie, de paiement mobile money ou
d'intégration e-MECEF/DGI n'est inclus. Les canaux de communication et les
règlements du prototype sont des simulations locales.
