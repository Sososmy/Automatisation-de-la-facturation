import pytest

from src.channels import CanauxSimules


def test_emission_simulee_sans_envoi_externe():
    canaux = CanauxSimules()
    resultat = canaux.emettre(
        "courriel",
        "client@example.com",
        "Votre facture est prête.",
        sujet="Facture",
    )
    assert resultat.simule is True
    assert resultat.canal == "courriel"
    assert resultat.destinataire == "client@example.com"


@pytest.mark.parametrize(
    ("canal", "destinataire"),
    [
        ("courriel", "adresse-invalide"),
        ("sms", ""),
        ("telegram", "destinataire"),
    ],
)
def test_canaux_invalides_refuses(canal, destinataire):
    with pytest.raises(ValueError):
        CanauxSimules().emettre(canal, destinataire, "Contenu")
