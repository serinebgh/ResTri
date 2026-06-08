"""
app.py
======
DASHBOARD DE TRI DE RÉSISTANCES — Flask + Flask-SocketIO
Tourne sur http://localhost:5000

Réunit :
  - PHASE 1   : serveur Flask + lien série STM32
  - SEMAINE 2 : flux vidéo (P2 / DroidCam) affiché dans la page HTML + WebSocket
  - SEMAINE 3 : dashboard complet
        * flux vidéo annoté live          (/video_feed, MJPEG)
        * valeur résistance temps réel    (event SocketIO "detection")
        * compteurs 1kΩ / 10kΩ / rebut    (event SocketIO "detection".counters)
        * score de confiance ML affiché   (info.confidence)

Lancer :
    pip install -r requirements.txt
    python app.py
"""

import os
from flask import Flask, render_template, Response, jsonify, request
from flask_socketio import SocketIO

from vision import ResistorSorter, CAMERA_URL, format_ohms
from serial_link import STM32Link, list_ports

# ───────────────────────── Flask / SocketIO ─────────────────────────
app      = Flask(__name__)
app.config["SECRET_KEY"] = "resistor-tri-g431"
socketio = SocketIO(app, async_mode="threading", cors_allowed_origins="*")

# ───────────────────────── Lien série STM32 ─────────────────────────
def on_stm32_line(line):
    # relaie chaque ligne reçue de la STM32 vers le navigateur
    socketio.emit("stm32", {"line": line})

stm32 = STM32Link(port=os.environ.get("STM32_PORT"), on_line=on_stm32_line)

# ═══════════════════════ CONFIGURATION DES 4 BACS ═══════════════════════
# 4 bacs espacés de 90° sur le carrousel 360°.
# value = valeur cible en ohms (None = bac "rebut" qui récupère tout le reste).
BIN_TOL_PCT = 10.0          # tolérance d'appartenance à un bac (%)

bins_config = [
    {"index": 0, "angle": 0,   "value": 1000.0,  "label": "1 kΩ",  "reject": False},
    {"index": 1, "angle": 90,  "value": 10000.0, "label": "10 kΩ", "reject": False},
    {"index": 2, "angle": 180, "value": 470.0,   "label": "470 Ω", "reject": False},
    {"index": 3, "angle": 270, "value": None,    "label": "Rebut", "reject": True},
]

def parse_ohms(txt):
    """'1k'->1000, '10k'->10000, '4.7k'->4700, '1M'->1e6, '470'->470. None si vide."""
    if txt is None:
        return None
    s = str(txt).strip().lower().replace("ω", "").replace("ohm", "").replace(" ", "")
    s = s.replace(",", ".")
    if s in ("", "rebut", "reject", "none", "-"):
        return None
    mult = 1.0
    if s.endswith("k"): mult, s = 1e3, s[:-1]
    elif s.endswith("m"): mult, s = 1e6, s[:-1]
    elif s.endswith("r"): s = s[:-1]
    try:
        return float(s) * mult
    except ValueError:
        return None

def classify(value):
    """Retourne le bac (dict) correspondant à la valeur mesurée."""
    # 1) bac dont la valeur cible correspond (à BIN_TOL_PCT près)
    best, best_diff = None, BIN_TOL_PCT
    for b in bins_config:
        if b["reject"] or not b["value"]:
            continue
        diff = abs(value - b["value"]) / b["value"] * 100.0
        if diff <= best_diff:
            best, best_diff = b, diff
    if best:
        return best
    # 2) sinon -> bac rebut
    for b in bins_config:
        if b["reject"]:
            return b
    return bins_config[-1]      # filet de sécurité

# ───────────────────────── Vision / Sorteur ─────────────────────────
def on_detection(info):
    """Appelé à chaque résistance verrouillée : push live + séquence de tri STM32."""
    socketio.emit("detection", info)
    # tourne le carrousel au bon bac, ouvre/ferme la trappe, revient à 0
    stm32.sort_sequence(info["bin_angle"])

sorter = ResistorSorter(camera_url=CAMERA_URL, on_detection=on_detection,
                        classifier=classify, n_bins=4)


# ═══════════════════════════ ROUTES HTTP ═══════════════════════════
@app.route("/")
def index():
    return render_template("index.html")


@app.route("/video_feed")
def video_feed():
    """Flux MJPEG annoté (SEMAINE 2 + 3)."""
    def gen():
        import time
        while True:
            jpeg = sorter.get_annotated_jpeg()
            yield (b"--frame\r\nContent-Type: image/jpeg\r\n\r\n" + jpeg + b"\r\n")
            time.sleep(0.05)              # ~20 fps
    return Response(gen(), mimetype="multipart/x-mixed-replace; boundary=frame")


@app.route("/api/status")
def api_status():
    return jsonify({
        "camera_connected": sorter.camera_ok(),
        "stm32_connected":  stm32.connected,
        "stm32_port":       stm32.port,
        "counters":         {str(k): v for k, v in sorter.counters.items()},
        "bins":             bins_config,
        "ports":            list_ports(),
    })


@app.route("/api/bins", methods=["GET"])
def api_get_bins():
    return jsonify({"bins": bins_config, "tol_pct": BIN_TOL_PCT})


@app.route("/api/bins", methods=["POST"])
def api_set_bins():
    """Met à jour la valeur cible de chaque bac depuis le site."""
    data = request.get_json(force=True) or {}
    for i, b in enumerate(data.get("bins", [])):
        if i >= len(bins_config):
            break
        v = parse_ohms(b.get("value"))
        reject = bool(b.get("reject")) or v is None
        bins_config[i]["value"]  = v
        bins_config[i]["reject"] = reject
        bins_config[i]["label"]  = "Rebut" if reject else format_ohms(v)
        if "angle" in b:
            bins_config[i]["angle"] = int(b["angle"])
    print("[BINS] config mise à jour :", [(b["label"], b["angle"]) for b in bins_config])
    socketio.emit("bins", {"bins": bins_config})
    return jsonify({"ok": True, "bins": bins_config})


@app.route("/api/reset", methods=["POST"])
def api_reset():
    sorter.reset_state()
    sorter.reset_counters()
    socketio.emit("counters_reset", sorter.counters)
    return jsonify({"ok": True, "counters": sorter.counters})


@app.route("/api/save", methods=["POST"])
def api_save():
    path = sorter.save_crop()
    return jsonify({"ok": path is not None, "path": path})


# ═══════════════════════════ SOCKET.IO ═══════════════════════════
@socketio.on("connect")
def on_connect():
    print("[WS] client connecté")
    socketio.emit("status", {
        "camera_connected": sorter.camera_ok(),
        "stm32_connected":  stm32.connected,
        "counters":         {str(k): v for k, v in sorter.counters.items()},
        "bins":             bins_config,
    })

@socketio.on("reset")
def ws_reset():
    sorter.reset_state()
    sorter.reset_counters()
    socketio.emit("counters_reset", sorter.counters)


# ═══════════════════════════ DÉMARRAGE ═══════════════════════════
if __name__ == "__main__":
    print("=== Dashboard Tri Résistances — STM32G431 ===")
    stm32.connect()      # tolérant : continue même sans carte
    sorter.start()       # démarre la caméra + analyse Claude
    print("  -> http://localhost:5000")
    socketio.run(app, host="0.0.0.0", port=5000,
                 debug=False, allow_unsafe_werkzeug=True)
