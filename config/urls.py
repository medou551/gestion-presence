from django.contrib import admin
from django.urls import path

from pointage import views, views_auth, views_gestion

urlpatterns = [
    # Accès
    path("connexion/", views_auth.Connexion.as_view(), name="connexion"),
    path("deconnexion/", views_auth.Deconnexion.as_view(), name="deconnexion"),
    path("mot-de-passe/", views_auth.ChangerMotDePasse.as_view(), name="changer_mdp"),
    path("accueil/", views_auth.accueil, name="accueil"),
    path("sans-role/", views.aucun_role, name="aucun_role"),
    path("diagnostic/", views.diagnostic, name="diagnostic"),

    # Borne (compte « Borne » uniquement)
    path("", views.borne, name="borne"),
    path("pointer/", views.pointer, name="pointer"),

    # Pointage depuis le téléphone de l'employé (compte « Employé »)
    path("pointer-telephone/", views.pointer_telephone, name="pointer_telephone"),
    path("pointer-telephone/envoyer/", views.pointer_moi, name="pointer_moi"),

    # Gestion (Admin, RH, Chef de service)
    path("tableau/", views.tableau, name="tableau"),
    path("export/", views.export_excel, name="export"),
    path("photos/pointage/<int:pk>/", views.photo_pointage, name="photo_pointage"),
    path("pointages/manuel/", views_gestion.ajouter_pointage_manuel, name="pointage_manuel"),
    path("pointages/manuel/<int:pk>/supprimer/", views_gestion.supprimer_pointage_manuel, name="supprimer_pointage_manuel"),
    path("photos/reference/<int:pk>/", views.photo_reference, name="photo_reference"),

    # Employés (Admin, RH)
    path("employes/", views_gestion.employes, name="employes"),
    path("employes/enregistrer/", views_gestion.enregistrer_employe, name="enregistrer_employe"),
    path("employes/services/", views_gestion.ajouter_service, name="ajouter_service"),
    path("employes/services/<int:pk>/supprimer/", views_gestion.supprimer_service, name="supprimer_service"),
    path("employes/<int:pk>/", views_gestion.modifier_employe, name="modifier_employe"),
    path("employes/<int:pk>/acces/", views_gestion.creer_acces_employe, name="creer_acces_employe"),
    path("employes/<int:pk>/effacer-biometrie/", views_gestion.effacer_biometrie, name="effacer_biometrie"),
    path("employes/<int:pk>/supprimer/", views_gestion.supprimer_employe, name="supprimer_employe"),

    # Administration (Admin)
    path("comptes/", views_gestion.comptes, name="comptes"),
    path("comptes/<int:pk>/", views_gestion.modifier_compte, name="modifier_compte"),
    path("lieux/", views_gestion.lieux, name="lieux"),
    path("audit/", views_gestion.audit, name="audit"),
    path("admin/", admin.site.urls),

    # Espace employé
    path("mon-espace/", views.mon_espace, name="mon_espace"),
    path("mon-espace/mes-donnees/", views.mes_donnees, name="mes_donnees"),
]

handler403 = "pointage.views.refus_403"
