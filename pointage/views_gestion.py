"""Pages de gestion (administrateur) : employés, comptes, lieux et journal d'audit."""
import secrets
import string

from django.contrib import messages
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from datetime import datetime

from django.utils import timezone
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from . import geo, visage
from .models import Employe, JournalAudit, Lieu, Pointage, Profil, Service
from .roles import ADMIN, journaliser, role_de, role_requis
from .views import _erreur, _verifier_photo

User = get_user_model()


# ---------------------------------------------------------------- Employés

@role_requis(ADMIN)
def employes(request):
    liste = Employe.objects.select_related("service").all()
    return render(request, "pointage/employes.html", {
        "employes": liste,
        "services": Service.objects.all(),
        "sans_reference": sum(1 for e in liste if e.actif and not e.a_reference),
    })


@require_POST
@role_requis(ADMIN)
def ajouter_service(request):
    nom = " ".join(request.POST.get("nom", "").split())[:100]
    if nom:
        s, cree = Service.objects.get_or_create(nom=nom)
        if cree:
            journaliser(request, "service_cree", nom)
            messages.success(request, f"Service « {nom} » ajouté.")
    return redirect("employes")


@require_POST
@role_requis(ADMIN)
def supprimer_service(request, pk):
    service = get_object_or_404(Service, pk=pk)
    nb_emp = service.employes.count()
    nb_chefs = Profil.objects.filter(service=service).count()
    if nb_emp or nb_chefs:
        messages.error(request, f"Impossible de supprimer « {service.nom} » : {nb_emp} employé(s) et {nb_chefs} chef(s) "
                                "y sont rattachés. Changez d'abord leur service.")
    else:
        journaliser(request, "service_supprime", service.nom)
        messages.success(request, f"Service « {service.nom} » supprimé.")
        service.delete()
    return redirect("employes")


def _lire_pin(valeur):
    pin = (valeur or "").strip()
    if pin and (not pin.isdigit() or not 4 <= len(pin) <= 8):
        raise ValidationError("Le code PIN doit contenir 4 à 8 chiffres.")
    return pin


@require_POST
@role_requis(ADMIN)
def enregistrer_employe(request):
    """Crée un employé (ou met à jour sa photo de référence) avec la signature de son visage."""
    employe_id = request.POST.get("employe", "").strip()
    photo = request.FILES.get("photo")
    probleme = _verifier_photo(photo)
    if probleme:
        return _erreur(probleme)
    descripteur = visage.lire_descripteur(request.POST.get("descripteur"))
    if descripteur is None:
        return _erreur("Aucun visage détecté sur la photo.")

    if employe_id:
        if not employe_id.isdigit():
            return _erreur("Employé introuvable.", 404)
        emp = Employe.objects.filter(pk=int(employe_id)).first()
        if emp is None:
            return _erreur("Employé introuvable.", 404)
    else:
        nom = " ".join(request.POST.get("nom", "").split())[:120]
        if not nom:
            return _erreur("Le nom est obligatoire.")
        if Employe.objects.filter(nom__iexact=nom).exists():
            return _erreur(f"Un employé nommé « {nom} » existe déjà.", 409)
        try:
            pin = _lire_pin(request.POST.get("pin"))
        except ValidationError as e:
            return _erreur(e.messages[0])
        sid = request.POST.get("service", "")
        emp = Employe(nom=nom, poste=request.POST.get("poste", "").strip()[:100],
                      service=Service.objects.filter(pk=sid).first() if sid.isdigit() else None)
        if pin:
            emp.definir_pin(pin)

    # Unicité : ce visage ne doit pas déjà appartenir à un autre employé
    autres = Employe.objects.exclude(descripteur_chiffre="")
    if emp.pk:
        autres = autres.exclude(pk=emp.pk)
    autre, dist = visage.plus_proche(descripteur, autres)
    if autre and dist <= visage.seuil():
        journaliser(request, "enrolement_refuse", f"employe={emp.nom} ; visage déjà enregistré pour {autre.nom}")
        return _erreur(f"Ce visage est déjà enregistré pour « {autre.nom} ». Un employé = un visage.", 409)

    nouveau = not emp.pk
    ancienne = emp.photo_reference.name if emp.pk and emp.photo_reference else None
    emp.descripteur = descripteur
    emp.reference_le = timezone.now()
    emp.photo_reference.save("reference.jpg", photo, save=False)
    emp.save()
    if ancienne and ancienne != emp.photo_reference.name:
        emp.photo_reference.storage.delete(ancienne)
    journaliser(request, "employe_cree" if nouveau else "photo_reference_changee", f"employe={emp.nom}")
    return JsonResponse({"ok": True, "message": f"Photo de référence enregistrée pour {emp.nom}.", "id": emp.pk})


@role_requis(ADMIN)
def modifier_employe(request, pk):
    emp = get_object_or_404(Employe, pk=pk)
    erreurs = []
    if request.method == "POST":
        nom = " ".join(request.POST.get("nom", "").split())[:120]
        if not nom:
            erreurs.append("Le nom est obligatoire.")
        elif Employe.objects.filter(nom__iexact=nom).exclude(pk=emp.pk).exists():
            erreurs.append(f"Un autre employé s'appelle déjà « {nom} ».")
        try:
            pin = _lire_pin(request.POST.get("pin"))
        except ValidationError as e:
            erreurs.append(e.messages[0])
            pin = ""
        if not erreurs:
            avant = f"{emp.nom} / {emp.poste} / {emp.service} / actif={emp.actif}"
            emp.nom = nom
            emp.poste = request.POST.get("poste", "").strip()[:100]
            sid = request.POST.get("service", "")
            emp.service = Service.objects.filter(pk=sid).first() if sid.isdigit() else None
            emp.actif = request.POST.get("actif") == "on"
            if request.POST.get("supprimer_pin") == "on":
                emp.code_pin = ""
            elif pin:
                emp.definir_pin(pin)
            emp.save()
            journaliser(request, "employe_modifie",
                        f"avant: {avant} ; après: {emp.nom} / {emp.poste} / {emp.service} / actif={emp.actif}")
            messages.success(request, f"{emp.nom} : modifications enregistrées.")
            return redirect("employes")
    compte = getattr(emp, "compte", None)
    return render(request, "pointage/employe_modifier.html", {
        "emp": emp, "services": Service.objects.all(), "erreurs": erreurs, "compte": compte,
        "identifiant_propose": "" if compte else _identifiant_propose(emp.nom),
        "adresse_site": request.build_absolute_uri("/connexion/")})


def _identifiant_propose(nom):
    """« Mohamed Ould Ahmed » → « mohamed.ould.ahmed » (sans accents), rendu unique."""
    import unicodedata
    base = unicodedata.normalize("NFKD", nom).encode("ascii", "ignore").decode().lower()
    base = ".".join("".join(c for c in mot if c.isalnum()) for mot in base.split()).strip(".")[:30] or "employe"
    identifiant, n = base, 2
    while User.objects.filter(username__iexact=identifiant).exists():
        identifiant, n = f"{base}{n}", n + 1
    return identifiant


@require_POST
@role_requis(ADMIN)
def creer_acces_employe(request, pk):
    """Crée le compte « Employé » qui permet de pointer avec son téléphone et de voir son historique."""
    emp = get_object_or_404(Employe, pk=pk)
    if getattr(emp, "compte", None):
        messages.error(request, f"{emp.nom} a déjà un compte : {emp.compte.utilisateur.username}.")
        return redirect("modifier_employe", pk=emp.pk)
    identifiant = request.POST.get("identifiant", "").strip()[:150] or _identifiant_propose(emp.nom)
    if not all(c.isalnum() or c in "._-@+" for c in identifiant):
        messages.error(request, "Identifiant invalide : lettres, chiffres et . _ - uniquement.")
        return redirect("modifier_employe", pk=emp.pk)
    if User.objects.filter(username__iexact=identifiant).exists():
        messages.error(request, f"L'identifiant « {identifiant} » est déjà utilisé.")
        return redirect("modifier_employe", pk=emp.pk)
    mdp = _mdp_temporaire()
    with transaction.atomic():
        user = User.objects.create_user(username=identifiant, password=mdp)
        _appliquer_role(user, Profil.EMPLOYE, None, emp)
    journaliser(request, "compte_cree", f"compte={identifiant} ; role=employe ; employe={emp.nom} ; depuis la fiche employé")
    messages.success(request, f"Accès créé pour {emp.nom} — identifiant : {identifiant} — mot de passe temporaire : {mdp}  "
                              "(notez-le maintenant, il ne sera plus affiché ; l'employé le changera à la première connexion).")
    return redirect("modifier_employe", pk=emp.pk)


@require_POST
@role_requis(ADMIN)
def effacer_biometrie(request, pk):
    """Pour un employé qui quitte l'entreprise : supprime photos et signatures, garde les heures."""
    emp = get_object_or_404(Employe, pk=pk)
    n = emp.effacer_biometrie()
    emp.actif = False
    emp.save(update_fields=["actif"])
    journaliser(request, "biometrie_effacee", f"employe={emp.nom} ; {n} photo(s) de pointage supprimée(s)")
    messages.success(request, f"Données biométriques de {emp.nom} effacées ({n} photo(s) de pointage). "
                              "L'employé est désactivé ; ses heures sont conservées.")
    return redirect("employes")


@require_POST
@role_requis(ADMIN)
def supprimer_employe(request, pk):
    """Effacement complet : employé, photos, pointages et compte associé."""
    emp = get_object_or_404(Employe, pk=pk)
    if request.POST.get("confirmation", "").strip() != emp.nom:
        messages.error(request, "Suppression annulée : le nom saisi ne correspond pas.")
        return redirect("modifier_employe", pk=emp.pk)
    nom, n = emp.nom, emp.pointages.count()
    with transaction.atomic():
        compte = getattr(emp, "compte", None)
        if compte:
            compte.utilisateur.delete()
        emp.effacer_biometrie()
        emp.delete()
    journaliser(request, "employe_supprime", f"employe={nom} ; {n} pointage(s) supprimé(s)")
    messages.success(request, f"{nom} et toutes ses données ont été supprimés définitivement.")
    return redirect("employes")


# ---------------------------------------------------------------- Comptes

def _mdp_temporaire():
    alphabet = string.ascii_letters + string.digits
    while True:
        mdp = "".join(secrets.choice(alphabet) for _ in range(12))
        if any(c.isdigit() for c in mdp) and any(c.isupper() for c in mdp) and any(c.islower() for c in mdp):
            return mdp


def _appliquer_role(user, role, service, employe):
    user.is_staff = user.is_superuser = (role == ADMIN)
    user.save()
    profil, _ = Profil.objects.get_or_create(utilisateur=user, defaults={"role": role})
    profil.role = role
    profil.service = None
    profil.employe = employe if role == Profil.EMPLOYE else None
    profil.save()
    return profil


def _valider_role(request, user=None):
    role = request.POST.get("role", "")
    if role not in dict(Profil.ROLES):
        return None, None, None, "Choisissez un rôle."
    sid, eid = request.POST.get("service", ""), request.POST.get("employe", "")
    service = Service.objects.filter(pk=sid).first() if sid.isdigit() else None
    employe = Employe.objects.filter(pk=eid).first() if eid.isdigit() else None
    if role == Profil.EMPLOYE:
        if not employe:
            return None, None, None, "Un compte employé doit être relié à un employé."
        deja = Profil.objects.filter(employe=employe)
        if user:
            deja = deja.exclude(utilisateur=user)
        if deja.exists():
            return None, None, None, f"{employe.nom} a déjà un compte."
    return role, service, employe, None


@role_requis(ADMIN)
def comptes(request):
    mdp_affiche = None
    if request.method == "POST":
        identifiant = request.POST.get("identifiant", "").strip()[:150]
        role, service, employe, erreur = _valider_role(request)
        if not erreur and not identifiant:
            erreur = "L'identifiant est obligatoire."
        if not erreur and User.objects.filter(username__iexact=identifiant).exists():
            erreur = f"L'identifiant « {identifiant} » est déjà utilisé."
        if erreur:
            messages.error(request, erreur)
        else:
            mdp = _mdp_temporaire()
            with transaction.atomic():
                user = User.objects.create_user(username=identifiant, password=mdp)
                _appliquer_role(user, role, service, employe)
            journaliser(request, "compte_cree",
                        f"compte={identifiant} ; role={role} ; service={service or ''} ; employe={employe or ''}")
            mdp_affiche = (identifiant, mdp)
    utilisateurs = User.objects.select_related("profil", "profil__service", "profil__employe").order_by("username")
    return render(request, "pointage/comptes.html", {
        "utilisateurs": utilisateurs, "roles": Profil.ROLES, "services": Service.objects.all(),
        "employes_sans_compte": Employe.objects.filter(compte__isnull=True, actif=True),
        "employes": Employe.objects.all(), "mdp_affiche": mdp_affiche,
    })


@require_POST
@role_requis(ADMIN)
def modifier_compte(request, pk):
    user = get_object_or_404(User, pk=pk)
    action = request.POST.get("action")
    if user == request.user and action in ("desactiver", "role", "supprimer"):
        messages.error(request, "Vous ne pouvez pas modifier votre propre rôle ou désactiver votre propre compte.")
        return redirect("comptes")

    if action == "reinitialiser":
        mdp = _mdp_temporaire()
        user.set_password(mdp)
        user.save()
        profil, _ = Profil.objects.get_or_create(utilisateur=user, defaults={"role": role_de(user) or Profil.EMPLOYE})
        profil.doit_changer_mdp = True
        profil.save()
        journaliser(request, "mot_de_passe_reinitialise", f"compte={user.username}")
        messages.success(request, f"Nouveau mot de passe temporaire pour « {user.username} » : {mdp}  — "
                                  "notez-le maintenant, il ne sera plus affiché. Il devra être changé à la première connexion.")
    elif action in ("desactiver", "activer"):
        user.is_active = action == "activer"
        user.save()
        journaliser(request, f"compte_{'active' if user.is_active else 'desactive'}", f"compte={user.username}")
        messages.success(request, f"Compte « {user.username} » {'activé' if user.is_active else 'désactivé'}.")
    elif action == "supprimer":
        if user.is_superuser and not User.objects.filter(is_superuser=True, is_active=True).exclude(pk=user.pk).exists():
            messages.error(request, "Impossible de supprimer le dernier administrateur.")
        elif request.POST.get("confirmation", "").strip() != user.username:
            messages.error(request, "Suppression annulée : l'identifiant saisi ne correspond pas.")
        else:
            nom = user.username
            journaliser(request, "compte_supprime", f"compte={nom}")
            user.delete()
            messages.success(request, f"Compte « {nom} » supprimé. (L'employé et ses pointages, s'il y en a, sont conservés.)")
    elif action == "role":
        role, service, employe, erreur = _valider_role(request, user)
        if erreur:
            messages.error(request, erreur)
        else:
            _appliquer_role(user, role, service, employe)
            journaliser(request, "role_modifie", f"compte={user.username} ; role={role} ; service={service or ''} ; employe={employe or ''}")
            messages.success(request, f"Rôle de « {user.username} » modifié.")
    return redirect("comptes")


# ---------------------------------------------------------------- Lieux de pointage (téléphone)

@role_requis(ADMIN)
def lieux(request):
    """Définir où le pointage par téléphone est autorisé : un point GPS et un rayon (20 m par défaut)."""
    if request.method == "POST":
        action = request.POST.get("action", "ajouter")
        if action == "ajouter":
            nom = " ".join(request.POST.get("nom", "").split())[:100]
            position = geo.lire_position(request.POST.get("latitude"), request.POST.get("longitude"),
                                         request.POST.get("precision"))
            try:
                rayon = int(request.POST.get("rayon", "20"))
            except ValueError:
                rayon = 0
            if not nom:
                messages.error(request, "Donnez un nom au lieu.")
            elif not position:
                messages.error(request, "Position manquante : appuyez sur « Utiliser ma position actuelle » "
                                        "et autorisez la localisation.")
            elif not 5 <= rayon <= 1000:
                messages.error(request, "Le rayon doit être compris entre 5 et 1000 mètres.")
            else:
                lat, lon, precision = position
                lieu = Lieu.objects.create(nom=nom, latitude=lat, longitude=lon, rayon_m=rayon)
                journaliser(request, "lieu_cree", f"lieu={nom} ; rayon={rayon} m ; précision GPS={precision:.0f} m")
                messages.success(request, f"Lieu « {nom} » enregistré : pointage par téléphone accepté à moins de {rayon} m.")
                if precision > rayon:
                    messages.warning(request, f"Attention : la position a été prise avec une précision de {precision:.0f} m. "
                                              "Pour plus d'exactitude, refaites-la dehors ou près d'une fenêtre, GPS activé.")
        else:
            lieu = get_object_or_404(Lieu, pk=request.POST.get("lieu") if str(request.POST.get("lieu", "")).isdigit() else 0)
            if action == "rayon":
                try:
                    rayon = int(request.POST.get("rayon", ""))
                except ValueError:
                    rayon = 0
                if 5 <= rayon <= 1000:
                    lieu.rayon_m = rayon
                    lieu.save(update_fields=["rayon_m"])
                    journaliser(request, "lieu_modifie", f"lieu={lieu.nom} ; rayon={rayon} m")
                    messages.success(request, f"« {lieu.nom} » : rayon de {rayon} m.")
                else:
                    messages.error(request, "Le rayon doit être compris entre 5 et 1000 mètres.")
            elif action in ("activer", "desactiver"):
                lieu.actif = action == "activer"
                lieu.save(update_fields=["actif"])
                journaliser(request, "lieu_modifie", f"lieu={lieu.nom} ; actif={lieu.actif}")
                messages.success(request, f"« {lieu.nom} » {'activé' if lieu.actif else 'désactivé'}.")
            elif action == "supprimer":
                journaliser(request, "lieu_supprime", f"lieu={lieu.nom}")
                messages.success(request, f"Lieu « {lieu.nom} » supprimé.")
                lieu.delete()
        return redirect("lieux")
    return render(request, "pointage/lieux.html", {
        "lieux": Lieu.objects.all(), "precision_max": geo.PRECISION_MAX_M})


# ---------------------------------------------------------------- Journal d'audit

LIBELLES_ACTIONS = {
    "connexion_reussie": "Connexion", "connexion_echouee": "Échec de connexion", "connexion_bloquee": "Connexion bloquée",
    "deconnexion": "Déconnexion", "deconnexion_inactivite": "Déconnexion (inactivité)",
    "mot_de_passe_change": "Mot de passe changé", "mot_de_passe_reinitialise": "Mot de passe réinitialisé",
    "acces_refuse": "Accès refusé", "consultation_tableau": "Consultation du tableau", "export_excel": "Export Excel",
    "export_donnees_personnelles": "Export de ses données", "pointage_refuse": "Pointage refusé",
    "employe_cree": "Employé créé", "employe_modifie": "Employé modifié", "photo_reference_changee": "Photo de référence changée",
    "enrolement_refuse": "Enregistrement refusé", "biometrie_effacee": "Biométrie effacée", "employe_supprime": "Employé supprimé",
    "service_cree": "Service créé", "compte_cree": "Compte créé", "compte_active": "Compte activé",
    "compte_desactive": "Compte désactivé", "role_modifie": "Rôle modifié", "purge_photos": "Purge des photos",
    "sauvegarde": "Sauvegarde", "sauvegarde_echec": "Sauvegarde échouée", "consultation_audit": "Consultation du journal",
    "service_supprime": "Service supprimé", "compte_supprime": "Compte supprimé",
    "tablette_activee": "Tablette activée", "tablette_modifiee": "Tablette modifiée", "tablette_supprimee": "Tablette supprimée",
    "lieu_cree": "Lieu ajouté", "lieu_modifie": "Lieu modifié", "lieu_supprime": "Lieu supprimé",
    "pointage_manuel_ajoute": "Correction ajoutée", "pointage_manuel_supprime": "Correction supprimée",
}


@role_requis(ADMIN)
def audit(request):
    lignes = JournalAudit.objects.all()
    action = request.GET.get("action", "")
    qui = request.GET.get("qui", "").strip()
    if action:
        lignes = lignes.filter(action=action)
    if qui:
        lignes = lignes.filter(nom_utilisateur__icontains=qui)
    page = Paginator(lignes, 50).get_page(request.GET.get("page"))
    roles = dict(Profil.ROLES)
    for l in page:
        l.libelle = LIBELLES_ACTIONS.get(l.action, l.action)
        l.role_libelle = roles.get(l.role, l.role)
    integre, info = JournalAudit.verifier_integrite()
    journaliser(request, "consultation_audit")
    return render(request, "pointage/audit.html", {
        "page": page, "actions": sorted(LIBELLES_ACTIONS.items(), key=lambda x: x[1]),
        "action": action, "qui": qui, "integre": integre, "info": info,
    })


# ---------------------------------------------------------------- Corrections manuelles (oublis de pointage)

def _retour_tableau(request):
    suivant = request.POST.get("suivant", "")
    if suivant and url_has_allowed_host_and_scheme(suivant, allowed_hosts={request.get_host()}):
        return redirect(suivant)
    return redirect("tableau")


@require_POST
@role_requis(ADMIN)
def ajouter_pointage_manuel(request):
    """Ajoute une entrée ou une sortie oubliée. Motif obligatoire, journalisé, marqué « manuel »."""
    eid = request.POST.get("employe", "")
    emp = Employe.objects.filter(pk=eid).first() if eid.isdigit() else None
    type_ = request.POST.get("type", "")
    motif = " ".join(request.POST.get("motif", "").split())[:200]
    quand = None
    texte = f"{request.POST.get('date', '').strip()} {request.POST.get('heure', '').strip()}"
    for format_ in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d %H:%M"):
        try:
            quand = timezone.make_aware(datetime.strptime(texte, format_))
            break
        except ValueError:
            continue

    erreur = None
    if not emp:
        erreur = "Choisissez l'employé."
    elif type_ not in (Pointage.ENTREE, Pointage.SORTIE):
        erreur = "Choisissez entrée ou sortie."
    elif not quand:
        erreur = "Date ou heure invalide."
    elif quand > timezone.now():
        erreur = "Impossible d'ajouter un pointage dans le futur."
    elif len(motif) < 5:
        erreur = "Indiquez le motif de la correction (5 caractères minimum)."
    elif emp.pointages.filter(horodatage=quand).exists():
        erreur = "Un pointage existe déjà à cette heure exacte."
    if erreur:
        messages.error(request, f"Correction non enregistrée : {erreur}")
        return _retour_tableau(request)

    p = Pointage.objects.create(employe=emp, type=type_, horodatage=quand, manuel=True, motif=motif,
                                saisi_par=request.user, adresse_ip=request.META.get("REMOTE_ADDR"))
    journaliser(request, "pointage_manuel_ajoute",
                f"employe={emp.nom} ; {p.get_type_display()} le {timezone.localtime(quand):%d/%m/%Y à %H:%M:%S} ; motif={motif}")
    messages.success(request, f"{p.get_type_display()} de {emp.nom} ajoutée le {timezone.localtime(quand):%d/%m/%Y à %H:%M}.")
    return _retour_tableau(request)


@require_POST
@role_requis(ADMIN)
def supprimer_pointage_manuel(request, pk):
    """Seules les corrections manuelles peuvent être supprimées ; les pointages de la borne sont intouchables."""
    p = get_object_or_404(Pointage, pk=pk, manuel=True)
    journaliser(request, "pointage_manuel_supprime",
                f"employe={p.employe.nom} ; {p.get_type_display()} du {timezone.localtime(p.horodatage):%d/%m/%Y %H:%M:%S} ; motif={p.motif}")
    messages.success(request, f"Correction supprimée ({p.employe.nom}, {p.get_type_display()} de {timezone.localtime(p.horodatage):%H:%M}).")
    p.delete()
    return _retour_tableau(request)
