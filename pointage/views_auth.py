"""Connexion, déconnexion et mot de passe — avec blocage après plusieurs échecs."""
import time

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import views as auth_views
from django.core.cache import cache
from django.shortcuts import redirect
from django.urls import reverse, reverse_lazy

from .roles import ADMIN, BORNE, CHEF, EMPLOYE, RH, journaliser, role_de


def _cles_blocage(request, nom):
    return [f"echecs:nom:{nom.lower()}", f"echecs:ip:{request.META.get('REMOTE_ADDR')}"]


def _echecs_recents(cle):
    limite = time.time() - settings.CONNEXION_BLOCAGE_MINUTES * 60
    return [t for t in cache.get(cle, []) if t > limite]


def minutes_de_blocage(request, nom):
    """0 si la connexion est autorisée, sinon le nombre de minutes restantes."""
    for cle in _cles_blocage(request, nom):
        echecs = _echecs_recents(cle)
        if len(echecs) >= settings.CONNEXION_ECHECS_MAX:
            reste = settings.CONNEXION_BLOCAGE_MINUTES * 60 - (time.time() - echecs[-settings.CONNEXION_ECHECS_MAX])
            return max(1, int(reste // 60) + 1)
    return 0


def noter_echec(request, nom):
    for cle in _cles_blocage(request, nom):
        cache.set(cle, _echecs_recents(cle) + [time.time()], settings.CONNEXION_BLOCAGE_MINUTES * 60)


def effacer_echecs(request, nom):
    cache.delete(_cles_blocage(request, nom)[0])


class Connexion(auth_views.LoginView):
    template_name = "pointage/connexion.html"
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        nom = request.POST.get("username", "")[:150]
        minutes = minutes_de_blocage(request, nom)
        if minutes:
            journaliser(request, "connexion_bloquee", f"identifiant={nom}")
            form = self.get_form()
            form.errors.clear()
            return self.render_to_response(self.get_context_data(form=form, bloque=minutes))
        return super().post(request, *args, **kwargs)

    def form_valid(self, form):
        reponse = super().form_valid(form)
        user = form.get_user()
        effacer_echecs(self.request, user.get_username())
        if role_de(user) == BORNE:
            # La borne reste connectée longtemps ; les autres comptes : 8 h maximum
            self.request.session.set_expiry(settings.SESSION_BORNE_JOURS * 86400)
        self.request.session["derniere_activite"] = int(time.time())
        journaliser(self.request, "connexion_reussie", utilisateur=user)
        return reponse

    def form_invalid(self, form):
        nom = self.request.POST.get("username", "")[:150]
        noter_echec(self.request, nom)
        journaliser(self.request, "connexion_echouee", f"identifiant={nom}")
        return super().form_invalid(form)

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["expire"] = self.request.GET.get("expire") == "1"
        return ctx


class Deconnexion(auth_views.LogoutView):
    def post(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            journaliser(request, "deconnexion")
        return super().post(request, *args, **kwargs)


class ChangerMotDePasse(auth_views.PasswordChangeView):
    template_name = "pointage/changer_mdp.html"
    success_url = reverse_lazy("accueil")

    def form_valid(self, form):
        reponse = super().form_valid(form)
        profil = getattr(self.request.user, "profil", None)
        if profil and profil.doit_changer_mdp:
            profil.doit_changer_mdp = False
            profil.save(update_fields=["doit_changer_mdp"])
        journaliser(self.request, "mot_de_passe_change")
        messages.success(self.request, "Mot de passe modifié.")
        return reponse


def accueil(request):
    """Redirige chacun vers sa page selon son rôle."""
    if not request.user.is_authenticated:
        return redirect(settings.LOGIN_URL)
    role = role_de(request.user)
    if role == BORNE:
        return redirect(reverse("borne"))
    if role == EMPLOYE:
        return redirect(reverse("mon_espace"))
    if role in (ADMIN, RH, CHEF):
        return redirect(reverse("tableau"))
    return redirect(reverse("aucun_role"))
