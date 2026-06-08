"""
test_complet.py  —  TEST A -> Z de toute la chaine de tri de resistances.

Lance :  python test_complet.py

Le script verifie, dans l'ordre :
  1. les librairies Python
  2. le port serie + la carte STM32 (PING -> PONG)
  3. le mouvement de la trappe        (confirmation visuelle o/n)
  4. le mouvement du carrousel        (confirmation visuelle o/n)
  5. un cycle complet de tri SORT:1K  (confirmation visuelle o/n)
  6. la camera (DroidCam)
  7. la cle API Claude
A la fin : un recapitulatif clair de ce qui marche / ne marche pas.
"""

import os
import sys
import time

resultats = {}

def titre(n, txt):
    print("\n" + "=" * 56)
    print(f"  ETAPE {n} : {txt}")
    print("=" * 56)

def demande_oui_non(question):
    while True:
        r = input(f"   >>> {question} (o/n) : ").strip().lower()
        if r in ("o", "oui", "y"): return True
        if r in ("n", "non"):      return False

# ─────────────────────────────────────────────────────────
# ETAPE 1 : librairies
# ─────────────────────────────────────────────────────────
titre(1, "Librairies Python")
try:
    import serial, serial.tools.list_ports
    import cv2
    import numpy
    resultats["Librairies"] = True
    print("   ✅ pyserial, opencv, numpy OK")
except Exception as e:
    resultats["Librairies"] = False
    print(f"   ❌ Librairie manquante : {e}")
    print("   -> pip install -r requirements.txt")
    sys.exit(1)

# ─────────────────────────────────────────────────────────
# ETAPE 2 : port serie + STM32 (PING -> PONG)
# ─────────────────────────────────────────────────────────
titre(2, "Liaison serie PC <-> STM32")
ser = None
ports = list(serial.tools.list_ports.comports())
print("   Ports detectes :")
for p in ports:
    print(f"     {p.device} -> {p.description}")

port = None
for p in ports:
    if any(k in (p.description or "").lower() for k in ("stm", "stlink", "st-link", "cdc", "usb serial")):
        port = p.device
        break
if port is None and ports:
    port = ports[0].device

if port is None:
    resultats["STM32"] = False
    print("   ❌ Aucun port serie. Carte branchee ? Driver ST-Link installe ?")
else:
    print(f"   Port utilise : {port}")
    try:
        ser = serial.Serial(port, 115200, timeout=0.3)
        time.sleep(0.5)
        ser.reset_input_buffer()
        ser.write(b"PING\r\n")
        t = time.time(); pong = False
        while time.time() - t < 3:
            line = ser.readline().decode("utf-8", "replace").strip()
            if line:
                print(f"     [STM32] {line}")
                if "PONG" in line: pong = True
        resultats["STM32"] = pong
        print("   ✅ STM32 repond (PONG)" if pong else "   ❌ Pas de PONG (programme en pause ? mauvais port ?)")
    except Exception as e:
        resultats["STM32"] = False
        print(f"   ❌ Ouverture du port impossible : {e}")

def envoie(cmd, duree=3):
    if not ser: return
    ser.write((cmd + "\r\n").encode())
    t = time.time()
    while time.time() - t < duree:
        line = ser.readline().decode("utf-8", "replace").strip()
        if line:
            print(f"     [STM32] {line}")

# ─────────────────────────────────────────────────────────
# ETAPE 3 : trappe
# ─────────────────────────────────────────────────────────
if ser and resultats.get("STM32"):
    titre(3, "Mouvement de la TRAPPE (PA10)")
    print("   Envoi TRAP:0 ...");   envoie("TRAP:0", 2);   time.sleep(0.5)
    print("   Envoi TRAP:180 ..."); envoie("TRAP:180", 2); time.sleep(0.5)
    print("   Envoi TRAP:90 (repos) ..."); envoie("TRAP:90", 1)
    resultats["Trappe"] = demande_oui_non("La trappe a-t-elle bien bouge ?")

    # ─── ETAPE 4 : carrousel ───
    titre(4, "Mouvement du CARROUSEL (PA9, 360 deg)")
    for a in ("0", "90", "180", "270", "360"):
        print(f"   Envoi CARR:{a} ..."); envoie(f"CARR:{a}", 1)
        time.sleep(0.6)
    print("   Retour CARR:0 ..."); envoie("CARR:0", 1)
    resultats["Carrousel"] = demande_oui_non("Le carrousel a-t-il tourne aux differentes positions ?")

    # ─── ETAPE 5 : cycle complet ───
    titre(5, "Cycle complet de tri  (SORT:1K)")
    print("   Le carrousel doit aller a 90, la trappe s'abaisser puis remonter, retour a 0.")
    envoie("SORT:1K", 5)
    resultats["Cycle tri"] = demande_oui_non("Le cycle complet s'est-il bien deroule ?")
else:
    print("\n   (Etapes 3-5 servos ignorees : pas de liaison STM32)")
    resultats["Trappe"] = resultats["Carrousel"] = resultats["Cycle tri"] = False

if ser:
    ser.close()

# ─────────────────────────────────────────────────────────
# ETAPE 6 : camera
# ─────────────────────────────────────────────────────────
titre(6, "Camera (DroidCam)")
cam_url = os.environ.get("CAMERA_URL", "http://10.78.23.48:4747/video")
print(f"   URL camera : {cam_url}")
print("   (definir $env:CAMERA_URL = \"http://IP_TEL:4747/video\" si besoin)")
try:
    cap = cv2.VideoCapture(cam_url)
    ok = False
    t = time.time()
    while time.time() - t < 5:
        ret, frame = cap.read()
        if ret and frame is not None:
            ok = True; break
    cap.release()
    resultats["Camera"] = ok
    print("   ✅ Image recue de la camera" if ok else "   ❌ Pas d'image (DroidCam lance ? bonne IP ? meme reseau Wi-Fi ?)")
except Exception as e:
    resultats["Camera"] = False
    print(f"   ❌ Erreur camera : {e}")

# ─────────────────────────────────────────────────────────
# ETAPE 7 : cle API Claude
# ─────────────────────────────────────────────────────────
titre(7, "Cle API Claude")
key = os.environ.get("ANTHROPIC_API_KEY", "")
try:
    import vision
    if not key:
        key = getattr(vision, "ANTHROPIC_API_KEY", "")
except Exception:
    pass
if key and key.startswith("sk-ant-"):
    resultats["Cle Claude"] = True
    print(f"   ✅ Cle presente ({key[:14]}...)")
else:
    resultats["Cle Claude"] = False
    print("   ❌ Cle API absente -> $env:ANTHROPIC_API_KEY = \"sk-ant-...\"")

# ─────────────────────────────────────────────────────────
# RECAP
# ─────────────────────────────────────────────────────────
print("\n" + "#" * 56)
print("  RECAPITULATIF")
print("#" * 56)
for k, v in resultats.items():
    print(f"   {'✅' if v else '❌'}  {k}")
tout = all(resultats.values())
print("\n  " + ("🎉 TOUT FONCTIONNE -> lance : python app.py" if tout
                else "⚠️  Corrige les ❌ ci-dessus, puis relance ce test."))
print("#" * 56)
