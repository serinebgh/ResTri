"""
calibrator.py — Outil de calibration HSV pour TRI_VISION
=========================================================
Usage : python calibrator.py

Workflow :
  1. Lance la caméra DroidCam
  2. Clique sur une bande de couleur dans l'image → sample HSV
  3. Clique sur le bouton de la couleur correspondante → assigne les samples
  4. Répète pour chaque couleur
  5. Clique "💾 Mettre à jour vision_opt.py" → écrit les nouvelles plages

Les plages sont calculées automatiquement :
  lo = (min_H - marge, min_S - marge, min_V - marge)
  hi = (max_H + marge, max_S + marge, max_V + marge)
avec marge configurable par slider.
"""

import cv2
import numpy as np
import threading
import tkinter as tk
from tkinter import ttk, messagebox, scrolledtext
import re
import os
import sys

# ═══════════════════════════════════════════════════
#  CONFIG
# ═══════════════════════════════════════════════════
CAMERA_URL  = "http://10.78.23.57:4747/video"
TARGET_FILE = "vision.py"   # fichier à mettre à jour
RESIZE_W    = 640
RESIZE_H    = 360
SAMPLE_R    = 4   # rayon de sampling (pixels autour du clic)

# Couleurs gérées q— (nom, valeur_résistance, couleur_UI_hex, bgr_display)
COLOUR_DEFS = [
    ("BLACK",  0,   "#2a2a2a",   (40,  40,  40)),
    ("BROWN",  1,   "#7B3F00",   (0,   60,  160)),
    ("RED",    2,   "#cc0000",   (0,   0,   220)),
    ("ORANGE", 3,   "#FF8C00",   (0,  120,  255)),
    ("YELLOW", 4,   "#cccc00",   (0,  210,  210)),
    ("GREEN",  5,   "#006600",   (0,  180,   50)),
    ("BLUE",   6,   "#0000cc",   (200, 30,    0)),
    ("PURPLE", 7,   "#660066",   (170,  0,  140)),
    ("GRAY",   8,   "#808080",   (120, 120,  120)),
    ("WHITE",  9,   "#dddddd",   (220, 220,  200)),
    ("GOLD",  -1,   "#B8860B",   (0,  180,  215)),
    ("SILVER",-1,   "#999999",   (192, 192,  192)),
]
COLOUR_NAMES = [d[0] for d in COLOUR_DEFS]
BODY_COLOURS = {"GRAY", "WHITE"}

# Marges HSV appliquées autour des valeurs mesurées
DEFAULT_MARGIN_H = 6
DEFAULT_MARGIN_S = 30
DEFAULT_MARGIN_V = 30


# ═══════════════════════════════════════════════════
#  CAMERA THREAD
# ═══════════════════════════════════════════════════
class CameraStream:
    def __init__(self, url):
        self.cap     = cv2.VideoCapture(url)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.frame   = None
        self.lock    = threading.Lock()
        self.running = True
        self.thread  = threading.Thread(target=self._run, daemon=True)
        self.thread.start()

    def _run(self):
        while self.running:
            ok, f = self.cap.read()
            if ok:
                with self.lock:
                    self.frame = f

    def read(self):
        with self.lock:
            return (True, self.frame.copy()) if self.frame is not None else (False, None)

    def isOpened(self):
        return self.cap.isOpened()

    def release(self):
        self.running = False
        self.thread.join(timeout=1)
        self.cap.release()


# ═══════════════════════════════════════════════════
#  PRÉTRAITEMENT (identique à vision_opt)
# ═══════════════════════════════════════════════════
def preprocess(img):
    img_f = img.astype(np.float32)
    for c in range(3):
        ref = np.percentile(img_f[:, :, c], 95)
        if ref > 1:
            img_f[:, :, c] = np.clip(img_f[:, :, c] * (255.0 / ref), 0, 255)
    img = img_f.astype(np.uint8)
    lab = cv2.cvtColor(img, cv2.COLOR_BGR2LAB)
    clahe = cv2.createCLAHE(clipLimit=2.0, tileGridSize=(4, 4))
    lab[:, :, 0] = clahe.apply(lab[:, :, 0])
    img = cv2.cvtColor(lab, cv2.COLOR_LAB2BGR)
    bil = cv2.bilateralFilter(img, 7, 75, 75)
    hsv = cv2.cvtColor(bil, cv2.COLOR_BGR2HSV)
    return bil, hsv


# ═══════════════════════════════════════════════════
#  CALCUL DES PLAGES HSV
# ═══════════════════════════════════════════════════
def compute_range(samples, margin_h, margin_s, margin_v):
    """
    Calcule lo/hi HSV depuis une liste de (H, S, V).
    Gère le wrap-around de la teinte (ex. rouge : 170–10).
    """
    if not samples:
        return None, None
    hs = [s[0] for s in samples]
    ss = [s[1] for s in samples]
    vs = [s[2] for s in samples]

    # Wrap-around H : si écart > 90, on est probablement sur le rouge (0/180)
    h_range = max(hs) - min(hs)
    if h_range > 90:
        # Décaler les H < 90 de +180 pour calculer min/max correctement
        hs_adj = [h + 180 if h < 90 else h for h in hs]
        h_lo = (min(hs_adj) - margin_h) % 180
        h_hi = (max(hs_adj) + margin_h) % 180
    else:
        h_lo = max(0,   min(hs) - margin_h)
        h_hi = min(179, max(hs) + margin_h)

    s_lo = max(0,   min(ss) - margin_s)
    s_hi = min(255, max(ss) + margin_s)
    v_lo = max(0,   min(vs) - margin_v)
    v_hi = min(255, max(vs) + margin_v)

    return (h_lo, s_lo, v_lo), (h_hi, s_hi, v_hi)


def build_colour_ranges(calibration, margin_h, margin_s, margin_v, existing_ranges):
    """
    Reconstruit COLOUR_RANGES en remplaçant uniquement les couleurs calibrées.
    Les couleurs non calibrées gardent leurs anciennes plages.
    Retourne la liste et un texte formaté prêt pour le code Python.
    """
    # Index des plages existantes par nom
    old_by_name = {}
    for entry in existing_ranges:
        name = entry[0]
        old_by_name.setdefault(name, []).append(entry)

    new_ranges = []
    for (cname, cval, _, cbgr) in COLOUR_DEFS:
        samples = calibration.get(cname, [])
        if samples:
            lo, hi = compute_range(samples, margin_h, margin_s, margin_v)
            if lo is not None:
                new_ranges.append((cname, lo, hi, cval, cbgr))
        else:
            # Garder les anciennes plages pour cette couleur
            for old in old_by_name.get(cname, []):
                new_ranges.append(old)

    return new_ranges


def format_ranges_code(new_ranges):
    """Formate la liste COLOUR_RANGES en code Python."""
    lines = ["COLOUR_RANGES = [\n"]
    for (name, lo, hi, val, bgr) in new_ranges:
        lines.append(
            f'    ("{name:<6}", {str(lo):<18}, {str(hi):<18}, '
            f'{str(val):>3},  {str(bgr)}),\n'
        )
    lines.append("]")
    return "".join(lines)


# ═══════════════════════════════════════════════════
#  MISE À JOUR DU FICHIER CIBLE
# ═══════════════════════════════════════════════════
def parse_existing_ranges(filepath):
    """Lit COLOUR_RANGES depuis le fichier cible."""
    try:
        with open(filepath, "r", encoding="utf-8") as f:
            content = f.read()
        # Extraire le bloc COLOUR_RANGES
        pattern = r'COLOUR_RANGES\s*=\s*\[(.*?)\]'
        match   = re.search(pattern, content, re.DOTALL)
        if not match:
            return []
        block = match.group(1)
        # Parser chaque ligne
        entry_pat = re.compile(
            r'\(\s*"(\w+)"\s*,\s*'
            r'\(([^)]+)\)\s*,\s*'
            r'\(([^)]+)\)\s*,\s*'
            r'(-?\d+)\s*,\s*'
            r'\(([^)]+)\)\s*\)'
        )
        ranges = []
        for m in entry_pat.finditer(block):
            name = m.group(1)
            lo   = tuple(int(x) for x in m.group(2).split(","))
            hi   = tuple(int(x) for x in m.group(3).split(","))
            val  = int(m.group(4))
            bgr  = tuple(int(x) for x in m.group(5).split(","))
            ranges.append((name, lo, hi, val, bgr))
        return ranges
    except Exception as e:
        return []


def update_file(filepath, new_ranges):
    """Remplace le bloc COLOUR_RANGES dans le fichier cible."""
    if not os.path.exists(filepath):
        return False, f"Fichier introuvable : {filepath}"
    with open(filepath, "r", encoding="utf-8") as f:
        content = f.read()

    new_code = format_ranges_code(new_ranges)
    pattern  = r'COLOUR_RANGES\s*=\s*\[.*?\]'
    new_content, n = re.subn(pattern, new_code, content, flags=re.DOTALL)
    if n == 0:
        return False, "Bloc COLOUR_RANGES introuvable dans le fichier"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(new_content)
    return True, f"✅ {filepath} mis à jour ({len(new_ranges)} plages)"


# ═══════════════════════════════════════════════════
#  APPLICATION TKINTER
# ═══════════════════════════════════════════════════
class CalibApp:
    def __init__(self, root):
        self.root       = root
        self.root.title("🎨 Calibrateur HSV — TRI_VISION")
        self.root.configure(bg="#1e1e2e")
        self.root.resizable(True, True)

        # État
        self.cam           = None
        self.running       = False
        self.current_hsv   = None          # image HSV courante
        self.current_bgr   = None          # image BGR courante (pour affichage)
        self.pending        = []           # samples cliqués non encore assignés
        self.calibration    = {n: [] for n in COLOUR_NAMES}  # couleur → [(H,S,V)]
        self.selected_colour= tk.StringVar(value="BLACK")
        self.margin_h       = tk.IntVar(value=DEFAULT_MARGIN_H)
        self.margin_s       = tk.IntVar(value=DEFAULT_MARGIN_S)
        self.margin_v       = tk.IntVar(value=DEFAULT_MARGIN_V)
        self.target_file    = tk.StringVar(value=TARGET_FILE)
        self.status_var     = tk.StringVar(value="Déconnecté")
        self.camera_url     = tk.StringVar(value=CAMERA_URL)

        self._build_ui()
        self._update_loop()

    # ──────────────────────────────────────────────
    #  UI
    # ──────────────────────────────────────────────
    def _build_ui(self):
        root = self.root
        PAD  = dict(padx=6, pady=4)

        # ── Barre du haut : URL + connexion ──────────
        top = tk.Frame(root, bg="#1e1e2e")
        top.pack(fill="x", padx=8, pady=(8, 0))

        tk.Label(top, text="Caméra URL :", bg="#1e1e2e", fg="#cdd6f4",
                 font=("Consolas", 9)).pack(side="left")
        tk.Entry(top, textvariable=self.camera_url, width=36,
                 bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4",
                 relief="flat", font=("Consolas", 9)).pack(side="left", padx=4)
        tk.Button(top, text="▶ Connecter", command=self._connect,
                  bg="#a6e3a1", fg="#1e1e2e", font=("Consolas", 9, "bold"),
                  relief="flat", padx=8).pack(side="left", padx=4)
        tk.Button(top, text="⏹ Déconnecter", command=self._disconnect,
                  bg="#f38ba8", fg="#1e1e2e", font=("Consolas", 9, "bold"),
                  relief="flat", padx=8).pack(side="left", padx=2)

        tk.Label(top, textvariable=self.status_var, bg="#1e1e2e", fg="#89b4fa",
                 font=("Consolas", 9)).pack(side="right", padx=8)

        # ── Zone centrale : vidéo + panneau droit ────
        mid = tk.Frame(root, bg="#1e1e2e")
        mid.pack(fill="both", expand=True, padx=8, pady=6)

        # Canvas vidéo
        self.canvas = tk.Canvas(mid, width=RESIZE_W, height=RESIZE_H,
                                 bg="#11111b", cursor="crosshair",
                                 highlightthickness=1, highlightbackground="#585b70")
        self.canvas.pack(side="left", fill="both", expand=True)
        self.canvas.bind("<Button-1>", self._on_click)

        # Panneau droite
        right = tk.Frame(mid, bg="#181825", width=260)
        right.pack(side="right", fill="y", padx=(8, 0))
        right.pack_propagate(False)

        # ── Section : Samples en attente ──────────────
        tk.Label(right, text="① Clique sur la bande",
                 bg="#181825", fg="#89dceb",
                 font=("Consolas", 9, "bold")).pack(anchor="w", **PAD)

        self.pending_listbox = tk.Listbox(
            right, height=4, bg="#313244", fg="#cdd6f4",
            selectbackground="#45475a", font=("Consolas", 8),
            relief="flat", borderwidth=0)
        self.pending_listbox.pack(fill="x", padx=6)

        tk.Button(right, text="✖ Effacer samples",
                  command=self._clear_pending,
                  bg="#45475a", fg="#cdd6f4", font=("Consolas", 8),
                  relief="flat").pack(fill="x", padx=6, pady=2)

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=6, padx=6)

        # ── Section : Choix couleur + assign ─────────
        tk.Label(right, text="② Assigne à la couleur :",
                 bg="#181825", fg="#89dceb",
                 font=("Consolas", 9, "bold")).pack(anchor="w", **PAD)

        colours_frame = tk.Frame(right, bg="#181825")
        colours_frame.pack(fill="x", padx=6)

        for i, (cname, cval, hex_col, _) in enumerate(COLOUR_DEFS):
            r, c = divmod(i, 3)
            fg = "#000000" if cname in ("YELLOW", "WHITE", "GOLD", "SILVER") else "#ffffff"
            btn = tk.Radiobutton(
                colours_frame, text=cname,
                variable=self.selected_colour, value=cname,
                bg=hex_col, fg=fg, selectcolor=hex_col,
                activebackground=hex_col, activeforeground=fg,
                font=("Consolas", 8, "bold"), relief="flat",
                indicatoron=False, padx=4, pady=2,
                bd=2
            )
            btn.grid(row=r, column=c, padx=2, pady=2, sticky="ew")
        for col in range(3):
            colours_frame.columnconfigure(col, weight=1)

        tk.Button(right, text="✅ Assigner les samples",
                  command=self._assign_samples,
                  bg="#cba6f7", fg="#1e1e2e",
                  font=("Consolas", 9, "bold"), relief="flat"
                  ).pack(fill="x", padx=6, pady=(6, 2))

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=6, padx=6)

        # ── Section : Marges ─────────────────────────
        tk.Label(right, text="③ Marges HSV :",
                 bg="#181825", fg="#89dceb",
                 font=("Consolas", 9, "bold")).pack(anchor="w", **PAD)

        for label, var, lo, hi in [
            ("± H (teinte)", self.margin_h, 0, 30),
            ("± S (saturation)", self.margin_s, 0, 80),
            ("± V (luminosité)", self.margin_v, 0, 80),
        ]:
            row = tk.Frame(right, bg="#181825")
            row.pack(fill="x", padx=6, pady=1)
            tk.Label(row, text=label, bg="#181825", fg="#bac2de",
                     font=("Consolas", 8), width=16, anchor="w").pack(side="left")
            tk.Scale(row, variable=var, from_=lo, to=hi,
                     orient="horizontal", bg="#181825", fg="#cdd6f4",
                     troughcolor="#313244", highlightthickness=0,
                     length=100, showvalue=True, font=("Consolas", 7)
                     ).pack(side="left", fill="x", expand=True)

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=6, padx=6)

        # ── Section : État de la calibration ─────────
        tk.Label(right, text="État de la calibration :",
                 bg="#181825", fg="#89dceb",
                 font=("Consolas", 9, "bold")).pack(anchor="w", **PAD)

        self.calib_status_frame = tk.Frame(right, bg="#181825")
        self.calib_status_frame.pack(fill="x", padx=6)
        self._status_labels = {}
        for i, (cname, _, hex_col, _) in enumerate(COLOUR_DEFS):
            r, c = divmod(i, 2)
            fg_col = "#000" if cname in ("YELLOW", "WHITE", "GOLD", "SILVER") else "#fff"
            lbl = tk.Label(
                self.calib_status_frame,
                text=f"{cname}: 0 pts",
                bg="#313244", fg="#585b70",
                font=("Consolas", 7), relief="flat", padx=3, pady=1
            )
            lbl.grid(row=r, column=c, padx=2, pady=1, sticky="ew")
            self._status_labels[cname] = lbl
        for c in range(2):
            self.calib_status_frame.columnconfigure(c, weight=1)

        tk.Button(right, text="🗑 Réinitialiser calibration",
                  command=self._reset_calib,
                  bg="#45475a", fg="#cdd6f4",
                  font=("Consolas", 8), relief="flat"
                  ).pack(fill="x", padx=6, pady=(6, 2))

        ttk.Separator(right, orient="horizontal").pack(fill="x", pady=6, padx=6)

        # ── Section : Fichier cible + export ─────────
        tk.Label(right, text="④ Mettre à jour le fichier :",
                 bg="#181825", fg="#89dceb",
                 font=("Consolas", 9, "bold")).pack(anchor="w", **PAD)

        file_row = tk.Frame(right, bg="#181825")
        file_row.pack(fill="x", padx=6, pady=2)
        tk.Entry(file_row, textvariable=self.target_file,
                 bg="#313244", fg="#cdd6f4", insertbackground="#cdd6f4",
                 font=("Consolas", 8), relief="flat").pack(fill="x")

        tk.Button(right, text="👁 Prévisualiser les plages",
                  command=self._preview,
                  bg="#89b4fa", fg="#1e1e2e",
                  font=("Consolas", 9, "bold"), relief="flat"
                  ).pack(fill="x", padx=6, pady=2)

        tk.Button(right, text="💾 Mettre à jour vision_opt.py",
                  command=self._write_file,
                  bg="#a6e3a1", fg="#1e1e2e",
                  font=("Consolas", 10, "bold"), relief="flat"
                  ).pack(fill="x", padx=6, pady=4)

        # ── Console bas ───────────────────────────────
        bot = tk.Frame(root, bg="#1e1e2e")
        bot.pack(fill="x", padx=8, pady=(0, 6))

        self.console = scrolledtext.ScrolledText(
            bot, height=5, bg="#11111b", fg="#a6e3a1",
            font=("Consolas", 8), relief="flat",
            insertbackground="#a6e3a1", state="disabled"
        )
        self.console.pack(fill="x")

        # ── Barre de statut bas ───────────────────────
        status_bar = tk.Frame(root, bg="#313244")
        status_bar.pack(fill="x")
        tk.Label(status_bar,
                 text="Clic G sur image = sampler pixel   |   Assigne la couleur   |   Exporte dans vision_opt.py",
                 bg="#313244", fg="#6c7086", font=("Consolas", 8)
                 ).pack(side="left", padx=8)

    # ──────────────────────────────────────────────
    #  CONNEXION CAMÉRA
    # ──────────────────────────────────────────────
    def _connect(self):
        if self.cam:
            self.cam.release()
        url = self.camera_url.get().strip()
        self._log(f"Connexion à {url} …")
        self.cam     = CameraStream(url)
        self.running = True
        self.status_var.set(f"⏳ Connexion…")

    def _disconnect(self):
        self.running = False
        if self.cam:
            self.cam.release()
            self.cam = None
        self.status_var.set("Déconnecté")
        self._log("Caméra déconnectée")

    # ──────────────────────────────────────────────
    #  BOUCLE VIDÉO
    # ──────────────────────────────────────────────
    def _update_loop(self):
        if self.running and self.cam:
            ok, frame = self.cam.read()
            if ok and frame is not None:
                self.status_var.set("🟢 Caméra active")
                img  = cv2.resize(frame, (RESIZE_W, RESIZE_H))
                bil, hsv = preprocess(img)
                self.current_hsv = hsv
                self.current_bgr = bil

                display = bil.copy()
                self._draw_pending_on(display)
                self._draw_calib_dots_on(display)

                # Afficher sur le canvas tkinter
                rgb   = cv2.cvtColor(display, cv2.COLOR_BGR2RGB)
                from PIL import Image, ImageTk
                pil   = Image.fromarray(rgb)
                self._tk_img = ImageTk.PhotoImage(pil)
                self.canvas.create_image(0, 0, anchor="nw", image=self._tk_img)
            elif self.cam and not self.cam.isOpened():
                self.status_var.set("❌ Caméra inaccessible")

        self.root.after(33, self._update_loop)   # ~30 fps

    def _draw_pending_on(self, img):
        for (h, s, v, px, py) in self.pending:
            cv2.drawMarker(img, (px, py), (255, 255, 255), cv2.MARKER_CROSS, 12, 1)
            cv2.drawMarker(img, (px, py), (0, 200, 255),  cv2.MARKER_CROSS, 8, 2)

    def _draw_calib_dots_on(self, img):
        """Affiche un petit indicateur de couleur pour les samples déjà assignés."""
        dot_y = 10
        for cname, _, hex_col, bgr in COLOUR_DEFS:
            n = len(self.calibration[cname])
            if n > 0:
                cv2.circle(img, (dot_y, 10), 6, bgr, -1)
                cv2.putText(img, str(n), (dot_y - 3, 14),
                            cv2.FONT_HERSHEY_SIMPLEX, 0.3, (255,255,255), 1)
            dot_y += 18

    # ──────────────────────────────────────────────
    #  GESTION DES CLICKS
    # ──────────────────────────────────────────────
    def _on_click(self, event):
        if self.current_hsv is None:
            self._log("⚠ Pas d'image caméra — connecte la caméra d'abord")
            return
        x, y = event.x, event.y
        x = max(0, min(x, RESIZE_W - 1))
        y = max(0, min(y, RESIZE_H - 1))

        r     = SAMPLE_R
        patch = self.current_hsv[
            max(0, y-r) : min(RESIZE_H-1, y+r) + 1,
            max(0, x-r) : min(RESIZE_W-1, x+r) + 1,
        ]
        h_val = int(np.median(patch[:, :, 0]))
        s_val = int(np.median(patch[:, :, 1]))
        v_val = int(np.median(patch[:, :, 2]))

        self.pending.append((h_val, s_val, v_val, x, y))
        self.pending_listbox.insert("end", f"  H={h_val:3d}  S={s_val:3d}  V={v_val:3d}")
        self._log(f"Sample ({x},{y}) → H={h_val}  S={s_val}  V={v_val}")

    def _clear_pending(self):
        self.pending.clear()
        self.pending_listbox.delete(0, "end")
        self._log("Samples en attente effacés")

    # ──────────────────────────────────────────────
    #  ASSIGNATION
    # ──────────────────────────────────────────────
    def _assign_samples(self):
        if not self.pending:
            self._log("⚠ Aucun sample à assigner — clique sur la bande d'abord")
            return
        cname = self.selected_colour.get()
        pts   = [(h, s, v) for h, s, v, _, _ in self.pending]
        self.calibration[cname].extend(pts)
        n = len(self.calibration[cname])
        self._log(f"✅ {len(pts)} sample(s) assignés à {cname}  (total: {n} pts)")
        self._clear_pending()
        self._refresh_status_labels()

    def _reset_calib(self):
        for k in self.calibration:
            self.calibration[k].clear()
        self._refresh_status_labels()
        self._log("🗑 Calibration réinitialisée")

    def _refresh_status_labels(self):
        for cname, _, hex_col, _ in COLOUR_DEFS:
            n   = len(self.calibration[cname])
            lbl = self._status_labels[cname]
            if n > 0:
                fg_col = "#000" if cname in ("YELLOW", "WHITE", "GOLD", "SILVER") else "#fff"
                lbl.config(text=f"{cname}: {n} pts",
                           bg=hex_col, fg=fg_col)
            else:
                lbl.config(text=f"{cname}: 0 pts",
                           bg="#313244", fg="#585b70")

    # ──────────────────────────────────────────────
    #  PRÉVISUALISATION
    # ──────────────────────────────────────────────
    def _preview(self):
        mh = self.margin_h.get()
        ms = self.margin_s.get()
        mv = self.margin_v.get()
        fp = self.target_file.get().strip()

        existing = parse_existing_ranges(fp)
        new_ranges = build_colour_ranges(self.calibration, mh, ms, mv, existing)
        code = format_ranges_code(new_ranges)

        win = tk.Toplevel(self.root)
        win.title("Prévisualisation COLOUR_RANGES")
        win.configure(bg="#1e1e2e")
        txt = scrolledtext.ScrolledText(win, width=72, height=28,
                                        bg="#11111b", fg="#a6e3a1",
                                        font=("Consolas", 9))
        txt.pack(padx=8, pady=8)
        txt.insert("1.0", code)
        txt.config(state="disabled")

        # Tableau récap des plages calculées
        for cname in COLOUR_NAMES:
            pts = self.calibration[cname]
            if pts:
                lo, hi = compute_range(pts, mh, ms, mv)
                self._log(f"  {cname:<7}: lo={lo}  hi={hi}  ({len(pts)} pts)")

    # ──────────────────────────────────────────────
    #  ÉCRITURE FICHIER
    # ──────────────────────────────────────────────
    def _write_file(self):
        calibrated = [k for k, v in self.calibration.items() if v]
        if not calibrated:
            messagebox.showwarning("Calibration vide",
                                   "Aucune couleur n'a été calibrée.\n"
                                   "Clique sur des pixels et assigne-les d'abord.")
            return

        fp  = self.target_file.get().strip()
        mh  = self.margin_h.get()
        ms  = self.margin_s.get()
        mv  = self.margin_v.get()

        existing   = parse_existing_ranges(fp)
        new_ranges = build_colour_ranges(self.calibration, mh, ms, mv, existing)

        ok, msg = update_file(fp, new_ranges)
        if ok:
            self._log(msg)
            messagebox.showinfo("Succès", msg)
        else:
            self._log(f"❌ Erreur : {msg}")
            messagebox.showerror("Erreur", msg)

    # ──────────────────────────────────────────────
    #  CONSOLE
    # ──────────────────────────────────────────────
    def _log(self, msg):
        self.console.config(state="normal")
        self.console.insert("end", msg + "\n")
        self.console.see("end")
        self.console.config(state="disabled")

    # ──────────────────────────────────────────────
    #  FERMETURE
    # ──────────────────────────────────────────────
    def on_close(self):
        self._disconnect()
        self.root.destroy()


# ═══════════════════════════════════════════════════
#  ENTRY POINT
# ═══════════════════════════════════════════════════
def main():
    try:
        from PIL import Image, ImageTk
    except ImportError:
        print("⚠ Pillow manquant — installe-le : pip install Pillow")
        sys.exit(1)

    root = tk.Tk()
    app  = CalibApp(root)
    root.protocol("WM_DELETE_WINDOW", app.on_close)
    root.mainloop()


if __name__ == "__main__":
    main()