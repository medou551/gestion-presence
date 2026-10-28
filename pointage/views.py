import ipaddress
from datetime import datetime, time, timedelta
from io import BytesIO

from django.conf import settings
from django.http import Http404, HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import geo, taches, visage
from .models import Employe, Lieu, Pointage, Service, resume_journee
from .roles import (ADMIN, EMPLOYE, employe_du_compte, employes_visibles, journaliser, pointages_visibles,
                    role_requis)

TAILLE_MAX_PHOTO = 5 * 1024 * 1024  # 5 Mo


def _est_une_image(fichier):
    """Vérifie la signature du fichier (JPEG ou PNG) sans dépendre de Pillow."""
    debut = fichier.read(8)
    fichier.seek(0)
    return debut.startswith(b"\xff\xd8\xff") or debut.startswith(b"\x89PNG\r\n\x1a\n")


def _type_image(donnees):
    return "image/png" if donnees.startswith(b"\x89PNG") else "image/jpeg"


def _erreur(message, status=400):
    return JsonResponse({"ok": False, "message": message}, status=status)


def _verifier_photo(photo):
    """Retourne un message d'erreur, ou None si la photo est acceptable."""
    if not photo:
        return "Photo manquante : autorisez la caméra."
    if photo.size > TAILLE_MAX_PHOTO:
        return "Photo trop volumineuse (5 Mo maximum)."
    if not _est_une_image(photo):
        return "Le fichier envoyé n'est pas une image valide."
    return None


def _duree(secondes):
    h, reste = divmod(int(secondes), 3600)
    m, s = divmod(reste, 60)
    return f"{h:02d}:{m:02d}:{s:02d}"


def _lire_date(valeur, defaut):
    try:
        return datetime.strptime(valeur, "%Y-%m-%d").date()
    except (TypeError, ValueError):
        return defaut


def _bornes_jour(jour):
    debut = timezone.make_aware(datetime.combine(jour, time.min))
    return debut, debut + timedelta(days=1)


# ---------------------------------------------------------------- Borne de pointage

@role_requis(ADMIN)
def borne(request):
    """Pointage sur un poste commun, ouvert par l'administrateur (ex. téléphone d'un employé en panne)."""
    employes = [{"id": e.id, "nom": e.nom, "poste": e.poste, "pin": e.demande_pin, "ref": e.a_reference}
                for e in Employe.objects.filter(actif=True)]
    return render(request, "pointage/borne.html", {
        "employes": employes,
        "serveur_ms": int(timezone.now().timestamp() * 1000),  # pour afficher l'heure du serveur
        "fuseau": settings.TIME_ZONE,
    })


def _refus(request, emp, message, status, raison):
    journaliser(request, "pointage_refuse", f"employe={emp.nom if emp else '?'} ; raison={raison}")
    return _erreur(message, status)


@require_POST
@role_requis(ADMIN)
def pointer(request):
    """Pointage sur le poste commun (administrateur) : on choisit le nom, puis le visage est vérifié."""
    employe_id = request.POST.get("employe", "").strip()
    if not employe_id.isdigit():
        return _erreur("Choisissez votre nom dans la liste.")
    emp = Employe.objects.filter(pk=int(employe_id), actif=True).first()
    return _enregistrer_pointage(request, emp, Pointage.BORNE, verifier_pin=True)


def _reseau_autorise(request):
    """Vrai si l'adresse du téléphone fait partie des réseaux autorisés (ou si aucune restriction n'est définie)."""
    reseaux = settings.POINTAGE_TELEPHONE_RESEAUX
    if not reseaux:
        return True
    try:
        ip = ipaddress.ip_address(request.META.get("REMOTE_ADDR", ""))
    except ValueError:
        return False
    for r in reseaux:
        try:
            if ip in ipaddress.ip_network(r, strict=False):
                return True
        except ValueError:
            continue
    return False


def _pointage_telephone_possible(request):
    """Retourne (employé, message d'erreur)."""
    if not settings.POINTAGE_TELEPHONE:
        return None, "Le pointage par téléphone est désactivé. Voyez l'administrateur."
    emp = employe_du_compte(request.user)
    if not emp or not emp.actif:
        return None, "Ce compte n'est relié à aucun employé actif. Voyez l'administrateur."
    if not _reseau_autorise(request):
        return emp, "Pointage refusé : connectez-vous au Wi-Fi du bureau pour pointer avec votre téléphone."
    return emp, None


@role_requis(EMPLOYE)
def pointer_telephone(request):
    """Page de pointage sur le téléphone de l'employé (son propre compte : pas de choix du nom)."""
    emp, probleme = _pointage_telephone_possible(request)
    dernier = emp.dernier_pointage() if emp else None
    aujourdhui = timezone.localdate()
    if dernier and timezone.localtime(dernier.horodatage).date() == aujourdhui and dernier.type == Pointage.ENTREE:
        prochain = "Sortie"
    else:
        prochain = "Entrée"
    return render(request, "pointage/pointer_telephone.html", {
        "employe": emp, "probleme": probleme, "prochain": prochain,
        "lieux": [{"nom": l.nom, "lat": l.latitude, "lon": l.longitude, "rayon": l.rayon_m}
                  for l in Lieu.objects.filter(actif=True)],
        "precision_max": geo.PRECISION_MAX_M,
        "dernier": dernier if dernier and timezone.localtime(dernier.horodatage).date() == aujourdhui else None,
        "serveur_ms": int(timezone.now().timestamp() * 1000), "fuseau": settings.TIME_ZONE,
    })


@require_POST
@role_requis(EMPLOYE)
def pointer_moi(request):
    """Pointage envoyé par le téléphone : l'employé est celui du compte connecté, jamais un autre."""
    emp, probleme = _pointage_telephone_possible(request)
    if probleme:
        if emp:
            journaliser(request, "pointage_refuse", f"employe={emp.nom} ; raison=téléphone hors du réseau autorisé")
        return _erreur(probleme, 403)
    lieu, distance_lieu, probleme = _verifier_position(request)
    if probleme:
        return _refus(request, emp, probleme, 403, f"position : {probleme}")
    return _enregistrer_pointage(request, emp, Pointage.TELEPHONE, verifier_pin=False,
                                 lieu=lieu, distance_lieu_m=distance_lieu)


def _verifier_position(request):
    """Si des lieux sont définis, le téléphone doit être à l'intérieur de l'un d'eux.
    Retourne (lieu, distance en m, message d'erreur)."""
    lieux = list(Lieu.objects.filter(actif=True))
    if not lieux:
        return None, None, None
    position = geo.lire_position(request.POST.get("latitude"), request.POST.get("longitude"),
                                 request.POST.get("precision"))
    if not position:
        return None, None, "Position introuvable : autorisez la localisation pour ce site et activez le GPS."
    lat, lon, precision = position
    if precision > geo.PRECISION_MAX_M:
        return None, None, (f"Position trop imprécise ({precision:.0f} m). Activez le GPS (localisation précise), "
                            "approchez-vous d'une fenêtre puis réessayez.")
    lieu, d = geo.lieu_le_plus_proche(lat, lon, lieux)
    if d > lieu.rayon_m:
        return None, None, (f"Vous êtes à {d:.0f} m de {lieu.nom}. Le pointage par téléphone n'est possible "
                            f"qu'à moins de {lieu.rayon_m} m.")
    return lieu, round(d, 1), None


def _enregistrer_pointage(request, emp, source, verifier_pin, **champs):
    """Contrôles communs à la borne et au téléphone, puis enregistrement à l'heure du serveur."""
    photo = request.FILES.get("photo")
    probleme = _verifier_photo(photo)
    if probleme:
        return _erreur(probleme)
    descripteur = visage.lire_descripteur(request.POST.get("descripteur"))
    if descripteur is None:
        return _erreur("Aucun visage détecté. Placez-vous bien face à la caméra.")

    if not emp:
        return _erreur("Employé introuvable.", 404)
    if not emp.a_reference:
        return _erreur(f"{emp.nom} n'a pas encore de photo de référence. Voyez le responsable.", 409)
    if verifier_pin and emp.demande_pin and not emp.verifier_pin(request.POST.get("pin", "").strip()):
        return _refus(request, emp, "Code PIN incorrect.", 403, "PIN incorrect")

    # 1) Le visage doit être celui de l'employé
    dist = visage.distance(descripteur, emp.descripteur)
    if dist > visage.seuil():
        return _refus(request, emp, f"Visage non reconnu : il ne correspond pas à la photo de référence de {emp.nom}.",
                      403, f"visage différent (distance {dist:.2f}) ; source={source}")

    # 2) ...et ne doit pas ressembler davantage à un autre employé (pas de pointage pour un collègue)
    autres = Employe.objects.filter(actif=True).exclude(pk=emp.pk).exclude(descripteur_chiffre="")
    autre, dist_autre = visage.plus_proche(descripteur, autres)
    if autre and dist_autre < dist and dist_autre <= visage.seuil():
        return _refus(request, emp, "Visage refusé : il ressemble davantage à un autre employé.", 403,
                      f"ressemble davantage à {autre.nom} ; source={source}")

    # 3) Pas de double pointage rapproché
    maintenant = timezone.now()
    dernier = emp.dernier_pointage()
    if dernier and (maintenant - dernier.horodatage).total_seconds() < settings.POINTAGE_DELAI_MIN_SECONDES:
        return _erreur(f"Déjà pointé à {timezone.localtime(dernier.horodatage):%H:%M:%S}. Réessayez dans une minute.", 429)

    # 4) Image unique : la même photo (même fichier) ne peut jamais servir deux fois
    empreinte = visage.empreinte_fichier(photo)
    if Pointage.objects.filter(empreinte=empreinte).exists():
        return _refus(request, emp, "Photo refusée : cette image a déjà été utilisée.", 409, "image déjà utilisée")

    # 5) Pas de photo réutilisée (copie de la photo de référence ou d'un ancien pointage)
    if dist < settings.SEUIL_DOUBLON:
        return _refus(request, emp, "Photo refusée : identique à la photo de référence. Utilisez la caméra en direct.",
                      409, "copie de la photo de référence")
    for ancien in emp.pointages.exclude(descripteur_chiffre="").order_by("-horodatage")[:200]:
        if visage.distance(descripteur, ancien.descripteur) < settings.SEUIL_DOUBLON:
            return _refus(request, emp, "Photo refusée : identique à un pointage précédent (doublon).", 409,
                          "copie d'un ancien pointage")

    # Alternance automatique : après une entrée du jour, le pointage suivant est une sortie
    meme_jour = dernier and timezone.localtime(dernier.horodatage).date() == timezone.localtime(maintenant).date()
    type_ = Pointage.SORTIE if (meme_jour and dernier.type == Pointage.ENTREE) else Pointage.ENTREE

    p = Pointage(employe=emp, type=type_, horodatage=maintenant, empreinte=empreinte, source=source,
                 distance=round(dist, 4), adresse_ip=request.META.get("REMOTE_ADDR"), **champs)
    p.descripteur = descripteur
    p.photo.save("pointage.jpg", photo, save=False)
    p.save()
    taches.purge_si_necessaire()

    local = timezone.localtime(p.horodatage)
    message = f"{'Bonjour' if type_ == 'E' else 'Au revoir'} {emp.nom} — {p.get_type_display()} à {local:%H:%M:%S}"
    if p.en_retard:
        message += " (en retard)"
    return JsonResponse({
        "ok": True, "message": message, "nom": emp.nom, "ressemblance": p.ressemblance,
        "type": p.get_type_display(), "heure": f"{local:%H:%M:%S}", "date": f"{local:%d/%m/%Y}",
    })


# ---------------------------------------------------------------- Tableau de bord

def _lignes_du_jour(jour, employes):
    lignes = []
    for emp in employes:
        entree, sortie, secondes, ouvert = resume_journee(emp, jour)
        if ouvert and jour == timezone.localdate():
            secondes += (timezone.now() - ouvert).total_seconds()  # temps écoulé depuis l'arrivée
        if not entree:
            statut = "Absent"
        elif ouvert and jour < timezone.localdate():
            statut = "Sortie manquante"   # oubli de pointage : à corriger par l'administrateur
        elif ouvert:
            statut = "Au travail"
        else:
            statut = "Parti"
        lignes.append({
            "employe": emp, "entree": entree, "sortie": sortie,
            "duree": _duree(secondes) if entree else "—",
            "statut": statut, "retard": bool(entree and entree.en_retard),
        })
    return lignes


def _filtre_service(request):
    """L'administrateur peut filtrer par service."""
    employes = employes_visibles(request.user).filter(actif=True).select_related("service")
    services = Service.objects.all()
    service_choisi = None
    sid = request.GET.get("service", "")
    if services and sid.isdigit():
        service_choisi = Service.objects.filter(pk=int(sid)).first()
        if service_choisi:
            employes = employes.filter(service=service_choisi)
    return employes, services, service_choisi


@role_requis(ADMIN)
def tableau(request):
    taches.purge_si_necessaire()
    aujourdhui = timezone.localdate()
    jour = _lire_date(request.GET.get("date"), aujourdhui)
    employes, services, service_choisi = _filtre_service(request)
    lignes = _lignes_du_jour(jour, employes)
    debut, fin = _bornes_jour(jour)
    journal = (pointages_visibles(request.user).filter(employe__in=employes, horodatage__range=(debut, fin))
               .select_related("employe", "saisi_par", "lieu"))
    stats = {
        "presents": sum(1 for l in lignes if l["statut"] != "Absent"),
        "absents": sum(1 for l in lignes if l["statut"] == "Absent"),
        "retards": sum(1 for l in lignes if l["retard"]),
        "total": len(lignes),
        "oublis": sum(1 for l in lignes if l["statut"] == "Sortie manquante"),
    }
    journaliser(request, "consultation_tableau",
                f"date={jour:%d/%m/%Y} ; service={service_choisi or 'tous'}")
    return render(request, "pointage/tableau.html", {
        "jour": jour, "veille": jour - timedelta(days=1), "lendemain": jour + timedelta(days=1),
        "est_aujourdhui": jour == aujourdhui, "lignes": lignes, "journal": journal, "stats": stats,
        "heure_arrivee": settings.HEURE_ARRIVEE, "services": services, "service_choisi": service_choisi,
        "conservation": settings.DUREE_CONSERVATION_PHOTOS_JOURS,
        "peut_corriger": True,
        "heure_actuelle": timezone.localtime().strftime("%H:%M"),
    })


def _classeur(titres_et_lignes):
    from openpyxl import Workbook
    from openpyxl.styles import Font, PatternFill

    wb = Workbook()
    entete, fond = Font(bold=True, color="FFFFFF"), PatternFill("solid", fgColor="1F4E78")
    for i, (titre, lignes) in enumerate(titres_et_lignes):
        ws = wb.active if i == 0 else wb.create_sheet()
        ws.title = titre
        for ligne in lignes:
            ws.append(ligne)
        for c in ws[1]:
            c.font, c.fill = entete, fond
        for col in ws.columns:
            ws.column_dimensions[col[0].column_letter].width = max(12, max(len(str(c.value or "")) for c in col) + 2)
        ws.freeze_panes = "A2"
    flux = BytesIO()
    wb.save(flux)
    return flux.getvalue()


def _reponse_excel(contenu, nom):
    r = HttpResponse(contenu, content_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
    r["Content-Disposition"] = f'attachment; filename="{nom}"'
    return r


@role_requis(ADMIN)
def export_excel(request):
    aujourdhui = timezone.localdate()
    du = _lire_date(request.GET.get("du"), aujourdhui.replace(day=1))
    au = _lire_date(request.GET.get("au"), aujourdhui)
    if au < du:
        du, au = au, du
    if (au - du).days > 366:
        du = au - timedelta(days=366)
    employes, _, service_choisi = _filtre_service(request)

    resume = [["Date", "Nom", "Service", "Arrivée", "Départ", "Durée (h:min:s)", "Statut", "Retard"]]
    jour = du
    while jour <= au:
        for l in _lignes_du_jour(jour, employes):
            resume.append([
                jour.strftime("%d/%m/%Y"), l["employe"].nom, str(l["employe"].service or ""),
                f"{timezone.localtime(l['entree'].horodatage):%H:%M:%S}" if l["entree"] else "",
                f"{timezone.localtime(l['sortie'].horodatage):%H:%M:%S}" if l["sortie"] else "",
                l["duree"] if l["entree"] else "", l["statut"], "Oui" if l["retard"] else "",
            ])
        jour += timedelta(days=1)

    journal = [["Date", "Heure", "Nom", "Service", "Type", "Origine", "Ressemblance (%)", "Adresse IP"]]
    debut, _ = _bornes_jour(du)
    _, fin = _bornes_jour(au)
    for p in (Pointage.objects.filter(employe__in=employes, horodatage__range=(debut, fin))
              .select_related("employe", "employe__service").order_by("horodatage")):
        local = timezone.localtime(p.horodatage)
        journal.append([f"{local:%d/%m/%Y}", f"{local:%H:%M:%S}", p.employe.nom, str(p.employe.service or ""),
                        p.get_type_display(), p.origine, p.ressemblance if p.ressemblance is not None else "", p.adresse_ip or ""])

    journaliser(request, "export_excel", f"du={du:%d/%m/%Y} ; au={au:%d/%m/%Y} ; service={service_choisi or 'tous'}")
    contenu = _classeur([("Résumé par jour", resume), ("Journal des pointages", journal)])
    return _reponse_excel(contenu, f"presence_{du:%Y%m%d}_{au:%Y%m%d}.xlsx")


# ---------------------------------------------------------------- Photos (déchiffrées à la volée)

def _envoyer_photo(champ):
    if not champ:
        raise Http404("Photo supprimée")
    donnees = champ.storage.lire(champ.name)
    r = HttpResponse(donnees, content_type=_type_image(donnees))
    r["Cache-Control"] = "no-store, private"
    r["Content-Disposition"] = "inline"
    return r


@role_requis(ADMIN, EMPLOYE)
def photo_pointage(request, pk):
    p = get_object_or_404(pointages_visibles(request.user), pk=pk)
    return _envoyer_photo(p.photo)


@role_requis(ADMIN, EMPLOYE)
def photo_reference(request, pk):
    e = get_object_or_404(employes_visibles(request.user), pk=pk)
    return _envoyer_photo(e.photo_reference)


# ---------------------------------------------------------------- Espace employé

def _mois(request):
    aujourdhui = timezone.localdate()
    try:
        a, m = map(int, request.GET.get("mois", "").split("-"))
        debut = aujourdhui.replace(year=a, month=m, day=1)
    except (ValueError, TypeError):
        debut = aujourdhui.replace(day=1)
    fin = (debut.replace(day=28) + timedelta(days=4)).replace(day=1)
    return debut, fin


@role_requis(EMPLOYE)
def mon_espace(request):
    emp = employe_du_compte(request.user)
    if not emp:
        return render(request, "pointage/aucun_role.html", {"message": "Ce compte n'est relié à aucun employé."})
    debut, fin = _mois(request)
    jours = []
    total = 0
    jour = debut
    aujourdhui = timezone.localdate()
    while jour < fin and jour <= aujourdhui:
        entree, sortie, secondes, ouvert = resume_journee(emp, jour)
        if ouvert and jour == aujourdhui:
            secondes += (timezone.now() - ouvert).total_seconds()
        if entree:
            total += secondes
            jours.append({"jour": jour, "entree": entree, "sortie": sortie, "duree": _duree(secondes),
                          "retard": entree.en_retard, "ouvert": bool(ouvert) and jour == aujourdhui,
                          "manquante": bool(ouvert) and jour < aujourdhui})
        jour += timedelta(days=1)
    jours.reverse()
    precedent = (debut - timedelta(days=1)).replace(day=1)
    return render(request, "pointage/mon_espace.html", {
        "employe": emp, "jours": jours, "total": _duree(total), "nb_jours": len(jours),
        "retards": sum(1 for j in jours if j["retard"]), "debut": debut,
        "precedent": precedent, "suivant": fin if fin <= aujourdhui else None,
        "conservation": settings.DUREE_CONSERVATION_PHOTOS_JOURS,
        "pointage_telephone": settings.POINTAGE_TELEPHONE,
    })


@role_requis(EMPLOYE)
def mes_donnees(request):
    """Droit d'accès : l'employé télécharge toutes les données le concernant."""
    emp = employe_du_compte(request.user)
    if not emp:
        raise Http404
    infos = [["Information", "Valeur"],
             ["Nom", emp.nom], ["Poste", emp.poste], ["Service", str(emp.service or "")],
             ["Code PIN défini", "Oui" if emp.demande_pin else "Non"],
             ["Photo de référence enregistrée", f"Oui, le {timezone.localtime(emp.reference_le):%d/%m/%Y}" if emp.reference_le else "Non"],
             ["Signature du visage enregistrée (chiffrée)", "Oui" if emp.descripteur_chiffre else "Non"],
             ["Conservation des photos de pointage", f"{settings.DUREE_CONSERVATION_PHOTOS_JOURS} jours"],
             ["Compte", request.user.get_username()],
             ["Export généré le", f"{timezone.localtime():%d/%m/%Y %H:%M:%S}"]]
    pts = [["Date", "Heure", "Type", "Origine", "Photo conservée", "Ressemblance (%)", "Adresse IP"]]
    for p in emp.pointages.order_by("horodatage"):
        local = timezone.localtime(p.horodatage)
        pts.append([f"{local:%d/%m/%Y}", f"{local:%H:%M:%S}", p.get_type_display(), p.origine,
                    "Oui" if p.photo else ("—" if p.manuel else "Non (supprimée)"), p.ressemblance if p.ressemblance is not None else "",
                    p.adresse_ip or ""])
    journaliser(request, "export_donnees_personnelles", f"employe={emp.nom}")
    return _reponse_excel(_classeur([("Mes informations", infos), ("Mes pointages", pts)]),
                          f"mes_donnees_{timezone.localdate():%Y%m%d}.xlsx")


def diagnostic(request):
    """Page publique (aucune donnée) qui vérifie la compatibilité du navigateur : caméra, reconnaissance, cookies."""
    return render(request, "pointage/diagnostic.html")


def aucun_role(request):
    return render(request, "pointage/aucun_role.html", {
        "message": "Ce compte n'a pas de rôle. Demandez à l'administrateur de vous en attribuer un."})


def refus_403(request, exception=None):
    return render(request, "pointage/403.html", status=403)
