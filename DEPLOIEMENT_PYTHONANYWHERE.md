# Déploiement sur PythonAnywhere

PythonAnywhere héberge l'application sur Internet, avec une adresse du type
**`https://VOTRE_NOM.pythonanywhere.com`**. Le **HTTPS est fourni** : la caméra fonctionne directement sur la borne
et sur tous les appareils, sans installer de certificat.

> Dans ce guide, remplacez **`medou551`** par votre nom d'utilisateur PythonAnywhere.

## 0. Avant de commencer : à savoir

- **Les données sont hébergées chez PythonAnywhere** (serveurs aux États-Unis, ou en Europe si vous créez le compte sur
  `eu.pythonanywhere.com`, conseillé). Les photos et signatures du visage restent **chiffrées** avec votre clé, mais les
  noms et les heures sont lisibles par l'hébergeur. Vérifiez que l'hébergement de données biométriques à l'étranger est
  compatible avec la loi n° 2017-020 et informez-en les employés.
- **L'application est accessible depuis Internet** : utilisez des mots de passe solides, peu de comptes administrateurs,
  et surveillez le **Journal** (tentatives de connexion échouées).
- **Compte gratuit** : suffisant pour tester et pour une petite équipe, avec des limites :
  1 application, environ 512 Mo de disque, temps de calcul limité, une seule tâche planifiée,
  et il faut cliquer « Run until 3 months from today » dans l'onglet *Web* tous les 3 mois.
  Les photos font environ 50 à 100 Ko et sont supprimées après 30 jours : comptez ~100 Mo pour 50 employés.
- La reconnaissance du visage tourne **dans le navigateur de la borne**, pas sur le serveur : un compte gratuit suffit.

## 1. Récupérer le code

Sur pythonanywhere.com : onglet **Consoles** → **Bash**. Puis :

```bash
git clone https://github.com/medou551/gestion-presence.git
cd gestion-presence
```

Dépôt privé : GitHub demande votre identifiant et un **jeton d'accès** à la place du mot de passe
(GitHub → Settings → Developer settings → Personal access tokens → *Fine-grained*, accès en lecture au dépôt).
Ou envoyez le zip par l'onglet **Files** puis `unzip gestion_presence.zip`.

## 2. Environnement Python

Toujours dans la console Bash :

```bash
mkvirtualenv --python=/usr/bin/python3.13 presence
pip install -r requirements.txt
```

(Si Python 3.13 n'est pas proposé, utilisez `python3.12` ici **et** à l'étape 4.)

## 3. Configuration et base de données

```bash
python manage.py configurer_pythonanywhere --domaine medou551.pythonanywhere.com
python manage.py initialiser
```

- La première commande écrit le fichier `.env` : mode production, HTTPS, vraie adresse IP des visiteurs
  (en-tête `X-Real-IP` de PythonAnywhere), SQLite adapté au disque réseau. Elle affiche aussi le **fichier WSGI**
  à utiliser à l'étape 4.
- La seconde crée la base, contrôle son intégrité, prépare les fichiers statiques et vous fait créer le
  **compte administrateur**.

**Copiez immédiatement le contenu du fichier `.env`** en lieu sûr (gestionnaire de mots de passe) :
`cat .env` dans la console. Sans `CLE_CHIFFREMENT`, les photos sont illisibles.

## 4. Créer l'application web

Onglet **Web** → **Add a new web app** :

1. Domaine : `medou551.pythonanywhere.com` → **Next**.
2. Choisissez **Manual configuration** (surtout pas « Django ») → **Python 3.13** (le même qu'à l'étape 2).
3. Dans la page de l'application :
   - **Virtualenv** : tapez `presence`.
   - **Source code** et **Working directory** : `/home/medou551/gestion-presence`.
   - **WSGI configuration file** : cliquez le lien, **effacez tout** et collez le contenu affiché à l'étape 3
     (aussi dans `deploiement/wsgi_pythonanywhere.py`). Enregistrez.
   - **Static files** : URL `/static/` → Directory `/home/medou551/gestion-presence/staticfiles`.
   - ⚠ **Ne créez aucune ligne pour `/media/`** : les photos chiffrées doivent passer par l'application,
     qui vérifie les droits.
   - **Security** : activez **Force HTTPS**.
4. Cliquez **Reload** en haut de la page.

Ouvrez **https://medou551.pythonanywhere.com/diagnostic/** puis **https://medou551.pythonanywhere.com/connexion/**.

## 5. Sauvegarde automatique

Onglet **Tasks** → tâche quotidienne (par exemple 21:00 UTC) :

```bash
cd /home/medou551/gestion-presence && /home/medou551/.virtualenvs/presence/bin/python manage.py sauvegarder
```

Les sauvegardes chiffrées vont dans `gestion-presence/sauvegardes/`. Téléchargez-en une régulièrement
(onglet **Files**) pour en garder une copie chez vous.

## 6. Mettre à jour après une modification sur GitHub

```bash
cd ~/gestion-presence
workon presence
git pull
pip install -r requirements.txt
python manage.py initialiser
```

Puis **Reload** dans l'onglet **Web**. (`initialiser` sauvegarde la base avant de la modifier.)

## 7. Vérifier

```bash
cd ~/gestion-presence && workon presence
python manage.py verifier_securite
python manage.py verifier_base
```

En cas d'erreur sur le site, regardez le **Error log** (lien dans l'onglet **Web**).

| Problème | Solution |
|---|---|
| « DisallowedHost » / Bad Request (400) | Relancez `configurer_pythonanywhere` avec le bon domaine, puis **Reload** |
| « CSRF verification failed » | Ouvrez le site en `https://` ; vérifiez **Force HTTPS** |
| Page sans mise en forme | Vérifiez la ligne **Static files** (`/static/` → `.../staticfiles`) puis **Reload** |
| « Impossible de déchiffrer » | Le fichier `.env` a été remplacé : remettez celui d'origine |
| Tout le monde bloqué après des erreurs de mot de passe | Vérifiez `EN_TETE_IP_CLIENT=HTTP_X_REAL_IP` dans `.env` |
| Site arrêté après 3 mois (compte gratuit) | Onglet **Web** → *Run until 3 months from today* |
