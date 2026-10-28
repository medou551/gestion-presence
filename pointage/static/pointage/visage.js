/* Analyse du visage dans le navigateur avec face-api.js (open source, licence MIT).
   Les modèles sont fournis dans static/pointage/faceapi/modeles : aucune connexion internet n'est nécessaire.

   Compatible avec Chrome, Edge, Firefox, Safari, Opera, Samsung Internet (versions récentes) :
   - moteur de calcul choisi automatiquement : carte graphique (WebGL) si possible, sinon processeur ;
   - chaque problème (caméra refusée, absente, occupée, adresse non sécurisée…) donne un message clair
     avec la marche à suivre pour le navigateur utilisé. */
window.Visage = (() => {
  let pret = null;
  let moteur = null;

  // ------------------------------------------------------------ Navigateur
  function navigateur() {
    const ua = navigator.userAgent || "";
    if (/Edg\//.test(ua)) return "Edge";
    if (/OPR\/|Opera/.test(ua)) return "Opera";
    if (/SamsungBrowser/.test(ua)) return "Samsung Internet";
    if (/Firefox\//.test(ua)) return "Firefox";
    if (/Chrome\//.test(ua) || /CriOS/.test(ua)) return "Chrome";
    if (/Safari\//.test(ua)) return "Safari";
    return "votre navigateur";
  }

  function aideCamera() {
    const n = navigateur();
    const aides = {
      Chrome: "cliquez l'icône à gauche de l'adresse (cadenas ou « i ») → Caméra → Autoriser, puis rechargez la page (F5).",
      Edge: "cliquez l'icône à gauche de l'adresse → Autorisations pour ce site → Caméra → Autoriser, puis rechargez la page (F5).",
      Opera: "cliquez l'icône à gauche de l'adresse → Caméra → Autoriser, puis rechargez la page.",
      Firefox: "cliquez l'icône de caméra barrée à gauche de l'adresse → retirez le blocage, puis rechargez la page (F5).",
      Safari: "menu Safari → Réglages pour ce site web → Caméra → Autoriser (sur iPad : Réglages → Safari → Caméra), puis rechargez.",
      "Samsung Internet": "menu ≡ → Paramètres → Sites et téléchargements → Autorisations des sites → Caméra, puis rechargez.",
    };
    return aides[n] || "autorisez la caméra pour ce site dans les réglages du navigateur, puis rechargez la page.";
  }

  // ------------------------------------------------------------ Compatibilité
  function webglDisponible() {
    try {
      const c = document.createElement("canvas");
      return !!(window.WebGLRenderingContext && (c.getContext("webgl2") || c.getContext("webgl")));
    } catch (e) { return false; }
  }

  function compatibilite() {
    return {
      navigateur: navigateur(),
      contexteSecurise: window.isSecureContext === true,
      camera: !!(navigator.mediaDevices && navigator.mediaDevices.getUserMedia),
      webgl: webglDisponible(),
      canvas: !!document.createElement("canvas").getContext,
      promesses: typeof Promise !== "undefined" && typeof fetch !== "undefined",
      adresse: location.protocol + "//" + location.host,
    };
  }

  /* Explique pourquoi la caméra n'est pas utilisable (ou null si tout va bien). */
  function problemeAvantCamera() {
    const c = compatibilite();
    if (!c.promesses || !c.canvas) {
      return "Ce navigateur est trop ancien. Utilisez une version récente de Chrome, Edge, Firefox ou Safari.";
    }
    if (!c.contexteSecurise) {
      return "La caméra est bloquée car l'adresse n'est pas sécurisée (" + c.adresse + "). " +
        "Sur le PC du serveur, ouvrez http://127.0.0.1:8000/ ou http://localhost:8000/ ; " +
        "depuis un autre appareil, utilisez l'adresse https:// du serveur (voir DEPLOIEMENT.md).";
    }
    if (!c.camera) {
      return "Ce navigateur ne donne pas accès à la caméra. Mettez-le à jour ou utilisez Chrome, Edge, Firefox ou Safari.";
    }
    return null;
  }

  function messageErreurCamera(err) {
    const nom = (err && err.name) || "";
    if (nom === "NotAllowedError" || nom === "PermissionDeniedError" || nom === "SecurityError" || nom === "NotSupportedError") {
      return "L'accès à la caméra a été refusé. Pour l'autoriser dans " + navigateur() + " : " + aideCamera();
    }
    if (nom === "NotFoundError" || nom === "DevicesNotFoundError" || nom === "OverconstrainedError") {
      return "Aucune caméra détectée. Branchez une webcam (ou vérifiez qu'elle est activée dans Windows : " +
        "Paramètres → Confidentialité → Caméra), puis rechargez la page.";
    }
    if (nom === "NotReadableError" || nom === "TrackStartError" || nom === "AbortError") {
      return "La caméra est déjà utilisée par une autre application (Teams, Zoom, Skype, un autre onglet…). " +
        "Fermez-la, puis rechargez la page.";
    }
    return "Impossible d'ouvrir la caméra (" + (nom || "erreur inconnue") + "). Rechargez la page ; " +
      "si le problème continue, ouvrez la page Diagnostic.";
  }

  /* Ouvre la caméra dans l'élément <video>. Résout avec le flux, ou rejette avec un message en français. */
  async function ouvrirCamera(video) {
    const probleme = problemeAvantCamera();
    if (probleme) throw new Error(probleme);
    const essais = [
      { video: { width: { ideal: 640 }, height: { ideal: 480 }, facingMode: "user" }, audio: false },
      { video: true, audio: false },  // caméras qui refusent les dimensions demandées
    ];
    let derniere = null;
    for (const contraintes of essais) {
      try {
        const flux = await navigator.mediaDevices.getUserMedia(contraintes);
        video.setAttribute("playsinline", "");  // Safari / iPad : pas de plein écran forcé
        video.muted = true;
        video.srcObject = flux;
        try { await video.play(); } catch (e) { /* lecture automatique déjà gérée par autoplay */ }
        return flux;
      } catch (err) {
        derniere = err;
        if (err && (err.name === "NotAllowedError" || err.name === "SecurityError")) break;
      }
    }
    throw new Error(messageErreurCamera(derniere));
  }

  // ------------------------------------------------------------ Moteur de calcul
  async function choisirMoteur() {
    const tf = faceapi.tf;
    const candidats = webglDisponible() ? ["webgl", "cpu"] : ["cpu"];
    for (const nom of candidats) {
      try {
        if (await tf.setBackend(nom)) {
          await tf.ready();
          // Petit calcul de contrôle : certains pilotes acceptent WebGL puis échouent au premier calcul
          const t = tf.tensor1d([1, 2, 3]).square().sum();
          const v = (await t.data())[0];
          t.dispose();
          if (v === 14) return nom;
        }
      } catch (e) { /* on essaie le moteur suivant */ }
    }
    throw new Error("Aucun moteur de calcul disponible dans ce navigateur.");
  }

  function optionsDetection() {
    // 0.4 : trouve aussi les visages un peu sombres ou de biais (l'identité est ensuite vérifiée par le serveur)
    return new faceapi.SsdMobilenetv1Options({ minConfidence: 0.4 });
  }

  /* Fait tourner une fois les 3 réseaux sur une image vide : la première vraie analyse est ensuite
     beaucoup plus rapide (compilation des calculs faite pendant le chargement, pas devant l'employé). */
  async function prechauffer() {
    try {
      const c = document.createElement("canvas");
      c.width = 320; c.height = 240;
      const g = c.getContext("2d"); g.fillStyle = "#808080"; g.fillRect(0, 0, c.width, c.height);
      await faceapi.detectAllFaces(c, optionsDetection());
      const v = document.createElement("canvas"); v.width = v.height = 150;
      v.getContext("2d").drawImage(c, 0, 0, 150, 150);
      await faceapi.detectFaceLandmarks(v);
      await faceapi.computeFaceDescriptor(v);
    } catch (e) { /* le préchauffage est facultatif */ }
  }

  function charger(urlModeles) {
    if (!pret) {
      pret = (async () => {
        if (typeof faceapi === "undefined") throw new Error("La bibliothèque de reconnaissance n'a pas pu être chargée. Rechargez la page.");
        moteur = await choisirMoteur();
        // Détecteur précis (SSD) dans tous les cas : les essais ont montré que le détecteur « léger »
        // rate des visages en gros plan. La fiabilité passe avant la vitesse.
        await Promise.all([
          faceapi.nets.ssdMobilenetv1.loadFromUri(urlModeles),
          faceapi.nets.faceLandmark68Net.loadFromUri(urlModeles),
          faceapi.nets.faceRecognitionNet.loadFromUri(urlModeles),
        ]);
        await prechauffer();
        return moteur;
      })();
      pret.catch(() => { pret = null; });  // permet de réessayer
    }
    return pret;
  }

  function libelleMoteur() {
    return moteur === "webgl" ? "carte graphique" : moteur === "cpu" ? "processeur — analyse un peu plus lente" : "";
  }

  /* Analyse une image (canvas, img ou video).
     Retourne { ok, message, descripteur } — ok seulement s'il y a exactement UN visage net. */
  async function analyser(source) {
    const visages = await faceapi.detectAllFaces(source, optionsDetection()).withFaceLandmarks().withFaceDescriptors();
    if (visages.length === 0) {
      return { ok: false, message: "Aucun visage détecté. Placez-vous bien face à la caméra, avec assez de lumière." };
    }
    if (visages.length > 1) {
      return { ok: false, message: "Plusieurs visages détectés. Une seule personne devant la caméra." };
    }
    const v = visages[0];
    const largeur = source.width || source.videoWidth || source.naturalWidth || 640;
    if (v.detection.box.width < largeur * 0.12) {
      return { ok: false, message: "Visage trop loin. Rapprochez-vous de la caméra." };
    }
    return { ok: true, descripteur: Array.from(v.descriptor), score: v.detection.score };
  }

  /* Copie l'image courante de la vidéo dans un canvas. */
  function capturer(video) {
    const c = document.createElement("canvas");
    c.width = video.videoWidth || 640;
    c.height = video.videoHeight || 480;
    c.getContext("2d").drawImage(video, 0, 0, c.width, c.height);
    return c;
  }

  /* Copie une image (fichier choisi) dans un canvas, réduite à 1024 px maximum. */
  function canvasDepuisImage(img) {
    const echelle = Math.min(1, 1024 / Math.max(img.naturalWidth, img.naturalHeight));
    const c = document.createElement("canvas");
    c.width = Math.round(img.naturalWidth * echelle);
    c.height = Math.round(img.naturalHeight * echelle);
    c.getContext("2d").drawImage(img, 0, 0, c.width, c.height);
    return c;
  }

  /* JPEG depuis un canvas — avec repli pour les navigateurs sans canvas.toBlob. */
  function enJpeg(canvas) {
    return new Promise(resolve => {
      if (canvas.toBlob) {
        canvas.toBlob(b => resolve(b), "image/jpeg", 0.9);
      } else {
        const data = atob(canvas.toDataURL("image/jpeg", 0.9).split(",")[1]);
        const octets = new Uint8Array(data.length);
        for (let i = 0; i < data.length; i++) octets[i] = data.charCodeAt(i);
        resolve(new Blob([octets], { type: "image/jpeg" }));
      }
    });
  }

  return {
    charger, analyser, capturer, canvasDepuisImage, enJpeg, ouvrirCamera,
    compatibilite, problemeAvantCamera, navigateur, libelleMoteur,
    get moteur() { return moteur; },
  };
})();
