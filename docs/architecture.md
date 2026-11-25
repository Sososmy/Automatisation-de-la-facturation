# Architecture et choix techniques
Python 3.11 · Pydantic · SQLite/SQLAlchemy · Decimal · LLM (extraction seule) · pdfplumber · rapidfuzz · ReportLab · Streamlit · pytest

Flux : extraction -> controls -> engine -> documents -> channels (audit transversal)

Le moteur reçoit les articles rapprochés et confirmés par les contrôles. Il
calcule chaque ligne en `Decimal`, applique la remise indiquée (0 % si absente),
puis la taxe configurée uniquement aux articles taxables. Les montants sont
arrondis à l'unité XOF avec `ROUND_HALF_UP`. Les totaux HT et TTC présents dans
la source sont comparés aux montants recalculés ; tout écart est signalé.

`documents.py` conserve les brouillons dans SQLite, applique les transitions
de validation et d'émission simulée avec contrôle de version, et peut créer un
avoir total. Les numéros `SIM-*` sont internes au prototype. `pdf.py` produit
un aperçu téléchargeable, qui porte explicitement la mention « non normalisée
DGI » : il ne constitue ni une facture normalisée ni une émission e-MECEF.
