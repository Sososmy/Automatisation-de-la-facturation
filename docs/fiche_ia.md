# Fiche IA : modèle et version, tâche, données et séparation des jeux, méthode d'évaluation, erreurs, seuils de revue humaine, limites

## Jeu d'évaluation

`data/eval/exemple.jsonl` contient six cas fictifs annotés. Chaque ligne JSONL
comprend un identifiant, le texte source et les champs attendus. Les cas couvrent
notamment une facture avec remise, des informations absentes, plusieurs lignes
et une opération exonérée.

Ce petit jeu sert aux tests de régression et ne suffit pas à démontrer la
performance générale d'un modèle. Toute comparaison de modèles doit préciser la
taille du jeu et compléter ces exemples par un ensemble de test distinct.
