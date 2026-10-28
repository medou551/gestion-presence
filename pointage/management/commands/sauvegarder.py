from django.core.management.base import BaseCommand, CommandError

from pointage.taches import creer_sauvegarde, purger_photos_anciennes


class Command(BaseCommand):
    help = "Crée une sauvegarde chiffrée de la base et des photos (et purge les photos trop anciennes)."

    def add_arguments(self, parser):
        parser.add_argument("--dossier", help="Dossier de destination (par défaut : DOSSIER_SAUVEGARDES)")

    def handle(self, *args, **options):
        purger_photos_anciennes()
        try:
            chemin = creer_sauvegarde(options.get("dossier"))
        except RuntimeError as e:
            raise CommandError(str(e))
        from pointage.models import JournalAudit
        details = JournalAudit.objects.filter(action="sauvegarde").order_by("-id").first().details
        self.stdout.write(self.style.SUCCESS(f"Sauvegarde chiffrée créée et {details.split(' — ', 1)[1]}"))
        self.stdout.write(f"Fichier : {chemin}")
        self.stdout.write("Rappel : elle ne peut être restaurée qu'avec la même CLE_CHIFFREMENT (fichier .env).")
