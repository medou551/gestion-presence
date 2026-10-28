"""Lance l'application avec Waitress (serveur web en Python pur, adapté à Windows).

    python serveur.py              (ouvre le navigateur automatiquement en local)
    python serveur.py --silencieux (ne pas ouvrir le navigateur ni afficher les visites)

Le serveur écoute UNIQUEMENT sur 127.0.0.1:8000 : il n'est pas joignable depuis le réseau.
En production, c'est Caddy (HTTPS) qui reçoit les connexions des autres postes et les transmet ici.
"""
import os
import socket
import subprocess
import sys
import threading
import time
import webbrowser
from pathlib import Path

BASE = Path(__file__).resolve().parent
sys.path.insert(0, str(BASE))
os.chdir(BASE)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")

from waitress import serve  # noqa: E402

from config.wsgi import application  # noqa: E402


def port_deja_utilise(hote, port):
    """Sous Windows, un 2e serveur peut s'attacher au même port sans erreur : on vérifie avant."""
    try:
        with socket.create_connection((hote, port), timeout=1):
            return True
    except OSError:
        return False


def ipv6_local_disponible(port):
    """Vrai si ::1 (localhost en IPv6) est utilisable : certains navigateurs essaient d'abord cette adresse."""
    if not socket.has_ipv6:
        return False
    try:
        with socket.socket(socket.AF_INET6, socket.SOCK_STREAM) as s:
            s.bind(("::1", port))
        return True
    except OSError:
        return False


def programmes_sur_le_port(port):
    if os.name != "nt":
        return []
    try:
        sortie = subprocess.run(["netstat", "-ano", "-p", "TCP"], capture_output=True, text=True, timeout=10).stdout
    except Exception:
        return []
    pids = set()
    for ligne in sortie.splitlines():
        parties = ligne.split()
        if len(parties) >= 5 and parties[1].endswith(f":{port}") and parties[3].upper() in ("LISTENING", "ÉCOUTE", "ECOUTE"):
            pids.add(parties[4])
    return sorted(pids)


def desactiver_mode_selection_windows():
    """Dans une fenêtre PowerShell/cmd, un clic active le mode « Sélection » qui MET EN PAUSE le programme
    (le site ne répond plus). On désactive ce mode pour cette fenêtre."""
    if os.name != "nt":
        return
    try:
        import ctypes
        k32 = ctypes.windll.kernel32
        entree = k32.GetStdHandle(-10)
        mode = ctypes.c_uint32()
        if k32.GetConsoleMode(entree, ctypes.byref(mode)):
            k32.SetConsoleMode(entree, (mode.value & ~0x0040) | 0x0080)  # sans QUICK_EDIT, avec EXTENDED_FLAGS
    except Exception:
        pass


def journal_des_visites(app):
    """Affiche chaque page demandée (sans les fichiers statiques ni les photos) pour voir que le serveur répond."""
    def enveloppe(environ, start_response):
        chemin = environ.get("PATH_INFO", "")
        def start(status, headers, exc_info=None):
            if not chemin.startswith(("/static/", "/photos/", "/favicon")):
                print(f"  {time.strftime('%H:%M:%S')}  {environ.get('REQUEST_METHOD')} {chemin}  →  {status}", flush=True)
            return start_response(status, headers, exc_info)
        return app(environ, start)
    return enveloppe


if __name__ == "__main__":
    from django.conf import settings

    hote = os.environ.get("GP_HOTE", "127.0.0.1")
    port = int(os.environ.get("GP_PORT", "8000"))
    silencieux = "--silencieux" in sys.argv or not sys.stdout.isatty()
    adresse = f"http://{hote}:{port}/"

    if port_deja_utilise(hote, port) or (hote == "127.0.0.1" and port_deja_utilise("::1", port)):
        print("=" * 64)
        print(f" ERREUR : le port {port} est déjà utilisé par un autre programme")
        print(" (souvent un ancien serveur encore ouvert dans une autre fenêtre).")
        pids = programmes_sur_le_port(port)
        if pids:
            print(f" Programme(s) concerné(s) : PID {', '.join(pids)}")
            print(f" Pour l'arrêter, dans PowerShell :  taskkill /PID {pids[0]} /F")
        else:
            print(" Fermez les autres fenêtres du serveur (ou redémarrez le PC), puis relancez.")
        print(" Ou utilisez un autre port :  $env:GP_PORT=8001; python serveur.py")
        print("=" * 64)
        sys.exit(1)

    desactiver_mode_selection_windows()

    print("=" * 64)
    print(" Gestion de présence — serveur démarré")
    if settings.HTTPS:
        print(" Mode production (HTTPS) : ouvrez https://localhost ou https://<adresse du serveur>")
    else:
        print(f" Ouvrez dans le navigateur :  {adresse}")
        print(f"   (ou http://localhost:{port}/ — Chrome, Edge, Firefox, Safari, Opera)")
        print(f" Problème de caméra ou de navigateur : http://{hote}:{port}/diagnostic/")
    print(" LAISSEZ CETTE FENÊTRE OUVERTE (la fermer arrête l'application).")
    print(" Ctrl+C pour arrêter.")
    print("=" * 64, flush=True)

    app = application
    if not silencieux:
        app = journal_des_visites(application)
        if not settings.HTTPS:
            threading.Timer(1.5, lambda: webbrowser.open(adresse)).start()

    # En local, écouter aussi sur ::1 pour que http://localhost:8000 marche dans tous les navigateurs
    ecoute = [f"{hote}:{port}"]
    if hote == "127.0.0.1" and ipv6_local_disponible(port):
        ecoute.append(f"[::1]:{port}")

    serve(
        app,
        listen=" ".join(ecoute),
        threads=8,
        # Seul Caddy (sur cette même machine) est autorisé à indiquer l'adresse réelle du client
        trusted_proxy="127.0.0.1",
        trusted_proxy_count=1,
        trusted_proxy_headers={"x-forwarded-for", "x-forwarded-proto", "x-forwarded-host"},
        clear_untrusted_proxy_headers=True,
        max_request_body_size=10 * 1024 * 1024,
        ident="presence",
    )
