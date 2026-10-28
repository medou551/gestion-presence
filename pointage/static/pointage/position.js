/* Localisation du téléphone (GPS) — pour le pointage limité au lieu de travail.
   On écoute le GPS quelques secondes et on garde la mesure la plus précise. */
(function () {
  "use strict";

  function messageErreur(err) {
    if (!window.isSecureContext) return "La localisation exige une adresse en https://.";
    if (!err) return "Localisation impossible.";
    if (err.code === 1) return "Localisation refusée. Autorisez la position pour ce site (icône à gauche de l'adresse → Autorisations → Position), "
      + "et vérifiez que la localisation du téléphone est activée (Paramètres → Localisation), puis réessayez.";
    if (err.code === 2) return "Position introuvable : activez le GPS (« localisation précise ») et réessayez, si possible près d'une fenêtre.";
    if (err.code === 3) return "Le GPS met trop de temps à répondre. Réessayez près d'une fenêtre ou dehors.";
    return "Localisation impossible : " + (err.message || "erreur inconnue");
  }

  function distanceM(lat1, lon1, lat2, lon2) {
    const r = Math.PI / 180, p1 = lat1 * r, p2 = lat2 * r, dp = (lat2 - lat1) * r, dl = (lon2 - lon1) * r;
    const a = Math.sin(dp / 2) ** 2 + Math.cos(p1) * Math.cos(p2) * Math.sin(dl / 2) ** 2;
    return 2 * 6371000 * Math.asin(Math.sqrt(a));
  }

  /** Écoute le GPS jusqu'à `dureeMs` (ou dès que la précision atteint `cible` m) et renvoie la meilleure mesure. */
  function meilleure(dureeMs, cible, auProgres) {
    return new Promise((resolve, reject) => {
      if (!navigator.geolocation) { reject(new Error("Ce navigateur ne permet pas la localisation.")); return; }
      let meilleur = null, fini = false, id = null;
      const terminer = (erreur) => {
        if (fini) return; fini = true;
        if (id !== null) navigator.geolocation.clearWatch(id);
        clearTimeout(minuteur);
        if (meilleur) resolve(meilleur); else reject(new Error(messageErreur(erreur)));
      };
      const minuteur = setTimeout(() => terminer({ code: 3 }), dureeMs);
      id = navigator.geolocation.watchPosition(pos => {
        const m = { lat: pos.coords.latitude, lon: pos.coords.longitude, precision: pos.coords.accuracy };
        if (!meilleur || m.precision < meilleur.precision) meilleur = m;
        if (auProgres) auProgres(meilleur);
        if (meilleur.precision <= cible) terminer();
      }, err => { if (err.code === 1 || !meilleur) terminer(err); },
      { enableHighAccuracy: true, maximumAge: 0, timeout: dureeMs });
    });
  }

  window.Position = { meilleure, distanceM, messageErreur };
})();
