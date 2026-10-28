import os
import stat

from django.conf import settings
from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError
from django.db import connection

from pointage import chiffrement
from pointage.models import Employe, JournalAudit


class Command(BaseCommand):
    help = "Vérifie la configuration de sécurité avant la mise en service."

    def handle(self, *args, **options):
        if "pointage_employe" not in connection.introspection.table_names():
            raise CommandError("La base de données n'est pas encore créée : lancez d'abord « python manage.py initialiser ».")
        ok = self.style.SUCCESS("  OK   ")
        ko = self.style.ERROR("  À FAIRE ")
        info = self.style.WARNING("  INFO ")
        problemes = 0

        def ligne(bon, texte, critique=True):
            nonlocal problemes
            if not bon and critique:
                problemes += 1
            self.stdout.write(f"{ok if bon else (ko if critique else info)} {texte}")

        ligne(not settings.DEBUG, "DEBUG est désactivé")
        ligne("*" not in settings.ALLOWED_HOSTS, f"ALLOWED_HOSTS limité : {', '.join(settings.ALLOWED_HOSTS)}")
        ligne(settings.HTTPS, "HTTPS activé (HTTPS=True, site servi par Caddy)")
        ligne(not settings.HTTPS or bool(settings.CSRF_TRUSTED_ORIGINS), "CSRF_TRUSTED_ORIGINS renseigné pour l'adresse HTTPS")
        ligne(len(settings.SECRET_KEY) >= 40 and not settings.SECRET_KEY.startswith("django-insecure"), "SECRET_KEY longue et unique")
        try:
            chiffrement.dechiffrer(chiffrement.chiffrer(b"test"))
            ligne(True, "Clé de chiffrement valide")
        except chiffrement.ErreurChiffrement as e:
            ligne(False, f"Clé de chiffrement : {e}")

        e = Employe.objects.exclude(photo_reference="").first()
        if e:
            try:
                e.photo_reference.storage.lire(e.photo_reference.name)
                ligne(True, "Les photos existantes se déchiffrent avec la clé actuelle")
            except Exception as exc:
                ligne(False, f"Photos illisibles avec la clé actuelle : {exc}")

        env = settings.FICHIER_ENV
        if os.name != "nt" and env.exists():
            ligne(not (env.stat().st_mode & (stat.S_IRGRP | stat.S_IROTH)), "Fichier .env lisible seulement par son propriétaire")

        from pointage.taches import etat_base
        eb = etat_base()
        ligne(eb["integre"], f"Base de données : {eb['message'].lower()} (mode {eb['journal_mode']}, {eb['taille_mo']} Mo)")
        ligne(eb["sauvegarde_recente"], "Sauvegarde de moins de 48 h" if eb["sauvegarde_recente"]
              else "Aucune sauvegarde récente : lancez « python manage.py sauvegarder »", critique=False)
        ligne(bool(settings.DOSSIER_SAUVEGARDES_COPIE),
              f"Copie des sauvegardes vers un autre disque : {settings.DOSSIER_SAUVEGARDES_COPIE or 'non configurée (DOSSIER_SAUVEGARDES_COPIE)'}",
              critique=False)

        integre, n = JournalAudit.verifier_integrite()
        ligne(integre, f"Journal d'audit intact ({n} entrées)" if integre else f"Journal d'audit MODIFIÉ à partir de la ligne {n}")

        User = get_user_model()
        admins = User.objects.filter(is_superuser=True, is_active=True).count()
        ligne(admins >= 1, f"{admins} compte(s) administrateur actif(s)")
        ligne(admins <= 3, "Pas trop de comptes administrateurs (3 maximum conseillé)", critique=False)

        sans = Employe.objects.filter(actif=True, descripteur_chiffre="").count()
        ligne(sans == 0, f"{sans} employé(s) actif(s) sans photo de référence", critique=False)
        ligne(True, f"Photos de pointage conservées {settings.DUREE_CONSERVATION_PHOTOS_JOURS} jours")

        self.stdout.write("")
        if problemes:
            self.stdout.write(self.style.ERROR(f"{problemes} point(s) à corriger avant la mise en service."))
        else:
            self.stdout.write(self.style.SUCCESS("Configuration prête pour la production."))
