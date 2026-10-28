import hashlib
import json
from datetime import datetime, time

from django.conf import settings
from django.contrib.auth.hashers import check_password, make_password
from django.db import models, transaction
from django.utils import timezone

from . import chiffrement
from .stockage import stockage_chiffre


class Service(models.Model):
    nom = models.CharField("Nom du service", max_length=100, unique=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Service"

    def __str__(self):
        return self.nom


class Employe(models.Model):
    nom = models.CharField("Nom complet", max_length=120, unique=True)
    poste = models.CharField("Poste", max_length=100, blank=True)
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True,
                                related_name="employes", verbose_name="Service")
    code_pin = models.CharField("Code PIN (chiffré)", max_length=128, blank=True,
                                help_text="Facultatif : si défini, il est demandé au pointage.")
    actif = models.BooleanField("Actif", default=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    # Photo de référence (fichier chiffré) : le visage de chaque pointage est comparé à celle-ci
    photo_reference = models.FileField("Photo de référence", upload_to="references/", blank=True,
                                       storage=stockage_chiffre)
    # Signature du visage (128 nombres), chiffrée
    descripteur_chiffre = models.TextField(blank=True, editable=False)
    reference_le = models.DateTimeField("Photo de référence prise le", null=True, blank=True, editable=False)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Employé"

    def __str__(self):
        return self.nom

    # -- PIN
    def definir_pin(self, pin_clair):
        self.code_pin = make_password(pin_clair)

    def verifier_pin(self, pin_clair):
        return check_password(pin_clair, self.code_pin)

    @property
    def demande_pin(self):
        return bool(self.code_pin)

    # -- Signature du visage (chiffrée)
    @property
    def descripteur(self):
        return chiffrement.dechiffrer_json(self.descripteur_chiffre)

    @descripteur.setter
    def descripteur(self, valeur):
        self.descripteur_chiffre = chiffrement.chiffrer_json(valeur) if valeur else ""

    @property
    def a_reference(self):
        return bool(self.descripteur_chiffre and self.photo_reference)

    def dernier_pointage(self):
        return self.pointages.order_by("-horodatage").first()

    def effacer_biometrie(self):
        """Supprime la photo de référence, la signature du visage et toutes les photos de pointage."""
        if self.photo_reference:
            self.photo_reference.delete(save=False)
        self.descripteur_chiffre = ""
        self.reference_le = None
        self.save()
        n = 0
        for p in self.pointages.exclude(photo=""):
            p.supprimer_photo()
            n += 1
        self.pointages.update(descripteur_chiffre="")
        return n


class Lieu(models.Model):
    """Lieu de travail : le pointage par téléphone n'est accepté qu'à l'intérieur de ce cercle."""
    nom = models.CharField(max_length=100)
    latitude = models.FloatField()
    longitude = models.FloatField()
    rayon_m = models.PositiveIntegerField("Rayon (mètres)", default=20)
    actif = models.BooleanField(default=True)
    cree_le = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nom"]
        verbose_name = "Lieu de pointage"

    def __str__(self):
        return self.nom


class Pointage(models.Model):
    ENTREE, SORTIE = "E", "S"
    TYPES = [(ENTREE, "Entrée"), (SORTIE, "Sortie")]
    BORNE, TELEPHONE, QR = "borne", "telephone", "qr"
    SOURCES = [(BORNE, "Poste de pointage"), (TELEPHONE, "Téléphone de l'employé (visage)"),
               (QR, "QR code de la tablette")]

    employe = models.ForeignKey(Employe, on_delete=models.CASCADE, related_name="pointages")
    type = models.CharField(max_length=1, choices=TYPES)
    # Heure fixée par le SERVEUR (jamais par le poste de l'employé)
    horodatage = models.DateTimeField(default=timezone.now, db_index=True)
    # Photo chiffrée ; supprimée automatiquement après DUREE_CONSERVATION_PHOTOS_JOURS
    photo = models.FileField(upload_to="pointages/%Y/%m/%d/", blank=True, storage=stockage_chiffre)
    photo_supprimee_le = models.DateTimeField(null=True, blank=True, editable=False)
    # Empreinte SHA-256 du fichier photo : une même image ne peut servir qu'une fois
    empreinte = models.CharField(max_length=64, unique=True, null=True, blank=True, editable=False)
    descripteur_chiffre = models.TextField(blank=True, editable=False)
    # Distance entre ce visage et la photo de référence (0 = identique ; plus petit = plus ressemblant)
    distance = models.FloatField(null=True, blank=True, editable=False)
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)
    # Correction manuelle (oubli de pointage) : saisie par l'administrateur avec un motif
    manuel = models.BooleanField("Saisie manuelle", default=False)
    motif = models.CharField("Motif de la correction", max_length=200, blank=True)
    saisi_par = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
                                  related_name="pointages_saisis", verbose_name="Saisi par")
    # D'où vient le pointage : la borne commune ou le téléphone personnel de l'employé
    source = models.CharField("Source", max_length=10, choices=SOURCES, default=BORNE)
    # Téléphone : lieu où l'employé se trouvait et sa distance au centre (les coordonnées GPS ne sont PAS conservées)
    lieu = models.ForeignKey("Lieu", on_delete=models.SET_NULL, null=True, blank=True, related_name="pointages")
    distance_lieu_m = models.FloatField(null=True, blank=True, editable=False)

    class Meta:
        ordering = ["-horodatage"]

    def __str__(self):
        local = timezone.localtime(self.horodatage)
        return f"{self.employe.nom} – {self.get_type_display()} – {local:%d/%m/%Y %H:%M:%S}"

    @property
    def origine(self):
        if self.manuel:
            par = self.saisi_par.get_username() if self.saisi_par else "?"
            return f"Manuel ({par}) : {self.motif}"
        if self.source == self.QR:
            return "QR code (tablette)"
        if self.source == self.TELEPHONE:
            if self.lieu_id and self.distance_lieu_m is not None:
                return f"Téléphone ({self.distance_lieu_m:.0f} m de {self.lieu.nom})"
            return "Téléphone"
        return "Poste de pointage"

    @property
    def descripteur(self):
        return chiffrement.dechiffrer_json(self.descripteur_chiffre)

    @descripteur.setter
    def descripteur(self, valeur):
        self.descripteur_chiffre = chiffrement.chiffrer_json(valeur) if valeur else ""

    @property
    def en_retard(self):
        if self.type != self.ENTREE:
            return False
        h, m = map(int, settings.HEURE_ARRIVEE.split(":"))
        return timezone.localtime(self.horodatage).time() > time(h, m)

    @property
    def ressemblance(self):
        """Pourcentage de ressemblance avec la photo de référence (pour l'affichage)."""
        if self.distance is None:
            return None
        return max(0, round((1 - self.distance) * 100))

    def supprimer_photo(self):
        if self.photo:
            self.photo.delete(save=False)
        self.photo = ""
        self.descripteur_chiffre = ""
        self.photo_supprimee_le = timezone.now()
        self.save(update_fields=["photo", "descripteur_chiffre", "photo_supprimee_le"])


# ---------------------------------------------------------------- Rôles

class Profil(models.Model):
    # Deux rôles seulement : l'administrateur gère tout, l'utilisateur (employé) pointe avec son téléphone.
    ADMIN, EMPLOYE = "admin", "employe"
    ROLES = [
        (ADMIN, "Administrateur"),
        (EMPLOYE, "Utilisateur (employé)"),
    ]
    # Anciens rôles (versions précédentes) : ces comptes sont désactivés et n'ont plus aucun accès
    ANCIENS_ROLES = ("rh", "chef", "borne")

    utilisateur = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profil")
    role = models.CharField("Rôle", max_length=10, choices=ROLES)
    service = models.ForeignKey(Service, on_delete=models.SET_NULL, null=True, blank=True,
                                verbose_name="Service (chef de service)")
    employe = models.OneToOneField(Employe, on_delete=models.CASCADE, null=True, blank=True,
                                   related_name="compte", verbose_name="Employé (compte employé)")
    doit_changer_mdp = models.BooleanField("Doit changer son mot de passe", default=True)

    class Meta:
        verbose_name = "Profil"

    def __str__(self):
        return f"{self.utilisateur.username} ({self.get_role_display()})"


# ---------------------------------------------------------------- Journal d'audit

class JournalAudit(models.Model):
    """Journal des actions : ajout uniquement. Chaque ligne contient l'empreinte de la précédente,
    ce qui permet de détecter toute modification ou suppression (chaîne d'empreintes)."""
    date = models.DateTimeField(default=timezone.now, db_index=True)
    utilisateur = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True)
    nom_utilisateur = models.CharField(max_length=150, blank=True)
    role = models.CharField(max_length=20, blank=True)
    action = models.CharField(max_length=60, db_index=True)
    details = models.TextField(blank=True)
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)
    empreinte_precedente = models.CharField(max_length=64, editable=False)
    empreinte = models.CharField(max_length=64, editable=False)

    class Meta:
        ordering = ["-id"]
        verbose_name = "Entrée du journal d'audit"
        verbose_name_plural = "Journal d'audit"

    def _calculer_empreinte(self):
        contenu = json.dumps([
            self.empreinte_precedente, self.date.isoformat(), self.nom_utilisateur, self.role,
            self.action, self.details, self.adresse_ip or "",
        ], ensure_ascii=False)
        return hashlib.sha256(contenu.encode()).hexdigest()

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("Le journal d'audit ne peut pas être modifié.")
        with transaction.atomic():
            precedent = JournalAudit.objects.select_for_update().order_by("-id").first()
            self.empreinte_precedente = precedent.empreinte if precedent else "0" * 64
            self.empreinte = self._calculer_empreinte()
            super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionError("Le journal d'audit ne peut pas être supprimé.")

    @classmethod
    def verifier_integrite(cls):
        """Retourne (True, nb_lignes) ou (False, id_de_la_premiere_ligne_alteree)."""
        precedente = "0" * 64
        n = 0
        for ligne in cls.objects.order_by("id").iterator():
            if ligne.empreinte_precedente != precedente or ligne._calculer_empreinte() != ligne.empreinte:
                return False, ligne.id
            precedente = ligne.empreinte
            n += 1
        return True, n


class Tablette(models.Model):
    """Tablette du bureau qui affiche le QR code. Elle n'a pas de compte : elle est reconnue par un jeton secret
    (cookie posé par l'administrateur). Seule l'empreinte du jeton est conservée."""
    nom = models.CharField(max_length=60)
    empreinte_jeton = models.CharField(max_length=64, unique=True, editable=False)
    active = models.BooleanField(default=True)
    creee_le = models.DateTimeField(auto_now_add=True)
    derniere_activite = models.DateTimeField(null=True, blank=True)
    adresse_ip = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        ordering = ["nom"]

    def __str__(self):
        return self.nom


class TacheSysteme(models.Model):
    """Mémorise la dernière exécution des tâches automatiques (purge des photos…)."""
    nom = models.CharField(max_length=50, primary_key=True)
    derniere_execution = models.DateTimeField()


# ---------------------------------------------------------------- Calculs

def heures_supplementaires(secondes):
    """Secondes travaillées au-delà de la journée normale (HEURES_JOURNEE, 8 h par défaut)."""
    return max(0, int(secondes - settings.HEURES_JOURNEE * 3600))

def resume_journee(employe, jour):
    """Retourne (premiere_entree, derniere_sortie, secondes_travaillees, entree_ouverte) pour un jour."""
    debut = timezone.make_aware(datetime.combine(jour, time.min))
    fin = timezone.make_aware(datetime.combine(jour, time.max))
    pts = list(employe.pointages.filter(horodatage__range=(debut, fin)).order_by("horodatage"))
    total, entree_ouverte = 0, None
    for p in pts:
        if p.type == Pointage.ENTREE:
            entree_ouverte = p.horodatage
        elif entree_ouverte:
            total += (p.horodatage - entree_ouverte).total_seconds()
            entree_ouverte = None
    entrees = [p for p in pts if p.type == Pointage.ENTREE]
    sorties = [p for p in pts if p.type == Pointage.SORTIE]
    return (
        entrees[0] if entrees else None,
        sorties[-1] if sorties else None,
        int(total),
        entree_ouverte,  # date/heure de l'entrée sans sortie (ou None)
    )
