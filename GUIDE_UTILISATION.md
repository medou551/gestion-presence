# Guide d'utilisation : ajouter et supprimer

Ce guide explique comment ajouter et supprimer les services, les employés, les comptes et les pointages oubliés.
Il n'y a que **deux rôles** : l'**Administrateur** (fait tout ce qui est décrit ici) et l'**Utilisateur (employé)**,
qui pointe avec son téléphone et consulte ses heures. Chaque action est enregistrée dans le **Journal**.

| Quoi | Ajouter | Modifier | Supprimer |
|---|---|---|---|
| Service | Employés → « Services » → Ajouter | Administration | × à côté du nom (s'il est vide) |
| Employé | Employés → formulaire « Nouvel employé » | Employés → Modifier | Employés → Modifier → bas de page |
| Photo de référence | Employés → Ajouter la photo | Employés → Changer la photo | Employés → Modifier → Effacer les données biométriques |
| Compte (connexion) | Comptes → « Nouveau compte » | Comptes → Gérer | Comptes → Gérer → Supprimer le compte |
| Pointage oublié | Tableau de bord → « Corriger un oubli » | — | « Supprimer » sur la correction |

---

## Les services

**Ajouter** : menu **Employés** → en bas à droite, section **Services** → tapez le nom (ex. « Comptabilité ») → **Ajouter**.

**Supprimer** : cliquez la **×** à côté du nom du service, puis confirmez.
Un service ne peut être supprimé que s'il est **vide** : changez d'abord le service de ses employés
(Employés → Modifier).

## Les employés

**Ajouter** (menu **Employés**, formulaire de gauche) :
1. Nom complet (obligatoire), poste, service, code PIN (facultatif).
2. **📷 Prendre la photo** (l'employé face à la caméra) ou **Choisir un fichier**.
3. Attendez « Visage détecté », puis **Enregistrer**.

Le même visage ne peut pas être enregistré pour deux employés. Ensuite, créez-lui son accès pour qu'il puisse pointer avec son téléphone (voir plus bas).

**Modifier** : dans la liste, **Modifier** → nom, poste, service, code PIN, actif / inactif.
**Changer la photo** : bouton **Changer la photo** dans la liste.

**Supprimer** — trois possibilités, de la plus douce à la plus définitive (Employés → **Modifier**) :

| Action | Effet | Quand l'utiliser |
|---|---|---|
| Décocher **Actif** | Ne peut plus pointer ; tout est conservé | Absence longue, suspension |
| **Effacer les données biométriques** | Supprime la photo de référence, la signature du visage et toutes les photos de pointage ; garde les heures ; désactive l'employé | **Départ de l'entreprise** (recommandé) |
| **Supprimer définitivement** (Admin) | Supprime l'employé, ses photos, **tous ses pointages** et son compte. Il faut retaper son nom pour confirmer | Erreur de saisie, demande d'effacement total |

Les heures de présence servent souvent pour la paie : préférez « Effacer les données biométriques » au départ d'un employé.

## Les comptes (connexions)

Un **employé** (fiche avec photo, qui pointe) et un **compte** (identifiant + mot de passe pour ouvrir l'application)
sont deux choses différentes : pour pointer avec son téléphone, l'employé a besoin d'un compte « Utilisateur ».

**Ajouter** (menu **Comptes**, réservé à l'administrateur) :
1. Identifiant (ex. `ahmed.salem`), puis le **rôle** : **Administrateur**, ou **Utilisateur (employé)** en choisissant
   l'employé concerné. (Plus simple pour un employé : Employés → Modifier → **Créer son accès**.)
2. **Créer le compte** : un mot de passe temporaire s'affiche **une seule fois**. Notez-le et remettez-le en main propre.
3. À la première connexion, la personne choisit son propre mot de passe (10 caractères minimum).

**Modifier** : **Gérer** → changer le rôle, **Nouveau mot de passe** (mot de passe oublié), **Désactiver** (bloque
la connexion sans rien supprimer).

**Supprimer** : **Gérer** → tapez l'identifiant dans la case → **Supprimer le compte**.
La fiche de l'employé et ses pointages sont conservés. Vous ne pouvez supprimer ni votre propre compte,
ni le dernier administrateur.

## Les pointages oubliés

Si un employé oublie de pointer sa sortie, le tableau de bord du jour concerné affiche **« Sortie manquante »**
(et la durée travaillée n'est pas calculée).

**Ajouter la correction** : **Tableau de bord** → choisissez la date → section **Corriger un oubli** :
employé, Entrée ou Sortie, heure, **motif** (obligatoire) → **Ajouter la correction**.
La ligne apparaît avec l'étiquette **Manuel**, votre nom et le motif ; l'employé la voit dans « Mon espace ».

**Supprimer une correction** : lien **Supprimer** sur la ligne « Manuel » du journal.
Les pointages faits avec le visage ne peuvent être ni modifiés ni supprimés : c'est ce qui garantit leur fiabilité.

## Pointer avec le QR code de la tablette (méthode par défaut)

Une tablette au bureau affiche un **QR code qui change toutes les 15 secondes**. Chaque employé le scanne avec
l'appareil photo de son téléphone : le serveur enregistre l'heure **à la seconde**.
Premier scan du jour = **entrée**, scan suivant = **sortie**.

**Afficher le QR code depuis l'administration (le plus simple)** : connecté en administrateur, menu **QR code**
(ou bouton « Afficher le QR code de pointage » sur le tableau de bord) → **Plein écran**. Les employés scannent l'écran.
Ne laissez pas cet appareil sans surveillance : il est connecté en administrateur.

**Ou : tablette dédiée sans compte (conseillé pour une tablette posée à l'entrée)**
1. Sur la tablette, ouvrez `https://alygo.pythonanywhere.com/connexion/` et connectez-vous en administrateur.
2. Bouton **Tablette dédiée (sans compte)** du tableau de bord → donnez un nom (ex. « Tablette entrée ») → **Utiliser cet appareil comme tablette**.
3. La session administrateur se ferme et le QR code s'affiche. Touchez **Plein écran**, laissez la tablette branchée.
   (Tablette perdue : **Tablette dédiée** → **Supprimer**, ses QR codes ne marchent plus.)

**Pour chaque employé (une fois)** : créez son accès (Employés → Modifier → **Créer son accès**). Au premier scan,
il se connecte avec son identifiant ; ensuite il **reste connecté** sur son téléphone (60 jours).

**Tous les jours**
1. L'employé ouvre l'**appareil photo** de son téléphone, vise le QR code de la tablette et touche le lien.
2. Le téléphone affiche « Bonjour … — Entrée à 08:01:22 » (ou « Au revoir … — Sortie à … »).
3. **Sortie avant 8 h de travail** : le téléphone demande de confirmer (« Oui, je sors maintenant »).
4. **Plus de 8 h** : le temps en plus compte comme **heures supplémentaires** ; il apparaît dans le tableau de bord,
   dans « Mon espace » de l'employé et dans l'export Excel (onglet « Total par employé »).

Si un **lieu** est défini (menu **Lieux**), le téléphone doit aussi être à moins de 20 m du bureau.
Le QR code expire au bout de 90 secondes : une photo du QR code envoyée à un collègue absent ne sert à rien.
La durée normale (8 h) se change dans le fichier `.env` : `HEURES_JOURNEE=8`.

## Pointer avec son téléphone et le visage (option)

Désactivé par défaut. Pour l'activer : ajoutez `POINTAGE_TELEPHONE=True` dans `.env`, puis **Reload**.


Chaque employé pointe depuis **son propre téléphone**. Son visage est vérifié, l'heure est celle du serveur, et il ne peut pointer **que pour lui-même** (son compte).

**1. Définir le lieu autorisé (une fois, administrateur, sur place)**
1. Allez **au centre du bureau (Beitik Soukouk)** avec votre téléphone, GPS activé.
2. Connectez-vous sur `https://alygo.pythonanywhere.com/connexion/` → menu **Lieux**.
3. Nom : *Beitik Soukouk* ; rayon : **20** m → **📍 Utiliser ma position actuelle** → autorisez la localisation.
4. Attendez une précision de 10 à 15 m au plus (sinon réessayez près d'une fenêtre) → **Enregistrer ce lieu**.

Dès qu'un lieu est actif, un pointage par téléphone fait **à plus de 20 m est refusé** (et noté dans le Journal).
Un GPS trop imprécis (plus de 50 m) est aussi refusé. Sans aucun lieu actif, le téléphone peut pointer de partout.
Le rayon se change dans **Lieux** (si des employés au fond du bâtiment sont refusés, passez à 30 m).
Seuls le nom du lieu et la distance sont conservés, jamais les coordonnées GPS des employés.

**2. Donner l'accès à un employé**
**Employés** → **Modifier** → section *Pointage avec son téléphone* → **Créer son accès**.
Notez l'identifiant et le mot de passe temporaire affichés et donnez-les à l'employé.
(L'employé doit avoir une photo de référence.)

**3. Côté employé**
1. Sur son téléphone (Chrome sur Android, Safari sur iPhone) : `https://alygo.pythonanywhere.com/connexion/`.
2. Première fois : il choisit son propre mot de passe. Astuce : *Ajouter à l'écran d'accueil* pour une icône.
3. Il autorise **la caméra** et **la position**, vérifie le message vert « Vous êtes à X m de Beitik Soukouk »,
   puis appuie sur **Pointer**. L'entrée et la sortie alternent automatiquement.

Dans le tableau de bord, ces pointages portent l'étiquette **📱 Téléphone** avec la distance au lieu.

## Le poste de pointage (administrateur)

Le menu **Poste de pointage** ouvre la page où l'on choisit un nom puis on vérifie le visage, sur l'appareil de
l'administrateur. Utile si le téléphone d'un employé est en panne : l'administrateur reste à côté, puis se déconnecte.
Ne laissez jamais un appareil connecté en administrateur sans surveillance.

## Mot de passe oublié

- **Un utilisateur** : l'administrateur va dans **Comptes → Gérer → Nouveau mot de passe**.
- **Le seul administrateur** : sur le serveur, PowerShell en administrateur :
  ```
  cd C:\GestionPresence
  .\venv\Scripts\python manage.py changepassword IDENTIFIANT
  ```
