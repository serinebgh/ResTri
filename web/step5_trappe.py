"""Test isole de la TRAPPE (PA10) vs CARROUSEL (PA9)."""
import serial, time

s = serial.Serial("COM3", 115200, timeout=0.3)
time.sleep(0.5); s.reset_input_buffer()

def cmd(c, w=2.0):
    print(f"\n>>> {c}")
    s.write((c + "\r\n").encode())
    t = time.time()
    while time.time() - t < w:
        line = s.readline()
        if line:
            print("    [STM32]", line.decode("utf-8", "replace").strip())

print("--- CARROUSEL (PA9) : doit bouger ---")
cmd("CARR:0"); cmd("CARR:180"); cmd("CARR:0")

print("\n--- TRAPPE (PA10) : doit bouger ---")
cmd("TRAP:0"); cmd("TRAP:180"); cmd("TRAP:90")

s.close()
print("\nFini.")
