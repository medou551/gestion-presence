"""Protections appliquées à toutes les pages."""
import ipaddress
import secrets
import time

from django.conf import settings
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse

from .roles import journaliser, role_de


class IPClientMiddleware:
    """Chez un hébergeur (PythonAnywhere…), REMOTE_ADDR est l'adresse du répartiteur de charge, la même pour tous.
    On la remplace par la vraie adresse du visiteur, lue dans l'en-tête indiqué par EN_TETE_IP_CLIENT.
    Indispensable pour le blocage après échecs de connexion (sinon tout le monde serait bloqué ensemble)
    et pour un journal d'audit exact."""

    def __init__(self, get_response):
        self.get_response = get_response
        self.en_tete = settings.EN_TETE_IP_CLIENT

    def __call__(self, request):
        if self.en_tete:
            valeur = request.META.get(self.en_tete, "").split(",")[0].strip()
            try:
                ipaddress.ip_address(valeur)
                request.META["REMOTE_ADDR"] = valeur
            except ValueError:
                pass
        return self.get_response(request)


class EnTetesSecuriteMiddleware:
    """Content-Security-Policy (avec nonce), Permissions-Policy et pages privées non mises en cache."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        request.csp_nonce = secrets.token_urlsafe(16)
        response = self.get_response(request)
        response.headers.setdefault("Content-Security-Policy", "; ".join([
            "default-src 'self'",
            f"script-src 'self' 'nonce-{request.csp_nonce}'",
            "style-src 'self' 'unsafe-inline'",
            "img-src 'self' data: blob:",
            "media-src 'self' blob:",
            "connect-src 'self'",
            "worker-src 'self' blob:",
            "font-src 'self'",
            "object-src 'none'",
            "base-uri 'self'",
            "form-action 'self'",
            "frame-ancestors 'none'",
        ]))
        # Caméra et localisation (pointage par téléphone) autorisées pour ce site seulement ; micro interdit
        response.headers.setdefault("Permissions-Policy", "camera=(self), microphone=(), geolocation=(self), payment=()")
        if request.user.is_authenticated and not request.path.startswith("/static/"):
            response.headers["Cache-Control"] = "no-store, private"
        return response


class SessionMiddleware:
    """Déconnexion après inactivité et changement de mot de passe obligatoire."""

    CHEMINS_LIBRES = ("/static/", "/deconnexion/", "/mot-de-passe/", "/diagnostic/")

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        user = request.user
        if user.is_authenticated and not request.path.startswith(self.CHEMINS_LIBRES[0]):
            role = role_de(user)
            maintenant = int(time.time())
            derniere = request.session.get("derniere_activite", maintenant)
            if maintenant - derniere > settings.SESSION_INACTIVITE_MINUTES * 60:
                journaliser(request, "deconnexion_inactivite")
                logout(request)
                return redirect(f"{settings.LOGIN_URL}?expire=1")
            request.session["derniere_activite"] = maintenant

            profil = getattr(user, "profil", None)
            if profil and profil.doit_changer_mdp and role and not request.path.startswith(self.CHEMINS_LIBRES):
                return redirect(reverse("changer_mdp"))
        return self.get_response(request)
