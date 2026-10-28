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
        self.connecter(Profil.BORNE)

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

    def test_seule_la_borne_peut_pointer(self):
        for role in (Profil.RH, Profil.CHEF, Profil.EMPLOYE):
            self.client.logout()
            kw = {"service": self.compta} if role == Profil.CHEF else {"employe": self.ali} if role == Profil.EMPLOYE else {}
            if role == Profil.EMPLOYE:
                Profil.objects.filter(employe=self.ali).delete()
            self.connecter(role, **kw)
            self.assertEqual(self.pointer(self.ali, variante(ALI)).status_code, 403, role)
            self.assertEqual(self.client.get("/").status_code, 403, role)

    def test_matrice_des_acces(self):
        attendu = {
            Profil.BORNE:   {"/tableau/": 403, "/employes/": 403, "/comptes/": 403, "/audit/": 403, "/mon-espace/": 403},
            Profil.EMPLOYE: {"/tableau/": 403, "/employes/": 403, "/comptes/": 403, "/audit/": 403, "/mon-espace/": 200},
            Profil.CHEF:    {"/tableau/": 200, "/employes/": 403, "/comptes/": 403, "/audit/": 403, "/mon-espace/": 403},
            Profil.RH:      {"/tableau/": 200, "/employes/": 200, "/comptes/": 403, "/audit/": 403, "/mon-espace/": 403},
            Profil.ADMIN:   {"/tableau/": 200, "/employes/": 200, "/comptes/": 200, "/audit/": 200, "/mon-espace/": 403},
        }
        for role, pages in attendu.items():
            self.client.logout()
            kw = {"service": self.compta} if role == Profil.CHEF else {"employe": self.oumar} if role == Profil.EMPLOYE else {}
            self.connecter(role, **kw)
            for url, code in pages.items():
                self.assertEqual(self.client.get(url).status_code, code, f"{role} {url}")

    def test_admin_django_reserve_a_l_administrateur(self):
        self.connecter(Profil.RH)
        self.assertNotEqual(self.client.get("/admin/").status_code, 200)
        self.client.logout()
        self.connecter(Profil.ADMIN)
        self.assertEqual(self.client.get("/admin/").status_code, 200)

    def test_chef_ne_voit_que_son_service(self):
        self.connecter(Profil.CHEF, service=self.accueil)
        p_ali = Pointage.objects.create(employe=self.ali, type="E")
        p_ali.photo.save("x.jpg", ContentFile(JPEG + b"ali"))
        p_fatou = Pointage.objects.create(employe=self.fatou, type="E")
        p_fatou.photo.save("y.jpg", ContentFile(JPEG + b"fatou"))

        r = self.client.get("/tableau/")
        self.assertContains(r, "Fatou Ba")
        self.assertNotContains(r, "Ali Ould Ahmed")
        self.assertNotContains(r, "Oumar Diallo")
        self.assertEqual(self.client.get(f"/photos/pointage/{p_fatou.id}/").status_code, 200)
        self.assertEqual(self.client.get(f"/photos/pointage/{p_ali.id}/").status_code, 404)
        self.assertEqual(self.client.get(f"/photos/reference/{self.ali.id}/").status_code, 404)
        # Le chef ne peut pas forcer un autre service par l'URL
        r = self.client.get(f"/tableau/?service={self.compta.id}")
        self.assertNotContains(r, "Ali Ould Ahmed")
        export = self.client.get("/export/")
        self.assertEqual(export.status_code, 200)

    def test_rh_voit_tout_et_peut_filtrer(self):
        self.connecter(Profil.RH)
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
        for role, cible in ((Profil.BORNE, "/"), (Profil.RH, "/tableau/")):
            self.client.logout()
            self.connecter(role)
            self.assertEqual(self.client.get("/accueil/")["Location"], cible)


# =========================================================================== Comptes

class ComptesTests(Base):
    def test_admin_cree_un_chef_avec_service(self):
        self.connecter(Profil.ADMIN)
        r = self.client.post("/comptes/", {"identifiant": "chef.compta", "role": "chef"})
        self.assertFalse(User.objects.filter(username="chef.compta").exists())
        r = self.client.post("/comptes/", {"identifiant": "chef.compta", "role": "chef", "service": self.compta.id})
        u = User.objects.get(username="chef.compta")
        self.assertEqual(u.profil.service, self.compta)
        self.assertTrue(u.profil.doit_changer_mdp)
        self.assertFalse(u.is_staff)
        mdp = r.context["mdp_affiche"][1]
        self.assertTrue(u.check_password(mdp))

    def test_compte_employe_unique(self):
        self.connecter(Profil.ADMIN)
        self.client.post("/comptes/", {"identifiant": "ali", "role": "employe", "employe": self.ali.id})
        self.client.post("/comptes/", {"identifiant": "ali2", "role": "employe", "employe": self.ali.id})
        self.assertTrue(User.objects.filter(username="ali").exists())
        self.assertFalse(User.objects.filter(username="ali2").exists())

    def test_changement_de_mot_de_passe_obligatoire(self):
        u = self.compte("nouveau", Profil.RH, changer=True)
        self.client.force_login(u)
        r = self.client.get("/tableau/")
        self.assertEqual(r["Location"], "/mot-de-passe/")
        self.client.post("/mot-de-passe/", {"old_password": "MotDePasse-Solide-1",
                                            "new_password1": "Nouveau-Secret-2026", "new_password2": "Nouveau-Secret-2026"})
        u.profil.refresh_from_db()
        self.assertFalse(u.profil.doit_changer_mdp)
        self.assertEqual(self.client.get("/tableau/").status_code, 200)

    def test_mot_de_passe_trop_faible_refuse(self):
        u = self.compte("faible", Profil.RH, changer=True)
        self.client.force_login(u)
        self.client.post("/mot-de-passe/", {"old_password": "MotDePasse-Solide-1",
                                            "new_password1": "12345678", "new_password2": "12345678"})
        u.refresh_from_db()
        self.assertTrue(u.check_password("MotDePasse-Solide-1"))

    def test_desactiver_et_reinitialiser(self):
        admin = self.connecter(Profil.ADMIN)
        rh = self.compte("rh1", Profil.RH)
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
        self.u = self.compte("chef", Profil.CHEF, service=self.compta)

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

    def test_borne_pas_deconnectee_par_inactivite(self):
        b = self.compte("borne1", Profil.BORNE, changer=True)
        self.client.force_login(b)
        s = self.client.session
        s["derniere_activite"] = int(time.time()) - 5 * 3600
        s.save()
        self.assertEqual(self.client.get("/").status_code, 200)

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

    def test_effacement_biometrie_par_rh(self):
        p = Pointage.objects.create(employe=self.ali, type="E")
        p.photo.save("x.jpg", ContentFile(JPEG + b"x"))
        fichiers = [Path(MEDIA_TEST, self.ali.photo_reference.name), Path(MEDIA_TEST, p.photo.name)]
        self.connecter(Profil.RH)
        self.client.post(f"/employes/{self.ali.id}/effacer-biometrie/")
        self.ali.refresh_from_db()
        self.assertFalse(self.ali.a_reference)
        self.assertFalse(self.ali.actif)
        self.assertTrue(all(not f.exists() for f in fichiers))
        self.assertEqual(Pointage.objects.filter(employe=self.ali).count(), 1)

    def test_suppression_complete_reservee_admin_avec_confirmation(self):
        self.connecter(Profil.RH)
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
        self.connecter(Profil.CHEF, service=self.compta)
        self.client.get("/tableau/")
        self.client.get("/export/")
        self.assertTrue(JournalAudit.objects.filter(action="consultation_tableau", details__contains="Comptabilité").exists())
        self.assertTrue(JournalAudit.objects.filter(action="export_excel").exists())

    def test_acces_refuse_journalise(self):
        self.connecter(Profil.EMPLOYE, employe=self.ali)
        self.client.get("/comptes/")
        self.assertTrue(JournalAudit.objects.filter(action="acces_refuse", details="/comptes/").exists())


# =========================================================================== Employés (RH)

class EmployesTests(Base):
    def setUp(self):
        super().setUp()
        self.connecter(Profil.RH)

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
        self.connecter(Profil.RH)
        vide = Service.objects.create(nom="Logistique")
        self.client.post(f"/employes/services/{self.compta.id}/supprimer/")
        self.assertTrue(Service.objects.filter(pk=self.compta.pk).exists())  # employés rattachés
        self.client.post(f"/employes/services/{vide.id}/supprimer/")
        self.assertFalse(Service.objects.filter(pk=vide.pk).exists())
        self.assertTrue(JournalAudit.objects.filter(action="service_supprime").exists())

    def test_service_d_un_chef_non_supprimable(self):
        vide = Service.objects.create(nom="Sécurité")
        self.compte("chef.secu", Profil.CHEF, service=vide)
        self.connecter(Profil.ADMIN)
        self.client.post(f"/employes/services/{vide.id}/supprimer/")
        self.assertTrue(Service.objects.filter(pk=vide.pk).exists())

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

    def test_rh_ne_peut_pas_supprimer_de_compte(self):
        u = self.compte("x", Profil.BORNE)
        self.connecter(Profil.RH)
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
        self.connecter(Profil.RH)
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
        self.connecter(Profil.RH)
        demain = (timezone.localdate() + timedelta(days=1)).isoformat()
        aujourdhui = timezone.localdate().isoformat()
        self.client.post("/pointages/manuel/", {"employe": self.ali.id, "type": "S", "date": demain, "heure": "10:00",
                                                "motif": "Motif suffisant"})
        self.client.post("/pointages/manuel/", {"employe": self.ali.id, "type": "S", "date": aujourdhui, "heure": "00:01",
                                                "motif": "ok"})
        self.client.post("/pointages/manuel/", {"employe": self.ali.id, "type": "X", "date": aujourdhui, "heure": "00:01",
                                                "motif": "Motif suffisant"})
        self.assertFalse(Pointage.objects.exists())

    def test_chef_ne_peut_pas_corriger(self):
        self.connecter(Profil.CHEF, service=self.compta)
        r = self.client.post("/pointages/manuel/", {"employe": self.ali.id, "type": "S",
                                                    "date": timezone.localdate().isoformat(), "heure": "00:01",
                                                    "motif": "Motif suffisant"})
        self.assertEqual(r.status_code, 403)

    def test_seules_les_corrections_sont_supprimables(self):
        self.connecter(Profil.RH)
        borne = Pointage.objects.create(employe=self.ali, type="E")
        manuel = Pointage.objects.create(employe=self.ali, type="S", manuel=True, motif="test")
        self.assertEqual(self.client.post(f"/pointages/manuel/{borne.id}/supprimer/").status_code, 404)
        self.client.post(f"/pointages/manuel/{manuel.id}/supprimer/")
        self.assertTrue(Pointage.objects.filter(pk=borne.pk).exists())
        self.assertFalse(Pointage.objects.filter(pk=manuel.pk).exists())

    def test_redirection_suivante_securisee(self):
        self.connecter(Profil.RH)
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
        u = self.compte("rh.ok", Profil.RH)
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
