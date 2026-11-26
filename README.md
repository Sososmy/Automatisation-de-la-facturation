# BWAI 2026 — Automatisation de la facturation

Prototype local du **cas pratique 2 du TDR BWAI 2026** : transformer un
message commercial ou un devis en brouillon de facture vérifiable, puis suivre
sa revue, sa validation, son émission et ses règlements simulés.

> **Prototype pédagogique uniquement.** Les numéros `SIM-*`, les règlements,
> les canaux et le PDF sont simulés. Le PDF n'est pas une facture normalisée
> DGI et aucune connexion e-MECEF, aucun courriel, SMS ou paiement réel n'est
> effectué.

## Parcours couvert

1. Importer localement un texte ou un fichier PDF contenant du texte, TXT ou MD.
   Les PDF scannés et les images ne sont pas pris en charge (pas d'OCR).
2. Extraire ou saisir client, référence, date, conditions et lignes. Chaque
   valeur proposée est accompagnée de son extrait source et d'une confiance.
   Une donnée absente n'est pas inventée. Une personne peut corriger et
   confirmer les valeurs.
3. Associer client et articles aux référentiels JSON, signaler les anomalies,
   doublons et écarts de prix, puis comparer les quantités commandées et
   livrées. Pour saisir une pièce de livraison, entrer une ligne
   `désignation;quantité` dans le panneau facultatif.
4. Recalculer les remises, taxes et totaux de manière déterministe avec
   `Decimal`, signaler les écarts et bloquer la validation tant qu'une anomalie
   bloquante n'a pas été traitée.
5. Enregistrer et reprendre le brouillon localement, attribuer un numéro
   interne à la validation humaine, préparer une émission simulée, enregistrer
   des règlements fictifs et exporter un aperçu PDF.
6. Consulter le journal d'audit append-only, chaîné par empreintes SHA-256.
   Les corrections humaines y sont enregistrées champ par champ.

Le parcours d'émission proposé est le courriel simulé. Le suivi des règlements
accepte des références et montants fictifs (Mobile Money, virement ou espèces);
les références répétées sont idempotentes et un paiement supérieur au solde
est refusé.

## Prérequis et installation

- Python 3.11 ou supérieur.
- Ollama local est facultatif. En son absence, le mode dégradé et la saisie
  humaine restent disponibles.
- PowerShell sous Windows :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

Le modèle par défaut est `qwen2.5:3b`. Pour l'utiliser avec Ollama, démarrez
Ollama et téléchargez-le une fois :

```powershell
ollama pull qwen2.5:3b
```

L'extraction est exécutée par le service Ollama local. Les calculs, les
rapprochements, la validation et la génération PDF sont effectués par le code
Python, sans envoi à un fournisseur externe.

## Configuration et lancement

Définir un mot de passe est obligatoire : l'application refuse de s'ouvrir
sans `APP_PASSWORD`. Le nom de compte local est `admin` par défaut et peut être
modifié avec `APP_USER`. Le mot de passe n'est ni fourni ni stocké dans le
dépôt. Le compte de test est donc `admin` (ou la valeur définie par
`APP_USER`) avec le mot de passe saisi au démarrage ; communiquez ce secret au
jury séparément, jamais dans le dépôt.

```powershell
$env:APP_USER = "admin"
$securePassword = Read-Host "Choisir le mot de passe local" -AsSecureString
$env:APP_PASSWORD = [System.Net.NetworkCredential]::new("", $securePassword).Password
streamlit run src/app.py
```

Paramètres disponibles (variables d'environnement ou fichier `.env`) :

| Paramètre | Valeur par défaut | Rôle |
|---|---:|---|
| `DATABASE_URL` | `sqlite:///./data/app.db` | Base SQLite locale des sources, factures et règlements |
| `TAX_RATE` | `0.18` | Taux de taxe utilisé par le moteur |
| `CONFIDENCE_THRESHOLD` | `0.80` | Seuil de signalement pour revue humaine |
| `PRICE_ANOMALY_THRESHOLD` | `0.30` | Écart relatif au prix de référence |
| `APP_USER` | `admin` | Nom du compte local |
| `APP_PASSWORD` | aucune | Mot de passe obligatoire, à garder hors du dépôt |

`.env.example` liste les noms de variables. Copiez-le en `.env` si souhaité,
puis renseignez un mot de passe sûr avant de démarrer. Ne commitez jamais `.env`
ni de données de clients. Les sources saisies et téléversées sont conservées
dans la base locale pour permettre une reprise ; protégez et sauvegardez ce
fichier comme une donnée métier sensible.

### Déploiement Docker local

```powershell
$securePassword = Read-Host "Choisir le mot de passe local" -AsSecureString
$env:APP_PASSWORD = [System.Net.NetworkCredential]::new("", $securePassword).Password
docker compose up --build -d
```

Le port est publié uniquement sur `127.0.0.1:8501`. Le volume Docker
`facturation-data` conserve la base. N'exposez pas ce prototype sur Internet :
le compte unique et le stockage SQLite ne constituent pas une sécurité de
production.

## Tests et démonstrations reproductibles

```powershell
python -m pytest -q
python -m scripts.run_scenarios
```

Les six scénarios de `data/scenarios/` sont déterministes, utilisent des données
fictives et n'appellent pas le modèle : cas nominal, doublon, écart de montant,
livraison partielle, avoir après émission et reprise après interruption.
L'évaluation du mode dégradé peut être relancée avec :

```powershell
python -m scripts.evaluate_extraction --mode degrade
```

Évaluer Ollama sur le jeu de développement ou de test :

```powershell
python -m scripts.evaluate_extraction --mode ollama --model qwen2.5:3b --dataset data/eval/bwai2026_developpement.jsonl
python -m scripts.evaluate_extraction --mode ollama --model qwen2.5:3b --dataset data/eval/bwai2026_test.jsonl
```

Les documents de test fictifs restent séparés de ceux de développement.
N'évaluez pas de documents contenant des données personnelles non anonymisées.

Pour repartir d'une base locale vide, après avoir vérifié `DATABASE_URL` :

```powershell
python -m scripts.reset_data --confirm
```

Cette opération efface de façon irréversible les factures, sources, règlements,
séquences et événements de la base ciblée. Elle est réservée aux démonstrations
locales.

## Architecture

- `src/extraction.py` : lecture, extraction Ollama optionnelle, validation des
  citations dans la source et mode dégradé.
- `src/controls.py` : rapprochements clients/articles, doublons, prix, confiance,
  écarts de livraison et anomalies bloquantes.
- `src/engine.py` : calcul déterministe en `Decimal`, taxes paramétrables,
  arrondi XOF et comparaison des totaux déclarés.
- `src/documents.py` : sources et dossiers de revue persistés, brouillons,
  transitions versionnées, numérotation, avoirs et règlements simulés SQLite.
- `src/audit.py` : journal transactionnel append-only, chaîne SHA-256 et
  vérification d'intégrité.
- `src/pdf.py`, `src/channels.py`, `src/app.py` : aperçu PDF non normalisé,
  canaux sans envoi externe et interface Streamlit.
- `data/referentiels/` : référentiels fictifs clients, articles et calcul.
- `data/eval/` : jeux synthétiques annotés et séparés.
- `data/scenarios/` : cas de démonstration reproductibles.
- `docs/` : architecture, fiche IA, licences et rapport de hackathon.

## Limites et suite

Les jeux d'évaluation sont petits et synthétiques ; ils ne démontrent pas la
fiabilité sur des factures réelles. Toute extraction et toute anomalie exigent
une revue humaine. Les photos, l'OCR, les accès multi-utilisateurs, le chiffrement
au repos, les sauvegardes automatisées et la conformité e-MECEF/DGI ne sont pas
implémentés ni certifiés. Une expérimentation réelle nécessiterait des données
anonymisées validées par des professionnels, une revue de sécurité et des
essais de conformité avant tout déploiement.

Voir le [rapport du projet](docs/rapport_hackathon.md),
la [fiche IA](docs/fiche_ia.md), l'[architecture](docs/architecture.md) et les
[licences](docs/licences.md).
