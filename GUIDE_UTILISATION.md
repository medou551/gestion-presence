# Guide d'utilisation : ajouter et supprimer

Ce guide explique comment ajouter et supprimer les services, les employés, les comptes et les pointages oubliés.
Chaque action est enregistrée dans le **Journal** (menu de l'administrateur).

| Quoi | Ajouter | Modifier | Supprimer | Qui |
|---|---|---|---|---|
| Service | Employés → « Services » → Ajouter | Administration | × à côté du nom (s'il est vide) | Admin, RH |
| Employé | Employés → formulaire « Nouvel employé » | Employés → Modifier | Employés → Modifier → bas de page | Admin, RH (suppression complète : Admin) |
| Photo de référence | Employés → Ajouter la photo | Employés → Changer la photo | Employés → Modifier → Effacer les données biométriques | Admin, RH |
| Compte (connexion) | Comptes → « Nouveau compte » | Comptes → Gérer | Comptes → Gérer → Supprimer le compte | Admin |
| Pointage oublié | Tableau de bord → « Corriger un oubli » | — | « Supprimer » sur la correction | Admin, RH |

---

## Les services

**Ajouter** : menu **Employés** → en bas à droite, section **Services** → tapez le nom (ex. « Comptabilité ») → **Ajouter**.

**Supprimer** : cliquez la **×** à côté du nom du service, puis confirmez.
Un service ne peut être supprimé que s'il est **vide** : changez d'abord le service de ses employés
(Employés → Modifier) et de son chef (Comptes → Gérer).

## Les employés

**Ajouter** (menu **Employés**, formulaire de gauche) :
1. Nom complet (obligatoire), poste, service, code PIN (facultatif).
2. **📷 Prendre la photo** (l'employé face à la caméra) ou **Choisir un fichier**.
3. Attendez « Visage détecté », puis **Enregistrer**.

Le même visage ne peut pas être enregistré pour deux employés. L'employé apparaît immédiatement sur la borne.

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
sont deux choses différentes. Un employé n'a pas besoin de compte pour pointer.

**Ajouter** (menu **Comptes**, réservé à l'administrateur) :
1. Identifiant (ex. `fatima.rh`), puis le **rôle** : Administrateur, Ressources humaines, Chef de service
   (choisir son service), Borne de pointage, ou Employé (choisir l'employé concerné).
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

**Ajouter la correction** (Admin, RH) : **Tableau de bord** → choisissez la date → section **Corriger un oubli** :
employé, Entrée ou Sortie, heure, **motif** (obligatoire) → **Ajouter la correction**.
La ligne apparaît avec l'étiquette **Manuel**, votre nom et le motif ; l'employé la voit dans « Mon espace ».

**Supprimer une correction** : lien **Supprimer** sur la ligne « Manuel » du journal.
Les pointages faits à la borne ne peuvent être ni modifiés ni supprimés : c'est ce qui garantit leur fiabilité.

## Mot de passe oublié

- **Un utilisateur** : l'administrateur va dans **Comptes → Gérer → Nouveau mot de passe**.
- **Le seul administrateur** : sur le serveur, PowerShell en administrateur :
  ```
  cd C:\GestionPresence
  .\venv\Scripts\python manage.py changepassword IDENTIFIANT
  ```
