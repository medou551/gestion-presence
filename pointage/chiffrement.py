"""Chiffrement des données sensibles (photos, signatures du visage, sauvegardes).

Chiffrement authentifié construit uniquement avec la bibliothèque standard de Python
(aucune dépendance compilée, compatible avec toutes les versions récentes de Python) :

- deux clés distinctes sont dérivées de CLE_CHIFFREMENT (chiffrement / authentification) ;
- chiffrement : flot pseudo-aléatoire HMAC-SHA256 en mode compteur, avec un nonce aléatoire
  de 16 octets différent pour chaque fichier ;
- authentification : HMAC-SHA256 sur l'en-tête, le nonce et le texte chiffré
  (« encrypt-then-MAC ») : toute modification du fichier est détectée.

Format : b"GPE1" + nonce (16) + texte chiffré + étiquette (32).
"""
import hashlib
import hmac
import json
import secrets
from base64 import urlsafe_b64decode

from django.conf import settings

ENTETE = b"GPE1"
TAILLE_NONCE = 16
TAILLE_TAG = 32


class ErreurChiffrement(Exception):
    pass


_cles_cache = {}


def _cles():
    brute = settings.CLE_CHIFFREMENT
    if brute not in _cles_cache:
        try:
            cle = urlsafe_b64decode(brute.encode() + b"=" * (-len(brute) % 4))
        except Exception as exc:
            raise ErreurChiffrement("CLE_CHIFFREMENT invalide dans le fichier .env") from exc
        if len(cle) < 32:
            raise ErreurChiffrement("CLE_CHIFFREMENT doit faire au moins 32 octets")
        _cles_cache.clear()
        _cles_cache[brute] = (
            hmac.new(cle, b"gestion-presence/chiffrement", hashlib.sha256).digest(),
            hmac.new(cle, b"gestion-presence/authentification", hashlib.sha256).digest(),
        )
    return _cles_cache[brute]


def _flot(cle, nonce, taille):
    blocs = []
    for compteur in range((taille + 31) // 32):
        blocs.append(hmac.new(cle, nonce + compteur.to_bytes(8, "big"), hashlib.sha256).digest())
    return b"".join(blocs)[:taille]


def _xor(a, b):
    return (int.from_bytes(a, "big") ^ int.from_bytes(b, "big")).to_bytes(len(a), "big") if a else b""


def est_chiffre(donnees):
    return donnees[:4] == ENTETE


def chiffrer(donnees: bytes) -> bytes:
    cle_c, cle_a = _cles()
    nonce = secrets.token_bytes(TAILLE_NONCE)
    chiffre = _xor(donnees, _flot(cle_c, nonce, len(donnees)))
    tag = hmac.new(cle_a, ENTETE + nonce + chiffre, hashlib.sha256).digest()
    return ENTETE + nonce + chiffre + tag


def dechiffrer(donnees: bytes) -> bytes:
    if not est_chiffre(donnees) or len(donnees) < 4 + TAILLE_NONCE + TAILLE_TAG:
        raise ErreurChiffrement("Données non chiffrées ou format inconnu.")
    cle_c, cle_a = _cles()
    nonce = donnees[4:4 + TAILLE_NONCE]
    chiffre, tag = donnees[4 + TAILLE_NONCE:-TAILLE_TAG], donnees[-TAILLE_TAG:]
    attendu = hmac.new(cle_a, ENTETE + nonce + chiffre, hashlib.sha256).digest()
    if not hmac.compare_digest(tag, attendu):
        raise ErreurChiffrement(
            "Impossible de déchiffrer : la clé CLE_CHIFFREMENT est différente de celle utilisée "
            "pour chiffrer, ou le fichier a été modifié."
        )
    return _xor(chiffre, _flot(cle_c, nonce, len(chiffre)))


# ---- Petites données (signatures du visage) stockées en texte dans la base ----

def chiffrer_json(valeur) -> str:
    return chiffrer(json.dumps(valeur, separators=(",", ":")).encode()).hex()


def dechiffrer_json(texte):
    if not texte:
        return None
    return json.loads(dechiffrer(bytes.fromhex(texte)).decode())
