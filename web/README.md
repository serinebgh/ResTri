# Dashboard Tri de Résistances — STM32G431 + Claude Vision

Système complet de **tri automatique de résistances** : une caméra (DroidCam = « P2 »)
filme la résistance, Claude Vision lit le code couleur, le dashboard web affiche la valeur
en temps réel et la carte **STM32G431** actionne le servo du bon bac (1 kΩ / 10 kΩ / rebut).

```
 Caméra (DroidCam) ──► vision.py (Claude API) ──► app.py (Flask+SocketIO) ──► navigateur
                                                        │
                                                        └─► serial_link.py ──► STM32G431 (servos)
```

## Arborescence

| Fichier | Rôle |
|---|---|
| `app.py` | Serveur **Flask + SocketIO** (localhost:5000), flux MJPEG, events temps réel |
| `vision.py` | Caméra + lecture résistance (Claude), confiance, catégorisation, compteurs |
| `serial_link.py` | Lien série **Python ↔ STM32** (115200 baud), envoi des ordres de tri |
| `test_serial.py` | **Test série basique** (Phase 1) |
| `templates/index.html` | Page du dashboard |
| `static/dashboard.js` / `style.css` | Front temps réel |

## Installation

```powershell
cd C:\Users\serin\Downloads\G431_base\web
pip install -r requirements.txt
```

Configurer (variables d'environnement, sinon valeurs par défaut du code) :

```powershell
$env:ANTHROPIC_API_KEY = "sk-ant-..."           # clé Claude
$env:CAMERA_URL        = "http://10.78.23.103:4747/video"   # IP DroidCam
$env:STM32_PORT        = "COM5"                  # optionnel : sinon auto-détection
```

---

## PHASE 1 — Flask + test série

**Serveur Flask sur localhost:5000 :**
```powershell
python app.py
```
Ouvre http://localhost:5000

**Test communication série Python ↔ STM32 :**
```powershell
python test_serial.py            # auto-détection du port
python test_serial.py COM5       # port forcé
```
Le test liste les ports, attend `STM32:READY`, affiche les `[tick ...]` des servos
pendant 10 s, puis envoie `SORT:1K`.

## SEMAINE 2 — Flux vidéo dans la page + WebSocket
- Flux vidéo de la caméra (P2) affiché dans `index.html` via la route MJPEG `/video_feed`.
- Structure **Flask-SocketIO** en place (`socketio` dans `app.py`, client `socket.io` dans `dashboard.js`).

## SEMAINE 3 — Dashboard complet
- ✅ **Flux vidéo annoté live** (rectangle de pose, valeur, pastilles couleur, état)
- ✅ **Valeur résistance en temps réel** (event SocketIO `detection`)
- ✅ **Compteurs par catégorie** 1 kΩ / 10 kΩ / rebut
- ✅ **Score de confiance ML** affiché (barre de progression)

---

## Mode dégradé
L'appli **démarre même sans carte ni caméra** : badges rouges, mais le serveur tourne.
- Pas de STM32 → le tri n'envoie rien (log « mode déconnecté »).
- Pas de DroidCam → image « En attente de la caméra… ».

## Chaîne complète (tout fonctionne ensemble)
1. Le téléphone (DroidCam) filme → Claude identifie la valeur.
2. `app.py` classe la résistance (1k / 10k / rebut) et envoie l'ordre à la STM32.
3. La STM32 (`app/main.c`) exécute la **séquence mécanique** :
   - **SERVO_2 (PA9)** tourne → amène le bon bac sous la trappe ;
   - **SERVO_3 (PA10)** abaisse la trappe → la résistance tombe dans le bac ;
   - la trappe se referme, puis le carrousel **revient à la position initiale**.
4. La carte renvoie `ACK:1K/10K/REJECT`, affiché dans la console du dashboard.
5. Après ~6 s (cooldown), la détection se **réarme** pour la résistance suivante.

### Protocole série (PC → STM32)
| Catégorie | Commande PC → STM32 | Réponse STM32 |
|---|---|---|
| 1 kΩ | `SORT:1K\r\n` | `ACK:1K` |
| 10 kΩ | `SORT:10K\r\n` | `ACK:10K` |
| rebut | `SORT:REJECT\r\n` | `ACK:REJECT` |
| test | `PING\r\n` | `PONG` |

### Réglages mécaniques (dans `app/main.c`)
À ajuster selon ton montage : `CARR_HOME / CARR_1K / CARR_10K / CARR_REBUT`
(angles du carrousel) et `TRAP_FERMEE / TRAP_OUVERTE` (trappe), plus les
temporisations `T_ROTATION / T_CHUTE / T_RETOUR`.
L'ancien firmware de test est sauvegardé dans `app/main_balayage.c.bak`.
