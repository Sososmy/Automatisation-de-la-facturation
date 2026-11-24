# Facturation automatisée

## Structure du projet

```text
bwai2026-facturation/
│
├── README.md                  ← installation, lancement, tests, limites
├── requirements.txt           ← dépendances
├── Makefile                   ← make install / run / test / reset / scenarios
├── .env.example               ← variables sans secret
├── .gitignore
│
├── src/                       ← tout le code
│   ├── schemas.py             ← contrat de données commun
│   ├── config.py              ← taux de taxe, seuils
│   ├── extraction.py          ← IA : source → champs
│   ├── controls.py            ← anomalies et contrôles
│   ├── engine.py              ← calculs déterministes
│   ├── documents.py           ← statuts, numéro, idempotence, avoir
│   ├── audit.py               ← journal d'audit
│   ├── channels.py            ← émission simulée
│   ├── pdf.py                 ← export PDF
│   └── app.py                 ← interface Streamlit
│
├── data/
│   ├── referentiels/          ← clients.json, articles.json, regles_calcul.json
│   └── scenarios/             ← 6 scénarios de démo (nominal, doublon, écart,
│                                livraison, avoir, reprise)
│
├── tests/                     ← un fichier de test par module + test_parcours.py
│
├── scripts/                   ← reset_data.py, run_scenarios.py, evaluate_extraction.py
│
└── docs/                      ← architecture.md, fiche_ia.md, licences.md
```
