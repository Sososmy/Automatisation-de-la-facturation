# Facturation automatisée – BWAI 2026 (Cas 2)
Source commerciale -> projet de facture vérifiable -> validation humaine -> émission simulée. Données fictives.

Équipe : <noms> · Version : tag `v1.0`, commit `<empreinte>`

## Installation
```bash
python -m venv .venv && source .venv/bin/activate
make install
cp .env.example .env
```
## Lancement
```bash
make reset && make run
```
Comptes de test : `<utilisateur>` / `<mot de passe>`

## Scénarios et tests
```bash
make scenarios
make test
```
## Documentation
`docs/architecture.md` · `docs/fiche_ia.md` · `docs/licences.md` · rapport PDF 3-5 pages · vidéo : <lien>

## Limites et suite
<à compléter>
