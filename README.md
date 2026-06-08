# ResTri — Tri automatique de résistances par vision

Projet DEEP (ESEO Vélizy, 2026). Une caméra lit le code couleurs d'une résistance,
le PC calcule la valeur (traitement HSV + validation E12/E24) et une carte
**STM32G431KB** commande des servomoteurs pour la trier dans le bon bac.

## Équipe
- **BOUGHELOUM Serine** — code de la détection (vision) ; structure mécanique
- **NKOUAKAM NGONGANG Romels** — firmware moteurs (servos, séquence de tri) ; PCB (Altium)
- **ARRIS Romane** — structure mécanique ; câblage et placement des moteurs

## Architecture
```
Caméra (DroidCam) → PC (vision + supervision web) → STM32G431 → servos → 4 bacs
```

## Contenu du dépôt
- `G431_base/app/` — firmware : `main.c` (séquence de tri), `config.h`
- `G431_base/drivers/bsp/bsp_servo.c` — PWM des servomoteurs
- `web/` — application PC : détection (`vision.py`), liaison série (`serial_link.py`),
  serveur de supervision (`app.py`), interface web

## Lancer la supervision (PC)
```bash
cd web
pip install -r requirements.txt
python app.py        # http://localhost:5000
```

## Protocole série (PC → STM32, 115200 bauds)
| Commande | Effet |
|---|---|
| `CARR:<angle>` | tourne le carrousel (0–360°) |
| `TRAP:<angle>` | place la trappe (0–180°) |
| `SORT:1K / 10K / REJECT` | cycle de tri complet |
| `PING` | test (réponse `PONG`) |
