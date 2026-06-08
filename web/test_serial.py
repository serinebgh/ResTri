"""
test_serial.py
==============
PHASE 1 — Test de communication série Python <-> STM32 basique.

Ce script :
  1. liste les ports série disponibles,
  2. se connecte à la STM32 (auto-détection ou port forcé),
  3. attend le message "STM32:READY" envoyé par le firmware au démarrage,
  4. affiche pendant 10 s toutes les lignes reçues (les [tick ...] des servos),
  5. envoie une commande de test SORT:1K.

Lance :
    python test_serial.py
    python test_serial.py COM5        (pour forcer un port)
"""

import sys
import time
from serial_link import STM32Link, list_ports


def main():
    forced_port = sys.argv[1] if len(sys.argv) > 1 else None

    print("=== Ports série détectés ===")
    ports = list_ports()
    if not ports:
        print("  (aucun)  -> branche la carte / installe pyserial")
    for dev, desc in ports:
        print(f"  {dev:10s} {desc}")
    print()

    got_ready = {"ok": False}

    def on_line(line):
        if "READY" in line.upper():
            got_ready["ok"] = True

    link = STM32Link(port=forced_port, on_line=on_line)
    if not link.connect():
        print("[TEST] Connexion échouée. Vérifie le câble USB et le port.")
        return

    print("[TEST] En attente de 'STM32:READY' (reset la carte si besoin)...")
    t0 = time.time()
    while time.time() - t0 < 6 and not got_ready["ok"]:
        time.sleep(0.1)

    if got_ready["ok"]:
        print("[TEST] ✅ STM32:READY reçu — communication OK !\n")
    else:
        print("[TEST] ⚠️  Pas de READY (la carte tourne peut-être déjà). On continue.\n")

    print("[TEST] Écoute des messages pendant 10 s...")
    time.sleep(10)

    print("\n[TEST] Envoi d'une commande de test : SORT:1K")
    link.sort("1k")
    time.sleep(1)

    link.close()
    print("[TEST] Terminé.")


if __name__ == "__main__":
    main()
