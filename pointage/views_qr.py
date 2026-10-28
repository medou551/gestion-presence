"""Pointage par QR code.

- La tablette du bureau affiche un QR code qui change toutes les 15 secondes (valable 90 secondes).
- L'employé le scanne avec l'appareil photo de son téléphone (il est connecté à son compte) :
  le serveur enregistre l'heure à la seconde. Premier scan du jour = entrée, suivant = sortie.
- Sortie avant la durée normale (8 h) : confirmation demandée. Au-delà de 8 h : heures supplémentaires.
"""
import hashlib
import secrets

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import logout
from django.core import signing
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .models import Pointage, Tablette, heures_supplementaires
from .roles import ADMIN, EMPLOYE, employe_du_compte, journaliser, role_de, role_requis

COOKIE_TABLETTE = "tablette_alygo"
SEL_QR = "pointage.qr"


def etat_du_jour(emp, maintenant=None):
    """Règle : deux scans par jour. 1) entrée ; 2) sortie, seulement après HEURES_JOURNEE (8 h 00 min) de travail.
    Retourne un dictionnaire : etape ("entree" | "attente" | "sortie" | "termine"), entree, sortie, sortie_possible_a."""
    from datetime import datetime, time, timedelta
    maintenant = maintenant or timezone.now()
    debut = timezone.make_aware(datetime.combine(timezone.localdate(maintenant), time.min))
    du_jour = list(emp.pointages.filter(horodatage__gte=debut, horodatage__lte=maintenant).order_by("horodatage"))
    entree = next((p for p in du_jour if p.type == Pointage.ENTREE), None)
    sortie = next((p for p in du_jour if p.type == Pointage.SORTIE and entree and p.horodatage > entree.horodatage), None)
    if not entree:
        return {"etape": "entree", "entree": None, "sortie": None, "sortie_possible_a": None}
    possible = entree.horodatage + timedelta(hours=settings.HEURES_JOURNEE)
    if sortie:
        etape = "termine"
    else:
        etape = "sortie" if maintenant >= possible else "attente"
    return {"etape": etape, "entree": entree, "sortie": sortie, "sortie_possible_a": possible}


def _duree_lisible(secondes):
    h, reste = divmod(int(secondes), 3600)
    return f"{h} h {reste // 60:02d} min"


# ---------------------------------------------------------------- Tablette

def _tablette(request):
    jeton = request.COOKIES.get(COOKIE_TABLETTE, "")
    if not jeton:
        return None
    return Tablette.objects.filter(empreinte_jeton=hashlib.sha256(jeton.encode()).hexdigest(), active=True).first()


@role_requis(ADMIN)
def tablettes(request):
    return render(request, "pointage/tablettes.html", {"tablettes": Tablette.objects.all()})


@require_POST
@role_requis(ADMIN)
def activer_tablette(request):
    """À faire SUR la tablette : l'administrateur s'y connecte, appuie sur « Utiliser cet appareil comme tablette ».
    La tablette reçoit un jeton secret (cookie) et la session administrateur est fermée."""
    nom = " ".join(request.POST.get("nom", "").split())[:60] or "Tablette"
    jeton = secrets.token_urlsafe(32)
    t = Tablette.objects.create(nom=nom, empreinte_jeton=hashlib.sha256(jeton.encode()).hexdigest(),
                                adresse_ip=request.META.get("REMOTE_ADDR"))
    journaliser(request, "tablette_activee", f"tablette={t.nom}")
    logout(request)  # la tablette ne reste jamais connectée en administrateur
    r = redirect("tablette")
    r.set_cookie(COOKIE_TABLETTE, jeton, max_age=5 * 365 * 86400, httponly=True, secure=settings.HTTPS, samesite="Lax")
    return r


@require_POST
@role_requis(ADMIN)
def modifier_tablette(request, pk):
    t = get_object_or_404(Tablette, pk=pk)
    if request.POST.get("action") == "supprimer":
        journaliser(request, "tablette_supprimee", f"tablette={t.nom}")
        t.delete()
        messages.success(request, f"Tablette « {t.nom} » supprimée : elle n'affiche plus de QR code.")
    else:
        t.active = not t.active
        t.save(update_fields=["active"])
        journaliser(request, "tablette_modifiee", f"tablette={t.nom} ; active={t.active}")
        messages.success(request, f"Tablette « {t.nom} » {'réactivée' if t.active else 'désactivée'}.")
    return redirect("tablettes")


def tablette(request):
    """Écran de la tablette (aucun compte nécessaire, seulement le jeton)."""
    t = _tablette(request)
    if not t:
        return render(request, "pointage/tablette_inactive.html", status=403)
    return render(request, "pointage/tablette.html", {
        "tablette": t, "serveur_ms": int(timezone.now().timestamp() * 1000), "fuseau": settings.TIME_ZONE,
        "renouvellement": settings.QR_RENOUVELLEMENT_SECONDES, "heures_journee": f"{settings.HEURES_JOURNEE:g}",
    })


@role_requis(ADMIN)
def qr_admin(request):
    """Le QR code affiché directement dans l'espace administrateur (même écran que la tablette)."""
    return render(request, "pointage/tablette.html", {
        "mode_admin": True, "serveur_ms": int(timezone.now().timestamp() * 1000), "fuseau": settings.TIME_ZONE,
        "renouvellement": settings.QR_RENOUVELLEMENT_SECONDES, "heures_journee": f"{settings.HEURES_JOURNEE:g}",
    })


@role_requis(ADMIN)
def qr_admin_code(request):
    return _reponse_qr(request, {"a": request.user.pk})


def tablette_code(request):
    """Nouveau QR code (image SVG) pour la tablette."""
    t = _tablette(request)
    if not t:
        return JsonResponse({"ok": False}, status=403)
    Tablette.objects.filter(pk=t.pk).update(derniere_activite=timezone.now(), adresse_ip=request.META.get("REMOTE_ADDR"))
    return _reponse_qr(request, {"t": t.pk})


def _reponse_qr(request, origine):
    import segno

    code = signing.dumps({**origine, "n": secrets.token_hex(4)}, salt=SEL_QR, compress=True)
    url = request.build_absolute_uri(f"/scan/{code}/")
    svg = segno.make(url, error="m").svg_inline(border=2, dark="#111111", light="#ffffff", omitsize=True)
    r = JsonResponse({"ok": True, "svg": svg, "serveur_ms": int(timezone.now().timestamp() * 1000)})
    r["Cache-Control"] = "no-store"
    return r


def _lire_code(code, marge=0):
    """Retourne la tablette du QR code, ou None s'il est faux ou expiré."""
    try:
        donnees = signing.loads(code, salt=SEL_QR, max_age=settings.QR_VALIDITE_SECONDES + marge)
    except signing.BadSignature:  # comprend SignatureExpired
        return None
    if "a" in donnees:  # QR affiché par un administrateur connecté
        from django.contrib.auth import get_user_model
        admin = get_user_model().objects.filter(pk=donnees["a"], is_active=True).first()
        return admin if role_de(admin) == ADMIN else None
    return Tablette.objects.filter(pk=donnees.get("t"), active=True).first()


# ---------------------------------------------------------------- Scan par l'employé

@role_requis(EMPLOYE)
def scanner(request):
    """Lecteur de QR code intégré à l'application (caméra arrière du téléphone)."""
    emp = employe_du_compte(request.user)
    etat = etat_du_jour(emp) if emp else {"etape": "entree"}
    return render(request, "pointage/scanner.html", {"employe": emp, "etat": etat, "heures_journee": settings.HEURES_JOURNEE})


@role_requis(EMPLOYE)
def scan(request, code):
    """Page ouverte par le téléphone après avoir scanné le QR code. Elle enregistre le pointage toute seule."""
    from .models import Lieu
    from . import geo

    emp = employe_du_compte(request.user)
    t = _lire_code(code)
    if not emp or not emp.actif:
        probleme = "Ce compte n'est relié à aucun employé actif. Voyez l'administrateur."
    elif not t:
        probleme = "QR code expiré ou invalide. Scannez à nouveau le QR code affiché sur la tablette."
    else:
        probleme = None
    lieux = [{"nom": l.nom, "lat": l.latitude, "lon": l.longitude, "rayon": l.rayon_m}
             for l in Lieu.objects.filter(actif=True)]
    return render(request, "pointage/scan.html", {
        "employe": emp, "code": code, "probleme": probleme, "lieux": lieux, "precision_max": geo.PRECISION_MAX_M,
    })


@require_POST
@role_requis(EMPLOYE)
def scan_valider(request, code):
    from .views import _verifier_position

    emp = employe_du_compte(request.user)
    if not emp or not emp.actif:
        return JsonResponse({"ok": False, "message": "Ce compte n'est relié à aucun employé actif."}, status=403)
    # Marge de 2 minutes : le temps d'ouvrir la page et de trouver la position GPS
    t = _lire_code(code, marge=120)
    if not t:
        journaliser(request, "pointage_refuse", f"employe={emp.nom} ; raison=QR code expiré ou invalide")
        return JsonResponse({"ok": False, "message": "QR code expiré. Scannez à nouveau le QR code de la tablette."}, status=403)

    lieu, distance_lieu, probleme = _verifier_position(request)
    if probleme:
        journaliser(request, "pointage_refuse", f"employe={emp.nom} ; raison=position : {probleme}")
        return JsonResponse({"ok": False, "message": probleme}, status=403)

    maintenant = timezone.now()
    dernier = emp.dernier_pointage()
    if dernier and (maintenant - dernier.horodatage).total_seconds() < settings.POINTAGE_DELAI_MIN_SECONDES:
        return JsonResponse({"ok": False, "message": f"Déjà pointé à {timezone.localtime(dernier.horodatage):%H:%M:%S}."},
                            status=429)

    # Deux scans par jour : entrée, puis sortie après 8 h 00 min de travail
    etat = etat_du_jour(emp, maintenant)
    if etat["etape"] == "termine":
        return JsonResponse({"ok": False, "message": (
            f"Journée terminée : entrée à {timezone.localtime(etat['entree'].horodatage):%H:%M:%S}, "
            f"sortie à {timezone.localtime(etat['sortie'].horodatage):%H:%M:%S}. À demain !")}, status=409)
    if etat["etape"] == "attente":
        reste = (etat["sortie_possible_a"] - maintenant).total_seconds()
        return JsonResponse({"ok": False, "attente": True, "message": (
            f"Sortie possible à partir de {timezone.localtime(etat['sortie_possible_a']):%H:%M:%S} "
            f"({settings.HEURES_JOURNEE:g} h après votre entrée à {timezone.localtime(etat['entree'].horodatage):%H:%M:%S}). "
            f"Encore {_duree_lisible(reste + 59)}.")}, status=409)
    type_ = Pointage.ENTREE if etat["etape"] == "entree" else Pointage.SORTIE
    travaille = (maintenant - etat["entree"].horodatage).total_seconds() if type_ == Pointage.SORTIE else 0

    p = Pointage.objects.create(employe=emp, type=type_, horodatage=maintenant, source=Pointage.QR,
                                adresse_ip=request.META.get("REMOTE_ADDR"), lieu=lieu, distance_lieu_m=distance_lieu)
    local = timezone.localtime(p.horodatage)
    reponse = {"ok": True, "type": p.get_type_display(), "heure": f"{local:%H:%M:%S}", "date": f"{local:%d/%m/%Y}",
               "nom": emp.nom}
    if type_ == Pointage.ENTREE:
        reponse["message"] = f"Bonjour {emp.nom} — Entrée à {local:%H:%M:%S}" + (" (en retard)" if p.en_retard else "")
    else:
        sup = heures_supplementaires(travaille)
        reponse["message"] = f"Au revoir {emp.nom} — Sortie à {local:%H:%M:%S}"
        reponse["detail"] = f"Temps travaillé : {_duree_lisible(travaille)}" + (
            f" — dont {_duree_lisible(sup)} d'heures supplémentaires" if sup else "")
    return JsonResponse(reponse)

