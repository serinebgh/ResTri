"""
resistor_claude.py
==================
Lecture de résistances via Claude API (vision) + DroidCam.
Un seul fichier, pas de détection HSV.

Contrôles : R = reset   S = sauvegarder   Q = quitter
"""

import cv2
import numpy as np
import anthropic
import base64
import json
import os
import threading

# ═══════════════════════════════════════════════════
#  CONFIG — MODIFIE CES DEUX LIGNES
# ═══════════════════════════════════════════════════
import os
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY", "")  # clé lue depuis l'environnement (jamais en clair)
CAMERA_URL        = "http://10.78.23.103:4747/video" # ← IP DroidCam

# ═══════════════════════════════════════════════════
#  PARAMÈTRES
# ═══════════════════════════════════════════════════
RESIZE_W = 640
RESIZE_H = 360
SAVE_DIR = "crops"
FONT     = cv2.FONT_HERSHEY_SIMPLEX

# Zone où poser la résistance (centre de l'image)
POSE_CX = 0.50
POSE_CY = 0.55
POSE_W  = 0.30
POSE_H  = 0.25

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
    "BLACK":   1,
    "BROWN":   10,
    "RED":     100,
    "ORANGE":  1_000,
    "YELLOW":  10_000,
    "GREEN":   100_000,
    "BLUE":    1_000_000,
    "PURPLE":  10_000_000,
    "GRAY":    0.01,
    "WHITE":   0.1,
}

DIGIT = {
    "BLACK":0,"BROWN":1,"RED":2,"ORANGE":3,"YELLOW":4,
    "GREEN":5,"BLUE":6,"PURPLE":7,"GRAY":8,"WHITE":9,
}

BGR_COLOUR = {
    "BLACK":  (40,  40,  40),
    "BROWN":  (0,   60,  160),
    "RED":    (0,   0,   220),
    "ORANGE": (0,   120, 255),
    "YELLOW": (0,   210, 210),
    "GREEN":  (0,   180, 50),
    "BLUE":   (200, 30,  0),
    "PURPLE": (170, 0,   140),
    "GRAY":   (120, 120, 120),
    "WHITE":  (220, 220, 200),
    "GOLD":   (0,   180, 215),
    "SILVER": (192, 192, 192),
}

def compute_value(bands):
    """Calcule la valeur en ohms depuis 3 couleurs."""
    if len(bands) < 3:
        return None
    b1, b2, b3 = bands[0], bands[1], bands[2]
    d1 = DIGIT.get(b1)
    d2 = DIGIT.get(b2)
    mult = MULTIPLIERS.get(b3)
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
    if v >= 1e6:  return f"{v/1e6:.2f} MΩ"
    if v >= 1e3:  return f"{v/1e3:.2f} kΩ"
    return f"{v:.1f} Ω"

def format_std(v):
    if v is None: return "?"
    if v >= 1e6:  return f"{v/1e6:.2g}MΩ"
    if v >= 1e3:  return f"{v/1e3:.2g}kΩ"
    return f"{v:.2g}Ω"


# ═══════════════════════════════════════════════════
#  ZONE DE POSE
# ═══════════════════════════════════════════════════
def compute_pose():
    pw = int(RESIZE_W * POSE_W)
    ph = int(RESIZE_H * POSE_H)
    cx = int(RESIZE_W * POSE_CX)
    cy = int(RESIZE_H * POSE_CY)
    return cx-pw//2, cy-ph//2, cx+pw//2, cy+ph//2

X1, Y1, X2, Y2 = compute_pose()


# ═══════════════════════════════════════════════════
#  CAMERA THREAD (DroidCam)
# ═══════════════════════════════════════════════════
class CameraStream:
    def __init__(self, url):
        self.cap = cv2.VideoCapture(url)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.frame   = None
        self.lock    = threading.Lock()
        self.running = True
        self.thread  = threading.Thread(target=self._loop, daemon=True)
        self.thread.start()

    def _loop(self):
        while self.running:
            ok, f = self.cap.read()
            if ok:
                with self.lock:
                    self.frame = f

    def read(self):
        with self.lock:
            return (True, self.frame.copy()) if self.frame is not None else (False, None)

    def isOpened(self): return self.cap.isOpened()

    def release(self):
        self.running = False
        self.thread.join(timeout=1)
        self.cap.release()


# ═══════════════════════════════════════════════════
#  APPEL CLAUDE API
# ═══════════════════════════════════════════════════
SYSTEM_PROMPT = """Tu es un expert en lecture de résistances électroniques à code couleur.
On te donne l'image d'une résistance horizontale.
Identifie exactement les 3 bandes de VALEUR (de gauche à droite).
Ignore la bande de tolérance (gold/silver) sur le bord droit.

RÈGLES CRITIQUES pour les couleurs difficiles — lis attentivement :

GRAY (gris) :
- Couleur neutre, ni chaude ni froide, sans teinte prononcée
- Plus clair que BLACK, plus sombre que WHITE
- Aucune dominante rouge, orange ou marron
- Si tu hésites entre GRAY et une autre couleur, regarde si la bande a une teinte colorée : si non → GRAY

BROWN (marron) :
- Brun chaud avec une dominante rouge-orangée mais très sombre
- Ressemble à du chocolat foncé ou de la terre
- Toujours plus sombre qu'ORANGE, souvent confondu mais clairement coloré (pas neutre)
- Si la bande est sombre ET a une teinte rouge/orange → BROWN

ORANGE :
- Orange vif et saturé, couleur potiron ou mandarine
- Clairement plus lumineux et vif que BROWN
- Pas de nuance marron, vraiment orange pur

DISTINCTIONS CLÉS :
- GRAY vs BROWN : GRAY est neutre (pas de teinte), BROWN est chaud (rouge-brun)
- BROWN vs ORANGE : BROWN est sombre comme du chocolat, ORANGE est vif et lumineux
- GRAY vs WHITE : WHITE est très clair/presque blanc, GRAY est intermédiaire

Réponds UNIQUEMENT en JSON, sans texte avant ou après :
{"bands": ["COULEUR1", "COULEUR2", "COULEUR3"]}

Couleurs possibles : BLACK, BROWN, RED, ORANGE, YELLOW, GREEN, BLUE, PURPLE, GRAY, WHITE
Si tu ne peux pas identifier clairement, réponds : {"bands": null}"""

def ask_claude(crop_bgr):
    """Envoie le crop à Claude et retourne (b1, b2, b3) ou None."""
    if crop_bgr is None or crop_bgr.size == 0:
        return None

    # Agrandir le crop — minimum 300px de haut pour que Claude voie bien les couleurs
    h, w = crop_bgr.shape[:2]
    target_h = 300
    if h < target_h:
        scale = target_h / h
        crop_bgr = cv2.resize(crop_bgr,
                              (int(w*scale), int(h*scale)),
                              interpolation=cv2.INTER_CUBIC)

    # Légère amélioration contraste pour mieux séparer GRAY/BROWN/ORANGE
    lab = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2LAB)
    clahe = cv2.createCLAHE(clipLimit=1.5, tileGridSize=(4,4))
    lab[:,:,0] = clahe.apply(lab[:,:,0])
    crop_bgr = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)

    _, buf = cv2.imencode(".jpg", crop_bgr, [cv2.IMWRITE_JPEG_QUALITY, 97])
    b64 = base64.standard_b64encode(buf).decode("utf-8")

    try:
        client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
        msg = client.messages.create(
            model="claude-opus-4-5",
            max_tokens=64,
            system=SYSTEM_PROMPT,
            messages=[{
                "role": "user",
                "content": [
                    {
                        "type": "image",
                        "source": {"type": "base64",
                                   "media_type": "image/jpeg",
                                   "data": b64}
                    },
                    {
                        "type": "text",
                        "text": "Identifie les 3 bandes de valeur de cette résistance."
                    }
                ]
            }]
        )

        raw = msg.content[0].text.strip()
        print(f"  [CLAUDE] {raw}")
        data = json.loads(raw)
        bands = data.get("bands")

        if bands is None or len(bands) != 3:
            return None

        bands = [b.upper().strip() for b in bands]
        valid = set(DIGIT.keys()) | {"GOLD","SILVER"}
        if any(b not in valid for b in bands):
            print(f"  [CLAUDE] Couleur inconnue dans {bands}")
            return None

        return tuple(bands)

    except json.JSONDecodeError as e:
        print(f"  [CLAUDE] JSON invalide : {e}")
        return None
    except anthropic.APIError as e:
        print(f"  [CLAUDE] Erreur API : {e}")
        return None
    except Exception as e:
        print(f"  [CLAUDE] Erreur : {e}")
        return None


# ═══════════════════════════════════════════════════
#  AFFICHAGE
# ═══════════════════════════════════════════════════
def draw_frame(display, state):
    fh, fw = display.shape[:2]

    # Zone de pose
    cv2.rectangle(display, (X1,Y1), (X2,Y2), (0,255,150), 2)
    L = 14
    for cx,cy,dx,dy in [(X1,Y1,1,1),(X2,Y1,-1,1),(X1,Y2,1,-1),(X2,Y2,-1,-1)]:
        cv2.line(display,(cx,cy),(cx+dx*L,cy),(0,255,150),3)
        cv2.line(display,(cx,cy),(cx,cy+dy*L),(0,255,150),3)
    cv2.putText(display, "Poser la resistance ici",
                (X1, Y1-8), FONT, 0.45, (0,255,150), 1, cv2.LINE_AA)

    # Bande de commandes
    cv2.rectangle(display, (0, fh-60), (fw, fh), (15,15,15), -1)

    status = state.get("status", "waiting")

    if status == "analysing":
        cv2.putText(display, "Analyse en cours...",
                    (10, fh-30), FONT, 0.9, (0,200,255), 2, cv2.LINE_AA)

    elif status == "locked":
        bands      = state["bands"]
        value      = state["value"]
        std_val    = state["std_val"]
        std_serie  = state["std_serie"]
        std_diff   = state["std_diff"]
        std_status = state["std_status"]

        if std_status == 'exact':
            col  = (0,255,100)
            icon = "OK"
            stxt = f"{std_serie}  ({std_diff:.1f}%)"
        elif std_status == 'close':
            col  = (0,200,255)
            icon = "~"
            stxt = f"Proche {format_std(std_val)}  ({std_diff:.1f}%)"
        else:
            col  = (0,80,255)
            icon = "?"
            stxt = f"Hors serie  ({std_diff:.0f}%)" if std_diff else "Non standard"

        cv2.putText(display, format_ohms(value),
                    (10, fh-28), FONT, 1.2, col, 2, cv2.LINE_AA)
        cv2.putText(display, f"[{icon}] {stxt}",
                    (10, fh-8), FONT, 0.42, col, 1, cv2.LINE_AA)

        # Pastilles de couleur
        px = fw - 20
        for cname in reversed(bands):
            bgr = BGR_COLOUR.get(cname, (128,128,128))
            cv2.circle(display, (px, fh-42), 13, bgr, -1)
            cv2.circle(display, (px, fh-42), 13, (70,70,70), 1)
            cv2.putText(display, cname[:2], (px-10, fh-38),
                        FONT, 0.34, (255,255,255), 1)
            px -= 34

        cv2.putText(display, "[LOCKED]",
                    (fw-115, 22), FONT, 0.65, (0,200,255), 2, cv2.LINE_AA)

    else:  # waiting
        cv2.putText(display,
                    "Place la resistance horizontalement dans le rectangle",
                    (10, fh-30), FONT, 0.45, (0,100,255), 1, cv2.LINE_AA)

    cv2.putText(display, "R=reset   S=sauvegarder   Q=quitter",
                (10, fh-78), FONT, 0.36, (100,100,100), 1, cv2.LINE_AA)
    cv2.putText(display, "Claude API",
                (fw-100, 18), FONT, 0.42, (0,200,255), 1, cv2.LINE_AA)


def save_crop(img):
    os.makedirs(SAVE_DIR, exist_ok=True)
    idx  = len([f for f in os.listdir(SAVE_DIR) if f.endswith(".png")])
    path = os.path.join(SAVE_DIR, f"crop_{idx:03d}.png")
    cv2.imwrite(path, img[Y1:Y2, X1:X2])
    print(f"  [S] Sauvegardé → {path}")


# ═══════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════
def main():
    cam = CameraStream(CAMERA_URL)
    if not cam.isOpened():
        print(f"[ERREUR] Impossible de se connecter à DroidCam : {CAMERA_URL}")
        print("  → Vérifie que l'app DroidCam est ouverte sur ton téléphone")
        print("  → Vérifie que l'IP est correcte (visible dans l'app)")
        return

    state    = {"status": "waiting"}
    last_img = None

    # Thread d'analyse pour ne pas bloquer l'affichage
    analyse_thread = None

    def run_analyse(img):
        crop = img[Y1:Y2, X1:X2]
        result = ask_claude(crop)
        if result is not None:
            value = compute_value(result)
            if value is not None:
                sv, ss, sd, st = find_standard(value)
                state.update({
                    "status":     "locked",
                    "bands":      result,
                    "value":      value,
                    "std_val":    sv,
                    "std_serie":  ss,
                    "std_diff":   sd,
                    "std_status": st,
                })
                icon = {"exact":"✅","close":"⚠️","none":"❌"}.get(st,"?")
                print(f"  [LOCK] {format_ohms(value)}  {result}")
                print(f"  [E24]  {icon} {st.upper()}  "
                      f"Plus proche : {format_std(sv)}  "
                      f"(écart={sd:.1f}%)")
            else:
                print(f"  [ERREUR] Calcul impossible pour {result}")
                state["status"] = "waiting"
        else:
            print("  [CLAUDE] Pas de résultat — réessaie")
            state["status"] = "waiting"

    print("=== Resistor Reader — Claude API + DroidCam ===")
    print(f"  Caméra : {CAMERA_URL}")
    print("  R=reset   S=sauvegarder   Q=quitter\n")

    cv2.namedWindow("Resistor Reader")

    while True:
        ret, frame = cam.read()
        if not ret or frame is None:
            cv2.waitKey(10)
            continue

        img      = cv2.resize(frame, (RESIZE_W, RESIZE_H))
        last_img = img

        # Lancer analyse si on est en attente et pas déjà en cours
        if state["status"] == "waiting":
            if analyse_thread is None or not analyse_thread.is_alive():
                state["status"] = "analysing"
                analyse_thread  = threading.Thread(
                    target=run_analyse, args=(img.copy(),), daemon=True)
                analyse_thread.start()

        display = img.copy()
        draw_frame(display, state)
        cv2.imshow("Resistor Reader", display)

        key = cv2.waitKey(1) & 0xFF
        if key == ord('q'):
            break
        elif key == ord('r'):
            state.clear()
            state["status"] = "waiting"
            print("  Reset")
        elif key == ord('s') and last_img is not None:
            save_crop(last_img)

    cam.release()
    cv2.destroyAllWindows()
    print("Terminé.")


if __name__ == "__main__":
    main()