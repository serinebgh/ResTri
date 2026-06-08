# -*- coding: utf-8 -*-
"""RAPPORT DEEP ResTri — mise en page professionnelle, palette vert d'eau."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.enums import TA_CENTER, TA_JUSTIFY
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable, ListFlowable, ListItem,
                                PageBreak, Image as RLImage)
from reportlab.graphics.shapes import Drawing, Rect, Line, String, Polygon
from reportlab.lib.utils import ImageReader
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
import os

PHOTO_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "photos")

# ── Polices ──
FONT, FONT_B, FONT_I = "Helvetica", "Helvetica-Bold", "Helvetica-Oblique"
try:
    pdfmetrics.registerFont(TTFont("Body",      r"C:\Windows\Fonts\arial.ttf"))
    pdfmetrics.registerFont(TTFont("Body-Bold", r"C:\Windows\Fonts\arialbd.ttf"))
    pdfmetrics.registerFont(TTFont("Body-It",   r"C:\Windows\Fonts\ariali.ttf"))
    FONT, FONT_B, FONT_I = "Body", "Body-Bold", "Body-It"
except Exception:
    pass

# ── Palette vert d'eau ──
SEA   = colors.HexColor("#159b8d")   # vert d'eau principal
SEA_D = colors.HexColor("#0d6f66")   # foncé (profondeur)
SEA_L = colors.HexColor("#e3f4f1")   # très clair (lignes de tableau)
SEA_L2= colors.HexColor("#f1faf8")
INK   = colors.HexColor("#1b2a28")
GREY  = colors.HexColor("#6a7572")
BORD  = colors.HexColor("#cfe3df")
GOLD  = colors.HexColor("#8a6d00")

W, H = A4

styles = getSampleStyleSheet()
def S(n, **k):
    return ParagraphStyle(n, parent=styles["Normal"], fontName=k.pop("font", FONT), **k)

st_h1   = S("h1", font=FONT_B, fontSize=14.5, textColor=SEA_D, leading=18, spaceBefore=14, spaceAfter=3)
st_h2   = S("h2", font=FONT_B, fontSize=11.5, textColor=SEA, leading=15, spaceBefore=9, spaceAfter=4)
st_body = S("b", fontSize=10, textColor=INK, leading=15, spaceAfter=6, alignment=TA_JUSTIFY)
st_li   = S("li", fontSize=10, textColor=INK, leading=14)
st_note = S("nt", font=FONT_I, fontSize=9, textColor=GREY, leading=13, leftIndent=8,
            borderColor=SEA, borderWidth=0, spaceAfter=6)
st_small= S("sm", fontSize=8.5, textColor=GREY, leading=12)
st_cellh= S("ch", font=FONT_B, fontSize=9, textColor=colors.white, leading=11)
st_cell = S("c", fontSize=9, textColor=INK, leading=11)
st_cellm= S("cm", font="Courier", fontSize=8.5, textColor=INK, leading=11)
st_toc  = S("toc", fontSize=10.5, textColor=INK, leading=18)
st_tocn = S("tocn", font=FONT_B, fontSize=10.5, textColor=SEA, leading=18)

story = []
def h1(t): story.append(Paragraph(t, st_h1)); story.append(HRFlowable(width="100%", thickness=0.8, color=SEA_L, spaceBefore=2, spaceAfter=6))
def h2(t): story.append(Paragraph(t, st_h2))
def p(t):  story.append(Paragraph(t, st_body))
def sp(h=6): story.append(Spacer(1, h))
def note(t): story.append(Paragraph("À compléter — " + t, st_note))
st_cap = S("cap", font=FONT_I, fontSize=8.5, textColor=GREY, leading=11, alignment=TA_CENTER, spaceBefore=3, spaceAfter=8)
def photo(fname, caption, maxw=150*mm, maxh=115*mm):
    """Insère une photo du dossier photos/ si elle existe, sinon une note."""
    for ext in ("", ".jpg", ".jpeg", ".png", ".JPG", ".PNG"):
        path = os.path.join(PHOTO_DIR, fname + ext if not fname.lower().endswith((".jpg",".jpeg",".png")) else fname)
        if os.path.exists(path):
            iw, ih = ImageReader(path).getSize()
            w = maxw; h = w*ih/iw
            if h > maxh: h, w = maxh, maxh*iw/ih
            im = RLImage(path, width=w, height=h); im.hAlign = "CENTER"
            story.append(im); story.append(Paragraph(caption, st_cap))
            return
    note("insérer la photo « %s » (fichier %s dans le dossier photos/)." % (caption, fname))
def bullets(items):
    story.append(ListFlowable([ListItem(Paragraph(i, st_li), leftIndent=10, value="–")
                 for i in items], bulletType="bullet", start="–", leftIndent=14, spaceAfter=6))
def numbered(items):
    story.append(ListFlowable([ListItem(Paragraph(i, st_li), leftIndent=10) for i in items],
                 bulletType="1", leftIndent=16, spaceAfter=6))
def table(data, widths, mono_col=None):
    rows=[]
    for r,row in enumerate(data):
        cells=[]
        for c,val in enumerate(row):
            if r==0: cells.append(Paragraph(val, st_cellh))
            elif mono_col is not None and c==mono_col: cells.append(Paragraph(val, st_cellm))
            else: cells.append(Paragraph(val, st_cell))
        rows.append(cells)
    t=Table(rows,colWidths=widths,hAlign="LEFT")
    t.setStyle(TableStyle([
        ("BACKGROUND",(0,0),(-1,0),SEA),
        ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,SEA_L]),
        ("GRID",(0,0),(-1,-1),0.5,BORD),
        ("VALIGN",(0,0),(-1,-1),"MIDDLE"),
        ("LEFTPADDING",(0,0),(-1,-1),6),("RIGHTPADDING",(0,0),(-1,-1),6),
        ("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
    ]))
    story.append(t)

# ════════════ GRAFCET ════════════
def grafcet():
    steps=[("0","Repos : carrousel à 0°, trappe fermée (90°)",True),
           ("1","Acquisition image + lecture des 3 bandes (HSV)",False),
           ("2","Calcul valeur + validation E12/E24 + choix du bac",False),
           ("3","Rotation carrousel vers l'angle du bac (CARR:a)",False),
           ("4","Ouverture trappe (TRAP:180) — chute de la résistance",False),
           ("5","Fermeture trappe (TRAP:90) puis retour carrousel (CARR:0)",False)]
    trans=["résistance posée dans la zone","3 bandes détectées","valeur calculée",
           "temporisation 2 s écoulée","temporisation chute (1 s)",
           "séquence terminée  →  retour étape 0"]
    ax=62;bw=32;bh=20;act_x=120;act_w=300;gap=46;n=len(steps);Hd=n*(bh+gap)+18
    d=Drawing(440,Hd)
    yof=lambda i:Hd-18-i*(bh+gap)
    d.add(Line(ax,yof(0)+bh,ax,yof(n-1)-gap+bh,strokeColor=INK,strokeWidth=1))
    for i,(num,act,init) in enumerate(steps):
        y=yof(i)
        d.add(Rect(ax-bw/2,y,bw,bh,strokeColor=INK,fillColor=colors.white,strokeWidth=1.3))
        if init: d.add(Rect(ax-bw/2-3,y-3,bw+6,bh+6,strokeColor=INK,fillColor=None,strokeWidth=1))
        d.add(String(ax,y+bh/2-4,num,fontName=FONT_B,fontSize=11,textAnchor="middle",fillColor=INK))
        d.add(Line(ax+bw/2,y+bh/2,act_x,y+bh/2,strokeColor=INK,strokeWidth=0.8))
        d.add(Rect(act_x,y,act_w,bh,strokeColor=BORD,fillColor=SEA_L,strokeWidth=0.8))
        d.add(String(act_x+8,y+bh/2-3.5,act,fontName=FONT,fontSize=8.2,fillColor=INK))
        ty=y-gap/2
        d.add(Line(ax-12,ty,ax+12,ty,strokeColor=INK,strokeWidth=1.4))
        d.add(String(ax+18,ty-3.5,trans[i],fontName=FONT,fontSize=8,fillColor=SEA_D))
    lx=ax-50;yt=yof(0)+bh/2
    d.add(Line(ax,yof(n-1)+bh/2,lx,yof(n-1)+bh/2,strokeColor=INK,strokeWidth=0.8))
    d.add(Line(lx,yof(n-1)+bh/2,lx,yt,strokeColor=INK,strokeWidth=0.8))
    d.add(Line(lx,yt,ax-bw/2,yt,strokeColor=INK,strokeWidth=0.8))
    d.add(Polygon([ax-bw/2,yt,ax-bw/2-7,yt+3.5,ax-bw/2-7,yt-3.5],fillColor=INK,strokeColor=INK))
    story.append(d)

# ════════════ COUVERTURE (canvas) ════════════
def cover(c, doc):
    c.saveState()
    # bande haute
    c.setFillColor(SEA);   c.rect(0, H-265, W, 265, fill=1, stroke=0)
    c.setFillColor(SEA_D); c.rect(0, H-273, W, 9, fill=1, stroke=0)
    # kicker + titre
    c.setFillColor(colors.white)
    c.setFont(FONT_B, 11); c.drawString(54, H-95, "R A P P O R T   D E   P R O J E T   D E E P")
    c.setFont(FONT_B, 46); c.drawString(52, H-160, "ResTri")
    c.setFont(FONT, 14);   c.drawString(54, H-190, "Système de tri automatique de résistances par vision")
    c.setFont(FONT, 10.5); c.drawString(54, H-214, "Digital Embedded Electronics Project — Livraison finale")
    # bloc infos
    y = H-330
    def info(lbl, val):
        nonlocal y
        c.setFillColor(SEA);  c.setFont(FONT_B, 10); c.drawString(54, y, lbl.upper())
        c.setFillColor(INK);  c.setFont(FONT, 11.5); c.drawString(54, y-16, val)
        y -= 46
    info("Équipe", "BOUGHELOUM Serine   ·   ARRIS Romane   ·   NKOUAKAM NGONGANG Romels")
    info("Établissement", "ESEO — Campus de Vélizy")
    info("Année", "2026")
    info("Cible matérielle", "NUCLEO-G431KB  ·  2 servomoteurs  ·  caméra")
    # filet + mention discrète
    c.setStrokeColor(BORD); c.setLineWidth(0.8); c.line(54, 120, W-54, 120)
    c.setFillColor(GREY); c.setFont(FONT_I, 9)
    c.drawString(54, 104, "Document de travail — certaines annexes (PCB, photos, dates) seront complétées à la livraison.")
    # bande basse
    c.setFillColor(SEA); c.rect(0, 0, W, 34, fill=1, stroke=0)
    c.setFillColor(colors.white); c.setFont(FONT, 9)
    c.drawCentredString(W/2, 12, "ResTri  ·  Tri automatique de résistances  ·  ESEO Vélizy 2026")
    c.restoreState()

# ════════════ EN-TÊTE / PIED (canvas) ════════════
def header_footer(c, doc):
    c.saveState()
    # en-tête
    c.setFillColor(SEA_D); c.setFont(FONT_B, 9); c.drawString(54, H-34, "ResTri")
    c.setFillColor(GREY);  c.setFont(FONT, 9)
    c.drawRightString(W-54, H-34, "Rapport DEEP — ESEO Vélizy")
    c.setStrokeColor(SEA_L); c.setLineWidth(1); c.line(54, H-40, W-54, H-40)
    # pied
    c.setStrokeColor(SEA_L); c.line(54, 38, W-54, 38)
    c.setFillColor(GREY); c.setFont(FONT, 8.5)
    c.drawString(54, 26, "Système de tri automatique de résistances")
    c.drawRightString(W-54, 26, "Page %d" % doc.page)
    c.restoreState()

# ════════════ PAGE 1 : couverture (vide, dessinée par cover) ════════════
story.append(Spacer(1, 2))
story.append(PageBreak())

# ════════════ SOMMAIRE ════════════
story.append(Paragraph("Sommaire", S("st", font=FONT_B, fontSize=18, textColor=SEA_D, leading=22, spaceAfter=10)))
story.append(HRFlowable(width="100%", thickness=1, color=SEA, spaceAfter=12))
toc=[("1","Compléments choisis"),("2","Remise du matériel"),("3","Cahier des charges"),
     ("4","Manuel d'utilisation"),("5","Affectation des ports"),("6","Câblage du PCB"),
     ("7","Algorithme — GRAFCET du cycle de tri"),("8","Structure du programme"),
     ("9","Tests"),("10","Cahier de suivi"),("11","État d'avancement et analyse"),
     ("12","Conclusion"),("A.","Annexe B — Design de PCB"),]
rows=[[Paragraph(n, st_tocn), Paragraph(t, st_toc)] for n,t in toc]
tt=Table(rows, colWidths=[14*mm, 150*mm], hAlign="LEFT")
tt.setStyle(TableStyle([("VALIGN",(0,0),(-1,-1),"TOP"),("BOTTOMPADDING",(0,0),(-1,-1),3),
                        ("LINEBELOW",(0,0),(-1,-2),0.4,SEA_L)]))
story.append(tt)
story.append(PageBreak())

# ════════════ 1. COMPLÉMENTS ════════════
h1("1. Compléments choisis")
p("ResTri trie automatiquement des résistances par lecture optique de leur code de couleurs. "
  "Au-delà du développement matériel et logiciel, l'équipe a retenu les compléments suivants, "
  "le routage de PCB étant obligatoire.")
table([
    ["Code","Complément","Points","Retenu"],
    ["B","Routage de PCB (avec Nucleo)","3","Oui"],
    ["A","Analyseur logique (trames UART)","2","—"],
    ["C","Design CAO d'un boîtier","2","—"],
    ["D","Documentation Doxygen","1","—"],
    ["G","Gestion de version (Git)","1","—"],
    ["T","Jeu de tests d'une fonctionnalité","1","—"],
], widths=[16*mm, 92*mm, 18*mm, 18*mm])
p("Le complément B est en cours de réalisation (NKOUAKAM NGONGANG Romels) : conception sous "
  "Altium d'une carte support recevant la Nucleo, avec les connecteurs des servomoteurs, de "
  "l'alimentation et de la liaison UART.")
note("préciser les compléments effectivement réalisés (objectif : 8 à 9 points).")

# ════════════ 2. REMISE DU MATÉRIEL ════════════
h1("2. Remise du matériel")
p("Carte fournie : NUCLEO-G431KB. L'ensemble du matériel prêté (carte, périphériques et "
  "câble USB) sera restitué à l'issue du projet.")
p("Numéro de la carte Nucleo : __________________")
note("renseigner le numéro de carte et la modalité de restitution.")

# ════════════ 3. CAHIER DES CHARGES ════════════
h1("3. Cahier des charges")
h2("Contexte et besoin")
p("Le tri manuel de résistances est fastidieux et sujet aux erreurs de lecture du code de "
  "couleurs. Un atelier d'électronique (le « client ») souhaite un poste capable d'identifier "
  "automatiquement la valeur d'une résistance et de la ranger dans le bac correspondant, afin "
  "de gagner du temps et de fiabiliser le rangement des composants.")
h2("Fonction principale")
p("Identifier la valeur d'une résistance posée devant une caméra, puis l'orienter "
  "mécaniquement vers l'un des bacs de tri à l'aide d'un carrousel et d'une trappe.")
h2("Exigences fonctionnelles")
bullets([
    "Lire les trois bandes de valeur d'une résistance (séries normalisées E12/E24).",
    "Afficher la valeur, le bac visé et un indicateur de fiabilité.",
    "Trier dans quatre bacs dont les valeurs sont paramétrables par l'utilisateur.",
    "Piloter un carrousel (sélection du bac) et une trappe (largage) via la carte STM32.",
    "Fournir une interface de supervision présentant l'état du poste en temps réel.",
])
h2("Contraintes")
bullets([
    "Cible imposée : microcontrôleur STM32G431KB (Nucleo-32).",
    "Liaison série UART entre le PC et la carte (115200 bauds).",
    "Servomoteurs de puissance (DS3225) alimentés par une source externe 5–6 V, masse "
    "commune avec la carte.",
    "Détection robuste aux variations d'éclairage (prétraitement de l'image).",
])
h2("Limites du projet")
p("Le périmètre couvre l'identification optique, la supervision et la commande des "
  "actionneurs. L'amenée automatique des résistances (convoyeur) n'est pas traitée : la "
  "résistance est posée manuellement dans la zone de lecture.")

# ════════════ 4. MANUEL ════════════
h1("4. Manuel d'utilisation")
h2("Alimentation")
bullets([
    "Carte STM32 : alimentée par le câble USB (5 V).",
    "Servomoteurs : alimentation externe 5–6 V (≈ 2–3 A), masse reliée au GND de la carte.",
])
h2("Mise en service")
numbered([
    "Brancher la carte en USB et mettre l'alimentation des servomoteurs.",
    "Activer le flux vidéo de la caméra sur le même réseau que le poste.",
    "Démarrer l'application de supervision et ouvrir l'interface.",
    "Renseigner la valeur de chaque bac (par exemple 1 kΩ, 10 kΩ, 470 Ω, rebut).",
    "Poser une résistance bien à plat dans le cadre repère.",
])
h2("Utilisation courante")
p("L'interface affiche la valeur lue, les couleurs des bandes, le niveau de fiabilité et le "
  "bac retenu. Le poste oriente le bac sous la trappe, patiente deux secondes, ouvre la "
  "trappe pour libérer la résistance, la referme et revient en position initiale. Le compteur "
  "du bac est alors incrémenté.")
sp(4)
photo("vue_ensemble", "Maquette ResTri : cadre support, caméra (smartphone), trappe et carrousel à 4 bacs.")
photo("vue_dessus", "Vue de dessus : carrousel à quatre compartiments placé sous la trappe.")
story.append(PageBreak())

# ════════════ 5. PORTS ════════════
h1("5. Affectation des ports")
p("Broches du STM32G431KB utilisées dans le projet :")
table([
    ["Broche","Usage dans le projet"],
    ["PA9","Servo CARROUSEL (DS3225, 25 kg) — PWM (TIM1_CH2)"],
    ["PA10","Servo TRAPPE — PWM (TIM1_CH3)"],
    ["PA8","PWM disponible (TIM1_CH1) — non utilisé"],
    ["PA2","UART2 TX → PC"],
    ["PA3","UART2 RX ← PC"],
    ["PB8","LED verte — indicateur de cycle de tri"],
    ["5V / VIN / 3V3 / AVDD","Alimentation"],
    ["GND","Masse (commune avec l'alimentation des servos)"],
    ["NRST","Reset"],
    ["Autres (PA0-1, PA4-7, PA11-12, PA15 ; PB0, PB3-7 ; PF0-1)","Non utilisées"],
], widths=[60*mm,100*mm], mono_col=0)

# ════════════ 6. PCB ════════════
h1("6. Câblage et maquette")
p("Dans la version actuelle, la carte Nucleo est implantée sur une platine d'essai "
  "(breadboard). Les deux servomoteurs (carrousel sur PA9, trappe sur PA10) sont alimentés "
  "par une source externe 5–6 V dont la masse est reliée au GND de la carte. Le PCB support "
  "définitif est en cours de conception (voir Annexe B).")
p("La structure porteuse a été réalisée en bois : l'imprimante 3D n'étant pas disponible, "
  "nous avons adapté la conception pour ne pas bloquer le projet. Seul le carrousel, pièce "
  "fonctionnelle essentielle, a pu être imprimé en 3D.")
sp(4)
photo("breadboard", "Carte Nucleo-G431KB sur la platine d'essai (liaison UART + commandes PWM).")
photo("carrousel", "Carrousel à quatre compartiments entraîné par le servomoteur DS3225 (25 kg).")
photo("trappe", "Mécanisme de trappe et son servomoteur (broche PA10).")
note("ajouter, lorsqu'il sera disponible, les photographies recto/verso du PCB câblé.")

# ════════════ 7. GRAFCET ════════════
h1("7. Algorithme — GRAFCET du cycle de tri")
p("La tâche principale exécutée par la carte est le cycle de tri, décrit ci-dessous au "
  "formalisme GRAFCET (étapes, transitions et actions associées).")
sp(4); grafcet(); sp(8)
p("L'étape initiale maintient le poste au repos. À la détection d'une résistance, l'image est "
  "analysée (étapes 1 et 2) ; une fois la valeur calculée et le bac déterminé, le carrousel "
  "s'oriente (3), la trappe libère la résistance après deux secondes (4), puis le poste "
  "referme la trappe et revient en position initiale (5) avant de reboucler.")
h2("Lecture des couleurs (principe)")
p("Acquisition de l'image, prétraitement (équilibrage des blancs, rehaussement de contraste, "
  "conversion HSV), repérage de la couleur du corps, balayage de la zone colonne par colonne "
  "avec classification de chaque pixel par plages HSV, regroupement en bandes, sélection des "
  "trois bandes de valeur, calcul puis validation E12/E24 (décision par vote sur cinq images).")
story.append(PageBreak())

# ════════════ 8. STRUCTURE ════════════
h1("8. Structure du programme")
h2("8.0  Répartition des tâches")
table([
    ["Membre","Contribution principale"],
    ["BOUGHELOUM Serine","Code de la détection (vision : HSV, segmentation, E12/E24) ; structure mécanique."],
    ["NKOUAKAM NGONGANG Romels","Code de fonctionnement des moteurs (firmware, séquence de tri) ; PCB (Altium)."],
    ["ARRIS Romane","Structure mécanique ; câblage, branchement et placement des moteurs."],
], widths=[48*mm,112*mm])
h2("8.1  Firmware — main.c  (Romels)")
table([
    ["Fonction","Auteur","Description"],
    ["main","Romels","Initialisation UART/servos, position initiale, boucle de réception des commandes."],
    ["cycle_tri","Romels","Séquence : carrousel → temporisation → trappe ouverte → fermée → retour 0°."],
    ["traite_commande","Romels","Interprétation des commandes reçues (CARR:, TRAP:, SORT:, PING)."],
], widths=[34*mm,20*mm,106*mm], mono_col=0)
h2("8.2  Firmware — bsp_servo.c  (Romels)")
table([
    ["Fonction","Auteur","Description"],
    ["BSP_SERVO_init","Romels","Configuration des PWM 50 Hz (carrousel réglé sur 0–360°)."],
    ["BSP_SERVO_set_angle","Romels","Conversion d'un angle en largeur d'impulsion appliquée au servo."],
], widths=[44*mm,20*mm,96*mm], mono_col=0)
h2("8.3  Logiciel PC — vision.py  (Serine)")
table([
    ["Fonction","Auteur","Description"],
    ["CameraStream","Serine","Capture vidéo dans un fil dédié."],
    ["preprocess","Serine","Équilibrage des blancs, CLAHE, filtre bilatéral, conversion HSV."],
    ["scan_zone / segment_colours","Serine","Balayage HSV de la zone et regroupement en bandes."],
    ["compute_value / find_standard","Serine","Calcul de la valeur et validation E12/E24."],
    ["analyse_frames","Serine","Analyse sur cinq images et vote majoritaire."],
], widths=[48*mm,20*mm,92*mm], mono_col=0)
h2("8.4  Logiciel PC — serial_link.py / app.py")
table([
    ["Fonction","Auteur","Description"],
    ["sort_sequence","Romels","Envoi de la séquence de tri (CARR/TRAP) à la carte."],
    ["app.py (supervision)","Équipe","Interface : vidéo, valeurs, compteurs, quatre bacs."],
], widths=[44*mm,20*mm,96*mm], mono_col=0)

# ════════════ 9. TESTS ════════════
h1("9. Tests")
table([
    ["Intitulé","Procédure / attendu","Résultat"],
    ["Alimentation microcontrôleur","Mesure au voltmètre ; entrée à 5 V.","OK"],
    ["Liaison série PC ↔ carte","Envoi de PING, réception de PONG.","OK"],
    ["Message de démarrage","Au reset, la carte émet STM32:READY.","OK"],
    ["Servo trappe","TRAP:90 / TRAP:180 → la trappe se déplace.","OK"],
    ["Servo carrousel","CARR:0/90/180/270 → rotation.","OK"],
    ["Cycle de tri complet","SORT → carrousel, tempo 2 s, trappe, retour 0°.","OK"],
    ["Lecture caméra","Le poste reçoit l'image (1280×720).","OK"],
    ["Lecture d'une résistance","Résistance connue → valeur correcte.","OK (démo vidéo)"],
], widths=[42*mm,84*mm,34*mm])
p("Le fonctionnement complet (lecture puis tri) est démontré dans la vidéo jointe à la livraison.")
story.append(PageBreak())

# ════════════ 10. SUIVI ════════════
h1("10. Cahier de suivi")
table([
    ["Date","Tâches, réalisateurs, difficultés"],
    ["__/__","Détection des couleurs HSV et validation E12/E24 (Serine)."],
    ["__/__","Firmware moteurs : PWM servos, carrousel 360°, trappe (Romels)."],
    ["__/__","Structure mécanique, câblage et placement des moteurs (Romane, Serine)."],
    ["__/__","Réglage des angles, liaison série, intégration du cycle de tri (équipe)."],
    ["__/__","Conception du PCB sous Altium (Romels)."],
], widths=[24*mm,136*mm])
note("renseigner les dates réelles et les difficultés rencontrées par séance.")

# ════════════ 11. AVANCEMENT ════════════
h1("11. État d'avancement et analyse")
h2("Réalisé")
bullets([
    "Communication série bidirectionnelle PC ↔ STM32.",
    "Commande des servomoteurs et cycle de tri complet (carrousel et trappe).",
    "Détection des couleurs HSV avec validation E12/E24 et décision par vote.",
    "Interface de supervision en temps réel (vidéo, valeur, compteurs, bacs paramétrables).",
])
h2("À finaliser")
bullets([
    "Réglage des angles des quatre bacs sur la maquette définitive.",
    "Campagne d'essais sur un lot de résistances variées (taux de bonne lecture).",
    "Réalisation et intégration du PCB.",
])
h2("Analyse")
bullets([
    "Les servomoteurs de puissance imposent une alimentation externe, à prévoir dès le câblage.",
    "Un faux contact sur une broche de commande a provoqué une panne difficile à diagnostiquer ; "
    "un test broche par broche aurait fait gagner du temps.",
    "Le prétraitement de l'image (équilibrage des blancs) est déterminant pour la stabilité des "
    "couleurs ; un mode de calibration a été ajouté pour s'adapter à l'éclairage.",
    "L'imprimante 3D étant tombée en panne, le bâti prévu en impression a été refait en bois. "
    "Cette adaptation rapide a évité de bloquer le projet ; avec plus de temps, un châssis "
    "imprimé (ou un PCB intégré au support) aurait amélioré la précision et la répétabilité.",
])

# ════════════ 12. CONCLUSION ════════════
h1("12. Conclusion")
p("ResTri met en œuvre une chaîne complète « perception – décision – action » : une caméra et "
  "un traitement d'image identifient la résistance, la valeur est validée par les séries "
  "normalisées, et la carte STM32 commande les actionneurs assurant le tri. Le projet a "
  "permis de mettre en pratique la liaison série, la génération de signaux PWM pour servos et "
  "le traitement d'image, tout en gérant des contraintes matérielles concrètes (alimentation, "
  "câblage, mécanique).")

# ════════════ ANNEXE B ════════════
story.append(PageBreak())
h1("Annexe B — Design de PCB (complément obligatoire)")
p("Conception sous Altium d'une carte support recevant la Nucleo et regroupant les "
  "connecteurs des servomoteurs, de l'alimentation et de la liaison UART.")
photo("pcb_schema", "Schéma électrique de la carte (Altium).")
photo("pcb_routage", "Vue 2D du routage (plans de masse masqués).")
photo("pcb_3d", "Vue 3D de la carte.")
note("reprendre le contenu du livrable intermédiaire : rôle des composants, difficultés "
     "rencontrées, estimation du coût de fabrication (Gerber). Joindre les fichiers SchDoc, "
     "PcbDoc et le PDF généré par Altium à l'archive livrable.")

# ════════════ BUILD ════════════
out = r"C:\Users\serin\Downloads\G431_base\Rapport_DEEP_ResTri.pdf"
doc = SimpleDocTemplate(out, pagesize=A4, leftMargin=19*mm, rightMargin=19*mm,
                        topMargin=24*mm, bottomMargin=20*mm,
                        title="Rapport DEEP - ResTri", author="ResTri")
doc.build(story, onFirstPage=cover, onLaterPages=header_footer)
print("PDF cree :", out)
