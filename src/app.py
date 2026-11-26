"""Interface de démonstration du parcours de facturation BWAI."""
from __future__ import annotations

import hashlib
import json
import hmac
from datetime import date
from decimal import Decimal
from pathlib import Path

import streamlit as st
from pydantic import ValidationError

from src.audit import JournalAudit
from src.channels import CanauxSimules
from src.config import settings
from src.controls import controler
from src.documents import (
    ConflitReglement,
    DepotDocuments,
    ErreurDocument,
    FactureIntrouvable,
)
from src.engine import calculer_facture
from src.extraction import (
    MODELE_DEFAUT,
    ClientOllama,
    ExtractionError,
    ResultatExtraction,
    SourceLue,
    extraire_avec_repli,
    extraire_degrade,
    lire_lignes_livraison,
    lire_televersement,
    lire_texte,
    normaliser_date,
)
from src.pdf import InformationsVendeur, generer_pdf
from src.schemas import (
    Article,
    Anomalie,
    ChampExtrait,
    Client,
    CodeAnomalie,
    DossierExtrait,
    Facture,
    LigneExtraite,
    Statut,
    en_decimal,
)


ROOT = Path(__file__).resolve().parents[1]
CLIENTS_PATH = ROOT / "data" / "referentiels" / "clients.json"
ARTICLES_PATH = ROOT / "data" / "referentiels" / "articles.json"
FIELDS = (
    ("numero_commande", "Référence de commande ou devis"),
    ("date", "Date"),
    ("conditions_paiement", "Conditions de paiement"),
    ("total_ht_declare", "Total HT indiqué dans la source"),
    ("total_ttc_declare", "Total TTC indiqué dans la source"),
    ("taux_taxe", "Taxe indiquée dans la source"),
)

st.set_page_config(page_title="Facturation BWAI 2026", layout="wide")
st.markdown(
    """
    <style>
    .stApp { background: #f5f7fb; }
    [data-testid="stHeader"] { background: rgba(245,247,251,.9); }
    [data-testid="stSidebar"] { background: #101b2d; }
    [data-testid="stSidebar"] * { color: #e7edf7; }
    [data-testid="stSidebar"] button { border-color: #44536b; }
    .hero {
        padding: 1.7rem 2rem; border-radius: 18px; color: white;
        background: linear-gradient(115deg,#10233f 0%,#174b60 65%,#168b78 100%);
        margin: .4rem 0 1.2rem;
    }
    .hero-kicker { color: #9de7d3; font-size: .75rem; font-weight: 700;
        letter-spacing: .13em; text-transform: uppercase; }
    .hero h1 { color: white; font-size: 2rem; margin: .45rem 0; }
    .hero p { color: #dce8f1; margin: 0; }
    .section-label { color: #15806f; font-size: .75rem; font-weight: 700;
        letter-spacing: .1em; text-transform: uppercase; margin: 1.3rem 0 .2rem; }
    .stepper { display: flex; gap: .55rem; margin: .9rem 0 1.6rem; }
    .step {
        flex: 1; background: white; border: 1px solid #e1e7ef; border-radius: 10px;
        padding: .75rem .85rem; color: #67758a; font-size: .84rem;
    }
    .step strong { color: #26364c; display: block; font-size: .75rem; margin-bottom: .2rem; }
    .step.active { background: #e8f5f1; border-color: #42a994; color: #315d56; }
    [data-testid="stMainBlockContainer"] { max-width: 1380px; padding-top: 1.4rem; }
    div[data-testid="stMetric"] {
        background: white; border: 1px solid #e3e9f1; padding: 1rem;
        border-radius: 12px; box-shadow: 0 3px 12px rgba(27,45,69,.04);
    }
    div[data-testid="stVerticalBlockBorderWrapper"] {
        background: white; border-radius: 12px;
    }
    div[data-testid="stExpander"] {
        border: 1px solid #e3e9f1; border-radius: 12px; overflow: hidden;
    }
    div.stButton > button[kind="primary"] {
        background: #117a69; border-color: #117a69;
    }
    div.stButton > button:hover { border-color: #117a69; color: #117a69; }
    [data-testid="stFileUploaderDropzone"] {
        border: 1px dashed #9aabba; border-radius: 12px; background: #fbfcfe;
    }
    @media (max-width: 760px) {
        .hero { padding: 1.25rem; }
        .hero h1 { font-size: 1.55rem; }
        .stepper { flex-direction: column; }
        .step { padding: .6rem .75rem; }
    }
    </style>
    """,
    unsafe_allow_html=True,
)


def verifier_acces() -> bool:
    if not settings.app_password:
        st.error(
            "Accès désactivé : définissez APP_PASSWORD avant de démarrer la plateforme."
        )
        return False
    if st.session_state.get("authentifie"):
        return True

    with st.form("connexion"):
        identifiant = st.text_input("Utilisateur")
        mot_de_passe = st.text_input("Mot de passe", type="password")
        if st.form_submit_button("Se connecter"):
            identifiant_valide = hmac.compare_digest(
                identifiant.encode("utf-8"), settings.app_user.encode("utf-8")
            )
            mot_de_passe_valide = hmac.compare_digest(
                mot_de_passe.encode("utf-8"), settings.app_password.encode("utf-8")
            )
            if identifiant_valide and mot_de_passe_valide:
                st.session_state["authentifie"] = True
                st.session_state["acteur"] = settings.app_user
                st.rerun()
            else:
                st.error("Identifiants incorrects.")
    return False


if not verifier_acces():
    st.stop()

st.sidebar.markdown(
    """
    <div style="padding:.4rem 0 1rem">
      <div style="font-size:.72rem;letter-spacing:.15em;color:#9de7d3;font-weight:700">
        BWAI · 2026
      </div>
      <div style="font-size:1.15rem;font-weight:700;color:white;margin-top:.35rem">
        Atelier Facturation
      </div>
      <div style="font-size:.8rem;color:#aab8ca;margin-top:.2rem">
        Prototype de démonstration
      </div>
    </div>
    """,
    unsafe_allow_html=True,
)
st.sidebar.markdown("---")
st.sidebar.caption("PARCOURS")
st.sidebar.markdown("①  Importer une pièce")
st.sidebar.markdown("②  Vérifier les données")
st.sidebar.markdown("③  Calculer et valider")
st.sidebar.markdown("④  Émission simulée")
st.sidebar.markdown("---")
st.sidebar.caption("MODE HORS LIGNE · DONNÉES FICTIVES")


def nouvelle_analyse() -> None:
    for cle in ("source", "resultat_extraction", "dossier", "texte_source"):
        st.session_state.pop(cle, None)


if st.sidebar.button("Nouvelle analyse", key="nouvelle_analyse"):
    nouvelle_analyse()
    st.rerun()

st.markdown(
    """
    <div class="hero">
      <div class="hero-kicker">Facturation · démonstration BWAI 2026</div>
      <h1>Du document au brouillon vérifié.</h1>
      <p>Importez une commande, contrôlez les informations, puis calculez et suivez
      la facture avec une validation humaine à chaque étape sensible.</p>
    </div>
    """,
    unsafe_allow_html=True,
)


def journaliser(action: str, facture_id: str, details: dict | None = None) -> None:
    with JournalAudit() as journal:
        journal.enregistrer(
            acteur=st.session_state.get("acteur", "utilisateur-local"),
            action=action,
            facture_id=facture_id,
            details=details,
        )


def charger_referentiels() -> tuple[list[Client], list[Article]]:
    clients_bruts = json.loads(CLIENTS_PATH.read_text(encoding="utf-8"))
    articles_bruts = json.loads(ARTICLES_PATH.read_text(encoding="utf-8"))
    return (
        [Client.model_validate(item) for item in clients_bruts],
        [Article.model_validate(item) for item in articles_bruts],
    )


try:
    CLIENTS, ARTICLES = charger_referentiels()
except (OSError, json.JSONDecodeError, ValidationError) as erreur:
    st.error(f"Impossible de charger les référentiels clients et articles : {erreur}")
    st.stop()

CLIENTS_PAR_ID = {client.id: client for client in CLIENTS}
ARTICLES_PAR_ID = {article.id: article for article in ARTICLES}

indicateur = st.columns(3)
indicateur[0].metric("Clients référencés", len(CLIENTS))
indicateur[1].metric("Articles disponibles", len(ARTICLES))
indicateur[2].metric("Taxe configurée", f"{settings.tax_rate:.0%}")

analyse_en_cours = bool(st.session_state.get("resultat_extraction"))
etapes = (
    ("01", "Importer", "Message, devis ou commande"),
    ("02", "Vérifier", "Champs et anomalies"),
    ("03", "Calculer", "Montants déterministes"),
    ("04", "Émettre", "Validation humaine"),
)
etapes_html = "".join(
    (
        f'<div class="step {"active" if (index == (1 if analyse_en_cours else 0)) else ""}">'
        f"<strong>{numero} · {titre}</strong>{description}</div>"
    )
    for index, (numero, titre, description) in enumerate(etapes)
)
st.markdown(f'<div class="stepper">{etapes_html}</div>', unsafe_allow_html=True)


def _cle_source(source_hash: str) -> str:
    return source_hash[:16]


def _corriger_champ(champ: ChampExtrait, valeur: str) -> ChampExtrait:
    valeur_nettoyee = valeur.strip() or None
    if valeur_nettoyee == champ.valeur:
        return champ.model_copy(deep=True)
    origine = champ.source or "aucun extrait disponible"
    return ChampExtrait(
        valeur=valeur_nettoyee,
        source=f"Correction humaine; extrait initial : {origine}",
        confiance=1.0,
    )


def _initialiser_editeur(
    cle: str,
    dossier: DossierExtrait,
    facture_enregistree: Facture | None,
    archive_source: dict,
) -> None:
    for attribut, _ in FIELDS:
        widget_key = f"{cle}_{attribut}"
        champ = getattr(dossier, attribut)
        if widget_key not in st.session_state:
            st.session_state[widget_key] = champ.valeur or ""

    client_key = f"{cle}_client_id"
    if client_key not in st.session_state:
        st.session_state[client_key] = (
            facture_enregistree.client_id
            if facture_enregistree
            else archive_source["client_id_revu"]
        )
    client_original_key = f"{cle}_client_id_original"
    if client_original_key not in st.session_state:
        st.session_state[client_original_key] = st.session_state[client_key]
    nom_client_key = f"{cle}_client_nom"
    if nom_client_key not in st.session_state:
        st.session_state[nom_client_key] = dossier.client.valeur or ""

    for index, ligne in enumerate(dossier.lignes):
        ancienne_ligne = (
            facture_enregistree.lignes[index]
            if facture_enregistree and index < len(facture_enregistree.lignes)
            else None
        )
        for attribut in ("designation", "quantite", "prix_unitaire", "remise"):
            widget_key = f"{cle}_ligne_{index}_{attribut}"
            if widget_key in st.session_state:
                continue
            valeur = getattr(ligne, attribut).valeur or ""
            if ancienne_ligne:
                if attribut == "designation":
                    valeur = ancienne_ligne.designation
                elif attribut == "quantite":
                    valeur = format(ancienne_ligne.quantite, "f")
                elif attribut == "prix_unitaire":
                    valeur = format(ancienne_ligne.prix_unitaire, "f")
                elif attribut == "remise":
                    valeur = format(ancienne_ligne.remise_pct, "f")
            st.session_state[widget_key] = valeur

        article_key = f"{cle}_article_{index}"
        if article_key not in st.session_state:
            articles_ids = archive_source["articles_ids_revus"]
            st.session_state[article_key] = (
                ancienne_ligne.article_id
                if ancienne_ligne
                else (
                    articles_ids[index]
                    if index < len(articles_ids)
                    else None
                )
            )
        article_original_key = f"{cle}_article_{index}_original"
        if article_original_key not in st.session_state:
            st.session_state[article_original_key] = st.session_state[article_key]

    livraison_key = f"{cle}_livraison_source"
    if livraison_key not in st.session_state:
        st.session_state[livraison_key] = "\n".join(
            f"{ligne.designation};{ligne.quantite}"
            for ligne in dossier.livraison
        )


def _dossier_edite(cle: str, dossier_source: DossierExtrait) -> DossierExtrait:
    dossier = dossier_source.model_copy(deep=True)
    client_id = st.session_state.get(f"{cle}_client_id")
    if client_id in CLIENTS_PAR_ID:
        dossier.client = _corriger_champ(
            dossier_source.client, CLIENTS_PAR_ID[client_id].nom
        )
    else:
        dossier.client = _corriger_champ(
            dossier_source.client,
            st.session_state.get(f"{cle}_client_nom", dossier_source.client.valeur or ""),
        )

    for attribut, _ in FIELDS:
        valeur = st.session_state.get(
            f"{cle}_{attribut}", getattr(dossier_source, attribut).valeur or ""
        )
        setattr(
            dossier,
            attribut,
            _corriger_champ(getattr(dossier_source, attribut), valeur),
        )

    for index, ligne in enumerate(dossier.lignes):
        ligne_source = dossier_source.lignes[index]
        for attribut in ("designation", "quantite", "prix_unitaire", "remise"):
            valeur = st.session_state.get(
                f"{cle}_ligne_{index}_{attribut}",
                getattr(ligne_source, attribut).valeur or "",
            )
            setattr(
                ligne,
                attribut,
                _corriger_champ(getattr(ligne_source, attribut), valeur),
            )

        article_id = st.session_state.get(f"{cle}_article_{index}")
        if article_id in ARTICLES_PAR_ID:
            article = ARTICLES_PAR_ID[article_id]
            ligne.designation = _corriger_champ(
                ligne_source.designation,
                article.designation,
            )
            ligne.designation.source = (
                "Association humaine au référentiel; source : "
                f"{ligne_source.designation.source or 'non disponible'}"
            )

    return dossier


def _meme_contenu(a: Facture, b: Facture) -> bool:
    return (
        a.id == b.id
        and a.client_id == b.client_id
        and a.lignes == b.lignes
        and a.total_ht == b.total_ht
        and a.total_taxe == b.total_taxe
        and a.total_ttc == b.total_ttc
        and a.facture_origine_id == b.facture_origine_id
    )


def _date_du_dossier(dossier: DossierExtrait) -> date | None:
    valeurs = normaliser_date(dossier.date.valeur)
    return date(*valeurs) if valeurs else None


def _changements_dossier(
    avant: DossierExtrait,
    apres: DossierExtrait,
) -> list[dict[str, str | None]]:
    changements = []

    def comparer(chemin: str, ancien: str | None, nouveau: str | None) -> None:
        if ancien != nouveau:
            changements.append(
                {"champ": chemin, "avant": ancien, "apres": nouveau}
            )

    comparer("client", avant.client.valeur, apres.client.valeur)
    for attribut, _ in FIELDS:
        comparer(
            attribut,
            getattr(avant, attribut).valeur,
            getattr(apres, attribut).valeur,
        )
    for index in range(max(len(avant.lignes), len(apres.lignes))):
        ancienne = avant.lignes[index] if index < len(avant.lignes) else None
        nouvelle = apres.lignes[index] if index < len(apres.lignes) else None
        for attribut in ("designation", "quantite", "prix_unitaire", "remise"):
            valeur_avant = (
                getattr(ancienne, attribut).valeur if ancienne is not None else None
            )
            valeur_apres = (
                getattr(nouvelle, attribut).valeur if nouvelle is not None else None
            )
            comparer(f"lignes[{index + 1}].{attribut}", valeur_avant, valeur_apres)
    livraison_avant = [
        {"designation": ligne.designation, "quantite": str(ligne.quantite)}
        for ligne in avant.livraison
    ]
    livraison_apres = [
        {"designation": ligne.designation, "quantite": str(ligne.quantite)}
        for ligne in apres.livraison
    ]
    if livraison_avant != livraison_apres:
        changements.append(
            {
                "champ": "livraison",
                "avant": json.dumps(livraison_avant, ensure_ascii=False),
                "apres": json.dumps(livraison_apres, ensure_ascii=False),
            }
        )
    return changements


def _enregistrer_revue_humaine(
    depot: DepotDocuments,
    cle: str,
    source_hash: str,
    facture_id: str,
    avant: DossierExtrait,
    apres: DossierExtrait,
) -> list[dict[str, str | None]]:
    changements = _changements_dossier(avant, apres)
    ancien_client_id = st.session_state.get(f"{cle}_client_id_original")
    nouveau_client_id = st.session_state.get(f"{cle}_client_id")
    if ancien_client_id != nouveau_client_id:
        changements.append(
            {
                "champ": "client_id",
                "avant": ancien_client_id,
                "apres": nouveau_client_id,
            }
        )
    articles_ids = [
        st.session_state.get(f"{cle}_article_{index}")
        for index in range(len(apres.lignes))
    ]
    for index, nouveau_id in enumerate(articles_ids):
        ancien_id = st.session_state.get(f"{cle}_article_{index}_original")
        if ancien_id != nouveau_id:
            changements.append(
                {
                    "champ": f"lignes[{index + 1}].article_id",
                    "avant": ancien_id,
                    "apres": nouveau_id,
                }
            )
        st.session_state[f"{cle}_article_{index}_original"] = nouveau_id
    depot.mettre_a_jour_dossier_source(
        source_hash,
        apres,
        client_id_revu=nouveau_client_id,
        articles_ids_revus=articles_ids,
    )
    if changements:
        journaliser(
            "CORRECTIONS_HUMAINES",
            facture_id,
            {"champs": changements},
        )
    st.session_state["dossier"] = apres.model_copy(deep=True)
    st.session_state[f"{cle}_client_id_original"] = nouveau_client_id
    return changements


with DepotDocuments() as depot_reprise:
    sources_enregistrees = depot_reprise.lister_sources()
if sources_enregistrees:
    sources_par_hash = {
        source_enregistree["source_hash"]: source_enregistree
        for source_enregistree in sources_enregistrees
    }
    st.sidebar.markdown("---")
    st.sidebar.caption("REPRISE LOCALE")
    source_a_reprendre = st.sidebar.selectbox(
        "Analyses enregistrées",
        options=["", *sources_par_hash],
        format_func=lambda source_hash: (
            "Choisir une analyse"
            if not source_hash
            else (
                f"{sources_par_hash[source_hash]['nom_fichier'] or 'Texte collé'} · "
                f"{source_hash[:10]}"
            )
        ),
        key="source_a_reprendre",
    )
    if st.sidebar.button(
        "Reprendre l'analyse", disabled=not source_a_reprendre, key="reprise_locale"
    ):
        archive = sources_par_hash[source_a_reprendre]
        source_reprise = SourceLue(
            texte=archive["texte"],
            hash=archive["source_hash"],
            nom_fichier=archive["nom_fichier"],
        )
        resultat_reprise = ResultatExtraction(
            dossier=archive["dossier"],
            mode="reprise locale",
            modele="SQLite",
            duree_s=0.0,
        )
        st.session_state["source"] = source_reprise
        st.session_state["resultat_extraction"] = resultat_reprise
        st.session_state["dossier"] = archive["dossier"].model_copy(deep=True)
        st.rerun()


st.markdown('<div class="section-label">Étape 1 · Source</div>', unsafe_allow_html=True)
st.header("Importer une pièce commerciale")
mode_source = st.radio(
    "Format de la source",
    ("Texte à coller", "Fichier PDF ou texte"),
    horizontal=True,
)

source_televersee = None
if mode_source == "Texte à coller":
    texte_source = st.text_area(
        "Message, devis ou commande",
        height=150,
        placeholder="Collez le texte commercial à traiter…",
        key="texte_source",
    )
else:
    source_televersee = st.file_uploader(
        "Choisir un fichier PDF, TXT ou MD",
        type=("pdf", "txt", "md"),
    )
    texte_source = ""

with st.expander("Réglages d'extraction"):
    utiliser_ollama = st.checkbox(
        "Essayer le modèle IA local via Ollama",
        value=True,
        help="Si Ollama n'est pas disponible, le mode dégradé est signalé et la saisie manuelle reste possible.",
    )
    modele = st.text_input("Modèle Ollama", value=MODELE_DEFAUT)

if st.button("Analyser la source", type="primary", key="analyser_source"):
    try:
        if mode_source == "Texte à coller":
            source = lire_texte(texte_source)
        else:
            if source_televersee is None:
                raise ExtractionError("Choisissez un fichier à analyser.")
            source = lire_televersement(
                source_televersee.name,
                source_televersee.getvalue(),
            )
        with st.spinner("Analyse de la source…"):
            if utiliser_ollama:
                resultat = extraire_avec_repli(
                    source,
                    ClientOllama(modele=modele.strip() or MODELE_DEFAUT),
                )
            else:
                resultat = extraire_degrade(
                    source,
                    raison="Extraction IA désactivée; saisie humaine requise.",
                )
        with DepotDocuments() as depot:
            try:
                archive_existante = depot.obtenir_source(source.hash)
            except ErreurDocument:
                archive_existante = None
            if archive_existante is None:
                depot.enregistrer_source(
                    source.hash,
                    source.nom_fichier,
                    source.texte,
                    resultat.dossier,
                )
                dossier_enregistre = resultat.dossier
                journaliser(
                    "SOURCE_IMPORTEE",
                    f"fact-{source.hash[:24]}",
                    {
                        "empreinte": source.hash,
                        "nom_fichier": source.nom_fichier,
                    },
                )
            else:
                dossier_enregistre = archive_existante["dossier"]
        st.session_state["source"] = source
        st.session_state["resultat_extraction"] = resultat
        st.session_state["dossier"] = dossier_enregistre.model_copy(deep=True)
    except (ExtractionError, ErreurDocument, OSError, ValueError) as erreur:
        st.error(f"Analyse impossible : {erreur}")

resultat = st.session_state.get("resultat_extraction")
dossier_source = st.session_state.get("dossier")
source = st.session_state.get("source")

if resultat and dossier_source and source:
    cle = _cle_source(source.hash)
    facture_id = f"fact-{source.hash[:24]}"
    with DepotDocuments() as depot:
        try:
            facture_enregistree = depot.obtenir(facture_id)
        except FactureIntrouvable:
            facture_enregistree = None
        try:
            archive_source = depot.obtenir_source(source.hash)
        except ErreurDocument:
            depot.enregistrer_source(
                source.hash,
                source.nom_fichier,
                source.texte,
                dossier_source,
            )
            archive_source = depot.obtenir_source(source.hash)
        if facture_enregistree:
            st.info(
                "Cette source a déjà un document local. La reprise conserve son "
                "identifiant et son historique pour éviter une seconde facture."
            )

        _initialiser_editeur(
            cle,
            dossier_source,
            facture_enregistree,
            archive_source,
        )
        st.markdown(
            '<div class="section-label">Étape 2 · Revue humaine</div>',
            unsafe_allow_html=True,
        )
        st.header("Vérifier et corriger")
        st.caption(
            f"Extraction : {resultat.mode} · {resultat.modele} · "
            f"{resultat.duree_s:.1f} s · source {source.nom_fichier or 'texte collé'}"
        )
        for avertissement in resultat.avertissements:
            st.warning(avertissement)
        for rejet in resultat.rejets:
            st.info(rejet)

        with st.expander("Afficher le texte source"):
            st.text(source.texte)

        verrouillee = bool(
            facture_enregistree
            and facture_enregistree.statut != Statut.BROUILLON
        )
        with st.form(f"{cle}_form_revue"):
            st.subheader("Client")
            client_initial = dossier_source.client
            if client_initial.source:
                st.caption(
                    f"Extrait : « {client_initial.source} » · "
                    f"confiance {client_initial.confiance:.0%}"
                )
            st.selectbox(
                "Associer et confirmer le client",
                options=[None, *CLIENTS_PAR_ID.keys()],
                format_func=lambda identifiant: (
                    "À associer / confirmer"
                    if identifiant is None
                    else CLIENTS_PAR_ID[identifiant].nom
                ),
                key=f"{cle}_client_id",
                disabled=verrouillee,
            )
            st.text_input(
                "Nom du client tel que lu dans la source",
                key=f"{cle}_client_nom",
                disabled=verrouillee or st.session_state.get(f"{cle}_client_id") is not None,
                help="Choisissez le client du référentiel pour confirmer son identité.",
            )

            colonnes = st.columns(2)
            for index, (attribut, libelle) in enumerate(FIELDS):
                champ = getattr(dossier_source, attribut)
                with colonnes[index % 2]:
                    st.text_input(
                        libelle,
                        key=f"{cle}_{attribut}",
                        disabled=verrouillee,
                    )
                    st.caption(
                        f"Source : {champ.source or 'non trouvée; renseigner sans inventer'}"
                        f" · confiance {champ.confiance:.0%}"
                    )

            st.subheader("Lignes de facture")
            if not dossier_source.lignes:
                st.info("Aucune ligne extraite : ajoutez une ligne puis saisissez ses valeurs.")
            for index, ligne in enumerate(dossier_source.lignes):
                with st.expander(f"Ligne {index + 1}", expanded=True):
                    options = [None, *ARTICLES_PAR_ID.keys()]
                    st.selectbox(
                        "Article du référentiel à associer",
                        options=options,
                        format_func=lambda identifiant: (
                            "À associer"
                            if identifiant is None
                            else (
                                f"{ARTICLES_PAR_ID[identifiant].designation} "
                                f"({ARTICLES_PAR_ID[identifiant].prix_reference} XOF)"
                            )
                        ),
                        key=f"{cle}_article_{index}",
                        disabled=verrouillee,
                    )
                    colonnes_ligne = st.columns(4)
                    for colonne, attribut, libelle in zip(
                        colonnes_ligne,
                        ("designation", "quantite", "prix_unitaire", "remise"),
                        ("Désignation", "Quantité", "Prix unitaire", "Remise (%)"),
                    ):
                        champ = getattr(ligne, attribut)
                        with colonne:
                            st.text_input(
                                libelle,
                                key=f"{cle}_ligne_{index}_{attribut}",
                                disabled=verrouillee,
                            )
                            st.caption(
                                f"{champ.source or 'saisie à vérifier'} · "
                                f"{champ.confiance:.0%}"
                            )
            with st.expander("Pièce de livraison facultative"):
                st.caption(
                    "Saisissez une ligne par article au format "
                    "désignation;quantité. Les quantités livrées sont comparées "
                    "aux quantités commandées."
                )
                st.text_area(
                    "Lignes effectivement livrées",
                    key=f"{cle}_livraison_source",
                    height=100,
                    disabled=verrouillee,
                )
            ajouter_ligne = st.form_submit_button(
                "Ajouter une ligne",
                disabled=verrouillee,
            )
            corrections_appliquees = st.form_submit_button(
                "Appliquer les corrections",
                disabled=verrouillee,
            )

        dossier = _dossier_edite(cle, dossier_source)
        erreur_livraison = None
        try:
            dossier.livraison = lire_lignes_livraison(
                st.session_state.get(f"{cle}_livraison_source", "")
            )
        except ExtractionError as erreur:
            erreur_livraison = str(erreur)
            st.error(f"Pièce de livraison invalide : {erreur_livraison}")

        if ajouter_ligne:
            if erreur_livraison:
                st.warning("Corrigez la pièce de livraison avant d'ajouter une ligne.")
                st.stop()
            dossier.lignes.append(LigneExtraite())
            try:
                _enregistrer_revue_humaine(
                    depot, cle, source.hash, facture_id, dossier_source, dossier
                )
                journaliser(
                    "LIGNE_AJOUTEE",
                    facture_id,
                    {"numero_ligne": len(dossier.lignes)},
                )
            except ErreurDocument as erreur:
                st.error(f"Enregistrement de la ligne impossible : {erreur}")
                st.stop()
            st.session_state["dossier"] = dossier
            st.rerun()
        if corrections_appliquees:
            if erreur_livraison:
                st.warning("Corrigez la pièce de livraison avant d'appliquer les corrections.")
                st.stop()
            try:
                _enregistrer_revue_humaine(
                    depot, cle, source.hash, facture_id, dossier_source, dossier
                )
                st.success("Corrections prises en compte; contrôles recalculés.")
            except ErreurDocument as erreur:
                st.error(f"Enregistrement des corrections impossible : {erreur}")

        anomalies = controler(
            dossier,
            CLIENTS,
            ARTICLES,
            historique=[
                dossier_historique
                for dossier_historique in depot.lister_dossiers_originaux()
                if dossier_historique.source_hash != source.hash
            ],
            seuil_prix=settings.price_anomaly_threshold,
            seuil_confiance=settings.confidence_threshold,
            taux_taxe_attendu=settings.tax_rate,
        )
        if erreur_livraison:
            anomalies.append(
                Anomalie(
                    code=CodeAnomalie.CHAMP_INVALIDE,
                    message=f"Pièce de livraison : {erreur_livraison}",
                )
            )

        client_id = st.session_state.get(f"{cle}_client_id")
        article_ids = [
            st.session_state.get(f"{cle}_article_{index}")
            for index in range(len(dossier.lignes))
        ]
        facture_proposee = None
        if client_id in CLIENTS_PAR_ID and all(
            article_id in ARTICLES_PAR_ID for article_id in article_ids
        ):
            try:
                facture_proposee, anomalies_calcul = calculer_facture(
                    dossier,
                    [ARTICLES_PAR_ID[article_id] for article_id in article_ids],
                    facture_id=facture_id,
                    client_id=client_id,
                    taux_taxe=settings.tax_rate,
                )
                anomalies.extend(anomalies_calcul)
            except ValueError as erreur:
                st.error(f"Calcul impossible : {erreur}")
        else:
            st.info("Associez un client et chaque ligne à un article pour calculer la facture.")

        st.subheader("Anomalies et revue humaine")
        if not anomalies:
            st.success("Aucune anomalie détectée par les contrôles exécutés.")
        for index, anomalie in enumerate(anomalies):
            st.warning(f"{anomalie.code.value} — {anomalie.message}")
            cle_anomalie = hashlib.sha256(
                f"{anomalie.code.value}|{anomalie.message}|{anomalie.ligne}".encode("utf-8")
            ).hexdigest()[:12]
            anomalies[index] = anomalie.model_copy(
                update={
                    "resolue": st.checkbox(
                        "Marquer comme traitée après vérification humaine",
                        value=anomalie.resolue,
                        key=f"{cle}_anomalie_{cle_anomalie}",
                        disabled=verrouillee,
                    )
                }
            )

        if facture_proposee:
            st.subheader("Calcul déterministe")
            metriques = st.columns(3)
            metriques[0].metric("Total HT", f"{facture_proposee.total_ht:,.0f} XOF")
            metriques[1].metric("Taxes", f"{facture_proposee.total_taxe:,.0f} XOF")
            metriques[2].metric("Total TTC", f"{facture_proposee.total_ttc:,.0f} XOF")

        if facture_enregistree:
            st.markdown(
                '<div class="section-label">Étape 3 · Cycle documentaire</div>',
                unsafe_allow_html=True,
            )
            st.subheader("État du document")
            statut_col, numero_col, version_col = st.columns(3)
            statut_col.metric("Statut", facture_enregistree.statut.value)
            numero_col.metric("Numéro", facture_enregistree.numero or "Brouillon")
            version_col.metric("Version", facture_enregistree.version)

        if facture_proposee and not verrouillee and not erreur_livraison:
            contenu_identique = (
                facture_enregistree is not None
                and _meme_contenu(facture_enregistree, facture_proposee)
            )
            if st.button(
                "Enregistrer le brouillon",
                key=f"{cle}_enregistrer",
                type="primary",
            ):
                try:
                    _enregistrer_revue_humaine(
                        depot, cle, source.hash, facture_id, dossier_source, dossier
                    )
                    if facture_enregistree is None:
                        facture_enregistree = depot.creer_brouillon(facture_proposee)
                    elif not contenu_identique:
                        facture_enregistree = depot.modifier_brouillon(
                            facture_proposee.model_copy(
                                update={"version": facture_enregistree.version}
                            ),
                            version_attendue=facture_enregistree.version,
                        )
                    journaliser(
                        "BROUILLON_ENREGISTRE",
                        facture_id,
                        {"version": facture_enregistree.version},
                    )
                    st.success("Brouillon enregistré dans SQLite.")
                except ErreurDocument as erreur:
                    st.error(f"Enregistrement impossible : {erreur}")

        if (
            facture_enregistree
            and facture_enregistree.statut == Statut.BROUILLON
            and facture_proposee
            and not erreur_livraison
            and _meme_contenu(facture_enregistree, facture_proposee)
        ):
            if st.button("Valider la facture", key=f"{cle}_valider"):
                try:
                    _enregistrer_revue_humaine(
                        depot, cle, source.hash, facture_id, dossier_source, dossier
                    )
                    facture_enregistree = depot.valider(
                        facture_id,
                        anomalies,
                        version_attendue=facture_enregistree.version,
                    )
                    journaliser(
                        "FACTURE_VALIDEE",
                        facture_id,
                        {
                            "numero": facture_enregistree.numero,
                            "version": facture_enregistree.version,
                        },
                    )
                    st.success(f"Facture validée : {facture_enregistree.numero}.")
                except ErreurDocument as erreur:
                    st.error(f"Validation impossible : {erreur}")

        if facture_enregistree and facture_enregistree.statut == Statut.VALIDEE:
            st.markdown(
                '<div class="section-label">Étape 4 · Émission simulée</div>',
                unsafe_allow_html=True,
            )
            st.subheader("Préparer le courriel")
            client_emission = CLIENTS_PAR_ID.get(facture_enregistree.client_id)
            if client_emission is None:
                st.error("Le client de cette facture n'existe plus dans le référentiel.")
            else:
                destinataire = st.text_input(
                    "Adresse courriel du destinataire",
                    value=client_emission.email or "",
                    key=f"{cle}_destinataire",
                )
                echeance_confirmee = st.checkbox(
                    "J'ai vérifié et confirmé la date d'échéance",
                    key=f"{cle}_echeance_confirmee",
                )
                date_initiale = _date_du_dossier(dossier) or date.today()
                echeance = st.date_input(
                    "Échéance à communiquer",
                    value=date_initiale,
                    disabled=not echeance_confirmee,
                    key=f"{cle}_echeance",
                )
                message = (
                    f"Bonjour {client_emission.nom}, votre facture "
                    f"{facture_enregistree.numero} d'un montant de "
                    f"{facture_enregistree.total_ttc} XOF est à régler au plus tard "
                    f"le {echeance.strftime('%d/%m/%Y')}. "
                    "Ceci est une notification de démonstration."
                )
                with st.expander("Aperçu du courriel"):
                    st.code(message, language=None)
                if st.button(
                    "Simuler l'envoi du courriel",
                    key=f"{cle}_emettre",
                    disabled=not echeance_confirmee,
                    type="primary",
                ):
                    try:
                        emission = CanauxSimules().emettre(
                            "courriel",
                            destinataire,
                            message,
                            sujet=f"Facture {facture_enregistree.numero}",
                        )
                        facture_enregistree = depot.emettre(
                            facture_id,
                            version_attendue=facture_enregistree.version,
                        )
                        journaliser(
                            "EMISSION_SIMULEE",
                            facture_id,
                            {
                                "canal": emission.canal,
                                "echeance": echeance.isoformat(),
                                "version": facture_enregistree.version,
                            },
                        )
                        st.success(
                            "Courriel simulé préparé; aucun message n'a été envoyé."
                        )
                    except (ValueError, ErreurDocument) as erreur:
                        st.error(f"Émission impossible : {erreur}")

        if facture_enregistree and facture_enregistree.statut == Statut.EMISE:
            st.markdown(
                '<div class="section-label">Suivi des règlements</div>',
                unsafe_allow_html=True,
            )
            st.subheader("Règlements simulés")
            reglements = depot.lister_reglements(facture_id)
            solde = depot.solde_restant(facture_id)
            solde_col, regle_col = st.columns(2)
            solde_col.metric("Solde restant", f"{solde:,.0f} XOF")
            regle_col.metric("Règlements enregistrés", len(reglements))
            progression = (
                Decimal("1") - solde / facture_enregistree.total_ttc
                if facture_enregistree.total_ttc > 0
                else Decimal("1")
            )
            st.progress(
                min(1.0, max(0.0, float(progression))),
                text="Progression des règlements",
            )
            if reglements:
                st.dataframe(
                    [
                        {
                            "Référence": paiement.reference,
                            "Montant (XOF)": f"{paiement.montant:,.0f}",
                            "Mode": paiement.mode,
                            "Date UTC": paiement.horodatage,
                        }
                        for paiement in reglements
                    ],
                    hide_index=True,
                    use_container_width=True,
                )
            if solde > 0:
                with st.form(f"{cle}_form_reglement"):
                    reference_reglement = st.text_input(
                        "Référence de règlement simulée",
                        key=f"{cle}_reference_reglement",
                    )
                    montant_reglement = st.text_input(
                        "Montant reçu (XOF)",
                        key=f"{cle}_montant_reglement",
                        placeholder="Ex. 10 000",
                    )
                    mode_reglement = st.selectbox(
                        "Mode",
                        ("Mobile Money simulé", "Virement simulé", "Espèces simulées"),
                        key=f"{cle}_mode_reglement",
                    )
                    confirmer_reglement = st.form_submit_button(
                        "Enregistrer le règlement simulé"
                    )
                if confirmer_reglement:
                    try:
                        montant = en_decimal(montant_reglement)
                        if montant is None:
                            raise ValueError("Saisissez un montant valide.")
                        paiement_existant = any(
                            paiement.reference == reference_reglement.strip()
                            for paiement in reglements
                        )
                        paiement = depot.enregistrer_reglement(
                            facture_id,
                            reference_reglement,
                            montant,
                            mode_reglement,
                        )
                        if not paiement_existant:
                            journaliser(
                                "REGLEMENT_SIMULE",
                                facture_id,
                                {
                                    "reference": paiement.reference,
                                    "montant": str(paiement.montant),
                                    "mode": paiement.mode,
                                },
                            )
                        st.success("Règlement simulé enregistré localement.")
                        st.rerun()
                    except (ValueError, ErreurDocument, ConflitReglement) as erreur:
                        st.error(f"Règlement impossible : {erreur}")
            else:
                st.success("La facture est entièrement réglée.")

        avoir_courant = None
        if facture_enregistree and facture_enregistree.statut in (
            Statut.VALIDEE,
            Statut.EMISE,
        ):
            st.markdown(
                '<div class="section-label">Correction après validation</div>',
                unsafe_allow_html=True,
            )
            st.caption(
                "Une facture validée est immuable. Une correction passe par un "
                "avoir total lié, puis par l'import d'une nouvelle pièce si nécessaire."
            )
            identifiant_avoir = f"avoir-{facture_id}"
            try:
                avoir_courant = depot.obtenir(identifiant_avoir)
            except FactureIntrouvable:
                avoir_courant = None
            if avoir_courant:
                st.info(f"Avoir lié créé : {avoir_courant.numero}.")
            elif st.button(
                "Créer un avoir total lié",
                key=f"{cle}_creer_avoir",
            ):
                try:
                    avoir_courant = depot.creer_avoir_total(
                        identifiant_avoir,
                        facture_id,
                        version_attendue=facture_enregistree.version,
                    )
                    journaliser(
                        "AVOIR_TOTAL_CREE",
                        facture_id,
                        {
                            "avoir_id": avoir_courant.id,
                            "numero": avoir_courant.numero,
                            "version": avoir_courant.version,
                        },
                    )
                    st.success(f"Avoir créé : {avoir_courant.numero}.")
                except ErreurDocument as erreur:
                    st.error(f"Création de l'avoir impossible : {erreur}")

        if facture_enregistree:
            date_document = _date_du_dossier(dossier)
            client_facture = CLIENTS_PAR_ID.get(facture_enregistree.client_id)
            if date_document is None:
                st.info("Renseignez une date valide pour exporter l'aperçu PDF.")
            elif client_facture is not None:
                pdf = generer_pdf(
                    facture_enregistree,
                    client_facture,
                    InformationsVendeur(nom="Entreprise de démonstration BWAI"),
                    date_document=date_document,
                    conditions_paiement=dossier.conditions_paiement.valeur,
                )
                st.download_button(
                    "Télécharger l'aperçu de facture (PDF)",
                    data=pdf,
                    file_name=f"{facture_enregistree.numero or facture_id}.pdf",
                    mime="application/pdf",
                    key=f"{cle}_telecharger_pdf",
                )
            if (
                avoir_courant
                and date_document is not None
                and client_facture is not None
            ):
                pdf_avoir = generer_pdf(
                    avoir_courant,
                    client_facture,
                    InformationsVendeur(nom="Entreprise de démonstration BWAI"),
                    date_document=date_document,
                    conditions_paiement=dossier.conditions_paiement.valeur,
                )
                st.download_button(
                    "Télécharger l'aperçu de l'avoir (PDF)",
                    data=pdf_avoir,
                    file_name=f"{avoir_courant.numero}.pdf",
                    mime="application/pdf",
                    key=f"{cle}_telecharger_avoir",
                )

            with st.expander("Historique des opérations", expanded=False):
                with JournalAudit() as journal:
                    evenements = journal.lister(facture_id)
                if evenements:
                    for evenement in reversed(evenements):
                        with st.container(border=True):
                            date_col, action_col, acteur_col = st.columns([2, 3, 2])
                            date_col.caption(evenement["horodatage"])
                            action_col.markdown(f"**{evenement['action']}**")
                            acteur_col.caption(evenement["acteur"])
                            st.caption(f"Détails : {evenement['details']}")
                else:
                    st.info("Aucune opération enregistrée pour ce document.")

        st.caption(
            "Prototype pédagogique · numéros SIM-* et émissions simulées · "
            "PDF non normalisé DGI."
        )
elif not resultat:
    st.info("Collez un texte ou choisissez un fichier, puis lancez l'analyse.")
