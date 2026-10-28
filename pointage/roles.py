"""Rôles et droits d'accès.

| Rôle            | Peut faire                                                                  |
|-----------------|-----------------------------------------------------------------------------|
| Administrateur  | tout : comptes, services, employés, tableau, exports, journal d'audit       |
| RH              | employés (création, photos de référence, effacement), tableau et exports    |
|                 | de TOUS les services                                                        |
| Chef de service | tableau et exports de SON service uniquement (lecture seule)                |
| Borne           | uniquement la page de pointage                                              |
| Employé         | uniquement son propre historique et ses propres données                     |
"""
from functools import wraps

from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied

from .models import Employe, JournalAudit, Pointage, Profil

ADMIN, RH, CHEF, BORNE, EMPLOYE = Profil.ADMIN, Profil.RH, Profil.CHEF, Profil.BORNE, Profil.EMPLOYE
GESTION = (ADMIN, RH, CHEF)


def role_de(user):
    if not user or not user.is_authenticated or not user.is_active:
        return None
    if user.is_superuser:
        return ADMIN
    profil = getattr(user, "profil", None)
    return profil.role if profil else None


def service_du_chef(user):
    profil = getattr(user, "profil", None)
    return profil.service if profil else None


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
    if role in (ADMIN, RH):
        return Employe.objects.all()
    if role == CHEF:
        service = service_du_chef(user)
        return Employe.objects.filter(service=service) if service else Employe.objects.none()
    if role == EMPLOYE:
        emp = employe_du_compte(user)
        return Employe.objects.filter(pk=emp.pk) if emp else Employe.objects.none()
    return Employe.objects.none()


def pointages_visibles(user):
    return Pointage.objects.filter(employe__in=employes_visibles(user))


def peut_gerer_employes(user):
    return role_de(user) in (ADMIN, RH)


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
        "est_gestion": role in GESTION,
        "peut_gerer_employes": role in (ADMIN, RH),
        "est_borne": role == BORNE,
        "est_employe": role == EMPLOYE,
    }
