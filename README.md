# Facturation automatisée 

Structure du projet 
bwai2026-facturation/
│
├── README.md                  ← installation, lancement, tests, limites
├── requirements.txt           ← dépendances
├── Makefile                   ← make install / run / test / reset / scenarios
├── .env.example               ← variables sans secret
├── .gitignore
│
├── src/                       ← tout le code
│   ├── schemas.py             ← contrat de données commun        [Toi]
│   ├── config.py              ← taux de taxe, seuils             [Toi]
│   ├── extraction.py          ← IA : source → champs             [B]
│   ├── controls.py            ← anomalies et contrôles           [C]
│   ├── engine.py              ← calculs déterministes            [C]
│   ├── documents.py           ← statuts, numéro, idempotence, avoir  [D]
│   ├── audit.py               ← journal d'audit                  [D]
│   ├── channels.py            ← émission simulée                 [D]
│   ├── pdf.py                 ← export PDF                       [D]
│   └── app.py                 ← interface Streamlit              [D]
│
├── data/
│   ├── referentiels/          ← clients.json, articles.json, regles_calcul.json
│   └── scenarios/             ← 6 scénarios de démo (nominal, doublon, écart,
│                                 livraison, avoir, reprise)
│
├── tests/                     ← un fichier de test par module + test_parcours.py
│
├── scripts/                   ← reset_data.py, run_scenarios.py, evaluate_extraction.py
│
└── docs/                      ← architecture.md, fiche_ia.md, licences.md
