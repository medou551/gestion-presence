"""Quand un employé ou un pointage est supprimé, ses fichiers photo chiffrés le sont aussi."""
from django.db.models.signals import post_delete
from django.dispatch import receiver

from .models import Employe, Pointage


@receiver(post_delete, sender=Pointage)
def supprimer_photo_pointage(sender, instance, **kwargs):
    if instance.photo:
        instance.photo.storage.delete(instance.photo.name)


@receiver(post_delete, sender=Employe)
def supprimer_photo_reference(sender, instance, **kwargs):
    if instance.photo_reference:
        instance.photo_reference.storage.delete(instance.photo_reference.name)

