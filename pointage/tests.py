import json
import random
import shutil
import tempfile
import time
from datetime import timedelta
from pathlib import Path

from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.files.base import ContentFile
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone

from . import chiffrement, taches, visage
from .models import Employe, JournalAudit, Pointage, Profil, Service

MEDIA_TEST = tempfile.mkdtemp()
SAUV_TEST = tempfile.mkdtemp()
JPEG = b"\xff\xd8\xff\xe0"


def photo(contenu=None):
    """Petit fichier JPEG (signature FF D8 FF). Contenu aléatoire = fichier unique."""
    contenu = contenu if contenu is not None else random.randbytes(200)
    return SimpleUploadedFile("p.jpg", JPEG + contenu, content_type="image/jpeg")


def signature(graine):
    r = random.Random(graine)
    return [r.uniform(-0.2, 0.2) for _ in range(128)]


def variante(sig, bruit=0.012, graine=0):
    """Même personne, autre photo : petite variation (distance ≈ 0,1)."""
    r = random.Random(graine)
    return [v + r.uniform(-bruit, bruit) * 2 for v in sig]


ALI, FATOU, OUMAR = signature(1), signature(2), signature(3)


REGLAGES = dict(MEDIA_ROOT=MEDIA_TEST, DOSSIER_SAUVEGARDES=SAUV_TEST, POINTAGE_DELAI_MIN_SECONDES=60,
                SEUIL_RECONNAISSANCE=0.5, SEUIL_DOUBLON=0.02, DUREE_CONSERVATION_PHOTOS_JOURS=30)


class Donnees:
    @classmethod
    def tearDownClass(cls):
        super().tearDownClass()
        shutil.rmtree(MEDIA_TEST, ignore_errors=True)
        shutil.rmtree(SAUV_TEST, ignore_errors=True)

    def setUp(self):
        cache.clear()
        self.compta = Service.objects.create(nom="Comptabilité")
        self.accueil = Service.objects.create(nom="Accueil")
        self.ali = self.creer_employe("Ali Ould Ahmed", ALI, self.compta)
        self.fatou = self.creer_employe("Fatou Ba", FATOU, self.accueil, pin="1234")
        self.oumar = self.creer_employe("Oumar Diallo", OUMAR, self.compta)

    def creer_employe(self, nom, sig, service=None, pin=None):
        e = Employe(nom=nom, service=service, reference_le=timezone.now())
        e.descripteur = sig
        if pin:
            e.definir_pin(pin)
        e.photo_reference.save("ref.jpg", ContentFile(JPEG + nom.encode()), save=False)
        e.save()
        return e

    def compte(self, nom, role, service=None, employe=None, changer=False):
        if role == Profil.ADMIN:
            u = User.objects.create_superuser(nom, "", "MotDePasse-Solide-1")
        else:
            u = User.objects.create_user(nom, password="MotDePasse-Solide-1")
        Profil.objects.create(utilisateur=u, role=role, service=service, employe=employe, doit_changer_mdp=changer)
        return u

    def connecter(self, role, **kw):
        u = self.compte(f"{role}_{random.randint(0, 10**9)}", role, **kw)
        self.client.force_login(u)
        return u

    def pointer(self, emp, sig, pin="", fichier=None):
        return self.client.post("/pointer/", {
            "employe": emp.id, "pin": pin, "descripteur": json.dumps(sig), "photo": fichier or photo(),
        })

    def vieillir(self, minutes=5):
        Pointage.objects.update(horodatage=timezone.now() - timedelta(minutes=minutes))


@override_settings(**REGLAGES)
class Base(Donnees, TestCase):
    pass


# =========================================================================== Pointage

class PointageTests(Base):
    def setUp(self):
        super().setUp()
        self.connecter(Profil.ADMIN)  # poste de pointage commun, ouvert par l'administrateur

    def test_bon_visage_accepte(self):
        r = self.pointer(self.ali, variante(ALI))
        self.assertEqual(r.status_code, 200, r.content)
        self.assertRegex(r.json()["heure"], r"^\d{2}:\d{2}:\d{2}$")
        p = Pointage.objects.get()
        self.assertEqual(p.type, "E")
        self.assertEqual(len(p.empreinte), 64)

    def test_alternance_entree_sortie(self):
        self.pointer(self.ali, variante(ALI, graine=1))
        self.vieillir()
        self.assertEqual(self.pointer(self.ali, variante(ALI, graine=2)).json()["type"], "Sortie")

    def test_visage_d_une_autre_personne_refuse_et_journalise(self):
        r = self.pointer(self.ali, signature(99))
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Pointage.objects.exists())
        self.assertTrue(JournalAudit.objects.filter(action="pointage_refuse", details__contains="Ali").exists())

    def test_pointer_pour_un_collegue_refuse(self):
        self.assertEqual(self.pointer(self.ali, variante(OUMAR)).status_code, 403)

    def test_signature_invalide_refusee(self):
        for mauvais in ["", "abc", json.dumps([0.1] * 10), json.dumps([0.0] * 128), json.dumps(["x"] * 128)]:
            r = self.client.post("/pointer/", {"employe": self.ali.id, "descripteur": mauvais, "photo": photo()})
            self.assertEqual(r.status_code, 400, mauvais)

    def test_meme_fichier_refuse_deux_fois(self):
        contenu = b"meme-image" * 20
        self.pointer(self.ali, variante(ALI, graine=1), fichier=photo(contenu))
        self.vieillir()
        r = self.pointer(self.ali, variante(ALI, graine=2), fichier=photo(contenu))
        self.assertEqual(r.status_code, 409)

    def test_copie_de_la_photo_de_reference_refusee(self):
        self.assertEqual(self.pointer(self.ali, list(ALI)).status_code, 409)

    def test_ancienne_photo_reutilisee_refusee(self):
        sig = variante(ALI, graine=7)
        self.pointer(self.ali, sig)
        self.vieillir(60 * 24)
        r = self.pointer(self.ali, [v + 0.0001 for v in sig])
        self.assertEqual(r.status_code, 409)
        self.assertIn("doublon", r.json()["message"])

    def test_double_clic_bloque(self):
        self.pointer(self.ali, variante(ALI, graine=1))
        self.assertEqual(self.pointer(self.ali, variante(ALI, graine=2)).status_code, 429)

    def test_pin(self):
        self.assertEqual(self.pointer(self.fatou, variante(FATOU, graine=1)).status_code, 403)
        self.assertEqual(self.pointer(self.fatou, variante(FATOU, graine=3), pin="1234").status_code, 200)

    def test_borne_ne_divulgue_aucun_secret(self):
        r = self.client.get("/")
        self.assertContains(r, "Ali Ould Ahmed")
        self.assertNotContains(r, "pbkdf2")
        self.assertNotContains(r, self.ali.descripteur_chiffre[:20])


# =========================================================================== Rôles

class RolesTests(Base):
    def test_anonyme_redirige_vers_connexion(self):
        for url in ["/", "/tableau/", "/employes/", "/comptes/", "/audit/", "/mon-espace/",
                    f"/photos/reference/{self.ali.id}/"]:
            r = self.client.get(url)
            self.assertEqual(r.status_code, 302, url)
            self.assertIn("/connexion/", r["Location"])
        self.assertEqual(self.client.post("/pointer/", {}).status_code, 302)

    def test_seul_l_admin_ouvre_le_poste_de_pointage(self):
        self.connecter(Profil.EMPLOYE, employe=self.ali)
        self.assertEqual(self.pointer(self.ali, variante(ALI)).status_code, 403)
        self.assertEqual(self.client.get("/").status_code, 403)

    def test_matrice_des_acces(self):
        attendu = {
            Profil.EMPLOYE: {"/tableau/": 403, "/employes/": 403, "/comptes/": 403, "/audit/": 403, "/lieux/": 403,
                             "/export/": 403, "/": 403, "/mon-espace/": 200, "/pointer-telephone/": 200},
            Profil.ADMIN:   {"/tableau/": 200, "/employes/": 200, "/comptes/": 200, "/audit/": 200, "/lieux/": 200,
                             "/": 200, "/mon-espace/": 403, "/pointer-telephone/": 403},
        }
        for role, pages in attendu.items():
            self.client.logout()
            kw = {"employe": self.oumar} if role == Profil.EMPLOYE else {}
            self.connecter(role, **kw)
            for url, code in pages.items():
                self.assertEqual(self.client.get(url).status_code, code, f"{role} {url}")

    def test_seulement_deux_roles(self):
        self.assertEqual([c for c, _ in Profil.ROLES], ["admin", "employe"])
        self.connecter(Profil.ADMIN)
        for ancien in ("rh", "chef", "borne"):
            self.client.post("/comptes/", {"identifiant": f"x.{ancien}", "role": ancien, "service": self.compta.id})
            self.assertFalse(User.objects.filter(username=f"x.{ancien}").exists(), ancien)

    def test_ancien_role_n_a_plus_aucun_acces(self):
        for ancien in ("rh", "chef", "borne"):
            self.client.logout()
            u = User.objects.create_user(f"ancien.{ancien}", password="MotDePasse-Solide-1")
            Profil.objects.create(utilisateur=u, role=ancien, service=self.compta, doit_changer_mdp=False)
            self.client.force_login(u)
            for url in ("/", "/tableau/", "/employes/", "/mon-espace/", "/pointer-telephone/"):
                self.assertEqual(self.client.get(url).status_code, 403, f"{ancien} {url}")

    def test_admin_django_reserve_a_l_administrateur(self):
        self.connecter(Profil.EMPLOYE, employe=self.ali)
        self.assertNotEqual(self.client.get("/admin/").status_code, 200)
        self.client.logout()
        self.connecter(Profil.ADMIN)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_admin_voit_tout_et_peut_filtrer(self):
        self.connecter(Profil.ADMIN)
        r = self.client.get("/tableau/")
        for nom in ("Ali Ould Ahmed", "Fatou Ba", "Oumar Diallo"):
            self.assertContains(r, nom)
        r = self.client.get(f"/tableau/?service={self.accueil.id}")
        self.assertContains(r, "Fatou Ba")
        self.assertNotContains(r, "Oumar Diallo")

    def test_employe_ne_voit_que_ses_donnees(self):
        self.connecter(Profil.EMPLOYE, employe=self.ali)
        mien = Pointage.objects.create(employe=self.ali, type="E")
        mien.photo.save("a.jpg", ContentFile(JPEG + b"a"))
        autre = Pointage.objects.create(employe=self.fatou, type="E")
        autre.photo.save("f.jpg", ContentFile(JPEG + b"f"))
        r = self.client.get("/mon-espace/")
        self.assertContains(r, "Ali Ould Ahmed")
        self.assertNotContains(r, "Fatou")
        self.assertEqual(self.client.get(f"/photos/pointage/{mien.id}/").status_code, 200)
        self.assertEqual(self.client.get(f"/photos/pointage/{autre.id}/").status_code, 404)
        export = self.client.get("/mon-espace/mes-donnees/")
        self.assertEqual(export.status_code, 200)
        self.assertTrue(JournalAudit.objects.filter(action="export_donnees_personnelles").exists())

    def test_compte_sans_role(self):
        u = User.objects.create_user("perdu", password="MotDePasse-Solide-1")
        self.client.force_login(u)
        r = self.client.get("/accueil/", follow=True)
        self.assertContains(r, "pas de rôle")
        self.assertEqual(self.client.get("/tableau/").status_code, 403)

    def test_redirection_selon_le_role(self):
        self.connecter(Profil.ADMIN)
        self.assertEqual(self.client.get("/accueil/")["Location"], "/tableau/")
        self.client.logout()
        self.connecter(Profil.EMPLOYE, employe=self.ali)
        self.assertEqual(self.client.get("/accueil/")["Location"], "/scanner/")


# =========================================================================== Comptes

class ComptesTests(Base):
    def test_admin_cree_un_utilisateur(self):
        self.connecter(Profil.ADMIN)
        self.client.post("/comptes/", {"identifiant": "ali", "role": "employe"})
        self.assertFalse(User.objects.filter(username="ali").exists())  # doit être relié à un employé
        r = self.client.post("/comptes/", {"identifiant": "ali", "role": "employe", "employe": self.ali.id})
        u = User.objects.get(username="ali")
        self.assertEqual(u.profil.employe, self.ali)
        self.assertTrue(u.profil.doit_changer_mdp)
        self.assertFalse(u.is_staff)
        self.assertTrue(u.check_password(r.context["mdp_affiche"][1]))

    def test_admin_cree_un_administrateur(self):
        self.connecter(Profil.ADMIN)
        self.client.post("/comptes/", {"identifiant": "admin2", "role": "admin"})
        self.assertTrue(User.objects.get(username="admin2").is_superuser)

    def test_compte_employe_unique(self):
        self.connecter(Profil.ADMIN)
        self.client.post("/comptes/", {"identifiant": "ali", "role": "employe", "employe": self.ali.id})
        self.client.post("/comptes/", {"identifiant": "ali2", "role": "employe", "employe": self.ali.id})
        self.assertTrue(User.objects.filter(username="ali").exists())
        self.assertFalse(User.objects.filter(username="ali2").exists())

    def test_changement_de_mot_de_passe_obligatoire(self):
        u = self.compte("nouveau", Profil.EMPLOYE, employe=self.ali, changer=True)
        self.client.force_login(u)
        r = self.client.get("/mon-espace/")
        self.assertEqual(r["Location"], "/mot-de-passe/")
        self.client.post("/mot-de-passe/", {"old_password": "MotDePasse-Solide-1",
                                            "new_password1": "Nouveau-Secret-2026", "new_password2": "Nouveau-Secret-2026"})
        u.profil.refresh_from_db()
        self.assertFalse(u.profil.doit_changer_mdp)
        self.assertEqual(self.client.get("/mon-espace/").status_code, 200)

    def test_mot_de_passe_trop_faible_refuse(self):
        u = self.compte("faible", Profil.EMPLOYE, employe=self.ali, changer=True)
        self.client.force_login(u)
        self.client.post("/mot-de-passe/", {"old_password": "MotDePasse-Solide-1",
                                            "new_password1": "12345678", "new_password2": "12345678"})
        u.refresh_from_db()
        self.assertTrue(u.check_password("MotDePasse-Solide-1"))

    def test_desactiver_et_reinitialiser(self):
        admin = self.connecter(Profil.ADMIN)
        rh = self.compte("rh1", Profil.EMPLOYE, employe=self.ali)
        self.client.post(f"/comptes/{rh.id}/", {"action": "desactiver"})
        rh.refresh_from_db()
        self.assertFalse(rh.is_active)
        self.client.post(f"/comptes/{rh.id}/", {"action": "reinitialiser"})
        rh.refresh_from_db()
        self.assertFalse(rh.check_password("MotDePasse-Solide-1"))
        self.assertTrue(rh.profil.doit_changer_mdp)
        # L'admin ne peut pas se désactiver lui-même
        self.client.post(f"/comptes/{admin.id}/", {"action": "desactiver"})
        admin.refresh_from_db()
        self.assertTrue(admin.is_active)


# =========================================================================== Connexion

class ConnexionTests(Base):
    def setUp(self):
        super().setUp()
        self.u = self.compte("chef", Profil.ADMIN)

    def test_connexion_reussie_journalisee(self):
        r = self.client.post("/connexion/", {"username": "chef", "password": "MotDePasse-Solide-1"})
        self.assertEqual(r.status_code, 302)
        self.assertTrue(JournalAudit.objects.filter(action="connexion_reussie", nom_utilisateur="chef").exists())

    def test_blocage_apres_5_echecs(self):
        for _ in range(5):
            self.client.post("/connexion/", {"username": "chef", "password": "mauvais"})
        r = self.client.post("/connexion/", {"username": "chef", "password": "MotDePasse-Solide-1"})
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Trop de tentatives")
        self.assertFalse(r.wsgi_request.user.is_authenticated)
        self.assertEqual(JournalAudit.objects.filter(action="connexion_echouee").count(), 5)
        self.assertTrue(JournalAudit.objects.filter(action="connexion_bloquee").exists())

    def test_deconnexion_apres_inactivite(self):
        self.client.force_login(self.u)
        s = self.client.session
        s["derniere_activite"] = int(time.time()) - 31 * 60
        s.save()
        r = self.client.get("/tableau/")
        self.assertEqual(r.status_code, 302)
        self.assertIn("expire=1", r["Location"])
        self.assertTrue(JournalAudit.objects.filter(action="deconnexion_inactivite").exists())

    def test_en_tetes_de_securite(self):
        self.client.force_login(self.u)
        r = self.client.get("/tableau/")
        csp = r["Content-Security-Policy"]
        self.assertIn("script-src 'self' 'nonce-", csp)
        self.assertIn("frame-ancestors 'none'", csp)
        self.assertNotIn("unsafe-eval", csp)
        self.assertIn("camera=(self)", r["Permissions-Policy"])
        self.assertEqual(r["X-Frame-Options"], "DENY")
        self.assertIn("no-store", r["Cache-Control"])
        nonce = csp.split("'nonce-")[1].split("'")[0]
        self.assertContains(r, f'nonce="{nonce}"')


# =========================================================================== Chiffrement et confidentialité

class ConfidentialiteTests(Base):
    def test_photos_chiffrees_sur_le_disque(self):
        brut = Path(MEDIA_TEST, self.ali.photo_reference.name).read_bytes()
        self.assertTrue(brut.startswith(b"GPE1"))
        self.assertNotIn(b"Ali Ould Ahmed", brut)
        self.assertEqual(self.ali.photo_reference.storage.lire(self.ali.photo_reference.name), JPEG + b"Ali Ould Ahmed")

    def test_signature_du_visage_chiffree_en_base(self):
        e = Employe.objects.get(pk=self.ali.pk)
        self.assertNotIn(str(round(ALI[0], 4))[:6], e.descripteur_chiffre)
        self.assertAlmostEqual(e.descripteur[0], ALI[0])

    def test_fichier_modifie_detecte(self):
        chemin = Path(MEDIA_TEST, self.ali.photo_reference.name)
        donnees = bytearray(chemin.read_bytes())
        donnees[30] ^= 1
        chemin.write_bytes(bytes(donnees))
        with self.assertRaises(chiffrement.ErreurChiffrement):
            self.ali.photo_reference.storage.lire(self.ali.photo_reference.name)

    def test_purge_des_photos_apres_30_jours(self):
        ancien = Pointage.objects.create(employe=self.ali, type="E", horodatage=timezone.now() - timedelta(days=31))
        ancien.descripteur = ALI
        ancien.photo.save("vieux.jpg", ContentFile(JPEG + b"vieux"))
        recent = Pointage.objects.create(employe=self.ali, type="E", horodatage=timezone.now() - timedelta(days=5))
        recent.photo.save("recent.jpg", ContentFile(JPEG + b"recent"))
        chemin = Path(MEDIA_TEST, ancien.photo.name)
        self.assertEqual(taches.purger_photos_anciennes(), 1)
        ancien.refresh_from_db()
        recent.refresh_from_db()
        self.assertFalse(ancien.photo)
        self.assertEqual(ancien.descripteur_chiffre, "")
        self.assertIsNotNone(ancien.photo_supprimee_le)
        self.assertFalse(chemin.exists())
        self.assertTrue(recent.photo)
        self.assertTrue(Pointage.objects.filter(pk=ancien.pk).exists())  # l'heure reste

    def test_effacement_biometrie(self):
        p = Pointage.objects.create(employe=self.ali, type="E")
        p.photo.save("x.jpg", ContentFile(JPEG + b"x"))
        fichiers = [Path(MEDIA_TEST, self.ali.photo_reference.name), Path(MEDIA_TEST, p.photo.name)]
        self.connecter(Profil.ADMIN)
        self.client.post(f"/employes/{self.ali.id}/effacer-biometrie/")
        self.ali.refresh_from_db()
        self.assertFalse(self.ali.a_reference)
        self.assertFalse(self.ali.actif)
        self.assertTrue(all(not f.exists() for f in fichiers))
        self.assertEqual(Pointage.objects.filter(employe=self.ali).count(), 1)

    def test_suppression_complete_reservee_admin_avec_confirmation(self):
        self.connecter(Profil.EMPLOYE, employe=self.oumar)
        self.assertEqual(self.client.post(f"/employes/{self.ali.id}/supprimer/", {"confirmation": "Ali Ould Ahmed"}).status_code, 403)
        self.client.logout()
        self.connecter(Profil.ADMIN)
        self.client.post(f"/employes/{self.ali.id}/supprimer/", {"confirmation": "mauvais nom"})
        self.assertTrue(Employe.objects.filter(pk=self.ali.pk).exists())
        self.client.post(f"/employes/{self.ali.id}/supprimer/", {"confirmation": "Ali Ould Ahmed"})
        self.assertFalse(Employe.objects.filter(pk=self.ali.pk).exists())


@override_settings(**REGLAGES)
class SauvegardeTests(Donnees, TransactionTestCase):
    """Conditions réelles : base en mode autocommit (comme en production)."""

    def test_sauvegarde_chiffree_et_restauration(self):
        chemin = taches.creer_sauvegarde()
        brut = chemin.read_bytes()
        self.assertTrue(brut.startswith(b"GPE1"))
        self.assertNotIn(b"SQLite format", brut)
        self.assertNotIn(b"Ali Ould Ahmed", brut)
        contenu = chiffrement.dechiffrer(brut)
        import io
        import zipfile
        z = zipfile.ZipFile(io.BytesIO(contenu))
        noms = z.namelist()
        self.assertIn("db.sqlite3", noms)
        self.assertTrue(any(n.startswith("media/references/") for n in noms))
        # La base sauvegardée contient bien les employés
        import sqlite3
        copie = Path(SAUV_TEST, "verif.sqlite3")
        copie.write_bytes(z.read("db.sqlite3"))
        noms_employes = {r[0] for r in sqlite3.connect(copie).execute("select nom from pointage_employe")}
        self.assertEqual(noms_employes, {"Ali Ould Ahmed", "Fatou Ba", "Oumar Diallo"})


# =========================================================================== Journal d'audit

class AuditTests(Base):
    def test_chaine_intacte_puis_alteration_detectee(self):
        self.connecter(Profil.ADMIN)
        self.client.get("/tableau/")
        self.client.get("/export/")
        ok, n = JournalAudit.verifier_integrite()
        self.assertTrue(ok)
        self.assertGreaterEqual(n, 2)
        # Quelqu'un modifie la base directement (contourne l'application)
        premiere = JournalAudit.objects.order_by("id").first()
        JournalAudit.objects.filter(pk=premiere.pk).update(details="falsifié")
        ok, ligne = JournalAudit.verifier_integrite()
        self.assertFalse(ok)
        self.assertEqual(ligne, premiere.pk)
        self.assertContains(self.client.get("/audit/"), "Journal modifié")

    def test_journal_non_modifiable_par_l_application(self):
        JournalAudit.objects.create(action="test")
        entree = JournalAudit.objects.get(action="test")
        entree.details = "x"
        with self.assertRaises(PermissionError):
            entree.save()
        with self.assertRaises(PermissionError):
            entree.delete()

    def test_consultations_et_exports_journalises(self):
        self.connecter(Profil.ADMIN)
        self.client.get(f"/tableau/?service={self.compta.id}")
        self.client.get("/export/")
        self.assertTrue(JournalAudit.objects.filter(action="consultation_tableau", details__contains="Comptabilité").exists())
        self.assertTrue(JournalAudit.objects.filter(action="export_excel").exists())

    def test_acces_refuse_journalise(self):
        self.connecter(Profil.EMPLOYE, employe=self.ali)
        self.client.get("/comptes/")
        self.assertTrue(JournalAudit.objects.filter(action="acces_refuse", details="/comptes/").exists())


# =========================================================================== Employés

class EmployesTests(Base):
    def setUp(self):
        super().setUp()
        self.connecter(Profil.ADMIN)

    def enregistrer(self, **donnees):
        donnees.setdefault("photo", photo())
        return self.client.post("/employes/enregistrer/", donnees)

    def test_creer_employe_avec_service(self):
        r = self.enregistrer(nom="  Aïcha   Mint Sidi ", poste="RH", service=self.accueil.id,
                             descripteur=json.dumps(signature(50)))
        self.assertEqual(r.status_code, 200, r.content)
        e = Employe.objects.get(nom="Aïcha Mint Sidi")
        self.assertEqual(e.service, self.accueil)
        self.assertTrue(e.a_reference)
        self.assertTrue(JournalAudit.objects.filter(action="employe_cree").exists())

    def test_meme_visage_pour_deux_employes_refuse(self):
        r = self.enregistrer(nom="Faux Ali", descripteur=json.dumps(variante(ALI)))
        self.assertEqual(r.status_code, 409)
        self.assertIn("Ali Ould Ahmed", r.json()["message"])

    def test_modifier_employe(self):
        self.client.post(f"/employes/{self.ali.id}/", {"nom": "Ali Ould Ahmed", "poste": "Comptable",
                                                       "service": self.accueil.id, "actif": "on"})
        self.ali.refresh_from_db()
        self.assertEqual(self.ali.service, self.accueil)
        self.assertEqual(self.ali.poste, "Comptable")


# =========================================================================== Base de données

class BaseDeDonneesTests(Base):
    def test_reglages_sqlite(self):
        from django.db import connection
        with connection.cursor() as c:
            self.assertEqual(c.execute("PRAGMA foreign_keys").fetchone()[0], 1)
            self.assertEqual(c.execute("PRAGMA secure_delete").fetchone()[0], 1)

    def test_controle_integrite(self):
        ok, message = taches.controle_integrite()
        self.assertTrue(ok, message)

    def test_restauration_refuse_une_sauvegarde_abimee_sans_rien_toucher(self):
        Path(SAUV_TEST).mkdir(parents=True, exist_ok=True)
        abimee = Path(SAUV_TEST, "abimee.sauvegarde")
        abimee.write_bytes(chiffrement.chiffrer(b"ceci n'est pas une sauvegarde"))
        with self.assertRaises(Exception):
            taches.restaurer_sauvegarde(abimee)
        falsifiee = Path(SAUV_TEST, "falsifiee.sauvegarde")
        falsifiee.write_bytes(b"GPE1" + random.randbytes(200))
        with self.assertRaises(chiffrement.ErreurChiffrement):
            taches.restaurer_sauvegarde(falsifiee)
        self.assertEqual(Employe.objects.count(), 3)
        self.assertFalse(taches.verifier_sauvegarde(falsifiee)[0])

    def test_initialiser_peut_etre_relance(self):
        from io import StringIO

        from django.core.management import call_command
        sortie = StringIO()
        call_command("initialiser", "--sans-admin", stdout=sortie)
        self.assertIn("Base de données prête", sortie.getvalue())
        self.assertEqual(Employe.objects.count(), 3)


# =========================================================================== Ajouter / supprimer

class AjouterSupprimerTests(Base):
    def test_supprimer_service_vide_seulement(self):
        self.connecter(Profil.ADMIN)
        vide = Service.objects.create(nom="Logistique")
        self.client.post(f"/employes/services/{self.compta.id}/supprimer/")
        self.assertTrue(Service.objects.filter(pk=self.compta.pk).exists())  # employés rattachés
        self.client.post(f"/employes/services/{vide.id}/supprimer/")
        self.assertFalse(Service.objects.filter(pk=vide.pk).exists())
        self.assertTrue(JournalAudit.objects.filter(action="service_supprime").exists())

    def test_supprimer_un_compte(self):
        self.connecter(Profil.ADMIN)
        u = self.compte("ali.compte", Profil.EMPLOYE, employe=self.ali)
        self.client.post(f"/comptes/{u.id}/", {"action": "supprimer", "confirmation": "mauvais"})
        self.assertTrue(User.objects.filter(pk=u.pk).exists())
        self.client.post(f"/comptes/{u.id}/", {"action": "supprimer", "confirmation": "ali.compte"})
        self.assertFalse(User.objects.filter(pk=u.pk).exists())
        self.assertTrue(Employe.objects.filter(pk=self.ali.pk).exists())  # l'employé reste
        self.assertTrue(JournalAudit.objects.filter(action="compte_supprime").exists())

    def test_admin_ne_peut_pas_se_supprimer(self):
        admin = self.connecter(Profil.ADMIN)
        self.client.post(f"/comptes/{admin.id}/", {"action": "supprimer", "confirmation": admin.username})
        self.assertTrue(User.objects.filter(pk=admin.pk).exists())

    def test_utilisateur_ne_peut_pas_supprimer_de_compte(self):
        u = self.compte("x", Profil.EMPLOYE, employe=self.ali)
        self.connecter(Profil.EMPLOYE, employe=self.oumar)
        self.assertEqual(self.client.post(f"/comptes/{u.id}/", {"action": "supprimer", "confirmation": "x"}).status_code, 403)


# =========================================================================== Corrections manuelles

class CorrectionsTests(Base):
    def entree_hier(self, emp):
        hier = timezone.localtime() - timedelta(days=1)
        debut = hier.replace(hour=8, minute=0, second=0, microsecond=0)
        Pointage.objects.create(employe=emp, type="E", horodatage=debut)
        return debut

    def test_sortie_oubliee_signalee_puis_corrigee(self):
        debut = self.entree_hier(self.ali)
        self.connecter(Profil.ADMIN)
        jour = debut.strftime("%Y-%m-%d")
        r = self.client.get(f"/tableau/?date={jour}")
        self.assertContains(r, "Sortie manquante")
        r = self.client.post("/pointages/manuel/", {"employe": self.ali.id, "type": "S", "date": jour,
                                                    "heure": "17:30", "motif": "Oubli de pointage, confirmé par le chef"})
        p = Pointage.objects.get(employe=self.ali, type="S")
        self.assertTrue(p.manuel)
        self.assertEqual(p.motif, "Oubli de pointage, confirmé par le chef")
        r = self.client.get(f"/tableau/?date={jour}")
        self.assertNotContains(r, "Sortie manquante")
        self.assertContains(r, "09:30:00")  # 8 h → 17 h 30
        self.assertTrue(JournalAudit.objects.filter(action="pointage_manuel_ajoute", details__contains="Ali").exists())

    def test_correction_refusee_sans_motif_ou_dans_le_futur(self):
        self.connecter(Profil.ADMIN)
        demain = (timezone.localdate() + timedelta(days=1)).isoformat()
        aujourdhui = timezone.localdate().isoformat()
        self.client.post("/pointages/manuel/", {"employe": self.ali.id, "type": "S", "date": demain, "heure": "10:00",
                                                "motif": "Motif suffisant"})
        self.client.post("/pointages/manuel/", {"employe": self.ali.id, "type": "S", "date": aujourdhui, "heure": "00:01",
                                                "motif": "ok"})
        self.client.post("/pointages/manuel/", {"employe": self.ali.id, "type": "X", "date": aujourdhui, "heure": "00:01",
                                                "motif": "Motif suffisant"})
        self.assertFalse(Pointage.objects.exists())

    def test_utilisateur_ne_peut_pas_corriger(self):
        self.connecter(Profil.EMPLOYE, employe=self.oumar)
        r = self.client.post("/pointages/manuel/", {"employe": self.ali.id, "type": "S",
                                                    "date": timezone.localdate().isoformat(), "heure": "00:01",
                                                    "motif": "Motif suffisant"})
        self.assertEqual(r.status_code, 403)

    def test_seules_les_corrections_sont_supprimables(self):
        self.connecter(Profil.ADMIN)
        borne = Pointage.objects.create(employe=self.ali, type="E")
        manuel = Pointage.objects.create(employe=self.ali, type="S", manuel=True, motif="test")
        self.assertEqual(self.client.post(f"/pointages/manuel/{borne.id}/supprimer/").status_code, 404)
        self.client.post(f"/pointages/manuel/{manuel.id}/supprimer/")
        self.assertTrue(Pointage.objects.filter(pk=borne.pk).exists())
        self.assertFalse(Pointage.objects.filter(pk=manuel.pk).exists())

    def test_redirection_suivante_securisee(self):
        self.connecter(Profil.ADMIN)
        r = self.client.post("/pointages/manuel/", {"employe": self.ali.id, "type": "S", "date": "x", "heure": "y",
                                                    "motif": "Motif", "suivant": "https://site-pirate.example/"})
        self.assertEqual(r["Location"], "/tableau/")


# =========================================================================== Compatibilité navigateurs

class CompatibiliteTests(Base):
    def test_page_diagnostic_publique(self):
        r = self.client.get("/diagnostic/")
        self.assertEqual(r.status_code, 200)
        self.assertContains(r, "Diagnostic du navigateur")
        nonce = r["Content-Security-Policy"].split("'nonce-")[1].split("'")[0]
        self.assertContains(r, f'nonce="{nonce}"')

    def test_lien_diagnostic_sur_la_connexion(self):
        self.assertContains(self.client.get("/connexion/"), "/diagnostic/")

    def test_localhost_ipv4_et_ipv6_acceptes(self):
        for hote in ("127.0.0.1:8000", "localhost:8000", "[::1]:8000"):
            self.assertEqual(self.client.get("/connexion/", HTTP_HOST=hote).status_code, 200, hote)

    def test_adresse_inconnue_refusee(self):
        self.assertEqual(self.client.get("/connexion/", HTTP_HOST="pirate.example").status_code, 400)

    def test_pages_camera_utilisent_le_module_compatible(self):
        self.connecter(Profil.ADMIN)
        for url in ("/", "/employes/"):
            r = self.client.get(url)
            self.assertContains(r, "Visage.ouvrirCamera")
            self.assertNotContains(r, "navigator.mediaDevices.getUserMedia")


# =========================================================================== Hébergeur (PythonAnywhere)

class HebergeurTests(Base):
    @override_settings(EN_TETE_IP_CLIENT="HTTP_X_REAL_IP")
    def test_vraie_ip_du_visiteur(self):
        from django.test import Client
        c = Client(REMOTE_ADDR="10.0.0.1", HTTP_X_REAL_IP="196.200.1.7")
        c.post("/connexion/", {"username": "inconnu", "password": "x"})
        self.assertEqual(JournalAudit.objects.get(action="connexion_echouee").adresse_ip, "196.200.1.7")

    @override_settings(EN_TETE_IP_CLIENT="HTTP_X_REAL_IP")
    def test_blocage_par_visiteur_et_non_global(self):
        """Derrière le répartiteur, 5 échecs d'un visiteur ne doivent pas bloquer les autres."""
        from django.test import Client
        u = self.compte("rh.ok", Profil.ADMIN)
        pirate = Client(REMOTE_ADDR="10.0.0.1", HTTP_X_REAL_IP="203.0.113.9")
        for _ in range(5):
            pirate.post("/connexion/", {"username": "autre", "password": "faux"})
        honnete = Client(REMOTE_ADDR="10.0.0.1", HTTP_X_REAL_IP="196.200.1.8")
        r = honnete.post("/connexion/", {"username": "rh.ok", "password": "MotDePasse-Solide-1"})
        self.assertEqual(r.status_code, 302, "un visiteur honnête ne doit pas être bloqué")
        self.assertTrue(u.is_active)

    @override_settings(EN_TETE_IP_CLIENT="HTTP_X_REAL_IP")
    def test_en_tete_invalide_ignore(self):
        from django.test import Client
        Client(REMOTE_ADDR="10.0.0.1", HTTP_X_REAL_IP="<script>").post("/connexion/", {"username": "x", "password": "y"})
        self.assertEqual(JournalAudit.objects.get(action="connexion_echouee").adresse_ip, "10.0.0.1")

    def test_sans_reglage_en_tete_non_utilise(self):
        from django.test import Client
        Client(REMOTE_ADDR="10.0.0.1", HTTP_X_REAL_IP="1.2.3.4").post("/connexion/", {"username": "x", "password": "y"})
        self.assertEqual(JournalAudit.objects.get(action="connexion_echouee").adresse_ip, "10.0.0.1")


class VisageTests(TestCase):
    def test_distance(self):
        self.assertEqual(visage.distance(ALI, ALI), 0)
        self.assertLess(visage.distance(ALI, variante(ALI)), 0.5)
        self.assertGreater(visage.distance(ALI, FATOU), 0.5)


# =========================================================================== Pointage par téléphone

@override_settings(POINTAGE_TELEPHONE=True)
class TelephoneTests(Base):
    def setUp(self):
        super().setUp()
        self.u_ali = self.connecter(Profil.EMPLOYE, employe=self.ali)

    def envoyer(self, sig, **extra):
        return self.client.post("/pointer-telephone/envoyer/", {
            "descripteur": json.dumps(sig), "photo": photo(), **extra}, **getattr(self, "meta", {}))

    def test_page_et_redirection_apres_connexion(self):
        self.assertEqual(self.client.get("/pointer-telephone/").status_code, 200)
        self.assertRedirects(self.client.get("/accueil/"), "/pointer-telephone/")

    def test_pointage_par_telephone_accepte(self):
        r = self.envoyer(variante(ALI))
        self.assertEqual(r.status_code, 200, r.content)
        p = Pointage.objects.get()
        self.assertEqual((p.employe, p.source, p.origine), (self.ali, Pointage.TELEPHONE, "Téléphone"))

    def test_impossible_de_pointer_pour_un_autre(self):
        # Le champ « employe » est ignoré : c'est toujours l'employé du compte connecté
        r = self.envoyer(variante(OUMAR), employe=self.oumar.id)
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Pointage.objects.exists())

    def test_visage_inconnu_refuse(self):
        self.assertEqual(self.envoyer(signature(77)).status_code, 403)

    def test_reservee_au_role_utilisateur(self):
        self.client.logout()
        self.connecter(Profil.ADMIN)
        self.assertEqual(self.envoyer(variante(ALI)).status_code, 403)

    @override_settings(POINTAGE_TELEPHONE_RESEAUX=["41.188.10.0/24"])
    def test_restriction_au_wifi_du_bureau(self):
        self.meta = {"REMOTE_ADDR": "102.2.3.4"}
        r = self.envoyer(variante(ALI, graine=1))
        self.assertEqual(r.status_code, 403)
        self.assertIn("Wi-Fi", r.json()["message"])
        self.meta = {"REMOTE_ADDR": "41.188.10.25"}
        self.assertEqual(self.envoyer(variante(ALI, graine=2)).status_code, 200)

    @override_settings(POINTAGE_TELEPHONE=False)
    def test_desactivable(self):
        self.assertEqual(self.envoyer(variante(ALI)).status_code, 403)
        self.assertRedirects(self.client.get("/accueil/"), "/scanner/")

    def test_admin_cree_l_acces_depuis_la_fiche(self):
        self.client.logout()
        self.connecter(Profil.ADMIN)
        r = self.client.post(f"/employes/{self.oumar.id}/acces/", {"identifiant": ""}, follow=True)
        self.assertContains(r, "oumar.diallo")
        profil = Profil.objects.get(employe=self.oumar)
        self.assertEqual(profil.role, Profil.EMPLOYE)
        self.assertTrue(profil.doit_changer_mdp)
        # Pas de second compte pour le même employé
        self.client.post(f"/employes/{self.oumar.id}/acces/", {"identifiant": "autre"})
        self.assertFalse(User.objects.filter(username="autre").exists())


# =========================================================================== Lieu de pointage (GPS)

from .geo import distance_m  # noqa: E402
from .models import Lieu  # noqa: E402

BUREAU = (18.0860, -15.9750)  # point de test (Nouakchott)


def decale(lat, lon, metres_nord):
    return lat + metres_nord / 111_195, lon


@override_settings(POINTAGE_TELEPHONE=True)
class LieuTests(Base):
    def setUp(self):
        super().setUp()
        self.connecter(Profil.EMPLOYE, employe=self.ali)
        self.lieu = Lieu.objects.create(nom="Beitik Soukouk", latitude=BUREAU[0], longitude=BUREAU[1], rayon_m=20)

    def envoyer(self, sig, position=None, precision=8):
        donnees = {"descripteur": json.dumps(sig), "photo": photo()}
        if position:
            donnees.update(latitude=position[0], longitude=position[1], precision=precision)
        return self.client.post("/pointer-telephone/envoyer/", donnees)

    def test_distance(self):
        self.assertAlmostEqual(distance_m(*BUREAU, *decale(*BUREAU, 15)), 15, delta=0.2)

    def test_a_moins_de_20_m_accepte(self):
        r = self.envoyer(variante(ALI), decale(*BUREAU, 12))
        self.assertEqual(r.status_code, 200, r.content)
        p = Pointage.objects.get()
        self.assertEqual(p.lieu, self.lieu)
        self.assertAlmostEqual(p.distance_lieu_m, 12, delta=0.5)
        self.assertIn("Beitik Soukouk", p.origine)

    def test_au_dela_de_20_m_refuse(self):
        r = self.envoyer(variante(ALI), decale(*BUREAU, 35))
        self.assertEqual(r.status_code, 403)
        self.assertIn("35 m", r.json()["message"])
        self.assertFalse(Pointage.objects.exists())
        self.assertTrue(JournalAudit.objects.filter(action="pointage_refuse", details__contains="position").exists())

    def test_sans_position_refuse(self):
        self.assertEqual(self.envoyer(variante(ALI)).status_code, 403)

    def test_position_imprecise_refusee(self):
        self.assertEqual(self.envoyer(variante(ALI), BUREAU, precision=200).status_code, 403)

    def test_lieu_desactive_plus_de_restriction(self):
        self.lieu.actif = False
        self.lieu.save()
        self.assertEqual(self.envoyer(variante(ALI)).status_code, 200)

    def test_le_poste_admin_n_est_pas_concerne(self):
        self.client.logout()
        self.connecter(Profil.ADMIN)
        self.assertEqual(self.pointer(self.ali, variante(ALI)).status_code, 200)

    def test_admin_enregistre_le_lieu(self):
        self.client.logout()
        self.connecter(Profil.ADMIN)
        r = self.client.post("/lieux/", {"action": "ajouter", "nom": "Annexe", "rayon": "20",
                                         "latitude": "18.1", "longitude": "-15.96", "precision": "6"}, follow=True)
        self.assertContains(r, "moins de 20 m")
        self.assertTrue(Lieu.objects.filter(nom="Annexe", rayon_m=20).exists())
        # Sans position : refusé
        self.client.post("/lieux/", {"action": "ajouter", "nom": "Sans GPS", "rayon": "20"})
        self.assertFalse(Lieu.objects.filter(nom="Sans GPS").exists())

    def test_lieux_reserve_a_l_admin(self):
        self.assertEqual(self.client.get("/lieux/").status_code, 403)


# =========================================================================== QR code (tablette)

import secrets  # noqa: E402
from django.core import signing  # noqa: E402
from .models import Tablette  # noqa: E402
from .views_qr import COOKIE_TABLETTE, SEL_QR  # noqa: E402


class QrTests(Base):
    def setUp(self):
        super().setUp()
        # L'administrateur installe la tablette (sur la tablette elle-même)
        self.connecter(Profil.ADMIN)
        r = self.client.post("/tablettes/activer/", {"nom": "Entrée"})
        self.assertRedirects(r, "/tablette/", fetch_redirect_response=False)
        self.jeton = r.cookies[COOKIE_TABLETTE].value
        self.assertFalse(r.wsgi_request.user.is_authenticated)  # session admin fermée sur la tablette
        self.tablette = Tablette.objects.get()

    def code(self):
        """La tablette affiche un QR code ; il contient l'adresse /scan/<code>/ signée par le serveur."""
        from django.test import Client
        t = Client()
        t.cookies[COOKIE_TABLETTE] = self.jeton
        self.assertEqual(t.get("/tablette/").status_code, 200)
        self.assertIn("<svg", t.get("/tablette/code/").json()["svg"])
        return signing.dumps({"t": self.tablette.pk, "n": secrets.token_hex(4)}, salt=SEL_QR, compress=True)

    def employe(self, emp=None):
        self.client.logout()
        return self.connecter(Profil.EMPLOYE, employe=emp or self.ali)

    def scanner(self, code, **donnees):
        self.assertEqual(self.client.get(f"/scan/{code}/").status_code, 200)
        return self.client.post(f"/scan/{code}/valider/", donnees)

    def test_tablette_sans_jeton_refusee(self):
        self.client.logout()
        self.assertEqual(self.client.get("/tablette/").status_code, 403)
        self.assertEqual(self.client.get("/tablette/code/").status_code, 403)

    def test_entree_puis_sortie_avec_heures_sup(self):
        self.employe()
        code = self.code()
        r = self.scanner(code)
        self.assertEqual(r.status_code, 200, r.content)
        self.assertEqual(r.json()["type"], "Entrée")
        self.assertRegex(r.json()["heure"], r"^\d{2}:\d{2}:\d{2}$")
        p = Pointage.objects.get()
        self.assertEqual((p.source, p.origine), (Pointage.QR, "QR code (tablette)"))
        # 9 h 30 plus tard : sortie sans confirmation, 1 h 30 d'heures sup.
        Pointage.objects.update(horodatage=timezone.now() - timedelta(hours=9, minutes=30))
        r = self.scanner(self.code())
        self.assertEqual(r.json()["type"], "Sortie")
        self.assertIn("1 h 30 min d'heures supplémentaires", r.json()["detail"])
        self.client.logout(); self.connecter(Profil.ADMIN)
        if timezone.localtime(Pointage.objects.filter(type="E").get().horodatage).date() == timezone.localdate():
            self.assertContains(self.client.get("/tableau/"), "+01:30:00")

    def test_sortie_avant_8h_demande_confirmation(self):
        self.employe()
        self.scanner(self.code())
        Pointage.objects.update(horodatage=timezone.now() - timedelta(hours=3))
        code = self.code()
        r = self.scanner(code)
        self.assertTrue(r.json()["confirmer"])
        self.assertEqual(Pointage.objects.count(), 1)
        r = self.scanner(code, confirmer="1")
        self.assertTrue(r.json()["ok"])
        self.assertEqual(Pointage.objects.filter(type="S").count(), 1)

    def test_qr_expire_ou_falsifie_refuse(self):
        self.employe()
        faux = signing.dumps({"t": self.tablette.pk}, salt="autre")
        self.assertEqual(self.client.post(f"/scan/{faux}/valider/").status_code, 403)
        with override_settings(QR_VALIDITE_SECONDES=-500):
            self.assertEqual(self.client.post(f"/scan/{self.code()}/valider/").status_code, 403)
        self.assertFalse(Pointage.objects.exists())

    def test_tablette_desactivee_ses_qr_ne_marchent_plus(self):
        code = self.code()
        self.tablette.active = False; self.tablette.save()
        self.employe()
        self.assertEqual(self.client.post(f"/scan/{code}/valider/").status_code, 403)

    def test_double_scan_bloque(self):
        self.employe()
        code = self.code()
        self.scanner(code)
        self.assertEqual(self.scanner(code).status_code, 429)

    def test_admin_ne_peut_pas_scanner(self):
        self.connecter(Profil.ADMIN)
        self.assertEqual(self.client.post(f"/scan/{self.code()}/valider/").status_code, 403)

    def test_lieu_applique_au_qr(self):
        Lieu.objects.create(nom="Beitik Soukouk", latitude=BUREAU[0], longitude=BUREAU[1], rayon_m=20)
        self.employe()
        r = self.scanner(self.code(), latitude=BUREAU[0] + 50 / 111195, longitude=BUREAU[1], precision=5)
        self.assertEqual(r.status_code, 403)
        r = self.scanner(self.code(), latitude=BUREAU[0] + 10 / 111195, longitude=BUREAU[1], precision=5)
        self.assertEqual(r.status_code, 200)

    def test_employe_reste_connecte(self):
        self.client.logout()
        u = self.compte("ali.tel", Profil.EMPLOYE, employe=self.ali)
        self.client.post("/connexion/", {"username": "ali.tel", "password": "MotDePasse-Solide-1"})
        self.assertGreater(self.client.session.get_expiry_age(), 30 * 86400)
        s = self.client.session; s["derniere_activite"] = int(time.time()) - 5 * 3600; s.save()
        self.assertEqual(self.client.get("/mon-espace/").status_code, 200)  # pas de déconnexion pour inactivité


class QrAdminTests(Base):
    def test_qr_affiche_dans_l_admin_et_scannable(self):
        admin = self.connecter(Profil.ADMIN)
        self.assertContains(self.client.get("/qr/"), "Scannez pour pointer")
        self.assertIn("<svg", self.client.get("/qr/code/").json()["svg"])
        code = signing.dumps({"a": admin.pk, "n": "x"}, salt=SEL_QR, compress=True)
        self.client.logout()
        self.connecter(Profil.EMPLOYE, employe=self.ali)
        self.assertEqual(self.client.get("/qr/").status_code, 403)  # réservé à l'administrateur
        r = self.client.post(f"/scan/{code}/valider/")
        self.assertEqual(r.status_code, 200, r.content)
        # QR d'un administrateur désactivé : refusé
        admin.is_active = False; admin.save()
        Pointage.objects.update(horodatage=timezone.now() - timedelta(minutes=5))
        self.assertEqual(self.client.post(f"/scan/{code}/valider/").status_code, 403)
        # Un faux « administrateur » (employé) ne peut pas fabriquer de QR
        faux = signing.dumps({"a": self.client.session["_auth_user_id"]}, salt="autre")
        self.assertEqual(self.client.post(f"/scan/{faux}/valider/").status_code, 403)


class ScannerTests(Base):
    def test_lecteur_integre(self):
        self.connecter(Profil.EMPLOYE, employe=self.ali)
        r = self.client.get("/scanner/")
        self.assertContains(r, "jsQR.js")
        self.assertContains(r, "Prochain : <strong>entrée</strong>", html=False)
        self.client.logout()
        self.connecter(Profil.ADMIN)
        self.assertEqual(self.client.get("/scanner/").status_code, 403)
