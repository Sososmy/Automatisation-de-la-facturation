import json
from pathlib import Path

from streamlit.testing.v1 import AppTest

from src.audit import JournalAudit
from src.config import settings
from src.documents import DepotDocuments
from src.extraction import lire_texte
from src.schemas import ChampExtrait, DossierExtrait, LigneExtraite


def test_parcours_streamlit_degrade_jusqua_emission(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_url", str(tmp_path / "documents.db"))
    monkeypatch.setattr(settings, "app_user", "admin")
    monkeypatch.setattr(settings, "app_password", "mot-de-passe-test")
    app_path = Path(__file__).parents[1] / "src" / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=15).run()

    app.text_input[0].set_value("admin")
    app.text_input[1].set_value("mot-de-passe-test")
    app.form_submit_button[0].click()
    app.run()
    assert not app.exception

    app.checkbox[0].uncheck()
    app.text_area[0].set_value(
        "Societe Exemple SARL commande 2 Ciment 50 kg a 6500 XOF unite "
        "le 20/11/2026. Total HT 13000 XOF, TVA 18 %, total TTC 15340 XOF. "
        "Paiement comptant."
    )
    app.button(key="analyser_source").click()
    app.run()
    assert not app.exception

    cle = app.selectbox[0].key.removesuffix("_client_id")
    app.selectbox[0].select(app.selectbox[0].options[1])
    app.text_input(key=f"{cle}_date").set_value("21/11/2026")
    app.form_submit_button[0].click()
    app.run()

    assert app.selectbox[0].value == "CLI-001"
    assert app.text_input(key=f"{cle}_date").value == "21/11/2026"

    article = app.selectbox(key=f"{cle}_article_0")
    article.select(article.options[1])
    for champ, valeur in {
        "designation": "Ciment 50 kg",
        "quantite": "2",
        "prix_unitaire": "6500",
        "remise": "0",
    }.items():
        app.text_input(key=f"{cle}_ligne_0_{champ}").set_value(valeur)
    app.form_submit_button[1].click()
    app.run()

    assert not app.exception
    assert [
        (metric.label, metric.value)
        for metric in app.metric
        if metric.label in {"Total HT", "Taxes", "Total TTC"}
    ] == [
        ("Total HT", "13,000 XOF"),
        ("Taxes", "2,340 XOF"),
        ("Total TTC", "15,340 XOF"),
    ]

    app.button(key=f"{cle}_enregistrer").click()
    app.run()
    app.button(key=f"{cle}_valider").click()
    app.run()
    app.checkbox(key=f"{cle}_echeance_confirmee").check()
    app.run()
    app.button(key=f"{cle}_emettre").click()
    app.run()

    assert not app.exception
    assert any("Courriel simulé préparé" in item.value for item in app.success)
    assert len(app.get("download_button")) == 1
    with JournalAudit(str(tmp_path / "documents.db")) as journal:
        evenements = journal.lister()
    corrections = [
        json.loads(evenement["details"])["champs"]
        for evenement in evenements
        if evenement["action"] == "CORRECTIONS_HUMAINES"
    ]
    assert corrections
    assert {
        "champ": "date",
        "avant": "20/11/2026",
        "apres": "21/11/2026",
    } in corrections[0]
    assert any(changement["champ"] == "client_id" for changement in corrections[0])


def test_plateforme_bloquee_sans_mot_de_passe(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "database_url", str(tmp_path / "documents.db"))
    monkeypatch.setattr(settings, "app_password", "")
    app_path = Path(__file__).parents[1] / "src" / "app.py"

    app = AppTest.from_file(str(app_path), default_timeout=15).run()

    assert not app.exception
    assert any("APP_PASSWORD" in message.value for message in app.error)


def test_reprise_dune_source_archivee_dans_linterface(tmp_path, monkeypatch):
    database = str(tmp_path / "documents.db")
    monkeypatch.setattr(settings, "database_url", database)
    monkeypatch.setattr(settings, "app_user", "admin")
    monkeypatch.setattr(settings, "app_password", "mot-de-passe-test")
    source = lire_texte("Commande de démonstration conservée localement.")
    dossier = DossierExtrait(
        source_hash=source.hash,
        client=ChampExtrait(
            valeur="Société Exemple SARL",
            source="Société Exemple SARL",
            confiance=1.0,
        ),
        lignes=[
            LigneExtraite(
                designation=ChampExtrait(valeur="Ciment 50 kg"),
                quantite=ChampExtrait(valeur="2"),
                prix_unitaire=ChampExtrait(valeur="6500"),
            )
        ],
    )
    with DepotDocuments(database) as depot:
        depot.enregistrer_source(
            source.hash,
            "reprise.txt",
            source.texte,
            dossier,
        )
        depot.mettre_a_jour_dossier_source(
            source.hash,
            dossier,
            client_id_revu="CLI-001",
            articles_ids_revus=["ART-001"],
        )

    app_path = Path(__file__).parents[1] / "src" / "app.py"
    app = AppTest.from_file(str(app_path), default_timeout=15).run()
    app.text_input[0].set_value("admin")
    app.text_input[1].set_value("mot-de-passe-test")
    app.form_submit_button[0].click()
    app.run()
    app.selectbox(key="source_a_reprendre").select(source.hash)
    app.run()
    app.button(key="reprise_locale").click()
    app.run()

    assert not app.exception
    assert any("Extraction : reprise locale" in caption.value for caption in app.caption)
    cle = source.hash[:16]
    assert app.selectbox(key=f"{cle}_client_id").value == "CLI-001"
    assert app.selectbox(key=f"{cle}_article_0").value == "ART-001"
