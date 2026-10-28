# Déploiement sur un serveur Windows du bureau

Ce guide installe l'application sur un PC Windows qui reste allumé au bureau (le « serveur »).
La borne de pointage et les postes des responsables s'y connectent par le réseau interne, en **HTTPS**.

```
 Borne (tablette/PC + webcam) ─┐
 Postes RH / chefs / employés ─┼──HTTPS──► Caddy (port 443) ──► Application (127.0.0.1:8000, Waitress)
                                │            certificat local      base SQLite + photos CHIFFRÉES
                                └─ réseau du bureau uniquement
```

## 1. Avant de commencer

- Un PC Windows 10/11 ou Windows Server, allumé en permanence, avec **une adresse IP fixe** sur le réseau
  (réservez-la dans votre box/routeur, par exemple `192.168.1.10`).
- **Python 3.10 ou plus récent** : https://www.python.org/downloads/ — cochez « Add python.exe to PATH ».
- Le réseau du PC doit être en mode **Privé** (Paramètres → Réseau → Propriétés).
- Activez **BitLocker** sur le disque du serveur si possible (protection en cas de vol du PC).

## 2. Installation (une seule fois)

1. Décompressez le projet dans **`C:\GestionPresence`** (pas dans Téléchargements ni dans votre dossier personnel).
2. Ouvrez **PowerShell en administrateur** (clic droit sur le menu Démarrer → Terminal (administrateur)).
3. Lancez :

```powershell
cd C:\GestionPresence\deploiement
powershell -ExecutionPolicy Bypass -File .\installer.ps1 -Adresse 192.168.1.10
```

Le script fait tout : environnement Python, base de données, mode production, protection du dossier,
téléchargement de Caddy (HTTPS), pare-feu, démarrage automatique au lancement de Windows, sauvegarde
chiffrée chaque soir à 21 h, puis une vérification de sécurité. Il vous demande de créer le compte administrateur.

4. **Mettez le fichier `C:\GestionPresence\.env` en lieu sûr** (clé USB rangée dans un coffre, ou gestionnaire
   de mots de passe). Il contient la clé de chiffrement : **sans elle, les photos et les sauvegardes sont
   définitivement illisibles**. Ne l'envoyez jamais par e-mail ou messagerie.

## 3. Installer le certificat sur la borne et les autres postes

Caddy crée sa propre autorité de certification pour le réseau interne. Chaque appareil qui ouvre l'application
doit lui faire confiance une fois, sinon le navigateur affiche « connexion non sécurisée » et **bloque la caméra**.

Le fichier à installer : `C:\GestionPresence\deploiement\certificat_a_installer_sur_les_postes.crt`
(copiez-le sur une clé USB).

- **Windows** : double-cliquez le fichier → *Installer le certificat* → *Ordinateur local* →
  *Placer tous les certificats dans le magasin suivant* → *Autorités de certification racines de confiance* → Terminer.
  Ou en PowerShell administrateur :
  `Import-Certificate -FilePath .\certificat_a_installer_sur_les_postes.crt -CertStoreLocation Cert:\LocalMachine\Root`
- **Android** : Paramètres → Sécurité → Chiffrement et identifiants → Installer un certificat → *Certificat CA*.
- **iPad / iPhone** : envoyez le fichier sur l'appareil, installez le profil, puis Réglages → Général →
  Informations → Réglages des certificats → activez la confiance totale.

Ouvrez ensuite **https://192.168.1.10** (votre adresse) : le cadenas doit apparaître sans avertissement.

## 4. Premiers réglages dans l'application

Connectez-vous avec le compte administrateur, puis (détails dans **[GUIDE_UTILISATION.md](GUIDE_UTILISATION.md)**) :

1. **Employés** → ajoutez les services (Comptabilité, Accueil…), puis chaque employé avec sa **photo de référence**.
2. **Comptes** → créez :
   - un compte **Borne de pointage** (ex. `borne-entree`) ;
   - les comptes **Ressources humaines** ;
   - un compte **Chef de service** par service ;
   - si vous le souhaitez, un compte **Employé** pour chaque employé (pour consulter son historique).

   Un mot de passe temporaire s'affiche **une seule fois** : remettez-le en main propre.
   Chacun devra le changer à sa première connexion (10 caractères minimum).

| Rôle | Accès |
|---|---|
| Administrateur | Tout : comptes, services, employés, tableau, exports, journal d'audit, administration |
| Ressources humaines | Employés (ajout, photos, modification, effacement), tableau et exports de tous les services |
| Chef de service | Tableau et exports de **son service uniquement**, en lecture seule |
| Borne de pointage | **Uniquement** la page de pointage |
| Employé | **Uniquement** son propre historique et le téléchargement de ses données |

Gardez 1 à 3 comptes administrateurs maximum.

## 5. Préparer la borne

1. Sur la tablette ou le PC de la borne, installez le certificat (étape 3).
2. Ouvrez Chrome ou Edge sur `https://192.168.1.10`, connectez-vous avec le compte **Borne**,
   et **autorisez la caméra** (une fois).
3. Le compte Borne reste connecté 30 jours et ne voit que la page de pointage.
4. Recommandé sur un PC Windows : **Google Chrome en mode kiosque** (plein écran, sans barre d'adresse) :
   `"C:\Program Files\Google\Chrome\Application\chrome.exe" --kiosk https://192.168.1.10`
   Placez ce raccourci dans le dossier Démarrage de Windows (touche Windows + R → `shell:startup`).
   Faites d'abord la connexion et l'autorisation de la caméra dans Chrome normal : le mode kiosque les conserve.
   (Évitez le mode kiosque d'Edge : il ouvre une session privée qui oublie la connexion et la caméra.)
5. Placez la borne face à une source de lumière (pas dos à une fenêtre).

## 6. Utilisation au quotidien

| Action | Comment |
|---|---|
| Arrêter / redémarrer | `deploiement\arreter.ps1` / `deploiement\demarrer.ps1` (PowerShell administrateur) — ou redémarrer Windows |
| Sauvegarde immédiate | double-clic sur `deploiement\sauvegarder_maintenant.bat` (en administrateur) |
| Vérifier la sécurité | `venv\Scripts\python manage.py verifier_securite` |
| Vérifier la base | `venv\Scripts\python manage.py verifier_base` |
| Journaux HTTPS | `deploiement\journaux\caddy.log` |

### Sauvegardes

- Chaque soir à 21 h, une sauvegarde **chiffrée** (base + photos) est créée dans `C:\GestionPresence\sauvegardes`,
  puis **vérifiée automatiquement** (déchiffrement et contrôle d'intégrité). Les 14 dernières sont gardées.
- **Copiez régulièrement ce dossier ailleurs** (disque externe, NAS) : une sauvegarde sur le même disque ne protège
  pas d'une panne. Les fichiers sont chiffrés : ils peuvent être stockés hors du bureau sans exposer les données.

### Restaurer une sauvegarde

```powershell
cd C:\GestionPresence
.\deploiement\arreter.ps1
.\venv\Scripts\python manage.py restaurer sauvegardes\presence_AAAAMMJJ_HHMMSS.sauvegarde
.\venv\Scripts\python manage.py migrate
.\deploiement\demarrer.ps1
```

La restauration exige le **même fichier `.env`** (même clé de chiffrement) que lors de la sauvegarde.
Elle contrôle la sauvegarde **avant** de toucher à quoi que ce soit, et sauvegarde l'état actuel
(`sauvegardes\avant_restauration_….sauvegarde`) : on peut toujours revenir en arrière.

### Mettre à jour l'application

Copiez les nouveaux fichiers par-dessus l'ancien dossier **sans remplacer** `.env`, `db.sqlite3`, `media`,
`sauvegardes`, `venv` et `deploiement\caddy_data`, puis :
`powershell -ExecutionPolicy Bypass -File .\deploiement\mettre_a_jour.ps1`
(sauvegarde automatique avant la mise à jour).

## 7. La base de données

L'application utilise **SQLite** : toute la base tient dans **un seul fichier**, `C:\GestionPresence\db.sqlite3`.
**Il n'y a rien à installer** (pas de serveur de base de données, pas de service, pas de mot de passe de base) :
SQLite est intégré à Python. La base est créée et mise à jour par l'installateur (commande `initialiser`).

**Ce qu'elle contient** : services, employés (nom, poste, service), pointages (date, heure, type, motif des corrections),
comptes (mots de passe hachés, jamais en clair), profils et rôles, journal d'audit.
Les **photos ne sont pas dans la base** : elles sont dans le dossier `media`, chiffrées.
Les **signatures du visage** sont dans la base, **chiffrées**.

**Comment elle est protégée**
- Fichier accessible aux seuls administrateurs Windows et au système (droits posés par l'installateur).
- Jamais exposée sur le réseau : seule l'application, sur le serveur, l'ouvre.
- Données biométriques chiffrées ; mots de passe et codes PIN hachés (PBKDF2).
- Effacement sécurisé : les données supprimées sont écrasées, pas seulement marquées comme libres.
- Journal d'audit chaîné : toute modification directe de la base est détectée.
- BitLocker recommandé pour protéger aussi les noms et les heures en cas de vol du PC.

**Fiabilité**
- Mode **WAL** : la borne peut pointer pendant que les responsables consultent le tableau, sans blocage.
- Contrôle d'intégrité à chaque installation, mise à jour et sauvegarde.
- Sauvegarde **avant chaque mise à jour** et **avant chaque restauration**, automatiquement.

**Commandes** (PowerShell, dans `C:\GestionPresence`) :

| Commande | Rôle |
|---|---|
| `.\venv\Scripts\python manage.py verifier_base` | Intégrité de la base, dernière sauvegarde et son contrôle |
| `.\venv\Scripts\python manage.py initialiser` | Crée ou met à jour la base (sans risque, peut être relancée) |
| `.\venv\Scripts\python manage.py sauvegarder` | Sauvegarde chiffrée et vérifiée, immédiate |
| `.\venv\Scripts\python manage.py compacter_base` | Compacte le fichier et efface les restes de données supprimées |

**Copie des sauvegardes sur un autre disque** : ajoutez dans le fichier `.env` une ligne comme
`DOSSIER_SAUVEGARDES_COPIE=D:\SauvegardesPresence` (disque externe) ou `DOSSIER_SAUVEGARDES_COPIE=\\NAS\presence`.
Chaque sauvegarde du soir y sera copiée. Les fichiers sont chiffrés : ils ne révèlent rien sans le fichier `.env`.

**Capacité** : SQLite convient très bien pour une entreprise de quelques centaines d'employés et quelques bornes.
Au-delà (plusieurs sites, des milliers d'employés), on peut passer à PostgreSQL ; l'application Django le permet.

## 8. Ce qui protège les données

| Protection | Détail |
|---|---|
| HTTPS partout | Certificat local, redirection automatique http → https, HSTS |
| Application non exposée | Le serveur Python n'écoute que sur 127.0.0.1 ; seul Caddy est joignable, et seulement sur le réseau privé |
| Photos chiffrées | Photos de référence et de pointage chiffrées sur le disque (chiffrement authentifié) ; jamais servies directement, toujours via une vérification des droits |
| Signatures du visage chiffrées | Dans la base de données |
| Sauvegardes chiffrées | Avec la même clé ; inutilisables sans le fichier `.env` |
| Rôles | Chacun ne voit que ce qui le concerne ; chaque refus d'accès est enregistré |
| Comptes | Mots de passe forts obligatoires, changement à la première connexion, blocage 15 min après 5 échecs, déconnexion après 30 min d'inactivité |
| Journal d'audit | Connexions, consultations, exports, modifications, pointages refusés. Infalsifiable : chaque ligne contient l'empreinte de la précédente ; toute modification directe de la base est signalée |
| Conservation limitée | Photos de pointage supprimées après 30 jours (les heures restent) ; effacement de la biométrie au départ d'un employé |
| Droits des employés | Chaque employé peut consulter et télécharger ses données |
| Navigateur | Content-Security-Policy stricte, anti-iframe, caméra autorisée seulement pour le site, pages privées non mises en cache |
| Dossier du serveur | Accessible aux seuls administrateurs Windows et au système |

## 9. Limites et bonnes pratiques

- **Accès physique au serveur** : un administrateur Windows du serveur peut tout lire (y compris le `.env`).
  Limitez les comptes administrateurs Windows, verrouillez la session, activez BitLocker.
- Le dossier `deploiement\caddy_data` contient la clé de l'autorité de certification locale : ne le copiez pas
  et ne le partagez pas.
- La reconnaissance du visage ne détecte pas encore une photo imprimée ou un écran présenté à la caméra ;
  les photos côte à côte du tableau de bord permettent de le repérer.
- **Cadre légal** : les photos et signatures du visage sont des données biométriques. Informez les employés par écrit
  (finalité, durée de conservation, droits d'accès et d'effacement), recueillez leur accord et vérifiez les formalités
  prévues par la loi de votre pays sur la protection des données personnelles (en Mauritanie : loi n° 2017-020).
  Demandez conseil à un juriste si nécessaire.
- Ne donnez pas accès à l'application depuis Internet : elle est prévue pour le réseau du bureau.

## 10. Désinstaller

`powershell -ExecutionPolicy Bypass -File .\deploiement\desinstaller.ps1` retire les tâches et la règle de pare-feu.
Les données restent dans le dossier.
