from django.core.management.base import BaseCommand, CommandError

from pointage.taches import etat_base, verifier_sauvegarde


class Command(BaseCommand):
    help = "Vérifie la base de données : intégrité, mode WAL, dernière sauvegarde (et la contrôle)."

    def handle(self, *args, **options):
        e = etat_base()
        ok = lambda b: self.style.SUCCESS("  OK   ") if b else self.style.ERROR("  ⚠    ")  # noqa: E731
        self.stdout.write(f"Base : {e['chemin']} ({e['taille_mo']} Mo) — {e['nb_employes']} employé(s), {e['nb_pointages']} pointage(s)")
        self.stdout.write(f"{ok(e['integre'])} {e['message']}")
        from django.conf import settings
        attendu = "wal" if settings.SQLITE_WAL else "delete"
        self.stdout.write(f"{ok(e['journal_mode'] == attendu)} Mode de journal : {e['journal_mode']}"
                          f"{'' if settings.SQLITE_WAL else ' (disque réseau : WAL désactivé)'}")
        der = e["derniere_sauvegarde"]
        if der:
            self.stdout.write(f"{ok(e['sauvegarde_recente'])} Dernière sauvegarde : {der.name} (il y a {e['age_sauvegarde_h']:.0f} h)")
            bon, message = verifier_sauvegarde(der)
            self.stdout.write(f"{ok(bon)} Contrôle de la dernière sauvegarde : {message}")
        else:
            self.stdout.write(f"{ok(False)} Aucune sauvegarde : lancez « python manage.py sauvegarder »")
        if not e["integre"]:
            raise CommandError("Base endommagée : restaurez la dernière sauvegarde (voir DEPLOIEMENT.md).")
