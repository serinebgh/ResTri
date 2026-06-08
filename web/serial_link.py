"""
serial_link.py
==============
Communication série Python <-> STM32G431 (UART2, 115200 baud).

La carte envoie au démarrage :
    STM32:READY
    ...lignes de log...

Côté Python on peut :
  - écouter en continu les lignes envoyées par la carte (thread lecteur)
  - envoyer une commande de tri :  SORT:1K  /  SORT:10K  /  SORT:REJECT
    (à implémenter côté firmware si tu veux piloter les servos depuis le PC)

Le lien est TOLÉRANT : si aucune carte n'est branchée, l'appli web continue
de tourner (mode "déconnecté"), on log juste un avertissement.
"""

import threading
import time

try:
    import serial
    import serial.tools.list_ports
    _HAS_PYSERIAL = True
except ImportError:               # pyserial pas installé -> mode simulation
    _HAS_PYSERIAL = False


# Correspondance catégorie -> commande envoyée à la STM32 (ancien mode 3 bacs)
SORT_COMMAND = {
    "1k":     b"SORT:1K\r\n",
    "10k":    b"SORT:10K\r\n",
    "rebut":  b"SORT:REJECT\r\n",
}

# Angles de la trappe et position de repos du carrousel (réglables)
# (0° = butée sur ce servo -> on reste entre 90° et 180° qui bougent bien)
TRAP_CLOSED = 90     # trappe fermée (retient la résistance)
TRAP_OPEN   = 180    # trappe ouverte (la résistance tombe)
CARR_HOME   = 0      # position initiale du carrousel


def list_ports():
    """Retourne la liste des ports série détectés (pour t'aider à trouver le bon COM)."""
    if not _HAS_PYSERIAL:
        return []
    return [(p.device, p.description) for p in serial.tools.list_ports.comports()]


def auto_detect_port():
    """Tente de trouver automatiquement un port STM32 (ST-Link / USB-CDC)."""
    if not _HAS_PYSERIAL:
        return None
    for p in serial.tools.list_ports.comports():
        desc = (p.description or "").lower()
        if any(k in desc for k in ("stm", "st-link", "stlink", "usb serial", "cdc", "virtual com")):
            return p.device
    # fallback : premier port disponible
    ports = serial.tools.list_ports.comports()
    return ports[0].device if ports else None


class STM32Link:
    """Lien série non bloquant vers la carte STM32."""

    def __init__(self, port=None, baudrate=115200, on_line=None):
        self.port      = port or auto_detect_port()
        self.baudrate  = baudrate
        self.on_line   = on_line          # callback(str) appelé pour chaque ligne reçue
        self.ser       = None
        self.connected = False
        self.last_line = ""
        self.running   = False
        self._thread   = None
        self._lock     = threading.Lock()

    # ---------- connexion ----------
    def connect(self):
        if not _HAS_PYSERIAL:
            print("[SERIAL] pyserial non installé -> mode déconnecté")
            return False
        if not self.port:
            print("[SERIAL] Aucun port série détecté -> mode déconnecté")
            return False
        try:
            self.ser = serial.Serial(self.port, self.baudrate, timeout=0.2)
            self.connected = True
            self.running   = True
            self._thread = threading.Thread(target=self._reader, daemon=True)
            self._thread.start()
            print(f"[SERIAL] Connecté à {self.port} @ {self.baudrate} baud")
            return True
        except Exception as e:
            print(f"[SERIAL] Connexion impossible sur {self.port} : {e}")
            self.connected = False
            return False

    # ---------- thread lecteur ----------
    def _reader(self):
        while self.running and self.ser:
            try:
                raw = self.ser.readline()
                if not raw:
                    continue
                line = raw.decode("utf-8", errors="replace").strip()
                if line:
                    self.last_line = line
                    print(f"[STM32] {line}")
                    if self.on_line:
                        self.on_line(line)
            except Exception as e:
                print(f"[SERIAL] Erreur lecture : {e}")
                time.sleep(0.5)

    # ---------- envoi ----------
    def send(self, data: bytes):
        if not self.connected or not self.ser:
            return False
        try:
            with self._lock:
                self.ser.write(data)
            return True
        except Exception as e:
            print(f"[SERIAL] Erreur envoi : {e}")
            return False

    def sort(self, category: str):
        """Envoie l'ordre de tri correspondant à la catégorie détectée."""
        cmd = SORT_COMMAND.get(category)
        if cmd:
            ok = self.send(cmd)
            print(f"[SERIAL] -> {cmd.decode().strip()}  ({'OK' if ok else 'échec'})")
            return ok
        return False

    # ──────────────────────────────────────────────────────────────
    #  Séquence de tri complète ORCHESTRÉE PAR LE PC
    #  (utilise les commandes CARR:/TRAP: du firmware, sans reflasher)
    #    1. tourner le carrousel vers l'angle du bon bac
    #    2. ouvrir la trappe  -> la résistance tombe
    #    3. refermer la trappe
    #    4. revenir à la position initiale
    # ──────────────────────────────────────────────────────────────
    def sort_sequence(self, angle,
                      trap_open=TRAP_OPEN, trap_closed=TRAP_CLOSED, home=CARR_HOME,
                      t_rot=2.0, t_drop=1.0, t_close=0.4, t_home=0.8):
        # t_rot = attente APRES que le carrousel a fini de bouger, avant
        #         d'ouvrir la trappe (2 s par defaut, comme demande).
        if not self.connected:
            print(f"[SERIAL] (déconnecté) sequence bac angle={angle} ignorée")
            return False

        def run():
            # 1) tourner le carrousel vers le bon bac, puis attendre 2 s
            self.send(f"CARR:{int(angle)}\r\n".encode())
            print(f"[SERIAL] carrousel -> {angle}°, attente {t_rot}s avant trappe")
            time.sleep(t_rot)
            # 2) ouvrir la trappe -> la resistance tombe
            self.send(f"TRAP:{int(trap_open)}\r\n".encode())
            time.sleep(t_drop)
            # 3) refermer la trappe
            self.send(f"TRAP:{int(trap_closed)}\r\n".encode())
            time.sleep(t_close)
            # 4) revenir a la position initiale
            self.send(f"CARR:{int(home)}\r\n".encode())
            print(f"[SERIAL] séquence terminée (bac à {angle}°)")

        threading.Thread(target=run, daemon=True).start()
        return True

    # ---------- fermeture ----------
    def close(self):
        self.running = False
        if self._thread:
            self._thread.join(timeout=1)
        if self.ser:
            self.ser.close()
        self.connected = False
        print("[SERIAL] Fermé")
