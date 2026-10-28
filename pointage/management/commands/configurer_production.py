"""Prépare la configuration de production : fichier .env et Caddyfile (HTTPS).

    python manage.py configurer_production --adresse 192.168.1.10
    python manage.py configurer_production --adresse 192.168.1.10 --adresse presence.local
"""
import ipaddress
import re

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

MODELE_CADDY = """# Caddy : reçoit les connexions HTTPS du réseau et les transmet au serveur de l'application.
# Fichier généré par « python manage.py configurer_production » — relancez cette commande pour le modifier.
{{
\t# Certificats délivrés par l'autorité de certification locale de Caddy (réseau interne)
\tlocal_certs
\t# L'interface d'administration de Caddy n'écoute que sur cette machine
\tadmin localhost:2019
}}

{sites} {{
\ttls internal
\tencode gzip
\trequest_body {{
\t\tmax_size 10MB
\t}}
\treverse_proxy 127.0.0.1:8000
\theader {{
\t\t-Server
\t\tStrict-Transport-Security "max-age=31536000"
\t}}
\tlog {{
\t\toutput file "{journal}" {{
\t\t\troll_size 10MiB
\t\t\troll_keep 5
\t\t}}
\t}}
}}
"""


def _valider(adresse):
    try:
        ipaddress.ip_address(adresse)
        return adresse
    except ValueError:
        pass
    if re.fullmatch(r"[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?(\.[A-Za-z0-9]([A-Za-z0-9-]{0,61}[A-Za-z0-9])?)*", adresse):
        return adresse.lower()
    raise CommandError(f"Adresse invalide : {adresse}")


class Command(BaseCommand):
    help = "Configure le fichier .env et le Caddyfile pour une utilisation en production (HTTPS)."

    def add_arguments(self, parser):
        parser.add_argument("--adresse", action="append", required=True,
                            help="Adresse IP ou nom du serveur sur le réseau (option répétable)")

    def handle(self, *args, **options):
        adresses = [_valider(a.strip()) for a in options["adresse"] if a.strip()]
        hotes = list(dict.fromkeys(["127.0.0.1", "localhost", "[::1]", *adresses]))
        origines = [f"https://{h}" for h in dict.fromkeys(["localhost", *adresses])]

        env = settings.FICHIER_ENV
        lignes = env.read_text(encoding="utf-8").splitlines()
        nouvelles = {
            "DEBUG": "False",
            "HTTPS": "True",
            "ALLOWED_HOSTS": ",".join(hotes),
            "CSRF_TRUSTED_ORIGINS": ",".join(origines),
        }
        vues = set()
        for i, ligne in enumerate(lignes):
            cle = ligne.split("=", 1)[0].strip()
            if cle in nouvelles and not ligne.lstrip().startswith("#"):
                lignes[i] = f"{cle}={nouvelles[cle]}"
                vues.add(cle)
        lignes += [f"{c}={v}" for c, v in nouvelles.items() if c not in vues]
        env.write_text("\n".join(lignes) + "\n", encoding="utf-8")

        dossier = settings.BASE_DIR / "deploiement"
        (dossier / "journaux").mkdir(parents=True, exist_ok=True)
        sites = ", ".join(origines)
        journal = (dossier / "journaux" / "caddy.log").as_posix()
        (dossier / "Caddyfile").write_text(MODELE_CADDY.format(sites=sites, journal=journal), encoding="utf-8")

        self.stdout.write(self.style.SUCCESS("Configuration de production enregistrée :"))
        self.stdout.write(f"  .env        : DEBUG=False, HTTPS=True, ALLOWED_HOSTS={','.join(hotes)}")
        self.stdout.write(f"  Caddyfile   : {sites}")
        self.stdout.write("Redémarrez le serveur et Caddy pour appliquer.")
