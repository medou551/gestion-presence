"""Réglages du projet « Gestion de présence ».

Les secrets (clé Django, clé de chiffrement) ne sont PAS dans ce fichier : ils sont lus dans le
fichier `.env` à la racine du projet, créé automatiquement au premier lancement.
Ne partagez jamais ce fichier `.env` et gardez-en une copie de sauvegarde à part (clé USB, coffre).
"""
import os
import secrets
from base64 import urlsafe_b64encode
from pathlib import Path

BASE_DIR = Path(__file__).resolve().parent.parent
FICHIER_ENV = BASE_DIR / ".env"


# ---------------------------------------------------------------- Lecture du fichier .env

def _lire_env(chemin):
    valeurs = {}
    if chemin.exists():
        for ligne in chemin.read_text(encoding="utf-8").splitlines():
            ligne = ligne.strip()
            if ligne and not ligne.startswith("#") and "=" in ligne:
                cle, _, valeur = ligne.partition("=")
                valeurs[cle.strip()] = valeur.strip().strip('"').strip("'")
    return valeurs


def _creer_env_si_absent(chemin):
    """Premier lancement : génère des secrets aléatoires et les enregistre dans .env."""
    if chemin.exists():
        return
    chemin.write_text(
        "# Configuration de Gestion de présence — NE PAS PARTAGER CE FICHIER.\n"
        "# Gardez une copie de ce fichier en lieu sûr : sans CLE_CHIFFREMENT, les photos sont illisibles.\n\n"
        f"SECRET_KEY={secrets.token_urlsafe(50)}\n"
        f"CLE_CHIFFREMENT={urlsafe_b64encode(secrets.token_bytes(32)).decode()}\n\n"
        "# True uniquement pour le développement (affiche les erreurs détaillées)\n"
        "DEBUG=False\n"
        "# Noms ou adresses par lesquels on accède au site, séparés par des virgules\n"
        "ALLOWED_HOSTS=127.0.0.1,localhost,[::1]\n"
        "# Mettre True quand le site est servi en HTTPS (derrière Caddy)\n"
        "HTTPS=False\n"
        "# Adresses HTTPS complètes autorisées (ex. https://presence.local,https://192.168.1.10)\n"
        "CSRF_TRUSTED_ORIGINS=\n",
        encoding="utf-8",
    )
    try:
        os.chmod(chemin, 0o600)
    except OSError:
        pass


if not os.environ.get("GP_PAS_DE_ENV"):
    _creer_env_si_absent(FICHIER_ENV)
_ENV = {**_lire_env(FICHIER_ENV), **{k: v for k, v in os.environ.items() if k.startswith(("GP_", "DJANGO_"))}}


def env(nom, defaut=""):
    return os.environ.get(nom, _ENV.get(nom, defaut))


def env_bool(nom, defaut=False):
    return env(nom, str(defaut)).strip().lower() in ("1", "true", "vrai", "oui", "yes")


def env_liste(nom, defaut=""):
    return [x.strip() for x in env(nom, defaut).split(",") if x.strip()]


# ---------------------------------------------------------------- Sécurité de base

SECRET_KEY = env("SECRET_KEY")
CLE_CHIFFREMENT = env("CLE_CHIFFREMENT")
DEBUG = env_bool("DEBUG", False)
ALLOWED_HOSTS = env_liste("ALLOWED_HOSTS", "127.0.0.1,localhost,[::1]")
# localhost en IPv6 (certains navigateurs l'utilisent en premier) : toujours autorisé
if "[::1]" not in ALLOWED_HOSTS and ("localhost" in ALLOWED_HOSTS or "127.0.0.1" in ALLOWED_HOSTS):
    ALLOWED_HOSTS.append("[::1]")
CSRF_TRUSTED_ORIGINS = env_liste("CSRF_TRUSTED_ORIGINS")
HTTPS = env_bool("HTTPS", False)

if not SECRET_KEY or not CLE_CHIFFREMENT:
    from django.core.exceptions import ImproperlyConfigured
    raise ImproperlyConfigured("SECRET_KEY et CLE_CHIFFREMENT doivent être définis dans le fichier .env")


# ---------------------------------------------------------------- Application

INSTALLED_APPS = [
    "django.contrib.admin",
    "django.contrib.auth",
    "django.contrib.contenttypes",
    "django.contrib.sessions",
    "django.contrib.messages",
    "django.contrib.staticfiles",
    "pointage",
]

MIDDLEWARE = [
    "pointage.securite.IPClientMiddleware",
    "django.middleware.security.SecurityMiddleware",
    "whitenoise.middleware.WhiteNoiseMiddleware",
    "django.contrib.sessions.middleware.SessionMiddleware",
    "django.middleware.common.CommonMiddleware",
    "django.middleware.csrf.CsrfViewMiddleware",
    "django.contrib.auth.middleware.AuthenticationMiddleware",
    "django.contrib.messages.middleware.MessageMiddleware",
    "django.middleware.clickjacking.XFrameOptionsMiddleware",
    "pointage.securite.EnTetesSecuriteMiddleware",
    "pointage.securite.SessionMiddleware",
]

ROOT_URLCONF = "config.urls"

TEMPLATES = [
    {
        "BACKEND": "django.template.backends.django.DjangoTemplates",
        "DIRS": [],
        "APP_DIRS": True,
        "OPTIONS": {
            "context_processors": [
                "django.template.context_processors.request",
                "django.contrib.auth.context_processors.auth",
                "django.contrib.messages.context_processors.messages",
                "pointage.roles.contexte_role",
            ],
        },
    },
]

WSGI_APPLICATION = "config.wsgi.application"

# ---------------------------------------------------------------- Base de données : SQLite
# WAL : idéal sur un disque local (serveur du bureau). À désactiver (SQLITE_WAL=False) sur un disque réseau,
# par exemple chez PythonAnywhere, où le mode WAL n'est pas fiable.
SQLITE_WAL = env_bool("SQLITE_WAL", True)

# Un seul fichier (db.sqlite3), rien à installer. Réglages pour plusieurs postes en même temps
# (borne + tableaux de bord) sans erreur « database is locked » :
#   - WAL : les lectures ne bloquent pas les écritures ;
#   - IMMEDIATE : chaque écriture réserve la base dès le début (pas de blocage mutuel) ;
#   - timeout : attend jusqu'à 20 s qu'une autre écriture se termine ;
#   - secure_delete : les données supprimées sont écrasées par des zéros ;
#   - foreign_keys : cohérence des liens entre tables garantie par la base.
DATABASES = {
    "default": {
        "ENGINE": "django.db.backends.sqlite3",
        "NAME": Path(env("CHEMIN_BASE", str(BASE_DIR / "db.sqlite3"))),
        "OPTIONS": {
            "timeout": 20,
            "transaction_mode": "IMMEDIATE",
            "init_command": (
                f"PRAGMA journal_mode={'WAL' if SQLITE_WAL else 'DELETE'};"
                "PRAGMA synchronous=NORMAL;"
                "PRAGMA secure_delete=ON;"
                "PRAGMA foreign_keys=ON;"
                "PRAGMA busy_timeout=20000;"
            ),
        },
    }
}

# Mots de passe : 10 caractères minimum, pas trop simples, pas uniquement des chiffres
AUTH_PASSWORD_VALIDATORS = [
    {"NAME": "django.contrib.auth.password_validation.UserAttributeSimilarityValidator"},
    {"NAME": "django.contrib.auth.password_validation.MinimumLengthValidator", "OPTIONS": {"min_length": 10}},
    {"NAME": "django.contrib.auth.password_validation.CommonPasswordValidator"},
    {"NAME": "django.contrib.auth.password_validation.NumericPasswordValidator"},
]

LANGUAGE_CODE = "fr-fr"
TIME_ZONE = "Africa/Nouakchott"
USE_I18N = True
USE_TZ = True

STATIC_URL = "static/"
STATIC_ROOT = BASE_DIR / "staticfiles"
STATIC_ROOT.mkdir(exist_ok=True)
# Les fichiers statiques sont servis par WhiteNoise (même sans « collectstatic » en local)
WHITENOISE_USE_FINDERS = True
WHITENOISE_MIMETYPES = {".bin": "application/octet-stream"}

DEFAULT_AUTO_FIELD = "django.db.models.BigAutoField"

# Photos : stockées CHIFFRÉES dans ce dossier, jamais servies directement
MEDIA_ROOT = BASE_DIR / "media"
DOSSIER_SAUVEGARDES = Path(env("DOSSIER_SAUVEGARDES", str(BASE_DIR / "sauvegardes")))
# Copie de chaque sauvegarde vers un autre disque ou un NAS (ex. D:\Sauvegardes ou \\NAS\presence) — facultatif
DOSSIER_SAUVEGARDES_COPIE = env("DOSSIER_SAUVEGARDES_COPIE", "")
# Alerte si la dernière sauvegarde a plus de ce nombre d'heures
SAUVEGARDE_ALERTE_HEURES = 48

LOGIN_URL = "/connexion/"
LOGIN_REDIRECT_URL = "/accueil/"
LOGOUT_REDIRECT_URL = "/connexion/"

# Cache sur disque : partagé entre tous les processus du serveur (blocage des connexions fiable partout)
CACHES = {"default": {
    "BACKEND": "django.core.cache.backends.filebased.FileBasedCache",
    "LOCATION": str(BASE_DIR / ".cache"),
}}

# Hébergeur derrière un répartiteur de charge : nom de l'en-tête contenant la VRAIE adresse IP du visiteur.
# PythonAnywhere : HTTP_X_REAL_IP. Laisser vide sur le serveur du bureau (Waitress s'en charge avec Caddy).
EN_TETE_IP_CLIENT = env("EN_TETE_IP_CLIENT", "")


# ---------------------------------------------------------------- Sessions et cookies

SESSION_COOKIE_HTTPONLY = True
SESSION_COOKIE_SAMESITE = "Lax"
CSRF_COOKIE_SAMESITE = "Lax"
SESSION_COOKIE_AGE = 8 * 3600              # 8 heures maximum pour une session de travail
SESSION_INACTIVITE_MINUTES = 30            # déconnexion après 30 minutes sans activité

if HTTPS:
    SESSION_COOKIE_SECURE = True
    CSRF_COOKIE_SECURE = True
    # Caddy ajoute cet en-tête : Django sait ainsi que la connexion d'origine était en HTTPS
    SECURE_PROXY_SSL_HEADER = ("HTTP_X_FORWARDED_PROTO", "https")
    SECURE_HSTS_SECONDS = 31536000
    SECURE_HSTS_INCLUDE_SUBDOMAINS = False
    # La redirection http → https est faite par Caddy
    SECURE_SSL_REDIRECT = False

SECURE_CONTENT_TYPE_NOSNIFF = True
SECURE_REFERRER_POLICY = "same-origin"
SECURE_CROSS_ORIGIN_OPENER_POLICY = "same-origin"
X_FRAME_OPTIONS = "DENY"


# ---------------------------------------------------------------- Protection des connexions

CONNEXION_ECHECS_MAX = 5                   # après 5 mots de passe faux…
CONNEXION_BLOCAGE_MINUTES = 15             # …le compte et l'adresse sont bloqués 15 minutes


# ---------------------------------------------------------------- Pointage

# Délai minimum entre deux pointages d'un même employé (évite les doubles clics)
POINTAGE_DELAI_MIN_SECONDES = 60
# Ancien « poste de pointage » (visage, choix du nom) : retiré de l'administration, désactivé par défaut
POSTE_POINTAGE = env_bool("POSTE_POINTAGE", False)
# Pointage depuis le téléphone de l'employé (compte « Employé » + vérification du visage)
POINTAGE_TELEPHONE = env_bool("POINTAGE_TELEPHONE", False)  # par défaut : pointage par QR code
# Réseaux autorisés pour ce pointage, ex. « 41.188.10.25 » (adresse publique du bureau) ou « 192.168.1.0/24 ».
# Vide = depuis n'importe où (déconseillé : un employé pourrait pointer depuis chez lui).
POINTAGE_TELEPHONE_RESEAUX = env_liste("POINTAGE_TELEPHONE_RESEAUX", "")
# Durée normale d'une journée : au-delà, ce sont des heures supplémentaires.
# Une sortie avant cette durée demande une confirmation (« sortie anticipée »).
HEURES_JOURNEE = float(env("HEURES_JOURNEE", "8"))
# QR code de la tablette : renouvelé toutes les 15 s, valable 90 s (une photo du QR envoyée à un collègue
# ne sert plus à rien quelques instants plus tard)
QR_RENOUVELLEMENT_SECONDES = 15
QR_VALIDITE_SECONDES = 90
# Les employés restent connectés sur leur téléphone (pour scanner sans retaper le mot de passe)
SESSION_EMPLOYE_JOURS = int(env("SESSION_EMPLOYE_JOURS", "60"))
# Heure normale d'arrivée : au-delà, l'entrée est marquée « en retard »
HEURE_ARRIVEE = env("HEURE_ARRIVEE", "08:00")
# Les photos des pointages sont supprimées après ce nombre de jours (les heures sont conservées)
DUREE_CONSERVATION_PHOTOS_JOURS = int(env("DUREE_CONSERVATION_PHOTOS_JOURS", "30"))
# Nombre de sauvegardes conservées
SAUVEGARDES_A_GARDER = int(env("SAUVEGARDES_A_GARDER", "14"))

# ---- Reconnaissance faciale ----
# Distance maximale entre le visage du pointage et la photo de référence.
# Plus petit = plus strict (0.45 très strict, 0.55 plus tolérant). 0.5 est un bon compromis.
SEUIL_RECONNAISSANCE = float(env("SEUIL_RECONNAISSANCE", "0.5"))
# En dessous de cette distance, deux photos sont considérées comme LA MÊME image (doublon / photo réutilisée).
SEUIL_DOUBLON = 0.02


# ---------------------------------------------------------------- Journaux techniques

LOGGING = {
    "version": 1,
    "disable_existing_loggers": False,
    "handlers": {"console": {"class": "logging.StreamHandler"}},
    "loggers": {"django.security": {"handlers": ["console"], "level": "WARNING"}},
}
