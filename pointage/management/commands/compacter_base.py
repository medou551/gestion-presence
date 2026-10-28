from django.core.management.base import BaseCommand
from django.db import connection


class Command(BaseCommand):
    help = "Compacte la base SQLite (VACUUM) : efface définitivement les restes de données supprimées."

    def handle(self, *args, **options):
        with connection.cursor() as c:
            c.execute("VACUUM;")
        self.stdout.write(self.style.SUCCESS("Base compactée."))
