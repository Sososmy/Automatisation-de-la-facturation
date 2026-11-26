import json
import subprocess
import sys
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_six_scenarios_du_cas_2_sont_reproductibles():
    resultat = subprocess.run(
        [sys.executable, "-m", "scripts.run_scenarios"],
        cwd=ROOT,
        check=True,
        capture_output=True,
        text=True,
        encoding="utf-8",
    )

    scenarios = json.loads(resultat.stdout)
    assert [scenario["id"] for scenario in scenarios] == [
        "01_nominal",
        "02_doublon",
        "03_ecart",
        "04_livraison",
        "05_avoir",
        "06_reprise",
    ]
    assert [scenario["resultat"] for scenario in scenarios] == [
        "EMISE",
        "DOUBLON",
        "BLOQUEE",
        "BLOQUEE",
        "AVOIR",
        "REPRISE",
    ]
