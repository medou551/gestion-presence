# Gestion de présence des employés (Django + SQLite)

![Tests](https://github.com/medou551/gestion-presence/actions/workflows/tests.yml/badge.svg)

Pointage avec **vérification du visage**, **rôles**, **données chiffrées** et **journal d'audit**.
Chaque employé a une photo de référence ; à chaque pointage, la borne prend une photo, le visage est comparé
à la référence et le **serveur enregistre l'heure exacte (h:min:s)**. Premier pointage du jour = entrée, suivant = sortie.

- **Mise en service au bureau (Windows, HTTPS)** : suivez **[DEPLOIEMENT.md](DEPLOIEMENT.md)**.
- **Hébergement en ligne (PythonAnywhere)** : suivez **[DEPLOIEMENT_PYTHONANYWHERE.md](DEPLOIEMENT_PYTHONANYWHERE.md)**.
- **Ajouter / supprimer** employés, services, comptes, pointages oubliés : **[GUIDE_UTILISATION.md](GUIDE_UTILISATION.md)**.
- **Essai rapide sur votre PC** : double-cliquez **`installer_local.bat`** (section ci-dessous).

## Fonctionnalités

**Gestion**
- Ajouter / modifier / supprimer : services, employés, comptes ; **correction des pointages oubliés** (sortie manquante)
  avec motif obligatoire, marquée « Manuel » et journalisée.

**Pointage**
- Borne réservée au compte « Borne » : horloge, recherche par nom, photo automatique, code PIN facultatif.
- Visage comparé à la photo de référence ; refus si ce n'est pas la bonne personne, s'il ressemble plus à un collègue,
  si l'image a déjà servi (même fichier, copie de la référence ou d'un ancien pointage), ou en cas de double clic.
- Heure du serveur uniquement.
- **Pointage avec son téléphone** (compte Employé) : visage vérifié, uniquement pour soi-même, et seulement
  **à moins de 20 m du lieu de travail** (GPS, rayon réglable dans *Lieux*). Voir GUIDE_UTILISATION.md.

**Rôles**
| Rôle | Accès |
|---|---|
| Administrateur | Tout : comptes, services, employés, tableau, exports, journal d'audit |
| Ressources humaines | Employés et photos de référence, tableau et exports de tous les services |
| Chef de service | Tableau et exports de **son service** uniquement |
| Borne de pointage | Uniquement la page de pointage |
| Employé | Pointer avec son téléphone (sur le lieu de travail), son historique, ses données |

**Sécurité et confidentialité**
- Photos (référence et pointages), signatures du visage et sauvegardes **chiffrées** ; photos jamais servies directement.
- Clés secrètes hors du code, dans le fichier `.env` (créé automatiquement au premier lancement).
- Mots de passe forts, changement obligatoire à la première connexion, blocage après 5 échecs, déconnexion après 30 min d'inactivité.
- **Journal d'audit infalsifiable** : connexions, consultations, exports, modifications, pointages refusés.
- Photos de pointage supprimées après **30 jours** (les heures restent) ; effacement de la biométrie au départ d'un employé.
- En-têtes de sécurité stricts (CSP, anti-iframe, caméra limitée au site), HTTPS via Caddy en production.
- Analyse du visage par face-api.js (open source, MIT), incluse : fonctionne sans Internet. Pas de Pillow, dlib ni OpenCV :
  compatible avec les versions récentes de Python (testé jusqu'à 3.13, prévu pour 3.15).

## Essai rapide sur votre PC

**Windows** : double-cliquez **`installer_local.bat`**. Il crée l'environnement Python, installe les dépendances,
crée la base de données, vous demande l'identifiant et le mot de passe de l'administrateur, puis ouvre
**http://127.0.0.1:8000/** dans le navigateur. Fermez la fenêtre noire pour arrêter.

**À la main** (Windows, macOS, Linux) :
```bash
cd gestion_presence
python -m venv venv
venv\Scripts\activate            # macOS / Linux : source venv/bin/activate
pip install -r requirements.txt
python manage.py initialiser     # base de données + compte administrateur
python serveur.py                # ou : python manage.py runserver
```

Ouvrez **http://127.0.0.1:8000/** (bien `http://`, pas `https://`). L'administrateur peut ouvrir la borne pour tester.
En local, la caméra fonctionne sur `127.0.0.1` / `localhost` sans HTTPS.

**La base de données** est SQLite : un seul fichier, `db.sqlite3`, **rien à installer**. La commande `initialiser`
la crée, la met à jour (avec sauvegarde préalable) et contrôle son intégrité ; elle peut être relancée sans risque.

Au premier lancement, le fichier **`.env`** est créé avec des clés aléatoires. **Ne le supprimez pas** et gardez-en
une copie : sans lui, les photos déjà enregistrées deviennent illisibles.

**Mise à jour depuis la version précédente** : remplacez les fichiers (gardez `db.sqlite3`, `media` et `.env`), puis
`pip install -r requirements.txt` et `python manage.py initialiser`. Les photos et signatures existantes sont
chiffrées automatiquement.

## Navigateurs

L'application fonctionne avec les versions récentes de **Chrome, Edge, Firefox, Safari (Mac, iPad, iPhone), Opera
et Samsung Internet**, sur PC, tablette et téléphone.

- **Page de diagnostic** : ouvrez **`/diagnostic/`** (lien sur la page de connexion, aucune connexion nécessaire).
  Elle vérifie l'adresse, la caméra, les cookies et la reconnaissance, et dit quoi faire en cas de problème.
- **Sans carte graphique** (vieux PC, bureau à distance, accélération désactivée) : l'analyse passe automatiquement
  sur le processeur. C'est un peu plus lent (quelques secondes), mais aussi fiable.
- **Caméra refusée, absente ou occupée** : un message explique la marche à suivre pour le navigateur utilisé,
  avec un bouton « Réessayer ».
- **Adresse** : en local, `http://127.0.0.1:8000/` et `http://localhost:8000/` marchent toutes les deux (IPv4 et IPv6).

**Un navigateur affiche une erreur alors qu'un autre fonctionne** (par exemple Chrome mais pas Edge) :
ce n'est pas l'application, c'est un réglage mémorisé par ce navigateur sur ce PC.
1. Essayez l'autre adresse : `http://localhost:8000/` au lieu de `http://127.0.0.1:8000/` (ou l'inverse).
2. Essayez une fenêtre privée (Ctrl+Maj+N) : si ça marche, une extension ou d'anciennes données bloquent.
3. Chrome qui transforme `http` en `https` : `chrome://net-internals/#hsts` → *Delete domain security policies* →
   `127.0.0.1` puis `localhost` → *Delete* ; et `chrome://settings/security` → désactivez
   « Toujours utiliser des connexions sécurisées ». Fermez complètement Chrome, puis rouvrez-le.
4. Au bureau, avec l'installation HTTPS, ce problème n'existe plus : tous les navigateurs utilisent `https://`.

## Commandes utiles

| Commande | Rôle |
|---|---|
| `python manage.py initialiser` | Crée / met à jour la base (sauvegarde avant, contrôle après) |
| `python manage.py verifier_base` | Intégrité de la base et contrôle de la dernière sauvegarde |
| `python manage.py verifier_securite` | Vérifie la configuration avant la mise en service |
| `python manage.py sauvegarder` | Sauvegarde chiffrée et vérifiée (base + photos) dans `sauvegardes/` |
| `python manage.py restaurer FICHIER` | Restaure une sauvegarde (serveur arrêté) |
| `python manage.py purger_photos` | Supprime les photos de plus de 30 jours (aussi automatique) |
| `python manage.py configurer_production --adresse IP` | Passe en mode production HTTPS (serveur du bureau) |
| `python manage.py configurer_pythonanywhere --domaine X` | Configure l'hébergement PythonAnywhere |
| `python manage.py compacter_base` | Efface définitivement les restes de données supprimées |
| `python manage.py test pointage` | Lance les 85 tests automatiques |

## Réglages

Dans `.env` (ou `config/settings.py` pour les valeurs par défaut) :

| Réglage | Défaut | Rôle |
|---|---|---|
| `HEURE_ARRIVEE` | `08:00` | Entrée après cette heure = « Retard » |
| `DUREE_CONSERVATION_PHOTOS_JOURS` | `30` | Durée de conservation des photos de pointage |
| `SEUIL_RECONNAISSANCE` | `0.5` | Plus petit = plus strict (0,45 à 0,55) |
| `SAUVEGARDES_A_GARDER` | `14` | Nombre de sauvegardes conservées |
| `DOSSIER_SAUVEGARDES_COPIE` | (vide) | Copie de chaque sauvegarde vers un autre disque ou un NAS |
| `TIME_ZONE` (settings.py) | `Africa/Nouakchott` | Fuseau horaire |
| `SQLITE_WAL` | `True` | `False` sur un disque réseau (PythonAnywhere) |
| `EN_TETE_IP_CLIENT` | (vide) | En-tête de la vraie IP derrière un hébergeur (`HTTP_X_REAL_IP` sur PythonAnywhere) |

## Problèmes fréquents

- **ERR_SSL_PROTOCOL_ERROR en local** : tapez bien `http://127.0.0.1:8000/` (le serveur de test ne fait pas de HTTPS) ;
  si le navigateur remet `https`, voir la section « Navigateurs ».
- **ERR_CONNECTION_REFUSED / ERR_TIMED_OUT** : le serveur n'est pas lancé, ou un ancien serveur occupe le port 8000
  (`serveur.py` le signale et indique comment l'arrêter). Ne cliquez pas dans la fenêtre du serveur.
- **« Accès refusé »** : votre rôle n'autorise pas cette page (voir le tableau des rôles).
- **« Trop de tentatives »** : attendez 15 minutes ; un administrateur peut aussi réinitialiser le mot de passe dans *Comptes*.
- **« Aucun visage détecté »** : rapprochez-vous, face à la caméra, avec de la lumière devant vous.
- **« Visage non reconnu » pour le bon employé** : refaites sa photo de référence avec la caméra de la borne.
- **« Impossible de déchiffrer »** : le fichier `.env` a changé ; remettez celui d'origine.
- **« database is locked »** : ne devrait plus arriver (mode WAL) ; si oui, vérifiez qu'un seul serveur tourne.
- **Base endommagée** (`verifier_base` le signale) : restaurez la dernière sauvegarde (voir DEPLOIEMENT.md).
- **`SystemError: module PIL._imaging…`** : ce projet n'utilise pas Pillow (`pip uninstall pillow`).

## Structure

```
config/                réglages (lit .env) et URLs
serveur.py             serveur de production (Waitress)
pointage/
  models.py            Service, Employe, Pointage, Profil (rôle), JournalAudit
  roles.py             rôles, périmètres visibles, journalisation
  securite.py          en-têtes de sécurité, inactivité, changement de mot de passe
  chiffrement.py       chiffrement authentifié (bibliothèque standard Python)
  stockage.py          stockage chiffré des photos
  views*.py            borne, tableau, employés, comptes, journal, espace employé, connexion
  taches.py            purge des photos, sauvegardes chiffrées
  management/commands  commandes ci-dessus
  static/pointage/     styles, visage.js, face-api.js et modèles
  tests.py             85 tests (rôles, chiffrement, audit, connexion, pointage…)
deploiement/           scripts Windows : installer, démarrer, arrêter, mettre à jour, Caddy
installer_local.bat    installation et lancement en double-clic (essai sur un PC)
DEPLOIEMENT.md         guide de mise en service (dont la base de données)
GUIDE_UTILISATION.md   ajouter / supprimer : services, employés, comptes, pointages oubliés
```
