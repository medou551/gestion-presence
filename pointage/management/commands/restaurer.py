from django.core.management.base import BaseCommand, CommandError

from pointage.chiffrement import ErreurChiffrement
from pointage.taches import restaurer_sauvegarde


class Command(BaseCommand):
    help = "Restaure une sauvegarde chiffrée. ARRÊTEZ LE SERVEUR AVANT. Remplace la base et les photos actuelles."

    def add_arguments(self, parser):
        parser.add_argument("fichier")
        parser.add_argument("--oui", action="store_true", help="Ne pas demander de confirmation")

    def handle(self, *args, **options):
        if not options["oui"]:
            rep = input("Les données actuelles seront REMPLACÉES. Le serveur est-il arrêté ? Taper OUI pour continuer : ")
            if rep.strip().upper() != "OUI":
                raise CommandError("Restauration annulée.")
        try:
            n, nb, securite = restaurer_sauvegarde(options["fichier"])
        except (ErreurChiffrement, ValueError) as e:
            raise CommandError(f"Restauration refusée, aucune donnée modifiée : {e}")
        self.stdout.write(self.style.SUCCESS(f"Restauration terminée : {nb} employé(s), {n} fichier(s)."))
        if securite:
            self.stdout.write(f"L'état précédent a été sauvegardé par sécurité : {securite}")
        self.stdout.write("Lancez « python manage.py migrate » puis redémarrez le serveur.")
