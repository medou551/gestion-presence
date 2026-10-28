"""Configure l'application pour PythonAnywhere (à lancer dans une console Bash de PythonAnywhere).

    python manage.py configurer_pythonanywhere --domaine monnom.pythonanywhere.com

Écrit dans le fichier .env :
- DEBUG=False, HTTPS=True (PythonAnywhere fournit le HTTPS) ;
- ALLOWED_HOSTS et CSRF_TRUSTED_ORIGINS = votre domaine ;
- EN_TETE_IP_CLIENT=HTTP_X_REAL_IP (vraie adresse des visiteurs derrière le répartiteur de PythonAnywhere) ;
- SQLITE_WAL=False (le disque de PythonAnywhere est un disque réseau).
Affiche ensuite le contenu exact du fichier WSGI à coller dans l'onglet « Web ».
"""
import re
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

MODELE_WSGI = '''# Fichier WSGI de PythonAnywhere pour « Gestion de présence »
# (onglet Web → section Code → lien « WSGI configuration file » : remplacez TOUT le contenu par ceci)
import os
import sys

chemin = "{racine}"
if chemin not in sys.path:
    sys.path.insert(0, chemin)
os.chdir(chemin)
os.environ["DJANGO_SETTINGS_MODULE"] = "config.settings"

from django.core.wsgi import get_wsgi_application  # noqa: E402
application = get_wsgi_application()
'''


class Command(BaseCommand):
    help = "Configure .env pour PythonAnywhere et affiche le fichier WSGI à utiliser."

    def add_arguments(self, parser):
        parser.add_argument("--domaine", required=True, help="ex. monnom.pythonanywhere.com ou monnom.eu.pythonanywhere.com")

    def handle(self, *args, **options):
        domaine = options["domaine"].strip().lower().removeprefix("https://").removeprefix("http://").strip("/")
        if not re.fullmatch(r"[a-z0-9-]+(\.[a-z0-9-]+)+", domaine):
            raise CommandError(f"Domaine invalide : {domaine}")

        nouvelles = {
            "DEBUG": "False",
            "HTTPS": "True",
            "ALLOWED_HOSTS": domaine,
            "CSRF_TRUSTED_ORIGINS": f"https://{domaine}",
            "EN_TETE_IP_CLIENT": "HTTP_X_REAL_IP",
            "SQLITE_WAL": "False",
        }
        env = settings.FICHIER_ENV
        lignes = env.read_text(encoding="utf-8").splitlines() if env.exists() else []
        vues = set()
        for i, ligne in enumerate(lignes):
            cle = ligne.split("=", 1)[0].strip()
            if cle in nouvelles and not ligne.lstrip().startswith("#"):
                lignes[i] = f"{cle}={nouvelles[cle]}"
                vues.add(cle)
        lignes += [f"{c}={v}" for c, v in nouvelles.items() if c not in vues]
        env.write_text("\n".join(lignes) + "\n", encoding="utf-8")
        env.chmod(0o600)

        racine = Path(settings.BASE_DIR).resolve()
        wsgi = MODELE_WSGI.format(racine=racine.as_posix())
        (racine / "deploiement" / "wsgi_pythonanywhere.py").write_text(wsgi, encoding="utf-8")

        self.stdout.write(self.style.SUCCESS(f"Configuration PythonAnywhere enregistrée pour https://{domaine}"))
        self.stdout.write("  DEBUG=False, HTTPS=True, IP réelle via X-Real-IP, SQLite sans WAL (disque réseau)")
        self.stdout.write("\nContenu à coller dans le fichier WSGI (onglet Web) — aussi enregistré dans "
                          "deploiement/wsgi_pythonanywhere.py :\n")
        self.stdout.write(wsgi)
        self.stdout.write("Puis : onglet Web → Static files : URL /static/  →  Directory "
                          f"{(racine / 'staticfiles').as_posix()}")
        self.stdout.write("NE créez PAS de correspondance pour /media/ : les photos chiffrées passent par l'application.")
