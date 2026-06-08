"""Etape 3 : envoie des commandes a la carte et affiche les reponses."""
import serial, time

PORT = "COM3"
s = serial.Serial(PORT, 115200, timeout=0.3)
time.sleep(0.5)
s.reset_input_buffer()

def envoie_et_ecoute(cmd, duree=3):
    print(f"\n>>> ENVOI : {cmd.strip()}")
    s.write(cmd.encode())
    t = time.time()
    while time.time() - t < duree:
        line = s.readline()
        if line:
            print("    [STM32]", line.decode("utf-8", errors="replace").strip())

# 1) test simple aller-retour
envoie_et_ecoute("PING\r\n", duree=2)

# 2) commande de tri 1k -> le carrousel doit tourner a 90 deg + trappe
envoie_et_ecoute("SORT:1K\r\n", duree=4)

s.close()
print("\nFin du test.")
