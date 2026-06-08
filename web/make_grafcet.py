# -*- coding: utf-8 -*-
"""GRAFCET autonome du cycle de tri ResTri (PDF 1 page)."""
from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
from reportlab.lib.enums import TA_CENTER
from reportlab.platypus import (SimpleDocTemplate, Paragraph, Spacer, Table,
                                TableStyle, HRFlowable)
from reportlab.graphics.shapes import Drawing, Rect, Line, String, Polygon
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont

FONT, FONT_B = "Helvetica", "Helvetica-Bold"
try:
    pdfmetrics.registerFont(TTFont("Body",      r"C:\Windows\Fonts\arial.ttf"))
    pdfmetrics.registerFont(TTFont("Body-Bold", r"C:\Windows\Fonts\arialbd.ttf"))
    FONT, FONT_B = "Body", "Body-Bold"
except Exception:
    pass

BLUE  = colors.HexColor("#1f6feb")
DARK  = colors.HexColor("#11151c")
GREY  = colors.HexColor("#5b6472")
LGREY = colors.HexColor("#eef2f8")
BORD  = colors.HexColor("#cdd5e2")

styles = getSampleStyleSheet()
def S(n, **k): return ParagraphStyle(n, parent=styles["Normal"],
        fontName=k.pop("font", FONT), **k)

STEPS = [
    ("0", "Repos : carrousel à 0°, trappe fermée (90°)", True),
    ("1", "Acquisition image + lecture des 3 bandes (HSV)", False),
    ("2", "Calcul valeur + validation E12/E24 + choix du bac", False),
    ("3", "Rotation carrousel vers l'angle du bac  (CARR:a)", False),
    ("4", "Ouverture trappe (TRAP:180) — chute de la résistance", False),
    ("5", "Fermeture trappe (TRAP:90) puis retour carrousel (CARR:0)", False),
]
TRANS = [
    "résistance posée dans la zone",
    "3 bandes détectées",
    "valeur calculée",
    "temporisation 2 s écoulée",
    "temporisation chute (1 s)",
    "séquence terminée  →  retour étape 0",
]

def grafcet():
    ax=80; bw=40; bh=26; act_x=150; act_w=320; gap=56
    n=len(STEPS); H=n*(bh+gap)+24
    d=Drawing(490, H)
    def y_of(i): return H-22-i*(bh+gap)
    d.add(Line(ax, y_of(0)+bh, ax, y_of(n-1)-gap+bh, strokeColor=DARK, strokeWidth=1))
    for i,(num,act,init) in enumerate(STEPS):
        y=y_of(i)
        d.add(Rect(ax-bw/2, y, bw, bh, strokeColor=DARK, fillColor=colors.white, strokeWidth=1.4))
        if init:
            d.add(Rect(ax-bw/2-3.5, y-3.5, bw+7, bh+7, strokeColor=DARK, fillColor=None, strokeWidth=1))
        d.add(String(ax, y+bh/2-5, num, fontName=FONT_B, fontSize=14, textAnchor="middle", fillColor=DARK))
        d.add(Line(ax+bw/2, y+bh/2, act_x, y+bh/2, strokeColor=DARK, strokeWidth=0.9))
        d.add(Rect(act_x, y, act_w, bh, strokeColor=BORD, fillColor=LGREY, strokeWidth=0.9))
        d.add(String(act_x+9, y+bh/2-4, act, fontName=FONT, fontSize=9, fillColor=DARK))
        ty=y-gap/2
        d.add(Line(ax-15, ty, ax+15, ty, strokeColor=DARK, strokeWidth=1.6))
        d.add(String(ax+22, ty-4, TRANS[i], fontName=FONT, fontSize=8.6, fillColor=BLUE))
    lx=ax-62; yt=y_of(0)+bh/2
    d.add(Line(ax, y_of(n-1)+bh/2, lx, y_of(n-1)+bh/2, strokeColor=DARK, strokeWidth=0.9))
    d.add(Line(lx, y_of(n-1)+bh/2, lx, yt, strokeColor=DARK, strokeWidth=0.9))
    d.add(Line(lx, yt, ax-bw/2, yt, strokeColor=DARK, strokeWidth=0.9))
    d.add(Polygon([ax-bw/2,yt, ax-bw/2-8,yt+4, ax-bw/2-8,yt-4], fillColor=DARK, strokeColor=DARK))
    return d

story=[]
story.append(Paragraph("GRAFCET — Cycle de tri ResTri",
             S("t", font=FONT_B, fontSize=18, textColor=DARK, alignment=TA_CENTER, leading=22)))
story.append(Paragraph("Tâche principale exécutée par la carte STM32G431",
             S("s", fontSize=10, textColor=GREY, alignment=TA_CENTER, leading=14)))
story.append(Spacer(1,6))
story.append(HRFlowable(width="100%", thickness=1, color=BLUE, spaceAfter=10))
story.append(grafcet())
story.append(Spacer(1,12))

# Légende
leg=[["Symbole","Signification"],
     ["Rectangle double","Étape initiale (état au démarrage)"],
     ["Rectangle simple","Étape (état du système)"],
     ["Trait horizontal","Transition + réceptivité (condition de franchissement)"],
     ["Rectangle gris","Action associée à l'étape active"]]
t=Table(leg, colWidths=[40*mm,120*mm], hAlign="LEFT")
t.setStyle(TableStyle([
    ("BACKGROUND",(0,0),(-1,0),BLUE),("TEXTCOLOR",(0,0),(-1,0),colors.white),
    ("FONTNAME",(0,0),(-1,0),FONT_B),("FONTSIZE",(0,0),(-1,-1),9),
    ("ROWBACKGROUNDS",(0,1),(-1,-1),[colors.white,LGREY]),
    ("GRID",(0,0),(-1,-1),0.5,BORD),("VALIGN",(0,0),(-1,-1),"MIDDLE"),
    ("LEFTPADDING",(0,0),(-1,-1),6),("TOPPADDING",(0,0),(-1,-1),4),("BOTTOMPADDING",(0,0),(-1,-1),4),
]))
story.append(t)

out=r"C:\Users\serin\Downloads\G431_base\GRAFCET_ResTri.pdf"
SimpleDocTemplate(out, pagesize=A4, leftMargin=18*mm, rightMargin=18*mm,
                  topMargin=16*mm, bottomMargin=15*mm, title="GRAFCET ResTri").build(story)
print("PDF cree :", out)
