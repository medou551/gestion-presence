"""Administration Django : réservée aux administrateurs.
Les employés, comptes et le journal d'audit se gèrent surtout via les pages dédiées
(Employés, Comptes, Journal) ; ici, les pointages sont en lecture seule."""
from django.contrib import admin
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html

from .models import Employe, Pointage, Service

# Seuls les super-utilisateurs (rôle Administrateur) entrent dans /admin/
admin.site.has_permission = lambda request: request.user.is_active and request.user.is_superuser
admin.site.site_header = "Gestion de présence — administration"
admin.site.site_title = "Présence"
admin.site.index_title = "Administration"


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ["nom", "nb_employes"]
    search_fields = ["nom"]

    @admin.display(description="Employés")
    def nb_employes(self, obj):
        return obj.employes.count()


@admin.register(Employe)
class EmployeAdmin(admin.ModelAdmin):
    list_display = ["nom", "poste", "service", "actif", "avec_reference"]
    list_filter = ["actif", "service"]
    search_fields = ["nom"]
    fields = ["nom", "poste", "service", "actif", "reference_le"]
    readonly_fields = ["reference_le"]

    @admin.display(description="Photo de référence", boolean=True)
    def avec_reference(self, obj):
        return obj.a_reference

    def has_delete_permission(self, request, obj=None):
        return False  # suppression via la page Employés (journalisée)


@admin.register(Pointage)
class PointageAdmin(admin.ModelAdmin):
    """Lecture seule : un pointage ne peut être ni créé, ni modifié, ni supprimé à la main."""
    list_display = ["employe", "type", "heure", "ressemblance_pct", "photo_lien"]
    list_filter = ["type", "horodatage", "employe__service"]
    search_fields = ["employe__nom"]
    date_hierarchy = "horodatage"

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    @admin.display(description="Date et heure")
    def heure(self, obj):
        return f"{timezone.localtime(obj.horodatage):%d/%m/%Y %H:%M:%S}"

    @admin.display(description="Ressemblance")
    def ressemblance_pct(self, obj):
        return f"{obj.ressemblance} %" if obj.ressemblance is not None else "—"

    @admin.display(description="Photo")
    def photo_lien(self, obj):
        if not obj.photo:
            return "supprimée"
        return format_html('<a href="{}" target="_blank" rel="noopener">voir</a>',
                           reverse("photo_pointage", args=[obj.pk]))
