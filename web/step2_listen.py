"""Etape 2 : ecoute le port COM3 pendant 8 s pour capter STM32:READY."""
import serial, time

PORT = "COM3"
s = serial.Serial(PORT, 115200, timeout=0.3)
print(f"Ecoute de {PORT} pendant 8 s...  >>> APPUIE SUR LE BOUTON RESET de la carte <<<")
t = time.time()
while time.time() - t < 8:
    line = s.readline()
    if line:
        print("  [STM32]", line.decode("utf-8", errors="replace").strip())
s.close()
print("Fin de l'ecoute.")
