"""
Etape 4 : reglage des angles EN DIRECT (sans reflasher).

Tape une commande puis Entree :
    TRAP:0      -> met la trappe a 0 deg
    TRAP:90     -> met la trappe a 90 deg
    CARR:180    -> met le carrousel a 180 deg
    SORT:1K     -> joue le cycle complet de tri 1k
    q           -> quitter

Le but : trouver l'angle TRAPPE FERMEE (retient la resistance)
et l'angle TRAPPE OUVERTE (la resistance tombe), puis les 3
angles du carrousel (1k / 10k / rebut).
"""
import serial, threading, time

PORT = "COM3"
s = serial.Serial(PORT, 115200, timeout=0.2)

def lecteur():
    while True:
        line = s.readline()
        if line:
            print("   [STM32]", line.decode("utf-8", errors="replace").strip())

threading.Thread(target=lecteur, daemon=True).start()
time.sleep(0.3)

print("=== Reglage des angles ===")
print("Exemples : TRAP:0  | TRAP:90  | CARR:90  | CARR:180  | CARR:270  | SORT:1K  | q")
while True:
    cmd = input("angle> ").strip()
    if cmd.lower() in ("q", "quit", "exit"):
        break
    if cmd:
        s.write((cmd + "\r\n").encode())
        time.sleep(0.2)

s.close()
print("Fin du reglage.")
