# Rapport du projet — BWAI 2026

**Cas pratique 2 : automatisation de la facturation**

## 1. Besoin et périmètre

Les devis, commandes, justificatifs de livraison et messages commerciaux sont
parfois dispersés et ressaisis dans Excel ou sur papier. Cette pratique expose
les PME à des doublons, omissions, erreurs de prix, écarts de livraison et
manque de traçabilité.

Le prototype transforme une source locale — texte, TXT, MD ou PDF contenant du
texte — en dossier de facture vérifiable. Il couvre :

1. l'import et l'extraction des champs ;
2. la citation de chaque valeur proposée dans la source ;
3. la correction et la confirmation humaines ;
4. les contrôles des référentiels et des pièces ;
5. le calcul déterministe en `Decimal` ;
6. le brouillon, la validation, l'émission simulée et les avoirs ;
7. les règlements fictifs et le journal d'audit.

Les données, comptes, numéros `SIM-*`, règlements, canaux, PDF et paiements sont
fictifs. Le PDF porte la mention « non normalisé DGI ». Aucun envoi réseau,
e-MECEF, courriel, SMS ou paiement réel n'est effectué.

## 2. Parcours métier et architecture

Le flux est :
`source locale -> proposition d'extraction -> revue humaine -> contrôles ->
moteur déterministe -> BROUILLON -> validation -> émission simulée`

**Interface et persistance.** Streamlit présente les champs, les citations, les
confiances, les anomalies et les actions. SQLite conserve les sources, factures,
brouillons, avoirs, règlements, séquences et événements. L'application est
locale, utilise un compte protégé par `APP_PASSWORD` et peut être reprise après
interruption.

**Frontière IA.** Ollama local peut suggérer les champs avec
`qwen2.5:3b`, température 0 et graine 42. Le modèle n'effectue aucun calcul.
Chaque proposition doit être retrouvée dans la source ; sinon elle est rejetée.
Les données absentes restent `null`. Sans modèle, le mode dégradé conserve une
saisie humaine sans prétendre à une extraction complète.

**Contrôles métier.** `src/controls.py` signale clients inconnus, doublons,
prix inhabituels, écarts de taxe et de livraison. Les anomalies bloquantes
empêchent la validation. `src/engine.py` applique remises, taxe configurable,
arrondi XOF `ROUND_HALF_UP` et comparaison des totaux déclarés.

**Protection des opérations.** Les transactions SQLite utilisent
`BEGIN IMMEDIATE`, une version optimiste et des contraintes d'unicité. Une
facture validée ou émise reste inchangée ; toute correction passe par un avoir
lié puis, si nécessaire, une nouvelle facture. Les règlements sont idempotents
par référence et ne peuvent dépasser le solde.

**Audit.** `src/audit.py` ajoute des événements pour imports, corrections,
validations, émissions et règlements. Chaque événement référence l'empreinte
SHA-256 précédente ; la chaîne peut être vérifiée.

## 3. Contrôles, protocole de tests et résultats

### Validation du prototype

Au 26 novembre 2026, la suite locale a donné :

- **156 tests réussis** sur 156 ;
- **6 scénarios reproductibles** exécutés ;
- **0 appel IA** requis par les scénarios déterministes.

Résultats des scénarios :

| Scénario | Résultat attendu | Preuve obtenue |
|---|---|---|
| Nominal | Facture calculée, validée et émise | `EMISE`, TTC fictif 15 340 |
| Doublon | Source déjà présente bloquée | anomalie `DOUBLON` |
| Écart de montant | Écart bloquant | `BLOQUEE`, `ECART_MONTANT` |
| Livraison partielle | Quantité livrée contrôlée | `BLOQUEE`, `ECART_LIVRAISON` |
| Avoir | Correction après émission | avoir total lié, `AVOIR` |
| Reprise | Reprise sans doublon | `REPRISE`, brouillon conservé |

Les commandes de reproduction sont fournies dans le `README.md`. Elles
initialisent les données fictives puis relancent les tests sans secret ni
connexion externe.

### Résultats métier de référence

Le parcours de référence est la ressaisie manuelle avec recalcul comptable.
Dans le jeu pédagogique fourni, il n'a pas été possible de mesurer en situation
réelle le gain de temps ou le taux d'erreur d'utilisateurs humains. Les preuves
actuelles portent donc sur la fidélité des règles : 156 tests, six transitions
et quatre classes d'anomalies bloquantes couvrent les parcours principaux.
Une mesure comparative devra être conduite avec des opérateurs, des documents
réels anonymisés et un chronométrage identique.

### Résultats de l'IA

Une mesure exploratoire locale a été effectuée le 25 novembre 2026 sur
`qwen2.5:3b`, avec 30 secondes maximum par appel et douze cas synthétiques :

| Mesure | Mode dégradé | Ollama `qwen2.5:3b` |
|---|---:|---:|
| Exactitude tous champs | 0,442 | 0,681 |
| Exactitude champs critiques | 0,000 | 0,707 |
| Omissions | 0,558 | 0,310 |
| Erreurs de valeur | 0,000 | 0,009 |
| Inventions | 0,000 | 0,029 |
| Rappel des lignes | 0,000 | 0,688 |
| Invention citée malgré tout dans la source | 0 | 1 cas |
| Latence moyenne / p95 | immédiate | 26,25 s / 32,26 s |

La mesure améliore donc de 0,239 point l'exactitude globale sur ce petit jeu
synthétique. Elle ne constitue ni un benchmark ni une certification sur des
documents réels. Une valeur de client a été inventée à partir d'une salutation,
même si sa citation était présente dans le texte. Les tests sont séparés en
jeux de développement (cas 1 à 6) et de test tenu à l'écart (cas 7 à 9).
Cette mesure précède les derniers ajustements du prompt et les garde-fous
sémantiques : elle ne représente pas les performances de la version actuelle.

## 4. Sécurité, limites et suite

### Sécurité et maîtrise

- la valeur totale de l'étiquette de confiance reste informative : toute
  extraction est modifiable ;
- le seuil de revue est fixé à 0,80 ; une valeur sous ce seuil est signalée ;
- les clients, prix, livraisons et doublons restent soumis à des contrôles ;
- les anomalies non résolues bloquent la validation ;
- les documents validés sont immuables ;
- les mots de passe ne sont ni inclus ni persistés dans le dépôt ;
- la base locale peut contenir des données sensibles et doit être protégée,
  sauvegardée et restaurée sous contrôle.

### Limites

Le prototype ne prend pas en charge les PDF scannés, les photos ou l'OCR.
Il n'est pas une solution de conformité e-MECEF/DGI, ne chiffre pas la base au
repos, n'offre pas de rôles avancés ni de sauvegarde automatisée et ne doit pas
être exposé sur Internet. Les jeux sont petits et synthétiques ; aucun document
réel anonymisé n'a été fourni. Par conséquent, les métriques ne démontrent pas
la précision générale ni la rentabilité du déploiement.

### Coûts estimatifs

Ollama est local : aucun coût par appel à un fournisseur externe n'est ajouté.
Le coût principal est l'achat ou le temps d'utilisation du matériel, l'électricité,
la maintenance et l'administration. La mesure locale a pris environ 26 secondes
en moyenne par cas, sous les conditions CPU disponibles. Une expérimentation
réelle doit budgéter ces ressources, un poste opérateur, la maintenance du
modèle, les sauvegardes et les validations comptables.

### Étapes d'expérimentation

1. recenser et anonymiser des devis, commandes, livraisons et factures réels ;
2. faire annoter et relire les champs attendus par des professionnels ;
3. conserver séparément les jeux de développement, de test et de démonstration ;
4. chronométrer la méthode manuelle et les utilisateurs du prototype ;
5. mesurer erreurs, omissions, inventions, reprise humaine et temps de traitement ;
6. réaliser une revue de sécurité, une gestion des rôles et des sauvegardes ;
7. obtenir une validation juridique, fiscale et comptable avant toute émission réelle.
