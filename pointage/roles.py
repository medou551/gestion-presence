"""Rôles et droits d'accès : deux rôles seulement.

| Rôle                   | Peut faire                                                                  |
|------------------------|-----------------------------------------------------------------------------|
| Administrateur         | tout : comptes, services, employés, lieux, tableau, exports, journal        |
| Utilisateur (employé)  | pointer avec son téléphone, son propre historique et ses propres données    |
"""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import Employe, JournalAudit, Pointage, Profil

ADMIN, EMPLOYE = Profil.ADMIN, Profil.EMPLOYE


def role_de(user):
    if not user or not user.is_authenticated or not user.is_active:
        return None
    if user.is_superuser:
        return ADMIN
    profil = getattr(user, "profil", None)
    # Un ancien rôle (RH, chef, borne) ne donne plus aucun accès
    return profil.role if profil and profil.role in (ADMIN, EMPLOYE) else None


def employe_du_compte(user):
    profil = getattr(user, "profil", None)
    return profil.employe if profil else None


def role_requis(*roles):
    """Décorateur : la vue n'est accessible qu'aux rôles indiqués."""
    def decorateur(vue):
        @wraps(vue)
        def enveloppe(request, *args, **kwargs):
            if not request.user.is_authenticated:
                return redirect_to_login(request.get_full_path())
            if role_de(request.user) not in roles:
                journaliser(request, "acces_refuse", request.path)
                raise PermissionDenied
            return vue(request, *args, **kwargs)
        return enveloppe
    return decorateur


# ---------------------------------------------------------------- Périmètre visible

def employes_visibles(user):
    """Employés que l'utilisateur a le droit de voir."""
    role = role_de(user)
    if role == ADMIN:
        return Employe.objects.all()
    if role == EMPLOYE:
        emp = employe_du_compte(user)
        return Employe.objects.filter(pk=emp.pk) if emp else Employe.objects.none()
    return Employe.objects.none()


def pointages_visibles(user):
    return Pointage.objects.filter(employe__in=employes_visibles(user))


# ---------------------------------------------------------------- Journal d'audit

def adresse_ip(request):
    # L'adresse réelle est fournie par Waitress (qui fait confiance uniquement à Caddy sur 127.0.0.1)
    return request.META.get("REMOTE_ADDR") if request else None


def journaliser(request, action, details="", utilisateur=None):
    user = utilisateur or (request.user if request and request.user.is_authenticated else None)
    JournalAudit.objects.create(
        utilisateur=user,
        nom_utilisateur=user.get_username() if user else "",
        role=role_de(user) or "",
        action=action,
        details=str(details)[:2000],
        adresse_ip=adresse_ip(request),
    )


# ---------------------------------------------------------------- Gabarits

def contexte_role(request):
    role = role_de(getattr(request, "user", None))
    return {
        "role": role,
        "role_libelle": dict(Profil.ROLES).get(role, ""),
        "est_admin": role == ADMIN,
        "est_employe": role == EMPLOYE,
    }
