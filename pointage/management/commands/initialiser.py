"""Installe ou met à jour la base de données en une seule commande, sans risque.

    python manage.py initialiser

- crée le fichier .env (clés secrètes) s'il n'existe pas ;
- sauvegarde la base existante avant toute modification ;
- crée / met à jour les tables (migrations) ;
- crée le compte administrateur s'il n'y en a pas ;
- contrôle l'intégrité de la base et protège les fichiers.
Peut être relancée sans danger à tout moment.
"""
import getpass
import os
import sys
from pathlib import Path

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.password_validation import validate_password
from django.core.exceptions import ValidationError
from django.core.management import call_command
from django.core.management.base import BaseCommand, CommandError
from django.db import connection
from django.db.migrations.executor import MigrationExecutor


class Command(BaseCommand):
    help = "Installe ou met à jour la base de données (sans risque, peut être relancée)."

    def add_arguments(self, parser):
        parser.add_argument("--admin", help="Identifiant de l'administrateur à créer (sinon demandé)")
        parser.add_argument("--sans-admin", action="store_true", help="Ne pas créer d'administrateur")

    def etape(self, texte):
        self.stdout.write(self.style.MIGRATE_HEADING(f"\n==> {texte}"))

    def handle(self, *args, **options):
        if sys.version_info < (3, 10):
            raise CommandError("Python 3.10 ou plus récent est nécessaire.")
        base = Path(settings.DATABASES["default"]["NAME"])
        self.stdout.write(f"Base de données : {base}")
        self.stdout.write(f"Clés secrètes   : {settings.FICHIER_ENV} (gardez-en une copie en lieu sûr)")

        # 1. Sauvegarde préalable si la base existe et doit évoluer
        connection.ensure_connection()
        executor = MigrationExecutor(connection)
        a_faire = executor.migration_plan(executor.loader.graph.leaf_nodes())
        existe = base.exists() and base.stat().st_size > 0 and "pointage_employe" in connection.introspection.table_names()
        if existe and a_faire:
            self.etape("Sauvegarde de sécurité avant mise à jour")
            from pointage.taches import creer_sauvegarde
            self.stdout.write(f"    {creer_sauvegarde(prefixe='avant_mise_a_jour')}")

        # 2. Tables
        self.etape("Création / mise à jour des tables")
        if a_faire:
            call_command("migrate", interactive=False, verbosity=1)
        else:
            self.stdout.write("    Déjà à jour.")

        # 3. Intégrité
        self.etape("Contrôle de la base")
        from pointage.taches import controle_integrite
        ok, message = controle_integrite()
        if not ok:
            raise CommandError(f"{message}. Restaurez une sauvegarde (python manage.py restaurer …).")
        with connection.cursor() as c:
            mode = c.execute("PRAGMA journal_mode").fetchone()[0]
        self.stdout.write(self.style.SUCCESS(f"    {message} — mode {mode}"))

        # 4. Fichiers statiques (production)
        if not settings.DEBUG:
            call_command("collectstatic", interactive=False, verbosity=0)

        # 5. Protection des fichiers (Linux/macOS ; sous Windows c'est installer.ps1 qui s'en charge)
        if os.name != "nt":
            for chemin, mode_f in ((base, 0o600), (settings.FICHIER_ENV, 0o600), (Path(settings.MEDIA_ROOT), 0o700)):
                if Path(chemin).exists():
                    os.chmod(chemin, mode_f)

        # 6. Administrateur
        User = get_user_model()
        if not options["sans_admin"] and not User.objects.filter(is_superuser=True, is_active=True).exists():
            self.etape("Création du compte administrateur")
            if not sys.stdin.isatty() and not options["admin"]:
                self.stdout.write(self.style.WARNING("    Pas de terminal interactif : lancez « python manage.py createsuperuser »."))
            else:
                self.creer_admin(User, options["admin"])

        self.stdout.write(self.style.SUCCESS("\nBase de données prête."))

    def creer_admin(self, User, identifiant=None):
        while not identifiant:
            identifiant = input("    Identifiant de l'administrateur : ").strip()
            if User.objects.filter(username__iexact=identifiant).exists():
                self.stdout.write(self.style.ERROR("    Cet identifiant existe déjà."))
                identifiant = None
        while True:
            mdp = getpass.getpass("    Mot de passe (10 caractères minimum, rien ne s'affiche) : ")
            if mdp != getpass.getpass("    Confirmez le mot de passe : "):
                self.stdout.write(self.style.ERROR("    Les deux mots de passe sont différents."))
                continue
            try:
                validate_password(mdp, User(username=identifiant))
                break
            except ValidationError as e:
                for m in e.messages:
                    self.stdout.write(self.style.ERROR(f"    {m}"))
        User.objects.create_superuser(identifiant, "", mdp)
        self.stdout.write(self.style.SUCCESS(f"    Administrateur « {identifiant} » créé."))
