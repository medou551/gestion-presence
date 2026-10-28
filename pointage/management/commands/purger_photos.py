from django.conf import settings
from django.core.management.base import BaseCommand

from pointage.taches import purger_photos_anciennes


class Command(BaseCommand):
    help = "Supprime les photos de pointage plus anciennes que DUREE_CONSERVATION_PHOTOS_JOURS (les heures sont gardées)."

    def handle(self, *args, **options):
        n = purger_photos_anciennes()
        self.stdout.write(self.style.SUCCESS(
            f"{n} photo(s) de plus de {settings.DUREE_CONSERVATION_PHOTOS_JOURS} jours supprimée(s)."))
