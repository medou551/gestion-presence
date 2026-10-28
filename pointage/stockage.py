"""Stockage des photos : chaque fichier est chiffré sur le disque.

Même si quelqu'un copie le dossier `media/`, il ne peut pas voir les photos sans la clé.
Les photos ne sont jamais servies directement : elles passent par une vue qui vérifie les droits.
"""
from django.core.files.base import ContentFile
from django.core.files.storage import FileSystemStorage

from . import chiffrement


class StockageChiffre(FileSystemStorage):
    def __init__(self, **kwargs):
        kwargs.setdefault("base_url", None)
        super().__init__(**kwargs)

    def _save(self, name, content):
        content.seek(0) if hasattr(content, "seek") else None
        donnees = content.read()
        if not chiffrement.est_chiffre(donnees):
            donnees = chiffrement.chiffrer(donnees)
        return super()._save(name, ContentFile(donnees))

    def _open(self, name, mode="rb"):
        with super()._open(name, "rb") as f:
            brut = f.read()
        return ContentFile(chiffrement.dechiffrer(brut), name=name)

    def lire(self, name):
        """Contenu déchiffré du fichier."""
        with self.open(name) as f:
            return f.read()

    def url(self, name):
        raise ValueError("Les photos chiffrées sont servies par une vue protégée, pas par URL directe.")


_stockage = None


def stockage_chiffre():
    """Utilisé par les champs FileField (fonction pour que les migrations restent simples)."""
    global _stockage
    if _stockage is None:
        _stockage = StockageChiffre()
    return _stockage
