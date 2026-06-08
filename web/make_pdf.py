# -*- coding: utf-8 -*-
"""Genere un PDF de documentation du projet ResTri (detection HSV + E12/E24)."""
import os
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, ListFlowable, ListItem)
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

# ---- Police Unicode (Ω, accents, °) ----
FONT, FONT_B = "Helvetica", "Helvetica-Bold"
try:
    pdfmetrics.registerFont(TTFont("Body",      r"C:\Windows\Fonts\arial.ttf"))
    pdfmetrics.registerFont(TTFont("Body-Bold", r"C:\Windows\Fonts\arialbd.ttf"))
    FONT, FONT_B = "Body", "Body-Bold"
except Exception:
    pass

GREEN = colors.HexColor("#10a37f")
DARK  = colors.HexColor("#0d0d0d")
GREY  = colors.HexColor("#6e6e80")
LGREY = colors.HexColor("#f4f4f5")
BORD  = colors.HexColor("#e0e0e4")

styles = getSampleStyleSheet()
def S(name, **kw):
    base = kw.pop("parent", styles["Normal"])
    return ParagraphStyle(name, parent=base, fontName=kw.pop("font", FONT), **kw)

st_title = S("t", font=FONT_B, fontSize=26, textColor=DARK, leading=30, spaceAfter=4)
st_sub   = S("s", fontSize=12, textColor=GREEN, leading=16, spaceAfter=2)
st_meta  = S("m", fontSize=9,  textColor=GREY, leading=12)
st_h2    = S("h2", font=FONT_B, fontSize=14, textColor=DARK, leading=18, spaceBefore=14, spaceAfter=6)
st_body  = S("b", fontSize=10.5, textColor=DARK, leading=16, spaceAfter=6, alignment=TA_LEFT)
st_li    = S("li", fontSize=10.5, textColor=DARK, leading=15)
st_small = S("sm", fontSize=9, textColor=GREY, leading=13)
st_cellh = S("ch", font=FONT_B, fontSize=9.5, textColor=colors.white, leading=12)
st_cell  = S("c", fontSize=9.5, textColor=DARK, leading=12)
st_cellm = S("cm", font="Courier", fontSize=9, textColor=DARK, leading=12)
st_flow  = S("fl", font=FONT_B, fontSize=9, textColor=DARK, leading=11, alignment=TA_CENTER)
st_flowg = S("flg", font=FONT_B, fontSize=9, textColor=colors.white, leading=11, alignment=TA_CENTER)

story = []
def h2(t): story.append(Paragraph(t, st_h2))
def p(t):  story.append(Paragraph(t, st_body))
def sp(h=6): story.append(Spacer(1, h))
def bullets(items):
    story.append(ListFlowable(
        [ListItem(Paragraph(i, st_li), leftIndent=10, value="•") for i in items],
        bulletType="bullet", start="•", leftIndent=14, spaceAfter=6))
def numbered(items):
    story.append(ListFlowable(
        [ListItem(Paragraph(i, st_li), leftIndent=10) for i in items],
        bulletType="1", leftIndent=16, spaceAfter=6))

def table(data, widths, header=True, mono_col=None):
    rows = []
    for r, row in enumerate(data):
        cells = []
        for c, val in enumerate(row):
            if r == 0 and header:        cells.append(Paragraph(val, st_cellh))
            elif mono_col is not None and c == mono_col: cells.append(Paragraph(val, st_cellm))
            else:                        cells.append(Paragraph(val, st_cell))
        rows.append(cells)
    t = Table(rows, colWidths=widths, hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND", (0,0), (-1,0), GREEN),
        ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, LGREY]),
        ("GRID", (0,0), (-1,-1), 0.5, BORD),
        ("VALIGN", (0,0), (-1,-1), "MIDDLE"),
        ("LEFTPADDING", (0,0), (-1,-1), 7), ("RIGHTPADDING", (0,0), (-1,-1), 7),
        ("TOPPADDING", (0,0), (-1,-1), 5), ("BOTTOMPADDING", (0,0), (-1,-1), 5),
    ]))
    story.append(t)

# ════════════════════ EN-TÊTE ════════════════════
story.append(Paragraph("ResTri", st_title))
story.append(Paragraph("Système de tri automatique de résistances par vision", st_sub))
story.append(Paragraph("Documentation de fonctionnement · STM32G431 + traitement d'image", st_meta))
sp(6)
story.append(HRFlowable(width="100%", thickness=1.2, color=GREEN, spaceAfter=8))

# ════════════════════ 1. PRÉSENTATION ════════════════════
h2("1. Présentation générale")
p("ResTri est une machine qui <b>trie automatiquement des résistances</b> selon leur valeur. "
  "Une caméra filme la résistance, le programme <b>analyse les bandes de couleur par "
  "traitement d'image (HSV)</b>, en déduit la valeur en ohms et la <b>valide</b> par rapport "
  "aux valeurs normalisées (séries E12/E24). Une carte STM32G431 commande alors des "
  "servomoteurs pour faire tomber la résistance dans le bon bac. Un tableau de bord web "
  "affiche le tout en temps réel.")
p("Une <b>IA de vision (Claude)</b> peut être utilisée en complément pour fiabiliser la "
  "lecture des couleurs ; en son absence, le programme fonctionne entièrement avec sa "
  "détection HSV locale.")

# ════════════════════ 2. ARCHITECTURE ════════════════════
h2("2. Vue d'ensemble (chaîne complète)")
flow = [[Paragraph("CAMÉRA<br/>(DroidCam)", st_flow),
         Paragraph("→", st_flow),
         Paragraph("PC — Analyse HSV<br/>+ validation E12/E24", st_flowg),
         Paragraph("→", st_flow),
         Paragraph("CARTE<br/>STM32G431", st_flow),
         Paragraph("→", st_flow),
         Paragraph("SERVOS<br/>+ 4 BACS", st_flowg)]]
tf = Table(flow, colWidths=[24*mm,7*mm,38*mm,7*mm,26*mm,7*mm,26*mm], hAlign="LEFT")
tf.setStyle(TableStyle([
    ("BACKGROUND", (2,0), (2,0), GREEN), ("BACKGROUND", (6,0), (6,0), GREEN),
    ("BACKGROUND", (0,0), (0,0), LGREY), ("BACKGROUND", (4,0), (4,0), LGREY),
    ("BOX", (0,0),(0,0),0.6,BORD), ("BOX",(4,0),(4,0),0.6,BORD),
    ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ("TOPPADDING",(0,0),(-1,-1),9),("BOTTOMPADDING",(0,0),(-1,-1),9),
]))
story.append(tf)
sp(8)
p("Le PC est le cerveau : il traite l'image, identifie la valeur, classe la résistance dans "
  "l'un des 4 bacs, puis envoie un ordre à la carte par liaison série (USB). La carte exécute "
  "le mouvement mécanique.")

# ════════════════════ 3. MATÉRIEL ════════════════════
h2("3. Le matériel")
table([
    ["Élément", "Broche STM32", "Rôle"],
    ["Servo carrousel (DS3225, 360°)", "PA9 (TIM1_CH2)", "Tourne à 90 / 180 / 270° pour choisir le bac"],
    ["Servo trappe (DS3225, 180°)",    "PA10 (TIM1_CH3)", "Ouvre/ferme la trappe (90° ↔ 180°)"],
    ["Liaison série",   "PA2 / PA3 (UART2)", "Dialogue avec le PC à 115200 bauds"],
    ["Caméra",          "smartphone DroidCam", "Flux vidéo par Wi-Fi"],
    ["Alimentation servos", "externe 5–6 V", "Masse commune avec la carte (servos puissants)"],
], widths=[52*mm, 38*mm, 70*mm], mono_col=1)

# ════════════════════ 4. MÉTHODE DE DÉTECTION (le coeur) ════════════════════
h2("4. Méthode de détection des couleurs (vision.py)")
p("La lecture des bandes ne se fait pas « d'un coup » : l'image passe par une chaîne de "
  "traitement qui isole les bandes, les classe par couleur et en déduit la valeur.")
numbered([
    "<b>Capture</b> : un fil dédié récupère en continu les images de la caméra (DroidCam).",
    "<b>Prétraitement</b> : équilibrage des blancs à partir du fond, amélioration du contraste "
    "(CLAHE), lissage (filtre bilatéral) et masquage des zones surexposées. L'image est "
    "convertie en espace <b>HSV</b> (Teinte, Saturation, Valeur), plus stable pour les couleurs.",
    "<b>Détection du corps</b> : la couleur du corps de la résistance (beige/bleu) est mesurée "
    "sur les bords, afin de l'<b>ignorer</b> et ne garder que les bandes.",
    "<b>Scan de la zone</b> : la zone de pose est balayée <b>colonne par colonne</b> ; chaque "
    "pixel est classé dans une couleur via des <b>plages HSV</b> prédéfinies (BLACK, BROWN, "
    "RED, … GOLD, SILVER), puis un vote donne la couleur dominante de chaque colonne.",
    "<b>Segmentation</b> : les colonnes de même couleur sont regroupées en <b>bandes</b> ; "
    "les bandes trop proches de la couleur du corps sont filtrées.",
    "<b>Sélection</b> : on retient les <b>3 bandes de valeur</b> (la bande de tolérance "
    "or/argent est écartée).",
    "<b>Calcul</b> : 1er chiffre, 2e chiffre, puis multiplicateur → valeur en ohms.",
    "<b>Vote sur plusieurs images</b> : l'analyse est faite sur <b>5 images</b> et la couleur "
    "la plus fréquente l'emporte (robustesse au bruit et à la lumière).",
])

# ════════════════════ 5. VALIDATION E12/E24 ════════════════════
h2("5. Validation E12 / E24 et fiabilité")
p("La valeur calculée est comparée à la grille des valeurs normalisées (séries <b>E12</b> et "
  "<b>E24</b>). Le résultat reçoit un niveau de fiabilité :")
table([
    ["Statut", "Condition", "Interprétation"],
    ["Exact",  "écart ≤ 2 %",  "Correspond à une valeur standard → haute confiance"],
    ["Proche", "écart ≤ 10 %", "Valeur plausible mais imparfaite (lumière, usure)"],
    ["Hors série", "écart > 10 %", "Lecture douteuse → à revérifier"],
], widths=[28*mm, 40*mm, 92*mm])
sp(4)
p("Ce mécanisme évite les valeurs aberrantes : si la lecture ne « tombe » pas sur une valeur "
  "réelle de résistance, elle est signalée comme douteuse.")

# ════════════════════ 6. IA EN COMPLÉMENT ════════════════════
h2("6. IA de vision en complément (optionnelle)")
p("Si le module Claude est disponible, le crop de la zone est aussi envoyé à l'<b>IA de "
  "vision</b> qui renvoie les 3 bandes ; on garde alors ce résultat, sinon on utilise la "
  "détection HSV locale. Le programme fonctionne donc dans les deux cas — l'IA sert "
  "uniquement à fiabiliser les couleurs difficiles (gris/marron/orange).")
bullets([
    "Mode <font face='Courier'>USE_CLAUDE_API = True</font> : IA prioritaire + repli HSV.",
    "Mode <font face='Courier'>USE_CLAUDE_API = False</font> : détection HSV locale seule.",
])

# ════════════════════ 7. OUTILS INTÉGRÉS ════════════════════
h2("7. Outils intégrés (raccourcis clavier)")
table([
    ["Touche", "Fonction"],
    ["S", "Sauvegarder l'image de la zone (crop)"],
    ["D", "Mode debug : visualise le scan colonne par colonne"],
    ["C", "Calibration HSV : clic souris pour relever H/S/V d'un pixel"],
    ["R", "Réinitialiser la détection"],
    ["Q", "Quitter"],
], widths=[22*mm, 138*mm], mono_col=0)

# ════════════════════ 8. FIRMWARE ════════════════════
h2("8. Le firmware de la carte STM32")
p("La carte attend des commandes du PC sur la liaison série, puis exécute la séquence "
  "mécanique. Au démarrage elle envoie <font face='Courier'>STM32:READY</font> et place les "
  "servos en position initiale (carrousel à 0°, trappe fermée).")

# ════════════════════ 9. DÉROULEMENT D'UN TRI ════════════════════
h2("9. Déroulement d'un tri (étape par étape)")
numbered([
    "La caméra filme la résistance posée dans la zone (cadre vert).",
    "Le programme lit les bandes (HSV, vote sur 5 images) et calcule la valeur.",
    "La valeur est validée par la grille E12/E24, avec un niveau de confiance.",
    "Le PC choisit le bac correspondant et envoie l'ordre à la carte.",
    "Le carrousel (PA9) tourne pour amener le bon bac sous la trappe.",
    "Après 2 secondes, la trappe (PA10) s'ouvre : la résistance tombe dans le bac.",
    "La trappe se referme, le carrousel revient à 0°, le dashboard se met à jour.",
])

# ════════════════════ 10. PROTOCOLE SÉRIE ════════════════════
h2("10. Protocole de communication (PC → STM32)")
table([
    ["Commande", "Effet", "Réponse"],
    ["CARR:angle", "Tourne le carrousel à l'angle (0–360°)", "CARR=angle"],
    ["TRAP:angle", "Place la trappe à l'angle (0–180°)", "TRAP=angle"],
    ["SORT:1K / 10K / REJECT", "Cycle de tri complet", "ACK:..."],
    ["PING", "Test de communication", "PONG"],
], widths=[48*mm, 78*mm, 34*mm], mono_col=0)

# ════════════════════ 11. MISE EN ROUTE ════════════════════
h2("11. Mise en route")
numbered([
    "Brancher la carte STM32 en USB et la flasher (STM32CubeIDE).",
    "Alimenter les servos (alim externe 5–6 V, masse commune).",
    "Lancer DroidCam sur le téléphone (même Wi-Fi que le PC) et régler l'IP.",
    "Sur le PC : lancer le programme, puis poser les résistances dans la zone.",
])

sp(10)
story.append(HRFlowable(width="100%", thickness=0.8, color=BORD, spaceAfter=6))
story.append(Paragraph("ResTri — Documentation de fonctionnement. Détection par traitement "
                       "d'image HSV + validation E12/E24, IA de vision en complément.", st_small))

out = r"C:\Users\serin\Downloads\G431_base\ResTri_fonctionnement.pdf"
doc = SimpleDocTemplate(out, pagesize=A4,
                        leftMargin=20*mm, rightMargin=20*mm,
                        topMargin=18*mm, bottomMargin=16*mm,
                        title="ResTri - Fonctionnement", author="ResTri")
doc.build(story)
print("PDF cree :", out)
