"""
vision.py — TRI_VISION P2
==========================
Scan zone complète + validation E12/E24 + GRAY/WHITE corrigés.
Identification couleurs via Claude API (vision) + fallback HSV local.

Contrôles :
  S → sauvegarder  D → debug  C → calibration  R → reset  Q → quitter
"""

import cv2
import numpy as np
import os
import threading
from collections import Counter

# ═══════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════
CAMERA_URL = "http://192.168.133.197:4747/video"   # ← IP DroidCam à adapter
RESIZE_W   = 640
RESIZE_H   = 360
SAVE_DIR   = "crops"
FONT       = cv2.FONT_HERSHEY_SIMPLEX

POSE_CX = 0.50
POSE_CY = 0.60
POSE_W  = 0.20
POSE_H  = 0.22

BODY_SAMPLE_PCT  = 0.08
BODY_DIST_THR    = 35
BODY_BAND_MARGIN = 15

MIN_SEG_WIDTH    = 5
MIN_COL_VOTES    = 0.10

ANALYSE_FRAMES    = 5
TOLERANCE_COLOURS = {"GOLD", "SILVER"}

MATCH_TOLERANCE_PCT = 2.0
CLOSE_TOLERANCE_PCT = 10.0

# Mode Claude : True = utilise l'API Claude pour identifier les bandes
#               False = utilise uniquement la détection HSV locale
USE_CLAUDE_API = False   # ← détection 100 % couleurs (HSV), sans Claude

# ═══════════════════════════════════════════════════
#  IMPORT CLAUDE (optionnel — désactivé si indispo)
# ═══════════════════════════════════════════════════
_claude_available = False
if USE_CLAUDE_API:
    try:
        from claude_vision import ask_claude_bands
        _claude_available = True
        print("[CLAUDE] Module chargé ✅")
    except ImportError as e:
        print(f"[CLAUDE] Module non disponible ({e}) — mode HSV seul")

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

def find_standard(value):
    if value is None or value <= 0:
        return None, None, None, 'none'
    best_val, best_diff = None, float('inf')
    for std in ALL_STANDARD:
        diff = abs(value - std) / std * 100
        if diff < best_diff:
            best_diff, best_val = diff, std
    if best_diff <= MATCH_TOLERANCE_PCT:
        serie = 'E12' if best_val in E12_VALUES else 'E24'
        return best_val, serie, best_diff, 'exact'
    elif best_diff <= CLOSE_TOLERANCE_PCT:
        serie = 'E12' if best_val in E12_VALUES else 'E24'
        return best_val, serie, best_diff, 'close'
    return best_val, None, best_diff, 'none'

def format_std(v):
    if v is None: return "?"
    if v >= 1e6:  return f"{v/1e6:.2g}MΩ"
    if v >= 1e3:  return f"{v/1e3:.2g}kΩ"
    return f"{v:.2g}Ω"


# ═══════════════════════════════════════════════════
#  PLAGES HSV
# ═══════════════════════════════════════════════════
COLOUR_RANGES = [
    ("BLACK",  (0,    0,   0),  (179, 255,  60),  0,  (40,  40,  40)),
    ("BROWN",  (3,  130,  25),  (16,  252, 130),  1,  (0,   60,  160)),
    ("RED",    (0,  146,  61),  (7,   255, 200),  2,  (0,   0,   220)),
    ("RED",    (162, 120, 50),  (179, 255, 230),  2,  (0,   0,   220)),
    ("ORANGE", (10, 170, 105),  (19,  255, 200),  3,  (0,  120,  255)),
    ("YELLOW", (25, 153,  70),  (40,  255, 200),  4,  (0,  210,  210)),
    ("GREEN",  (33,  81,  31),  (90,  255, 200),  5,  (0,  180,   50)),
    ("BLUE",   (91,  50,  30),  (128, 255, 200),  6,  (200,  30,   0)),
    ("PURPLE", (115, 39,  40),  (162, 255, 200),  7,  (170,   0, 140)),
    ("GRAY",   (0,    0,  61),  (179,  60, 200),  8,  (120, 120, 120)),
    ("WHITE",  (0,    0, 200),  (179,  15, 255),  9,  (220, 220, 200)),
    ("GOLD",   (8,  110,  65),  (26,  182, 186), -1,  (0,  180,  215)),
    ("SILVER", (0,    0, 160),  (179,  20, 220), -1,  (192, 192, 192)),
]

MULTIPLIERS = {
    0:1, 1:10, 2:100, 3:1_000, 4:10_000,
    5:100_000, 6:1_000_000, 7:1e7, 8:0.01, 9:0.1,
}
BGR_MAP = {name: bgr for name,_,_,_,bgr in COLOUR_RANGES}


# ═══════════════════════════════════════════════════
#  ZONE DE POSE
# ═══════════════════════════════════════════════════
def _compute_pose():
    pw = int(RESIZE_W * POSE_W)
    ph = int(RESIZE_H * POSE_H)
    cx = int(RESIZE_W * POSE_CX)
    cy = int(RESIZE_H * POSE_CY)
    return cx-pw//2, cy-ph//2, cx+pw//2, cy+ph//2, cx, cy

POSE_X1, POSE_Y1, POSE_X2, POSE_Y2, POSE_CX_PX, POSE_CY_PX = _compute_pose()
POSE_W_PX = POSE_X2 - POSE_X1
POSE_H_PX = POSE_Y2 - POSE_Y1


# ═══════════════════════════════════════════════════
#  CALIBRATION
# ═══════════════════════════════════════════════════
_calib_mode    = False
_calib_samples = []
_hsv_current   = None
_SAMPLE_R      = 3


def _mouse_cb(event, x, y, flags, param):
    global _calib_samples
    if not _calib_mode or _hsv_current is None:
        return
    if event == cv2.EVENT_RBUTTONDOWN:
        _calib_samples.clear()
        print("  [CALIB] Samples effacés")
        return
    if event != cv2.EVENT_LBUTTONDOWN:
        return
    r = _SAMPLE_R
    patch = _hsv_current[
        max(0,y-r):min(RESIZE_H-1,y+r)+1,
        max(0,x-r):min(RESIZE_W-1,x+r)+1,
    ]
    if patch.size == 0: return
    h_val = int(np.median(patch[:,:,0]))
    s_val = int(np.median(patch[:,:,1]))
    v_val = int(np.median(patch[:,:,2]))
    matched,_,_ = classify_pixel(h_val,s_val,v_val)
    _calib_samples.append((x,y,h_val,s_val,v_val,matched))
    label = matched if matched else "NON DÉTECTÉ"
    print(f"  [CALIB] ({x:3d},{y:3d})  H={h_val:3d}  S={s_val:3d}  V={v_val:3d}  → {label}")
    if matched is None:
        best_name, best_dist = "?", 10_000
        for (name,lo,hi,val,bgr) in COLOUR_RANGES:
            d = (max(0,lo[0]-h_val,h_val-hi[0])
               + max(0,lo[1]-s_val,s_val-hi[1])
               + max(0,lo[2]-v_val,v_val-hi[2]))
            if d < best_dist:
                best_dist, best_name = d, name
        print(f"           → Plus proche : {best_name}  (écart={best_dist})")
        print(f"           → Élargir : H~{h_val}  S~{s_val}  V~{v_val}")


def _draw_calib_overlay(display):
    fh, fw = display.shape[:2]
    cv2.rectangle(display,(0,0),(fw,28),(25,25,70),-1)
    cv2.putText(display,
                "CALIBRATION  |  Clic G = sample   Clic D = effacer   C = quitter",
                (6,19),FONT,0.40,(80,220,255),1,cv2.LINE_AA)
    for (sx,sy,hv,sv,vv,matched) in _calib_samples:
        bgr   = BGR_MAP.get(matched,(128,128,128)) if matched else (128,128,128)
        label = f"H{hv} S{sv} V{vv}  {matched or '???'}"
        cv2.drawMarker(display,(sx,sy),(255,255,255),cv2.MARKER_CROSS,14,1,cv2.LINE_AA)
        cv2.drawMarker(display,(sx,sy),bgr,cv2.MARKER_CROSS,10,2,cv2.LINE_AA)
        (tw,th),_ = cv2.getTextSize(label,FONT,0.38,1)
        bx = min(sx+10, fw-tw-14)
        by = max(sy-10, th+6)
        cv2.rectangle(display,(bx-2,by-th-3),(bx+tw+th+4,by+3),(15,15,15),-1)
        cv2.rectangle(display,(bx-2,by-th-3),(bx+tw+th+4,by+3),bgr,1)
        cv2.rectangle(display,(bx-2,by-th-3),(bx+th,by+3),bgr,-1)
        cv2.putText(display,label,(bx+th+2,by-1),FONT,0.38,(220,220,220),1,cv2.LINE_AA)
    if len(_calib_samples) >= 2:
        hs=[s[2] for s in _calib_samples]
        ss=[s[3] for s in _calib_samples]
        vs=[s[4] for s in _calib_samples]
        summary=(f"Plage   H[{min(hs)}–{max(hs)}]  "
                 f"S[{min(ss)}–{max(ss)}]  "
                 f"V[{min(vs)}–{max(vs)}]   ({len(_calib_samples)} pts)")
        cv2.rectangle(display,(0,fh-22),(fw,fh),(20,20,60),-1)
        cv2.putText(display,summary,(6,fh-7),FONT,0.42,(80,220,255),1,cv2.LINE_AA)


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
        self.thread  = threading.Thread(target=self._capture, daemon=True)
        self.thread.start()

    def _capture(self):
        while self.running:
            ok, f = self.cap.read()
            if ok:
                with self.lock:
                    self.frame = f

    def read(self):
        with self.lock:
            return (True,self.frame.copy()) if self.frame is not None else (False,None)

    def isOpened(self): return self.cap.isOpened()

    def release(self):
        self.running = False
        self.thread.join(timeout=1)
        self.cap.release()


# ═══════════════════════════════════════════════════
#  PRÉTRAITEMENT
# ═══════════════════════════════════════════════════
def white_balance_from_background(img):
    mask = np.ones(img.shape[:2], dtype=bool)
    m = 20
    mask[max(0,POSE_Y1-m):min(RESIZE_H,POSE_Y2+m),
         max(0,POSE_X1-m):min(RESIZE_W,POSE_X2+m)] = False
    img_f = img.astype(np.float32)
    for c in range(3):
        ch  = img_f[:,:,c]
        ref = np.percentile(ch[mask], 90)
        if ref > 10:
            img_f[:,:,c] = np.clip(ch * (255.0/ref), 0, 255)
    return img_f.astype(np.uint8)


def preprocess(img):
    img = white_balance_from_background(img)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4,4))
    lab[:,:,0] = clahe.apply(lab[:,:,0])
    img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    bil = cv2.bilateralFilter(img, 7, 75, 75)
    gray = cv2.cvtColor(bil, cv2.COLOR_BGR2GRAY)
    _, overexp = cv2.threshold(gray, 252, 255, cv2.THRESH_BINARY)
    valid_mask = cv2.bitwise_not(overexp)
    hsv = cv2.cvtColor(bil, cv2.COLOR_BGR2HSV)
    return bil, hsv, valid_mask


# ═══════════════════════════════════════════════════
#  DÉTECTION COULEUR DU CORPS
# ═══════════════════════════════════════════════════
def detect_body_colour(hsv):
    bw = max(3, int(POSE_W_PX * BODY_SAMPLE_PCT))
    y1 = max(0, POSE_CY_PX - 6)
    y2 = min(RESIZE_H-1, POSE_CY_PX + 6)
    left  = hsv[y1:y2+1, POSE_X1:POSE_X1+bw].reshape(-1,3)
    right = hsv[y1:y2+1, POSE_X2-bw:POSE_X2].reshape(-1,3)
    combined = np.concatenate([left,right], axis=0)
    if combined.size == 0:
        return (15, 60, 120)
    return (int(np.median(combined[:,0])),
            int(np.median(combined[:,1])),
            int(np.median(combined[:,2])))


def hsv_dist(h1,s1,v1,h2,s2,v2):
    dh = min(abs(int(h1)-int(h2)), 180-abs(int(h1)-int(h2)))
    return dh*2 + abs(int(s1)-int(s2)) + abs(int(v1)-int(v2))


def is_body(h,s,v,body):
    return hsv_dist(h,s,v,*body) < BODY_DIST_THR


# ═══════════════════════════════════════════════════
#  CLASSIFIER UN PIXEL (HSV local)
# ═══════════════════════════════════════════════════
def classify_pixel(h,s,v):
    for (name,lo,hi,val,bgr) in COLOUR_RANGES:
        if lo[0]<=h<=hi[0] and lo[1]<=s<=hi[1] and lo[2]<=v<=hi[2]:
            return name,val,bgr
    return None,None,None


# ═══════════════════════════════════════════════════
#  SCAN ZONE COMPLÈTE (HSV local)
# ═══════════════════════════════════════════════════
def scan_zone(hsv, valid_mask, body_hsv, debug, bil):
    zone_hsv   = hsv[POSE_Y1:POSE_Y2, POSE_X1:POSE_X2]
    zone_valid = valid_mask[POSE_Y1:POSE_Y2, POSE_X1:POSE_X2]
    zone_h, zone_w = zone_hsv.shape[:2]

    bh, bs, bv = body_hsv
    H = zone_hsv[:,:,0].astype(np.int32)
    S = zone_hsv[:,:,1].astype(np.int32)
    V = zone_hsv[:,:,2].astype(np.int32)
    dH = np.minimum(np.abs(H-bh), 180-np.abs(H-bh))
    body_mask = (dH*2 + np.abs(S-bs) + np.abs(V-bv)) < BODY_DIST_THR
    non_body  = (~body_mask) & (zone_valid > 0)

    pixel_colours = []
    for col in range(zone_w):
        col_mask = non_body[:, col]
        n_valid  = int(col_mask.sum())
        if n_valid == 0:
            pixel_colours.append(None)
            continue
        votes = {}
        for row in range(zone_h):
            if not col_mask[row]:
                continue
            hv = int(zone_hsv[row, col, 0])
            sv = int(zone_hsv[row, col, 1])
            vv = int(zone_hsv[row, col, 2])
            name,_,_ = classify_pixel(hv,sv,vv)
            if name and name not in TOLERANCE_COLOURS:
                votes[name] = votes.get(name,0) + 1
        dominant = None
        if votes:
            best = max(votes, key=votes.get)
            if votes[best] >= max(1, n_valid * MIN_COL_VOTES):
                dominant = best
        pixel_colours.append(dominant)

    if debug:
        dbg = bil.copy()
        cv2.rectangle(dbg,(POSE_X1,POSE_Y1),(POSE_X2,POSE_Y2),(0,255,150),1)
        for col in range(zone_w):
            cname = pixel_colours[col]
            if cname:
                bgr = BGR_MAP.get(cname,(128,128,128))
                cv2.line(dbg,
                         (POSE_X1+col, POSE_Y1),
                         (POSE_X1+col, POSE_Y2),
                         bgr, 1)
        body_bgr = cv2.cvtColor(np.uint8([[list(body_hsv)]]),
                                cv2.COLOR_HSV2BGR)[0][0].tolist()
        cv2.rectangle(dbg,(4,4),(22,22),body_bgr,-1)
        cv2.putText(dbg,"corps",(26,17),FONT,0.35,(255,255,255),1)
        cv2.imshow("DEBUG - Scan", dbg)

    return pixel_colours


# ═══════════════════════════════════════════════════
#  SEGMENTATION
# ═══════════════════════════════════════════════════
def segment_colours(pixel_colours):
    ref = {}
    for name,_,_,val,bgr in COLOUR_RANGES:
        if name not in ref:
            ref[name] = (val,bgr)
    bands = []
    i, n = 0, len(pixel_colours)
    while i < n:
        c = pixel_colours[i]
        if c is None:
            i += 1
            continue
        j = i
        while j < n and pixel_colours[j] == c:
            j += 1
        if (j-i) >= MIN_SEG_WIDTH:
            val, bgr = ref.get(c,(0,(128,128,128)))
            if not bands or bands[-1][1] != c:
                bands.append(((i+j)//2, c, val, bgr,
                               POSE_X1+i, POSE_X1+j))
        i = j
    return bands


# ═══════════════════════════════════════════════════
#  FILTRE BANDES PROCHES DU CORPS
# ═══════════════════════════════════════════════════
def filter_body_bands(bands, body_hsv):
    if not bands or body_hsv is None:
        return bands
    threshold = BODY_DIST_THR + BODY_BAND_MARGIN
    filtered  = []
    for b in bands:
        bgr = b[3]
        hsv_band = cv2.cvtColor(np.uint8([[list(bgr)]]),
                                cv2.COLOR_BGR2HSV)[0][0]
        dist = hsv_dist(int(hsv_band[0]),int(hsv_band[1]),int(hsv_band[2]),
                        *body_hsv)
        if dist > threshold:
            filtered.append(b)
        else:
            print(f"  [FILTRE] '{b[1]}' retiré (dist={dist})")
    return filtered


# ═══════════════════════════════════════════════════
#  SÉLECTION DES 3 BANDES
# ═══════════════════════════════════════════════════
def pick_3_bands(value_bands):
    if len(value_bands) <= 3:
        return value_bands[:3]
    gaps = [value_bands[i+1][4] - value_bands[i][5]
            for i in range(len(value_bands)-1)]
    max_gap_idx = gaps.index(max(gaps))
    if max_gap_idx == 0:
        return value_bands[1:4]
    elif max_gap_idx == len(gaps)-1:
        return value_bands[-4:-1] if len(value_bands)>=4 else value_bands[:-1]
    else:
        mid = len(value_bands)//2
        return value_bands[mid-1:mid+2]


# ═══════════════════════════════════════════════════
#  ANALYSE N FRAMES + VOTE MAJORITAIRE
#  → si Claude disponible : appel API sur le crop
#  → sinon : détection HSV locale
# ═══════════════════════════════════════════════════
def analyse_frames(cam, n_frames, debug):
    results   = []
    last_all  = []
    last_body = None
    last_img  = None

    for fi in range(n_frames):
        ret, frame = cam.read()
        if not ret or frame is None:
            continue
        img = cv2.resize(frame, (RESIZE_W, RESIZE_H))
        bil, hsv, valid_mask = preprocess(img)
        body_hsv      = detect_body_colour(hsv)
        pixel_colours = scan_zone(hsv, valid_mask, body_hsv, debug, bil)
        all_bands     = segment_colours(pixel_colours)
        all_bands     = filter_body_bands(all_bands, body_hsv)

        value_bands = [b for b in all_bands if b[1] not in TOLERANCE_COLOURS]

        # ── MODE CLAUDE : on envoie le crop à l'API ──
        if _claude_available and USE_CLAUDE_API:
            crop = bil[POSE_Y1:POSE_Y2, POSE_X1:POSE_X2]
            claude_result = ask_claude_bands(crop, verbose=True)
            if claude_result is not None:
                results.append(claude_result)
                print(f"  [ANALYSE] Frame {fi+1}/{n_frames} [CLAUDE] → {claude_result}")
                last_all  = all_bands
                last_body = body_hsv
                last_img  = img
                cv2.waitKey(40)
                continue  # pas besoin de continuer avec HSV

        # ── MODE HSV LOCAL ──
        if len(value_bands) >= 3:
            if len(value_bands) > 3:
                value_bands = pick_3_bands(value_bands)
            colours = tuple(b[1] for b in value_bands[:3])
            results.append(colours)
            print(f"  [ANALYSE] Frame {fi+1}/{n_frames} [HSV] → {colours}")
        else:
            print(f"  [ANALYSE] Frame {fi+1}/{n_frames} → {len(value_bands)} bande(s)")

        last_all  = all_bands
        last_body = body_hsv
        last_img  = img
        cv2.waitKey(40)

    if not results:
        return None, last_all, last_body, last_img

    winner = Counter(results).most_common(1)[0][0]
    count  = Counter(results)[winner]
    mode   = "CLAUDE" if _claude_available and USE_CLAUDE_API else "HSV"
    print(f"  [ANALYSE] Résultat [{mode}] : {winner}  ({count}/{n_frames} frames)")
    return winner, last_all, last_body, last_img


# ═══════════════════════════════════════════════════
#  CALCUL
# ═══════════════════════════════════════════════════
def compute_value_from_names(colour_names):
    if len(colour_names) < 3:
        return None
    ref = {}
    for name,_,_,val,_ in COLOUR_RANGES:
        if name not in ref:
            ref[name] = val
    vals = [ref.get(c) for c in colour_names[:3]]
    if None in vals or vals[2] not in MULTIPLIERS:
        return None
    try:
        return int(f"{vals[0]}{vals[1]}") * MULTIPLIERS[vals[2]]
    except (ValueError, OverflowError):
        return None


def format_ohms(value):
    if value is None: return "???"
    if value >= 1e6:  return f"{value/1e6:.2f} MΩ"
    if value >= 1e3:  return f"{value/1e3:.2f} kΩ"
    return f"{value:.1f} Ω"


# ═══════════════════════════════════════════════════
#  AFFICHAGE
# ═══════════════════════════════════════════════════
def draw_pose_zone(img, body_hsv, all_bands, val_colours):
    cv2.rectangle(img,(POSE_X1,POSE_Y1),(POSE_X2,POSE_Y2),(0,255,150),2)
    L = 12
    for cx,cy,dx,dy in [(POSE_X1,POSE_Y1,1,1),(POSE_X2,POSE_Y1,-1,1),
                        (POSE_X1,POSE_Y2,1,-1),(POSE_X2,POSE_Y2,-1,-1)]:
        cv2.line(img,(cx,cy),(cx+dx*L,cy),(0,255,150),3)
        cv2.line(img,(cx,cy),(cx,cy+dy*L),(0,255,150),3)
    cv2.line(img,(POSE_X1,POSE_CY_PX),(POSE_X2,POSE_CY_PX),(0,255,150),1,cv2.LINE_AA)
    cv2.putText(img,"Poser la resistance ici",
                (POSE_X1,POSE_Y1-6),FONT,0.40,(0,255,150),1,cv2.LINE_AA)

    if body_hsv is not None:
        body_bgr = cv2.cvtColor(np.uint8([[list(body_hsv)]]),
                                cv2.COLOR_HSV2BGR)[0][0].tolist()
        cv2.rectangle(img,(POSE_X1,POSE_Y2+4),(POSE_X1+14,POSE_Y2+18),body_bgr,-1)
        cv2.putText(img,"corps",(POSE_X1+18,POSE_Y2+15),FONT,0.30,(150,150,150),1)

    val_set = set(val_colours) if val_colours else set()
    for b in all_bands:
        is_tol = b[1] in TOLERANCE_COLOURS
        is_val = b[1] in val_set and not is_tol
        if is_val:
            col, thick, label = b[3], 2, b[1][:2]
        elif is_tol:
            col, thick, label = (0,180,215), 1, "tol"
        else:
            col, thick, label = (100,100,100), 1, "?"
        cv2.rectangle(img,(b[4],POSE_Y1),(b[5],POSE_Y2),col,thick)
        cv2.putText(img,label,(b[4],POSE_Y1-4),FONT,0.35,col,1,cv2.LINE_AA)


def draw_result(display, cur_value, cur_colours, std_val, std_serie, std_diff, std_status):
    fh, fw = display.shape[:2]
    if std_status == 'exact':
        sc=(0,255,100); icon="OK"; stxt=f"{std_serie}  ({std_diff:.1f}%)"
    elif std_status == 'close':
        sc=(0,200,255); icon="~";  stxt=f"Proche {format_std(std_val)}  ({std_diff:.1f}%)"
    else:
        sc=(0,80,255);  icon="?";  stxt=f"Hors série  ({std_diff:.0f}%)" if std_diff else "Non standard"

    cv2.putText(display, format_ohms(cur_value),
                (10,fh-36), FONT, 1.1, sc, 2, cv2.LINE_AA)
    cv2.putText(display, f"[{icon}] {stxt}",
                (10,fh-10), FONT, 0.40, sc, 1, cv2.LINE_AA)

    # Indicateur mode Claude ou HSV
    mode_lbl = "CLAUDE API" if _claude_available and USE_CLAUDE_API else "HSV local"
    mode_col = (0,200,255) if _claude_available and USE_CLAUDE_API else (150,150,150)
    cv2.putText(display, mode_lbl, (fw-120, 18), FONT, 0.42, mode_col, 1, cv2.LINE_AA)

    if cur_colours:
        ref_bgr = {}
        for name,_,_,_,bgr in COLOUR_RANGES:
            if name not in ref_bgr: ref_bgr[name] = bgr
        px = fw-16
        for cname in reversed(cur_colours):
            bgr = ref_bgr.get(cname,(128,128,128))
            cv2.circle(display,(px,fh-42),11,bgr,-1)
            cv2.circle(display,(px,fh-42),11,(70,70,70),1)
            cv2.putText(display,cname[:2],(px-9,fh-38),FONT,0.33,(255,255,255),1)
            px -= 30


def save_crop(img):
    os.makedirs(SAVE_DIR, exist_ok=True)
    idx  = len([f for f in os.listdir(SAVE_DIR) if f.endswith("_bgr.png")])
    path = os.path.join(SAVE_DIR, f"crop_{idx:03d}_bgr.png")
    cv2.imwrite(path, img[POSE_Y1:POSE_Y2, POSE_X1:POSE_X2])
    print(f"  [S] Sauvegardé → {path}")


# ═══════════════════════════════════════════════════
#  MAIN
# ═══════════════════════════════════════════════════
def main():
    global _calib_mode, _calib_samples, _hsv_current

    cam = CameraStream(CAMERA_URL)
    if not cam.isOpened():
        print(f"[ERREUR] Connexion impossible : {CAMERA_URL}")
        print("  → Vérifie que DroidCam est lancé et que l'IP est correcte")
        print(f"  → URL utilisée : {CAMERA_URL}")
        return

    debug      = False
    analysing  = False
    cur_all    = []
    cur_colours= None
    cur_value  = None
    cur_body   = None
    locked     = False
    last_img   = None

    std_val=None; std_serie=None; std_diff=None; std_status='none'

    cv2.namedWindow("Resistor Reader")
    cv2.setMouseCallback("Resistor Reader", _mouse_cb)

    mode_str = "Claude API" if _claude_available and USE_CLAUDE_API else "HSV local"
    print(f"=== Resistor Reader — TRI_VISION ===  [Mode: {mode_str}]")
    print("  S=sauvegarder  D=debug  C=calibration  R=reset  Q=quitter\n")

    while True:
        ret, frame = cam.read()
        if not ret or frame is None:
            cv2.waitKey(10)
            continue

        img = cv2.resize(frame, (RESIZE_W, RESIZE_H))
        last_img = img

        if not locked and not analysing:
            bil, hsv, valid_mask = preprocess(img)
            _hsv_current = hsv
            body_hsv     = detect_body_colour(hsv)
            cur_body     = body_hsv

            pixel_colours = scan_zone(hsv, valid_mask, body_hsv, debug, bil)
            all_bands     = segment_colours(pixel_colours)
            all_bands     = filter_body_bands(all_bands, body_hsv)
            cur_all       = all_bands

            value_live = [b for b in all_bands if b[1] not in TOLERANCE_COLOURS]

            # Déclenchement analyse : HSV voit ≥3 bandes ou mode Claude actif
            trigger_analyse = (
                len(value_live) >= 3 or
                (_claude_available and USE_CLAUDE_API and len(value_live) >= 1)
            )

            if trigger_analyse:
                analysing = True
                print(f"  [ANALYSE] {ANALYSE_FRAMES} frames en cours... [{mode_str}]")

                winner, last_all, last_body, last_img = analyse_frames(
                    cam, ANALYSE_FRAMES, debug)

                analysing = False
                cur_all  = last_all
                cur_body = last_body

                if winner is not None:
                    cur_colours = winner
                    cur_value   = compute_value_from_names(winner)
                    if cur_value is not None:
                        std_val,std_serie,std_diff,std_status = find_standard(cur_value)
                        locked = True
                        icon = {"exact":"✅","close":"⚠️","none":"❌"}.get(std_status,"?")
                        print(f"  [LOCK] {format_ohms(cur_value)}  {winner}")
                        print(f"  [E24]  {icon} {std_status.upper()}  "
                              f"Plus proche : {format_std(std_val)}  "
                              f"(écart={std_diff:.1f}%)")
                    else:
                        print(f"  [ERREUR] Calcul impossible pour {winner}")
                        cur_colours = None
                else:
                    print("  [ANALYSE] Résultat insuffisant — réessaie")

        # ── Affichage ──────────────────────────────
        display = (last_img if last_img is not None else img).copy()
        draw_pose_zone(display, cur_body, cur_all, cur_colours)

        fh, fw = display.shape[:2]
        if locked:
            cv2.putText(display,"[LOCKED]",
                        (RESIZE_W-110,22),FONT,0.65,(0,200,255),2,cv2.LINE_AA)

        ov = display.copy()
        cv2.rectangle(ov,(0,fh-65),(fw,fh),(15,15,15),-1)
        cv2.addWeighted(ov,0.7,display,0.3,0,display)

        if analysing:
            cv2.putText(display,"Analyse en cours...",
                        (10,fh-36),FONT,0.9,(0,200,255),2,cv2.LINE_AA)
        elif cur_value is not None and cur_colours is not None:
            draw_result(display,cur_value,cur_colours,
                        std_val,std_serie,std_diff,std_status)
        else:
            n = len([b for b in cur_all if b[1] not in TOLERANCE_COLOURS])
            msg = (f"{n} bande(s) detectee(s) — besoin de 3"
                   if n > 0 else "Aucune bande — place la resistance horizontalement")
            cv2.putText(display,msg,(10,fh-36),FONT,0.48,(0,100,255),1,cv2.LINE_AA)

        cv2.putText(display,"S=sauvegarder  R=reset  D=debug  C=calibration  Q=quitter",
                    (10,fh-80),FONT,0.34,(120,120,120),1,cv2.LINE_AA)
        if debug:
            cv2.putText(display,"[DEBUG]",(fw-80,18),FONT,0.5,(0,200,255),2)
        if _calib_mode:
            _draw_calib_overlay(display)

        cv2.imshow("Resistor Reader", display)
        key = cv2.waitKey(1) & 0xFF

        if key == ord('q'):
            break
        elif key == ord('d'):
            debug = not debug
            if not debug:
                try: cv2.destroyWindow("DEBUG - Scan")
                except: pass
            print(f"  Debug : {'ON' if debug else 'OFF'}")
        elif key == ord('c'):
            _calib_mode = not _calib_mode
            if _calib_mode:
                print("\n  ══ CALIBRATION ACTIVE ══")
                print("  Clic G = sample HSV | Clic D = effacer | C = quitter\n")
            else:
                _calib_samples.clear()
                print("  Calibration désactivée")
        elif key == ord('r'):
            cur_all=[]; cur_colours=None; cur_value=None
            cur_body=None; locked=False; analysing=False
            std_val=None; std_serie=None; std_diff=None; std_status='none'
            _calib_samples.clear()
            print("  Reset — pose la résistance dans le rectangle")
        elif key == ord('s'):
            save_crop(img)

    cam.release()
    cv2.destroyAllWindows()
    print("Terminé.")


if __name__ == "__main__":
    main()