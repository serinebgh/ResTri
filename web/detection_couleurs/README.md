# Détection des résistances par couleurs (HSV) — sans Claude

Version de la détection qui lit les bandes **uniquement par traitement d'image local
(espace HSV)**, sans appel à une API externe.

## Fichiers
| Fichier | Rôle |
|---|---|
| **`vision.py`** | Interface de tri (caméra en direct, scan de la zone, lecture des bandes par couleurs, validation E12/E24). `USE_CLAUDE_API = False`. |
| **`resistor_API.py`** | Conversion couleurs → valeur (chiffres + multiplicateur + tolérance), grille E12/E24. |
| **`calibrator.py`** | Outil de calibration des plages de couleurs selon l'éclairage. |

## Lancer
```bash
pip install opencv-python numpy
python vision.py
```
> Adapter l'adresse de la caméra (DroidCam) en haut de `vision.py` :
> `CAMERA_URL = "http://<IP_DU_TELEPHONE>:4747/video"`

## Commandes dans la fenêtre
`S` sauvegarder · `D` debug · `C` calibration · `R` reset · `Q` quitter

## Lien avec le reste du projet
- **Moteurs** : le tri est exécuté par la carte STM32 (`../../G431_base/app/main.c`),
  pilotée depuis le PC via `../serial_link.py`.
- **Supervision web** : `../app.py` (version dashboard).
