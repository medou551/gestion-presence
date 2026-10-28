"""Comparaison des visages.

Le navigateur (face-api.js) calcule la « signature » d'un visage : 128 nombres.
Deux photos de la même personne donnent des signatures proches ; deux personnes
différentes donnent des signatures éloignées. Ici on mesure cette distance et on décide.
"""
import hashlib
import json
import math

from django.conf import settings

TAILLE_SIGNATURE = 128


def lire_descripteur(texte):
    """Transforme le texte JSON reçu en liste de 128 nombres, ou None s'il est invalide."""
    try:
        valeurs = json.loads(texte)
    except (TypeError, ValueError):
        return None
    if not isinstance(valeurs, list) or len(valeurs) != TAILLE_SIGNATURE:
        return None
    try:
        valeurs = [float(v) for v in valeurs]
    except (TypeError, ValueError):
        return None
    if not all(math.isfinite(v) and -10 < v < 10 for v in valeurs):
        return None
    if math.sqrt(sum(v * v for v in valeurs)) < 1e-6:  # signature vide
        return None
    return valeurs


def distance(a, b):
    """Distance euclidienne entre deux signatures (0 = identiques)."""
    return math.sqrt(sum((x - y) ** 2 for x, y in zip(a, b)))


def seuil():
    """Au-delà de cette distance, ce n'est pas la même personne."""
    return getattr(settings, "SEUIL_RECONNAISSANCE", 0.5)


def plus_proche(descripteur, employes):
    """Retourne (employe, distance) de l'employé dont la photo de référence ressemble le plus."""
    meilleur, meilleure_dist = None, float("inf")
    for emp in employes:
        ref = emp.descripteur  # déchiffrée une seule fois
        if ref:
            d = distance(descripteur, ref)
            if d < meilleure_dist:
                meilleur, meilleure_dist = emp, d
    return meilleur, meilleure_dist


def empreinte_fichier(fichier):
    """Empreinte SHA-256 du contenu du fichier (deux fichiers identiques ont la même empreinte)."""
    h = hashlib.sha256()
    for morceau in fichier.chunks():
        h.update(morceau)
    fichier.seek(0)
    return h.hexdigest()
