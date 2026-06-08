"""
vision.py
=========
Lecture de résistances via Claude API (vision) + caméra DroidCam.
Adapté de resistor_API.py pour fonctionner comme backend du dashboard web :

  - flux vidéo annoté disponible image par image  (get_annotated_frame)
  - à chaque résistance "verrouillée", appelle un callback on_detection(...)
    avec : valeur, bandes, score de confiance, catégorie (1k/10k/rebut)
  - tient à jour les compteurs par catégorie

Contrôle des couleurs / E12-E24 identique à resistor_API.py.
"""

import cv2
import numpy as np
import base64
import json
import os
import threading
import time

try:
    import anthropic
    _HAS_ANTHROPIC = True
except ImportError:
    _HAS_ANTHROPIC = False

# ═══════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════
# La clé API est lue UNIQUEMENT depuis la variable d'environnement (jamais en clair).
# Avant de lancer l'app :  $env:ANTHROPIC_API_KEY = "sk-ant-..."
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")
CAMERA_URL = os.environ.get("CAMERA_URL", "http://10.78.23.72:4747/video")
CLAUDE_MODEL = "claude-opus-4-5"

RESIZE_W = 640
RESIZE_H = 360
SAVE_DIR = "crops"
FONT     = cv2.FONT_HERSHEY_SIMPLEX

POSE_CX, POSE_CY, POSE_W, POSE_H = 0.50, 0.55, 0.30, 0.25

# Catégories de tri : valeur cible (ohms) + tolérance d'appartenance
TARGETS = {"1k": 1_000.0, "10k": 10_000.0}
CATEGORY_TOL_PCT = 10.0   # à ±10 % d'une cible on classe dedans, sinon "rebut"

# Temps (s) pendant lequel on reste "locked" après un tri, le temps que le
# cycle servo de la STM32 s'achève et que l'opérateur place la résistance
# suivante. Ensuite on réarme automatiquement la détection.
LOCK_COOLDOWN = 6.0

# ═══════════════════════════════════════════════════
#  SÉRIES E12 / E24
# ═══════════════════════════════════════════════════
_E12_BASE = [1.0,1.2,1.5,1.8,2.2,2.7,3.3,3.9,4.7,5.6,6.8,8.2]
_E24_BASE = [1.0,1.1,1.2,1.3,1.5,1.6,1.8,2.0,2.2,2.4,2.7,3.0,
             3.3,3.6,3.9,4.3,4.7,5.1,5.6,6.2,6.8,7.5,8.2,9.1]

def _build_series(base):
    values = set()
    for n in range(-1, 7):
        for b in base:
            values.add(round(b * (10**n), 6))
    return sorted(values)

E12_VALUES   = _build_series(_E12_BASE)
E24_VALUES   = _build_series(_E24_BASE)
ALL_STANDARD = sorted(set(E12_VALUES + E24_VALUES))

MULTIPLIERS = {
    "BLACK":1,"BROWN":10,"RED":100,"ORANGE":1_000,"YELLOW":10_000,
    "GREEN":100_000,"BLUE":1_000_000,"PURPLE":10_000_000,"GRAY":0.01,"WHITE":0.1,
}
DIGIT = {
    "BLACK":0,"BROWN":1,"RED":2,"ORANGE":3,"YELLOW":4,
    "GREEN":5,"BLUE":6,"PURPLE":7,"GRAY":8,"WHITE":9,
}
BGR_COLOUR = {
    "BLACK":(40,40,40),"BROWN":(0,60,160),"RED":(0,0,220),"ORANGE":(0,120,255),
    "YELLOW":(0,210,210),"GREEN":(0,180,50),"BLUE":(200,30,0),"PURPLE":(170,0,140),
    "GRAY":(120,120,120),"WHITE":(220,220,200),"GOLD":(0,180,215),"SILVER":(192,192,192),
}

def compute_value(bands):
    if len(bands) < 3:
        return None
    d1, d2, mult = DIGIT.get(bands[0]), DIGIT.get(bands[1]), MULTIPLIERS.get(bands[2])
    if d1 is None or d2 is None or mult is None:
        return None
    return (d1 * 10 + d2) * mult

def find_standard(value):
    if value is None or value <= 0:
        return None, None, None, 'none'
    best_val, best_diff = None, float('inf')
    for std in ALL_STANDARD:
        diff = abs(value - std) / std * 100
        if diff < best_diff:
            best_diff, best_val = diff, std
    if best_diff <= 2.0:
        serie = 'E12' if best_val in E12_VALUES else 'E24'
        return best_val, serie, best_diff, 'exact'
    elif best_diff <= 10.0:
        serie = 'E12' if best_val in E12_VALUES else 'E24'
        return best_val, serie, best_diff, 'close'
    return best_val, None, best_diff, 'none'

def format_ohms(v):
    if v is None: return "???"
    if v >= 1e6:  return f"{v/1e6:.2f} MOhm"
    if v >= 1e3:  return f"{v/1e3:.2f} kOhm"
    return f"{v:.1f} Ohm"

def categorize(value):
    """Classe la valeur en '1k', '10k' ou 'rebut' selon la tolérance."""
    if value is None or value <= 0:
        return "rebut"
    for cat, target in TARGETS.items():
        if abs(value - target) / target * 100 <= CATEGORY_TOL_PCT:
            return cat
    return "rebut"

def confidence_score(std_status, std_diff):
    """
    Score de confiance ML [0..100] dérivé de la concordance avec la grille E12/E24.
      - 'exact'  : très haute confiance (écart quasi nul)
      - 'close'  : confiance moyenne, décroît avec l'écart
      - 'none'   : faible confiance
    """
    if std_diff is None:
        return 0.0
    if std_status == 'exact':
        return round(max(90.0, 100.0 - std_diff * 2.0), 1)
    if std_status == 'close':
        return round(max(50.0, 90.0 - std_diff * 4.0), 1)
    return round(max(5.0, 40.0 - min(std_diff, 35.0)), 1)


# ═══════════════════════════════════════════════════
#  ZONE DE POSE
# ═══════════════════════════════════════════════════
def compute_pose():
    pw, ph = int(RESIZE_W*POSE_W), int(RESIZE_H*POSE_H)
    cx, cy = int(RESIZE_W*POSE_CX), int(RESIZE_H*POSE_CY)
    return cx-pw//2, cy-ph//2, cx+pw//2, cy+ph//2

X1, Y1, X2, Y2 = compute_pose()


# ═══════════════════════════════════════════════════
#  CAMERA THREAD (DroidCam)
# ═══════════════════════════════════════════════════
class CameraStream:
    def __init__(self, url):
        self.url     = url
        self.cap     = None
        self.frame   = None
        self.lock    = threading.Lock()
        self.running = True
        # L'ouverture (potentiellement lente/bloquante) se fait DANS le thread,
        # pour ne jamais bloquer le démarrage du serveur web.
        self.thread  = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _open(self):
        cap = cv2.VideoCapture(self.url)
        try:
            cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass
        return cap

    def _loop(self):
        while self.running:
            if self.cap is None or not self.cap.isOpened():
                self.cap = self._open()
                if not self.cap.isOpened():
                    time.sleep(1.0)      # caméra absente -> on réessaie
                    continue
            ok, f = self.cap.read()
            if ok and f is not None:
                with self.lock:
                    self.frame = f
            else:
                time.sleep(0.05)         # flux interrompu -> on reboucle/reconnecte
                try:
                    self.cap.release()
                except Exception:
                    pass
                self.cap = None

    def read(self):
        with self.lock:
            return (True, self.frame.copy()) if self.frame is not None else (False, None)

    def isOpened(self):
        return self.cap is not None and self.cap.isOpened()

    def release(self):
        self.running = False
        self.thread.join(timeout=1)
        if self.cap is not None:
            self.cap.release()


# ═══════════════════════════════════════════════════
#  APPEL CLAUDE API
# ═══════════════════════════════════════════════════
SYSTEM_PROMPT = """Tu es un expert en lecture de résistances électroniques à code couleur.
On te donne l'image d'une résistance horizontale.
Identifie exactement les 3 bandes de VALEUR (de gauche à droite).
Ignore la bande de tolérance (gold/silver) sur le bord droit.

RÈGLES CRITIQUES pour les couleurs difficiles :
GRAY : neutre, sans teinte, plus clair que BLACK, plus sombre que WHITE.
BROWN : brun chaud sombre (chocolat/terre), dominante rouge-orangée, plus sombre qu'ORANGE.
ORANGE : orange vif et saturé (potiron/mandarine), lumineux.

Réponds UNIQUEMENT en JSON :
{"bands": ["COULEUR1", "COULEUR2", "COULEUR3"]}
Couleurs possibles : BLACK, BROWN, RED, ORANGE, YELLOW, GREEN, BLUE, PURPLE, GRAY, WHITE
Si illisible : {"bands": null}"""

def ask_claude(crop_bgr):
    if not _HAS_ANTHROPIC or crop_bgr is None or crop_bgr.size == 0:
        return None

    h, w = crop_bgr.shape[:2]
    if h < 300:
        scale = 300 / h
        crop_bgr = cv2.resize(crop_bgr, (int(w*scale), int(h*scale)),
                              interpolation=cv2.INTER_CUBIC)

    lab = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2LAB)
    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(4,4))
    lab[:,:,0] = clahe.apply(lab[:,:,0])
    crop_bgr = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    _, buf = cv2.imencode(".jpg", crop_bgr, [cv2.IMWRITE_JPEG_QUALITY, 97])
    b64 = base64.standard_b64encode(buf).decode("utf-8")

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model=CLAUDE_MODEL, max_tokens=64, system=SYSTEM_PROMPT,
            messages=[{"role":"user","content":[
                {"type":"image","source":{"type":"base64","media_type":"image/jpeg","data":b64}},
                {"type":"text","text":"Identifie les 3 bandes de valeur de cette résistance."},
            ]}],
        )
        raw = msg.content[0].text.strip()
        print(f"  [CLAUDE] {raw}")
        bands = json.loads(raw).get("bands")
        if bands is None or len(bands) != 3:
            return None
        bands = [b.upper().strip() for b in bands]
        valid = set(DIGIT.keys()) | {"GOLD","SILVER"}
        if any(b not in valid for b in bands):
            return None
        return tuple(bands)
    except Exception as e:
        print(f"  [CLAUDE] Erreur : {e}")
        return None


# ═══════════════════════════════════════════════════
#  ANNOTATION DE L'IMAGE
# ═══════════════════════════════════════════════════
def draw_frame(display, state):
    # Vidéo PROPRE : aucun texte n'est écrit sur l'image.
    # On dessine seulement le cadre vert (repère de pose). Toutes les infos
    # (valeur, bac, confiance) sont affichées dans le dashboard, pas sur la vidéo.
    cv2.rectangle(display, (X1, Y1), (X2, Y2), (0, 255, 150), 2)
    L = 14
    for cx, cy, dx, dy in [(X1,Y1,1,1),(X2,Y1,-1,1),(X1,Y2,1,-1),(X2,Y2,-1,-1)]:
        cv2.line(display, (cx, cy), (cx + dx*L, cy), (0, 255, 150), 3)
        cv2.line(display, (cx, cy), (cx, cy + dy*L), (0, 255, 150), 3)


# ═══════════════════════════════════════════════════
#  SORTEUR — orchestration vision + compteurs
# ═══════════════════════════════════════════════════
class ResistorSorter:
    """
    Boucle de capture + analyse. À chaque verrouillage, appelle on_detection(info)
    où info = {value, value_str, bands, confidence, category, std_status, std_diff}.
    """
    def __init__(self, camera_url=CAMERA_URL, on_detection=None,
                 classifier=None, n_bins=4):
        self.camera_url   = camera_url
        self.on_detection = on_detection
        self.classifier   = classifier          # fn(value_ohms) -> bin dict
        self.n_bins       = n_bins
        self.cam          = None
        self.state        = {"status": "waiting"}
        self.counters     = {i: 0 for i in range(n_bins)}
        self.last_frame   = None
        self.running      = False
        self._analyse_thr = None
        self._frame_lock  = threading.Lock()

    def start(self):
        self.cam = CameraStream(self.camera_url)
        self.running = True
        threading.Thread(target=self._loop, daemon=True).start()
        print(f"[VISION] Démarré sur {self.camera_url}")

    def camera_ok(self):
        return self.cam is not None and self.cam.isOpened()

    def reset_state(self):
        self.state = {"status": "waiting"}

    def reset_counters(self):
        self.counters = {i: 0 for i in range(self.n_bins)}

    def _run_analyse(self, img):
        crop = img[Y1:Y2, X1:X2]
        result = ask_claude(crop)
        if result is None:
            self.state["status"] = "waiting"
            return
        value = compute_value(result)
        if value is None:
            self.state["status"] = "waiting"
            return

        sv, ss, sd, st = find_standard(value)
        conf     = confidence_score(st, sd)

        # Classement dans l'un des bacs (config fournie par l'app)
        if self.classifier:
            b = self.classifier(value)
        else:
            b = {"index": 0, "angle": 0, "label": format_ohms(value), "reject": False}
        bin_index = b["index"]

        self.state.update({
            "status": "locked", "bands": list(result), "value": value,
            "std_status": st, "std_diff": sd, "confidence": conf,
            "bin_index": bin_index, "bin_label": b["label"], "bin_reject": b.get("reject", False),
            "lock_time": time.time(),
        })
        self.counters[bin_index] = self.counters.get(bin_index, 0) + 1

        info = {
            "value": value, "value_str": format_ohms(value), "bands": list(result),
            "confidence": conf,
            "bin_index": bin_index, "bin_label": b["label"],
            "bin_angle": b["angle"], "bin_reject": b.get("reject", False),
            "std_status": st, "std_diff": round(sd, 2) if sd else None,
            "counters": {str(k): v for k, v in self.counters.items()},
        }
        print(f"  [LOCK] {info['value_str']}  {result}  -> bac {bin_index} "
              f"({b['label']}, {b['angle']}deg, conf {conf}%)")
        if self.on_detection:
            self.on_detection(info)

    def _loop(self):
        while self.running:
            ok, frame = self.cam.read()
            if not ok or frame is None:
                time.sleep(0.02)
                continue
            img = cv2.resize(frame, (RESIZE_W, RESIZE_H))

            if self.state["status"] == "waiting":
                if self._analyse_thr is None or not self._analyse_thr.is_alive():
                    self.state["status"] = "analysing"
                    self._analyse_thr = threading.Thread(
                        target=self._run_analyse, args=(img.copy(),), daemon=True)
                    self._analyse_thr.start()

            # Réarmement automatique : après le tri, on repasse en "waiting"
            elif self.state["status"] == "locked":
                if time.time() - self.state.get("lock_time", 0) >= LOCK_COOLDOWN:
                    self.state = {"status": "waiting"}

            display = img.copy()
            draw_frame(display, self.state)
            with self._frame_lock:
                self.last_frame = display

    def get_annotated_jpeg(self):
        """Retourne l'image annotée encodée en JPEG (pour le flux MJPEG)."""
        with self._frame_lock:
            frame = None if self.last_frame is None else self.last_frame.copy()
        if frame is None:
            frame = np.zeros((RESIZE_H, RESIZE_W, 3), dtype=np.uint8)
            cv2.putText(frame, "En attente de la camera...", (60, RESIZE_H//2),
                        FONT, 0.7, (0,200,255), 2, cv2.LINE_AA)
        ok, buf = cv2.imencode(".jpg", frame, [cv2.IMWRITE_JPEG_QUALITY, 80])
        return buf.tobytes() if ok else b""

    def save_crop(self):
        with self._frame_lock:
            if self.last_frame is None:
                return None
            img = self.last_frame.copy()
        os.makedirs(SAVE_DIR, exist_ok=True)
        idx  = len([f for f in os.listdir(SAVE_DIR) if f.endswith(".png")])
        path = os.path.join(SAVE_DIR, f"crop_{idx:03d}.png")
        cv2.imwrite(path, img[Y1:Y2, X1:X2])
        return path

    def stop(self):
        self.running = False
        if self.cam:
            self.cam.release()
