"""Tâches automatiques : purge des anciennes photos, sauvegardes chiffrées."""
import io
import os
import shutil
import sqlite3
import tempfile
import zipfile
from datetime import timedelta
from pathlib import Path

from django.conf import settings
from django.db import connection
from django.utils import timezone

from . import chiffrement
from .models import JournalAudit, Pointage, TacheSysteme


# ---------------------------------------------------------------- Purge des photos

def purger_photos_anciennes():
    """Supprime les photos (et signatures) des pointages plus anciens que la durée de conservation.
    Les heures de pointage sont conservées."""
    limite = timezone.now() - timedelta(days=settings.DUREE_CONSERVATION_PHOTOS_JOURS)
    n = 0
    for p in Pointage.objects.filter(horodatage__lt=limite).exclude(photo="", descripteur_chiffre=""):
        p.supprimer_photo()
        n += 1
    TacheSysteme.objects.update_or_create(nom="purge_photos", defaults={"derniere_execution": timezone.now()})
    if n:
        JournalAudit.objects.create(nom_utilisateur="système", action="purge_photos",
                                    details=f"{n} photo(s) de plus de {settings.DUREE_CONSERVATION_PHOTOS_JOURS} jours supprimée(s)")
    return n


def purge_si_necessaire():
    """Lance la purge au plus une fois par jour (appelée pendant l'utilisation normale)."""
    t = TacheSysteme.objects.filter(nom="purge_photos").first()
    if not t or timezone.now() - t.derniere_execution > timedelta(hours=24):
        return purger_photos_anciennes()
    return 0


# ---------------------------------------------------------------- Santé de la base

def controle_integrite(chemin_ou_connexion=None):
    """PRAGMA integrity_check + foreign_key_check. Retourne (ok, message)."""
    if chemin_ou_connexion is None:
        connection.ensure_connection()
        cnx, fermer = connection.connection, False
    else:
        cnx, fermer = sqlite3.connect(str(chemin_ou_connexion)), True
    try:
        integrite = cnx.execute("PRAGMA integrity_check").fetchall()
        liens = cnx.execute("PRAGMA foreign_key_check").fetchall()
    finally:
        if fermer:
            cnx.close()
    if integrite != [("ok",)]:
        return False, "Base endommagée : " + "; ".join(r[0] for r in integrite[:5])
    if liens:
        return False, f"{len(liens)} lien(s) incohérent(s) entre tables"
    return True, "Base intègre"


def derniere_sauvegarde():
    dossier = Path(settings.DOSSIER_SAUVEGARDES)
    fichiers = sorted(dossier.glob("presence_*.sauvegarde")) if dossier.exists() else []
    return fichiers[-1] if fichiers else None


def etat_base():
    """Informations sur la base pour la page d'état et la vérification."""
    base = Path(settings.DATABASES["default"]["NAME"])
    ok, message = controle_integrite()
    with connection.cursor() as c:
        mode = c.execute("PRAGMA journal_mode").fetchone()[0]
    der = derniere_sauvegarde()
    age_h = None
    if der:
        age_h = (timezone.now().timestamp() - der.stat().st_mtime) / 3600
    from .models import Employe
    return {
        "chemin": base, "taille_mo": round(base.stat().st_size / 1e6, 2) if base.exists() else 0,
        "integre": ok, "message": message, "journal_mode": mode,
        "nb_employes": Employe.objects.count(), "nb_pointages": Pointage.objects.count(),
        "derniere_sauvegarde": der, "age_sauvegarde_h": age_h,
        "sauvegarde_recente": age_h is not None and age_h <= settings.SAUVEGARDE_ALERTE_HEURES,
    }


# ---------------------------------------------------------------- Sauvegardes chiffrées

def _contenu_sauvegarde(fichier):
    """Déchiffre une sauvegarde et contrôle la base qu'elle contient. Retourne (zip, nb_employes)."""
    contenu = chiffrement.dechiffrer(Path(fichier).read_bytes())
    z = zipfile.ZipFile(io.BytesIO(contenu))
    noms = z.namelist()
    if "db.sqlite3" not in noms:
        raise ValueError("Sauvegarde invalide : base de données absente.")
    for n in noms:
        if n.startswith("/") or ".." in Path(n).parts or ":" in n:
            raise ValueError(f"Chemin suspect dans la sauvegarde : {n}")
    with tempfile.TemporaryDirectory() as tmp:
        copie = Path(tmp) / "verif.sqlite3"
        copie.write_bytes(z.read("db.sqlite3"))
        ok, message = controle_integrite(copie)
        cnx = sqlite3.connect(str(copie))
        try:
            nb = cnx.execute("SELECT COUNT(*) FROM pointage_employe").fetchone()[0]
        finally:
            cnx.close()
    if not ok:
        raise ValueError(f"Sauvegarde inutilisable : {message}")
    return z, nb


def verifier_sauvegarde(fichier):
    """Retourne (ok, message). Vérifie déchiffrement, contenu et intégrité de la base sauvegardée."""
    try:
        z, nb = _contenu_sauvegarde(fichier)
        photos = sum(1 for n in z.namelist() if n.startswith("media/"))
        return True, f"vérifiée : base intègre, {nb} employé(s), {photos} photo(s)"
    except (chiffrement.ErreurChiffrement, ValueError, zipfile.BadZipFile, sqlite3.Error) as e:
        return False, str(e)


def _garder_les_plus_recentes(dossier, motif="presence_*.sauvegarde"):
    for f in sorted(Path(dossier).glob(motif))[:-settings.SAUVEGARDES_A_GARDER]:
        f.unlink()


def creer_sauvegarde(dossier=None, prefixe="presence"):
    """Crée une sauvegarde chiffrée (base + photos), la vérifie, la copie si demandé, et retourne son chemin."""
    dossier = Path(dossier or settings.DOSSIER_SAUVEGARDES)
    dossier.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory() as tmp:
        copie = Path(tmp) / "db.sqlite3"
        connection.ensure_connection()
        dst = sqlite3.connect(str(copie))
        with dst:
            connection.connection.backup(dst)  # copie cohérente même si le serveur tourne
        dst.close()

        tampon = io.BytesIO()
        with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
            z.write(copie, "db.sqlite3")
            media = Path(settings.MEDIA_ROOT)
            if media.exists():
                for f in media.rglob("*"):
                    if f.is_file():
                        z.write(f, f"media/{f.relative_to(media).as_posix()}")

    nom = dossier / f"{prefixe}_{timezone.localtime():%Y%m%d_%H%M%S}.sauvegarde"
    nom.write_bytes(chiffrement.chiffrer(tampon.getvalue()))
    try:
        os.chmod(nom, 0o600)
    except OSError:
        pass

    ok, message = verifier_sauvegarde(nom)
    if not ok:
        nom.unlink(missing_ok=True)
        JournalAudit.objects.create(nom_utilisateur="système", action="sauvegarde_echec", details=message)
        raise RuntimeError(f"La sauvegarde a échoué à la vérification : {message}")

    details = f"{nom.name} — {message}"
    if prefixe == "presence":
        _garder_les_plus_recentes(dossier)
        if settings.DOSSIER_SAUVEGARDES_COPIE:
            try:
                copie_ext = Path(settings.DOSSIER_SAUVEGARDES_COPIE)
                copie_ext.mkdir(parents=True, exist_ok=True)
                shutil.copy2(nom, copie_ext / nom.name)
                _garder_les_plus_recentes(copie_ext)
                details += f" ; copie : {copie_ext}"
            except OSError as e:
                details += f" ; COPIE EXTERNE IMPOSSIBLE : {e}"
    JournalAudit.objects.create(nom_utilisateur="système", action="sauvegarde", details=details)
    return nom


def restaurer_sauvegarde(fichier):
    """Remplace la base et les photos par le contenu d'une sauvegarde. Le serveur doit être arrêté.
    La sauvegarde est vérifiée avant, et l'état actuel est sauvegardé par sécurité."""
    z, nb = _contenu_sauvegarde(fichier)  # refuse une sauvegarde abîmée AVANT de toucher aux données
    base = Path(settings.DATABASES["default"]["NAME"])
    securite = None
    if base.exists():
        securite = creer_sauvegarde(prefixe="avant_restauration")
    connection.close()

    media = Path(settings.MEDIA_ROOT)
    if media.exists():
        shutil.rmtree(media)
    for suffixe in ("-wal", "-shm"):  # journaux WAL de l'ancienne base : à retirer
        Path(f"{base}{suffixe}").unlink(missing_ok=True)
    noms = z.namelist()
    for n in noms:
        if n == "db.sqlite3":
            base.write_bytes(z.read(n))
        elif n.startswith("media/") and not n.endswith("/"):
            cible = media / n[len("media/"):]
            cible.parent.mkdir(parents=True, exist_ok=True)
            cible.write_bytes(z.read(n))
    return len(noms), nb, securite
