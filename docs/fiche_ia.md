# Fiche IA

## Modèle et version

- **Modèle :** `qwen2.5:3b`
- **Exécution :** Ollama local, sans fournisseur externe
- **Options :** température `0`, graine `42`, contexte `2048`, prédiction `512`
- **Repli :** mode dégradé déterministe avec saisie humaine

## Tâche

Extraire, à partir d'un message commercial ou d'un PDF textuel, les identifiants,
client, date, conditions de paiement, lignes, quantités, prix unitaires,
remises, totaux et taux. L'IA ne calcule pas la facture : elle propose des
champs que le code vérifie dans la source. Une donnée absente est conservée à
`null`, une proposition non retrouvée est rejetée et chaque valeur est
modifiable par l'utilisateur.

## Données et séparation des jeux

`data/eval/exemple.jsonl` contient douze cas synthétiques annotés utilisés pour
la régression. Les jeux BWAI 2026 sont explicitement séparés :

- `data/eval/bwai2026_developpement.jsonl` : exemples 1 à 6 (développement).
- `data/eval/bwai2026_test.jsonl` : exemples 7 à 9 (test tenu à l'écart).

L'exemple portant sur un avoir avec quantité négative est exclu du score, car
ce cas n'est pas représenté par le schéma d'extraction actuel. Les jeux restent
fictifs et petits ; ils ne remplacent pas des documents métier réels anonymisés
et ne suffisent pas à fixer des critères de validation généraux.

## Futur jeu de test réel

Aucun document métier réel anonymisé n'a été fourni; aucun score sur des
données métier réelles ne peut donc être calculé. Les fichiers de
`data/scenarios/` sont actuellement des gabarits vides, pas des exemples
évaluables.

Pour constituer le jeu, anonymiser les documents avant leur ajout et vérifier
manuellement chaque annotation de référence. Une ligne JSONL doit contenir un
identifiant, le texte anonymisé et les champs attendus au format de
`data/eval/exemple.jsonl`; une information absente doit rester `null`. Conserver
les documents de test réels séparés du jeu de régression synthétique et ne pas
les utiliser pour ajuster les prompts ou les règles avant la mesure.

Une fois ce fichier créé, le mesurer sans modifier le jeu avec :

```powershell
python -m scripts.evaluate_extraction --dataset data/eval/test_reel_anonymise.jsonl --mode ollama --model qwen2.5:3b
```

Le rapport ne sera représentatif que du corpus fourni; un petit échantillon ne
permettra pas à lui seul de certifier la fiabilité générale.

## Méthode d'évaluation

Commande reproductible, sans réseau ni modèle :

```powershell
python -m scripts.evaluate_extraction --mode degrade
```

Sur les douze cas, le mode dégradé obtient une exactitude de `0.442`, une
exactitude sur les champs critiques (client, quantité, prix unitaire) de `0.0`,
un taux d'omission de `0.558`, aucune invention et un rappel des lignes de
`0.0`. C'est une baseline volontairement limitée : ce mode ne cherche pas à
extraire le client ni les lignes. Ces scores ne mesurent pas Ollama. Le rappel
des lignes, ici, est calculé par rapport aux lignes annotées attendues.

Pour évaluer explicitement le modèle Ollama local configuré :

```powershell
python -m scripts.evaluate_extraction --mode ollama --model qwen2.5:3b
```

Le rapport JSON comprend les métriques agrégées et les erreurs par champ ; ajoutez
`--output <chemin>` pour le sauvegarder. La commande Ollama envoie les textes du
jeu au service local; ne lui fournissez pas de documents contenant des données
personnelles non anonymisées.

## Résultats exploratoires IA

Mesure du 25 novembre 2026 sur `qwen2.5:3b`, avec un délai de 30 secondes par
appel et les douze exemples synthétiques :

| Mesure | Résultat |
|---|---:|
| Erreurs d'extraction | 2 |
| Exactitude tous champs | 0.681 |
| Exactitude champs critiques | 0.707 |
| Omissions | 0.310 |
| Erreurs de valeur | 0.009 |
| Inventions | 0.029 (1 cas) |
| Rappel des lignes | 0.688 |
| Latence moyenne / p95 | 26.25 s / 32.26 s |

L'évaluation assimile « 7 jours » et « sous 7 jours » comme une même durée de
paiement ; cette correction sémantique fait passer l'exactitude mesurée de
`0.673` à `0.681`. Une valeur de client inventée à partir d'une salutation a
également été observée, même si sa citation existe dans la source.

Ces résultats sont exploratoires, non représentatifs et confirment que la revue
humaine demeure obligatoire ; ils ne justifient pas une validation automatique.
Cette mesure précède les derniers ajustements du prompt et les garde-fous
sémantiques : elle ne représente pas les performances de la version actuelle.

## Erreurs observées

- omissions de désignations, quantités ou prix ;
- invention occasionnelle d'un client à partir d'une salutation ;
- faible rappel des lignes sur les cas synthétiques ;
- confusion possible des dates, identifiants ou montants ;
- absence de prise en charge d'un OCR ou d'un PDF scanné.

Les erreurs de valeur sont distinguées des omissions, inventions et erreurs
liées aux lignes dans le rapport JSON.

## Seuils de revue humaine

- seuil de signalement de la confiance : `0.80` ;
- mode dégradé : confiance volontairement basse ;
- client inconnu, doublon, prix inhabituel ou livraison incohérente : revue ;
- anomalie bloquante : validation impossible jusqu'à résolution ;
- extrait introuvable : proposition supprimée ;
- toute facture validée reste inchangée ; une correction passe par un avoir.

## Résultats métier distincts

Les tests métier sont séparés des résultats IA : `python -m pytest -q` a donné
156 tests réussis et `python -m scripts.run_scenarios` a validé six scénarios
dont le nominal, les doublons, les écarts, la livraison, l'avoir et la reprise.
Ces résultats démontrent les contrôles déterministes, pas la précision du
modèle sur des documents réels.

## Limites

Pas de données métier réelles anonymisées, de jeu public représentatif ni de
mesure comparative avec des opérateurs humains. Pas de certification comptable,
fiscale ou e-MECEF/DGI. Pas d'OCR, de chiffrement au repos, de rôles multiples
ou de sauvegarde automatisée dans cette version. Toute utilisation réelle
nécessite une anonymisation, une validation professionnelle, une revue de
sécurité et une expérimentation sur corpus réel.
