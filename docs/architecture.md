# Architecture et choix techniques
Python 3.11 · Pydantic · SQLite/SQLAlchemy · Decimal · LLM (extraction seule) · pdfplumber · rapidfuzz · ReportLab · Streamlit · pytest

Flux : extraction -> controls -> engine -> documents -> channels (audit transversal)

Le moteur reçoit les articles rapprochés et confirmés par les contrôles. Il
calcule chaque ligne en `Decimal`, applique la remise indiquée (0 % si absente),
puis la taxe configurée uniquement aux articles taxables. Les montants sont
arrondis à l'unité XOF avec `ROUND_HALF_UP`. Les totaux HT et TTC présents dans
la source sont comparés aux montants recalculés ; tout écart est signalé.
