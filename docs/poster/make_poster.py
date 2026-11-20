"""TURN FYP poster v2: vintage screen-print film poster. 22.5in x 34.5in portrait.

python poster2.py F26-XXX "Mr."   ->  FYPPoster-F26-XXX-TURN.pdf (+ preview PNGs)
"""

import asyncio
import math
import random
import sys
from pathlib import Path

HERE = Path(__file__).parent
FONTS = HERE.parent / "fonts"
PID = sys.argv[1] if len(sys.argv) > 1 else "F26-XXX"
SUP = sys.argv[2] if len(sys.argv) > 2 else "Mr."
OUT = HERE / f"FYPPoster-{PID}-TURN.pdf"

PAPER, INK, RED, YEL, DRED = "#EFE5CF", "#151413", "#D62718", "#F4B400", "#A81C10"


def font(fam, pkg, file):
    return f"@font-face {{ font-family: '{fam}'; src: url('file://{FONTS}/{pkg}/files/{file}'); }}"


FONTFACE = "\n".join(
    [
        font("Anton", "fontsource-anton-5.3.0", "anton-latin-400-normal.woff2"),
        font("Bebas", "fontsource-bebas-neue-5.3.0", "bebas-neue-latin-400-normal.woff2"),
        font("Elite", "fontsource-special-elite-5.3.0", "special-elite-latin-400-normal.woff2"),
        "@font-face { font-family: 'Oswald'; font-weight: 400; src: url('file://%s/fontsource-oswald-5.3.0/files/oswald-latin-400-normal.woff2'); }" % FONTS,
        "@font-face { font-family: 'Oswald'; font-weight: 600; src: url('file://%s/fontsource-oswald-5.3.0/files/oswald-latin-600-normal.woff2'); }" % FONTS,
        "@font-face { font-family: 'Oswald'; font-weight: 700; src: url('file://%s/fontsource-oswald-5.3.0/files/oswald-latin-700-normal.woff2'); }" % FONTS,
        "@font-face { font-family: 'Narrow'; font-weight: 400; src: url('file://%s/fontsource-archivo-narrow-5.3.0/files/archivo-narrow-latin-400-normal.woff2'); }" % FONTS,
        "@font-face { font-family: 'Narrow'; font-weight: 700; src: url('file://%s/fontsource-archivo-narrow-5.3.0/files/archivo-narrow-latin-700-normal.woff2'); }" % FONTS,
    ]
)


# ---------------------------------------------------------------- art
def sunburst(w, h, cx, cy, rays=30, c1=RED, c2=DRED):
    r = math.hypot(w, h)
    s = [f'<svg viewBox="0 0 {w} {h}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg"><rect width="{w}" height="{h}" fill="{c1}"/>']
    for i in range(0, rays, 2):
        a0, a1 = 2 * math.pi * i / rays, 2 * math.pi * (i + 1) / rays
        s.append(
            f'<polygon points="{cx},{cy} {cx + r * math.cos(a0):.0f},{cy + r * math.sin(a0):.0f} '
            f'{cx + r * math.cos(a1):.0f},{cy + r * math.sin(a1):.0f}" fill="{c2}"/>'
        )
    s.append("</svg>")
    return "".join(s)


def torn(w=2160, h=70, seed=3, fill=PAPER, top=True):
    rnd = random.Random(seed)
    pts, x = [], 0
    while x < w:
        pts.append((x, rnd.uniform(8, h - 8)))
        x += rnd.uniform(14, 46)
    pts.append((w, rnd.uniform(8, h - 8)))
    edge = " ".join(f"{a:.0f},{b:.0f}" for a, b in pts)
    poly = f"0,{h} {edge} {w},{h}" if top else f"0,0 {edge} {w},0"
    shadow = " ".join(f"{a:.0f},{b + 7:.0f}" for a, b in pts)
    sh = f"0,{h} {shadow} {w},{h}" if top else ""
    return (
        f'<svg class="torn" viewBox="0 0 {w} {h}" preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">'
        + (f'<polygon points="{sh}" fill="#00000033"/>' if sh else "")
        + f'<polygon points="{poly}" fill="{fill}"/></svg>'
    )


def iso(x, y, lvl, cx, cy, gap, k=1.0):
    return ((x - y) * 0.866 * k + cx, (x + y) * 0.5 * k + cy - lvl * gap)


def building(cx=430, cy=560, gap=210, k=1.25, label=True, pin=True, vb="0 0 860 900", sw=1.0):
    """Three stacked floors, ink on paper, with a route climbing the stairs."""

    def P(pts, lvl, **kw):
        p = " ".join(f"{a:.1f},{b:.1f}" for a, b in (iso(x, y, lvl, cx, cy, gap, k) for x, y in pts))
        attrs = " ".join(f'{kk.replace("_", "-")}="{v}"' for kk, v in kw.items())
        return f'<polyline points="{p}" {attrs}/>'

    W, H = 300, 200
    s = [f'<svg viewBox="{vb}" xmlns="http://www.w3.org/2000/svg" font-family="Bebas">']

    def floor(lvl, name):
        o = []
        box = [(0, 0), (W, 0), (W, H), (0, H), (0, 0)]
        # print shadow
        p = " ".join(f"{a + 14:.1f},{b + 14:.1f}" for a, b in (iso(x, y, lvl, cx, cy, gap, k) for x, y in box))
        o.append(f'<polygon points="{p}" fill="{INK}"/>')
        o.append(P(box, lvl, fill=PAPER, stroke=INK, stroke_width=7 * sw, stroke_linejoin="round"))
        o.append(P([(255, 85), (W, 85), (W, 115), (255, 115), (255, 85)], lvl, fill=YEL, stroke="none"))
        for sx in (262, 271, 280, 289):
            o.append(P([(sx, 87), (sx, 113)], lvl, stroke=INK, stroke_width=3 * sw, fill="none"))
        for y in (85, 115):
            for a, b in ((0, 28), (52, 98), (122, 178), (202, 255)):
                o.append(P([(a, y), (b, y)], lvl, stroke=INK, stroke_width=5.5 * sw, fill="none", stroke_linecap="round"))
        for x in (75, 150, 225):
            o.append(P([(x, 0), (x, 85)], lvl, stroke=INK, stroke_width=5.5 * sw, fill="none"))
            o.append(P([(x, 115), (x, 200)], lvl, stroke=INK, stroke_width=5.5 * sw, fill="none"))
        # hatch two rooms (screen-print texture)
        for i in range(8, 75, 11):
            o.append(P([(i, 120), (min(i + 60, 75), 120 + min(60, 75 - i))], lvl, stroke=INK, stroke_width=1.6 * sw, stroke_opacity=0.55, fill="none"))
        if label:
            lx, ly = iso(-10, 205, lvl, cx, cy, gap, k)
            o.append(f'<text x="{lx - 18:.0f}" y="{ly + 8:.0f}" text-anchor="end" font-size="{38 * sw:.0f}" fill="{INK}" letter-spacing="2">{name}</text>')
        return "\n".join(o)

    def route(pts, lvl):
        return P(pts, lvl, stroke=INK, stroke_width=22 * sw, fill="none", stroke_linecap="round", stroke_linejoin="round") + P(
            pts, lvl, stroke=YEL, stroke_width=12 * sw, fill="none", stroke_linecap="round", stroke_linejoin="round"
        )

    s.append(floor(0, "GROUND"))
    s.append(route([(40, 160), (40, 100), (272, 100)], 0))
    x0, y0 = iso(40, 160, 0, cx, cy, gap, k)
    s.append(f'<circle cx="{x0:.0f}" cy="{y0:.0f}" r="{17 * sw:.0f}" fill="{RED}" stroke="{INK}" stroke-width="{6 * sw:.0f}"/>')
    s.append(floor(1, "FLOOR 1"))
    s.append(floor(2, "FLOOR 2"))
    a, b = iso(272, 100, 0, cx, cy, gap, k), iso(272, 100, 2, cx, cy, gap, k)
    s.append(f'<line x1="{a[0]:.0f}" y1="{a[1]:.0f}" x2="{b[0]:.0f}" y2="{b[1]:.0f}" stroke="{INK}" stroke-width="{22 * sw:.0f}" stroke-dasharray="{6 * sw:.0f} {20 * sw:.0f}" stroke-linecap="round"/>')
    s.append(f'<line x1="{a[0]:.0f}" y1="{a[1]:.0f}" x2="{b[0]:.0f}" y2="{b[1]:.0f}" stroke="{YEL}" stroke-width="{12 * sw:.0f}" stroke-dasharray="{6 * sw:.0f} {20 * sw:.0f}" stroke-linecap="round"/>')
    s.append(route([(272, 100), (112, 100), (112, 45)], 2))
    if pin:
        px, py = iso(112, 45, 2, cx, cy, gap, k)
        z = 1.9 * sw
        s.append(
            f'<g transform="translate({px:.0f},{py:.0f}) scale({z})"><path d="M0,0 C-20,-26 -24,-38 -24,-48 A24,24 0 1 1 24,-48 C24,-38 20,-26 0,0Z" '
            f'fill="{RED}" stroke="{INK}" stroke-width="4.5"/><circle cx="0" cy="-48" r="9" fill="{PAPER}" stroke="{INK}" stroke-width="3"/></g>'
        )
    s.append("</svg>")
    return "\n".join(s)


def plan_sheet():
    W, H = 300, 200
    g = ['<svg viewBox="0 0 420 470" xmlns="http://www.w3.org/2000/svg" font-family="Narrow">']
    g.append(f'<g transform="translate(46,40) rotate(4 170 200)"><rect width="340" height="400" fill="{PAPER}" stroke="{INK}" stroke-width="5"/></g>')
    g.append(f'<g transform="translate(26,24) rotate(-3 170 200)"><rect x="10" y="10" width="340" height="400" fill="{INK}"/><rect width="340" height="400" fill="#FBF6EA" stroke="{INK}" stroke-width="5"/>')
    g.append(f'<g transform="translate(20,64)" stroke="{INK}" fill="none" stroke-width="5"><rect width="{W}" height="{H}"/>')
    for y in (85, 115):
        for a, b in ((0, 28), (52, 98), (122, 178), (202, 255)):
            g.append(f'<line x1="{a}" y1="{y}" x2="{b}" y2="{y}"/>')
    for x in (75, 150, 225):
        g.append(f'<line x1="{x}" y1="0" x2="{x}" y2="85"/><line x1="{x}" y1="115" x2="{x}" y2="200"/>')
    for x in (262, 271, 280, 289):
        g.append(f'<line x1="{x}" y1="87" x2="{x}" y2="113" stroke-width="2.5"/>')
    for d in (40, 110, 190):
        g.append(f'<path d="M{d - 12},85 a24,24 0 0 1 24,-24" stroke-width="2.5"/>')
    g.append("</g>")
    g.append(f'<g font-size="17" fill="{INK}" font-weight="700"><text x="34" y="112">C-101</text><text x="108" y="112">C-102</text><text x="186" y="112">LAB</text><text x="34" y="232">C-104</text><text x="104" y="232">OFFICE</text><text x="182" y="232">C-106</text></g>')
    g.append(f'<g fill="{INK}" opacity=".75"><rect x="20" y="300" width="160" height="12"/><rect x="20" y="322" width="250" height="9"/><rect x="20" y="340" width="200" height="9"/><rect x="20" y="358" width="230" height="9"/></g>')
    g.append(f'<text x="20" y="44" font-family="Bebas" font-size="36" fill="{RED}" letter-spacing="2">FLOOR PLAN</text>')
    g.append("</g></svg>")
    return "\n".join(g)


def phone():
    return f"""<svg viewBox="0 0 360 520" xmlns="http://www.w3.org/2000/svg" font-family="Bebas">
<rect x="58" y="22" width="260" height="480" rx="40" fill="{INK}"/>
<rect x="44" y="10" width="260" height="480" rx="40" fill="{INK}" stroke="{INK}" stroke-width="6"/>
<rect x="60" y="30" width="228" height="440" rx="26" fill="#FBF6EA"/>
<rect x="74" y="50" width="200" height="64" fill="{RED}"/>
<text x="86" y="76" font-size="24" fill="{YEL}" letter-spacing="1">IN 12 M</text>
<text x="86" y="104" font-size="30" fill="{PAPER}" letter-spacing="1">STAIRS UP 2 FLOORS</text>
<g transform="translate(74,128)" stroke="{INK}" stroke-width="4.5" fill="none">
<rect width="200" height="250"/>
<line x1="78" y1="0" x2="78" y2="44"/><line x1="78" y1="70" x2="78" y2="140"/><line x1="78" y1="166" x2="78" y2="250"/>
<line x1="122" y1="0" x2="122" y2="28"/><line x1="122" y1="54" x2="122" y2="122"/><line x1="122" y1="148" x2="122" y2="250"/>
<line x1="0" y1="96" x2="78" y2="96"/><line x1="0" y1="186" x2="78" y2="186"/><line x1="122" y1="92" x2="200" y2="92"/><line x1="122" y1="178" x2="200" y2="178"/>
<rect x="80" y="2" width="40" height="34" fill="{YEL}" stroke="none"/>
<polyline points="100,214 100,30" stroke="{INK}" stroke-width="18" stroke-linecap="round"/>
<polyline points="100,214 100,30" stroke="{YEL}" stroke-width="9" stroke-linecap="round"/>
<circle cx="100" cy="214" r="17" fill="{RED}" stroke="{INK}" stroke-width="5"/>
</g>
<text x="74" y="420" font-size="30" fill="{INK}" letter-spacing="1">TO C-202 · 94 M</text>
<rect x="134" y="448" width="80" height="8" rx="4" fill="{INK}"/>
</svg>"""


def logo(size="100%"):
    return f"""<svg viewBox="0 0 200 200" width="{size}" height="{size}" xmlns="http://www.w3.org/2000/svg">
<rect x="14" y="14" width="186" height="186" rx="34" fill="{INK}"/>
<rect width="186" height="186" rx="34" fill="{RED}" stroke="{INK}" stroke-width="8"/>
<path d="M58,150 V92 a30,30 0 0 1 30,-30 H124" fill="none" stroke="{PAPER}" stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
<path d="M110,32 L142,62 L110,92" fill="none" stroke="{PAPER}" stroke-width="24" stroke-linecap="round" stroke-linejoin="round"/>
<circle cx="58" cy="150" r="15" fill="{YEL}" stroke="{INK}" stroke-width="7"/>
</svg>"""


ARROW = f"""<svg viewBox="0 0 160 90" class="arr"><path d="M10,52 C50,30 90,62 132,40" fill="none" stroke="{RED}" stroke-width="13" stroke-linecap="round"/>
<path d="M104,20 L140,38 L112,70" fill="none" stroke="{RED}" stroke-width="13" stroke-linecap="round" stroke-linejoin="round"/></svg>"""

STAMP = lambda big, small, rot, col=RED: f'<div class="stamp" style="transform: rotate({rot}deg); --c:{col}"><b>{big}</b><span>{small}</span></div>'


def frame(n, when, title, items, outcome, tag=None):
    tg = f'<div class="ftag">{tag}</div>' if tag else ""
    lis = "".join(f"<li>{i}</li>" for i in items)
    return f'<div class="frame">{tg}<div class="fn">{n}</div><div class="fw">{when}</div><h4>{title}</h4><ul>{lis}</ul><div class="fo">{outcome}</div></div>'


HTML = f"""<!doctype html><html><head><meta charset="utf-8"><style>
{FONTFACE}
@page {{ size: 22.5in 34.5in; margin: 0 }}
* {{ box-sizing: border-box; margin: 0; padding: 0 }}
html, body {{ width: 22.5in; height: 34.5in; background: {PAPER}; color: {INK}; -webkit-print-color-adjust: exact; print-color-adjust: exact; overflow: hidden }}
body {{ font-family: Narrow, sans-serif; position: relative }}
.grain {{ position: absolute; inset: 0; background: url('file://{HERE}/grain.png'); background-size: 100% 100%; mix-blend-mode: multiply; opacity: .55; pointer-events: none; z-index: 50 }}
.frameline {{ position: absolute; inset: .32in; border: 5px solid {INK}; pointer-events: none; z-index: 40 }}

/* ---------- hero ---------- */
.hero {{ position: relative; height: 11.95in; overflow: hidden; color: {PAPER} }}
.hero .burst {{ position: absolute; inset: 0 }}
.hero .burst svg {{ width: 100%; height: 100% }}
.hero .dots {{ position: absolute; inset: 0; background-image: radial-gradient({INK} 28%, transparent 31%); background-size: 22px 22px; opacity: .22;
  -webkit-mask-image: linear-gradient(180deg, #000 0%, transparent 55%, transparent 70%, #000 100%) }}
.topline {{ position: absolute; top: .62in; left: .85in; right: .85in; display: flex; justify-content: space-between; align-items: center; z-index: 3 }}
.pres {{ display: flex; align-items: center; gap: .3in }}
.pres .nu {{ width: 1.55in; height: 1.55in; border-radius: 50%; background: {PAPER}; border: 6px solid {INK}; display: flex; align-items: center; justify-content: center; box-shadow: 8px 8px 0 {INK} }}
.pres .nu img {{ width: 1.36in; height: 1.36in }}
.pres div {{ font-family: Elite; font-size: 27pt; line-height: 1.2; color: {PAPER}; text-shadow: 3px 3px 0 {INK} }}
.pres div b {{ font-family: Bebas; font-weight: 400; font-size: 46pt; letter-spacing: .06em; display: block; line-height: 1 }}
.pid {{ font-family: Bebas; font-size: 40pt; letter-spacing: .08em; background: {PAPER}; color: {INK}; padding: .06in .3in .02in; border: 6px solid {INK}; transform: rotate(3deg); box-shadow: 8px 8px 0 {INK} }}
.head {{ position: absolute; top: 2.3in; left: .85in; z-index: 2; font-family: Anton; line-height: .84; color: {PAPER}; text-shadow: 12px 12px 0 {INK} }}
.head .l1 {{ font-size: 236pt; letter-spacing: -.01em; display: block; position: relative }}
.head .l2 {{ font-size: 88pt; display: block; margin-top: .1in; letter-spacing: .005em }}
.tape {{ position: absolute; left: -.2in; top: .98in; width: 6.1in; transform: rotate(-7deg); background: {YEL}; color: {INK}; font-family: Bebas; font-size: 40pt;
  letter-spacing: .12em; text-align: center; padding: .1in 0 .03in; text-shadow: none; border-top: 5px solid {INK}; border-bottom: 5px solid {INK}; box-shadow: 10px 10px 0 {INK} }}
.hero .art {{ position: absolute; right: .25in; top: 1.85in; width: 10.4in; height: 9.8in; z-index: 1 }}
.hero .art svg {{ width: 100%; height: 100% }}
.hstats {{ position: absolute; left: .85in; top: 7.36in; width: 10.6in; z-index: 3; display: grid; grid-template-columns: 1fr 1fr; gap: .34in .36in }}
.hstats .k {{ font-family: Elite; font-size: 23pt; color: {PAPER}; text-shadow: 2px 2px 0 {INK}; grid-column: 1 / -1; margin-bottom: -.18in }}
.torn {{ position: absolute; left: 0; bottom: -1px; width: 100%; height: .95in; z-index: 4 }}

/* ---------- title ---------- */
.title {{ position: relative; display: flex; align-items: center; gap: .45in; padding: .02in .85in 0; margin-top: -.15in; z-index: 5 }}
.title .lg {{ width: 2.4in; height: 2.4in; flex: none }}
.title h1 {{ font-family: Anton; font-weight: 400; font-size: 236pt; line-height: .9; color: {RED}; letter-spacing: -.005em; text-shadow: 14px 14px 0 {INK} }}
.title .tl {{ font-family: Anton; font-size: 58pt; line-height: 1.02; text-transform: uppercase }}
.title .tl em {{ font-style: normal; color: {RED} }}
.badge {{ margin-left: auto; width: 3.3in; height: 3.3in; flex: none; border-radius: 50%; background: {RED}; color: {PAPER}; border: 7px solid {INK};
  box-shadow: 10px 10px 0 {INK}; display: flex; flex-direction: column; align-items: center; justify-content: center; text-align: center; transform: rotate(-9deg);
  outline: 4px dashed {PAPER}; outline-offset: -.24in }}
.badge b {{ font-family: Anton; font-weight: 400; font-size: 54pt; line-height: .95 }}
.badge span {{ font-family: Bebas; font-size: 30pt; letter-spacing: .08em; color: {YEL}; line-height: 1 }}
.title .tl small {{ display: block; font-family: Elite; font-size: 27pt; line-height: 1.3; margin-top: .14in; text-transform: none }}

.obj {{ margin: .2in .85in 0; background: {INK}; color: {PAPER}; padding: .26in .45in .28in; display: flex; gap: .4in; align-items: center; transform: rotate(-.6deg); box-shadow: 12px 12px 0 {RED} }}
.obj .lab {{ font-family: Bebas; font-size: 46pt; letter-spacing: .1em; color: {YEL}; flex: none; line-height: 1 }}
.obj p {{ font-family: Oswald; font-weight: 400; font-size: 31pt; line-height: 1.22 }}
.obj p b {{ font-weight: 700; color: {YEL} }}

/* ---------- sections ---------- */
.sec {{ margin: .3in .85in 0 }}
.kick {{ display: flex; align-items: baseline; gap: .3in; margin-bottom: .16in }}
.kick h2 {{ font-family: Anton; font-weight: 400; font-size: 54pt; line-height: 1; letter-spacing: .01em }}
.kick h2 em {{ font-style: normal; color: {RED} }}
.kick span {{ font-family: Elite; font-size: 25pt }}
.kick::after {{ content: ""; flex: 1; border-bottom: 6px solid {INK}; transform: translateY(-.12in) }}
.acts {{ display: grid; grid-template-columns: minmax(0,1fr) 1.0in minmax(0,1fr) 1.0in minmax(0,1fr); align-items: start }}
.act .pic {{ height: 2.15in; display: flex; align-items: center; justify-content: center }}
.act .pic svg {{ height: 100%; max-width: 100% }}
.arr {{ width: 1.0in; margin-top: .9in }}
.act .an {{ font-family: Bebas; font-size: 34pt; letter-spacing: .1em; color: {RED}; margin-top: .1in; line-height: 1 }}
.act h3 {{ font-family: Anton; font-weight: 400; font-size: 42pt; line-height: 1.02; text-transform: uppercase }}
.act ul, .frame ul {{ list-style: none }}
.act li {{ font-size: 25pt; line-height: 1.22; margin-top: .07in; padding-left: .34in; position: relative }}
.act li::before {{ content: "■"; position: absolute; left: 0; top: .02in; color: {RED}; font-size: 20pt }}

.stats {{ display: flex; justify-content: space-between; margin: .38in .95in 0 }}
.stamp {{ --c: {RED}; border: 7px solid var(--c); outline: 3px solid {PAPER}; outline-offset: 5px; color: var(--c); padding: .12in .2in .1in; background: {PAPER};
  display: flex; align-items: center; gap: .2in; box-shadow: 10px 10px 0 {INK} }}
.stamp b {{ font-family: Anton; font-weight: 400; font-size: 62pt; line-height: 1; color: {RED}; flex: none }}
.stamp span {{ font-family: Bebas; font-size: 27pt; letter-spacing: .04em; line-height: 1.04; color: {INK}; white-space: nowrap }}

.strip {{ background: {INK}; padding: .48in .38in; position: relative; display: grid; grid-template-columns: repeat(4, minmax(0,1fr)); gap: .3in }}
.strip::before, .strip::after {{ content: ""; position: absolute; left: .2in; right: .2in; height: .2in;
  background: repeating-linear-gradient(90deg, {PAPER} 0 .26in, transparent .26in .52in); border-radius: 4px }}
.strip::before {{ top: .15in }} .strip::after {{ bottom: .15in }}
.frame {{ background: #F6EEDC; padding: .22in .26in .26in; position: relative; min-height: 2.75in }}
.frame .fn {{ font-family: Anton; font-size: 64pt; line-height: .9; color: {RED}; float: left; margin-right: .16in }}
.frame .fw {{ font-family: Bebas; font-size: 27pt; letter-spacing: .06em; line-height: 1.05; padding-top: .04in }}
.frame h4 {{ font-family: Anton; font-weight: 400; font-size: 36pt; line-height: 1.02; text-transform: uppercase; clear: both; margin-top: .1in }}
.frame li {{ font-size: 23pt; line-height: 1.2; margin-top: .05in; padding-left: .3in; position: relative }}
.frame li::before {{ content: "→"; position: absolute; left: 0; color: {RED}; font-weight: 700 }}
.frame .fo {{ margin-top: .14in; padding-top: .1in; border-top: 4px dashed {INK}; font-family: Narrow; font-weight: 700; font-size: 23pt; line-height: 1.18 }}
.ftag {{ position: absolute; top: -.36in; right: -.1in; z-index: 2; font-family: Bebas; font-size: 30pt; letter-spacing: .08em; padding: .03in .2in 0; background: {RED}; color: {PAPER}; transform: rotate(6deg); border: 4px solid {INK} }}
.ftag.y {{ background: {YEL}; color: {INK} }}
.small {{ font-family: Elite; font-size: 21pt; margin-top: .12in }}

/* ---------- credits ---------- */
.credits {{ margin: .26in .85in 0; text-align: center; font-family: Bebas; line-height: 1; border-top: 6px solid {INK}; padding-top: .26in }}
.credits .row {{ display: flex; justify-content: center; align-items: baseline; gap: .26in; flex-wrap: wrap; margin-top: .08in }}
.credits .lab {{ font-size: 30pt; letter-spacing: .1em; color: {RED} }}
.credits .nm {{ font-size: 54pt; letter-spacing: .02em }}
.credits .nm small {{ font-family: Narrow; font-size: 22pt; letter-spacing: 0; font-weight: 700; margin-left: .06in; vertical-align: .14in }}
.credits .dot {{ font-size: 40pt; color: {RED} }}
.credits .tools {{ font-size: 25pt; letter-spacing: .035em; line-height: 1.14; max-width: 20in; margin: .1in auto 0 }}
.credits .tools .lab {{ margin-right: .14in }}
.foot {{ position: absolute; left: .85in; right: .85in; bottom: .5in; display: flex; justify-content: space-between; align-items: flex-end; font-family: Bebas; font-size: 34pt; letter-spacing: .08em }}
.foot .cs {{ font-family: Anton; font-size: 46pt; letter-spacing: .02em; color: {RED}; line-height: 1 }}
.foot .cs small {{ display: block; font-family: Elite; font-size: 22pt; color: {INK}; letter-spacing: 0; margin-top: .06in }}
</style></head><body>
<div class="grain"></div><div class="frameline"></div>

<div class="hero">
  <div class="burst">{sunburst(2160, 1147, 1500, 540)}</div>
  <div class="dots"></div>
  <div class="topline">
    <div class="pres"><div class="nu"><img src="file://{HERE}/nu_logo.png"></div><div><b>FAST NUCES · ISLAMABAD CAMPUS</b>School of Computing presents a Final Year Project</div></div>
    <div class="pid">PROJECT {PID}</div>
  </div>
  <div class="head"><span class="l1">GPS<div class="tape">NO SIGNAL INDOORS</div></span><span class="l2">STOPS AT<br>THE DOOR.</span></div>
  <div class="art">{building()}</div>
  <div class="hstats"><div class="k">Progress at mid evaluation:</div>
    {STAMP("14", "CAMPUS FLOORS<br>MAPPED FROM ONE PDF", -3, INK)}
    {STAMP("200/200", "ROUTES FOUND ACROSS<br>FLOORS AND BLOCKS", 2, INK)}
    {STAMP("11/12", "TEST PLANS CORRECT<br>IN 6 DRAWING STYLES", 2, INK)}
    {STAMP("145", "AUTOMATED TESTS<br>PASSING (MAPPER)", -2, INK)}
  </div>
  {torn()}
</div>

<div class="title">
  <div class="lg">{logo()}</div>
  <h1>TURN</h1>
  <div class="tl">takes it<br><em>from here.</em><small>Indoor navigation from any floor plan.<br>No beacons. No new hardware.</small></div>
  <div class="badge"><span>ONE PHONE.</span><b>ZERO<br>BEACONS.</b><span>ANY PLAN.</span></div>
</div>

<div class="obj"><div class="lab">OBJECTIVE</div><p>Turn a building's ordinary floor plan into <b>turn-by-turn indoor navigation</b> on an Android phone, using only the phone's own sensors and the Wi&#8209;Fi already in the building.</p></div>

<div class="sec">
  <div class="kick"><h2>THE PLOT <em>· IN THREE ACTS</em></h2><span>system architecture</span></div>
  <div class="acts">
    <div class="act"><div class="pic">{plan_sheet()}</div><div class="an">ACT I · INPUT</div><h3>Any floor plan</h3><ul><li>PDF, scan, photo or CAD</li><li>One floor or a whole campus</li></ul></div>
    {ARROW}
    <div class="act"><div class="pic">{building(cx=430, cy=600, gap=190, k=1.15, label=False, pin=False, vb="40 40 820 760", sw=1.15)}</div><div class="an">ACT II · TURN-MAPPER</div><h3>Plan becomes map</h3><ul><li>Walls, rooms, doors, labels</li><li>Route graph in metres, floors linked</li><li>Checked by a person in TURN Studio</li></ul></div>
    {ARROW}
    <div class="act"><div class="pic">{phone()}</div><div class="an">ACT III · TURN APP</div><h3>Phone finds its way</h3><ul><li>Steps + compass + Wi&#8209;Fi fingerprints</li><li>Particle filter → live blue dot</li><li>Shortest route, turn by turn</li></ul></div>
  </div>
</div>


<div class="sec">
  <div class="kick"><h2>THE SCHEDULE <em>· FOUR ITERATIONS</em></h2><span>each one ships a working outcome</span></div>
  <div class="strip">
    {frame("01", "AUG – SEP 2026", "One floor, end to end", ["Import plan, set scale", "Survey Wi&#8209;Fi, A* route"], "Android prototype on one real floor", "DONE")}
    {frame("02", "OCT – NOV 2026", "Automatic maps", ["Plan → rooms, doors, paths", "Routes across floors + blocks"], "14 floors, 3 blocks joined + TURN Studio", "NOW SHOWING")}
    {frame("03", "DEC 2026 – FEB 2027", "App meets map", ["App imports map package", "Tracking tuned on site"], "Live navigation in one building")}
    {frame("04", "MAR – MAY 2027", "Campus pilot", ["Routes between blocks", "Accuracy + effort study"], "Campus pilot + final evaluation")}
  </div>
  <div class="small">Every iteration: plan → build → test on real floors → supervisor review. Iterations 3 and 4 are tentative.</div>
</div>

<div class="credits">
  <div class="row"><span class="lab">STARRING</span>
    <span class="nm">ZAKI NABEEL<small>23I-0508</small></span><span class="dot">✦</span>
    <span class="nm">SHEHRYAR FAISAL<small>23I-0604</small></span><span class="dot">✦</span>
    <span class="nm">MUHAMMAD SAMEER<small>23I-0634</small></span></div>
  <div class="row"><span class="lab">SUPERVISOR</span><span class="nm">{SUP.upper()} SHAMS FAROOQ</span></div>
  <div class="tools"><span class="lab">DELIVERABLES</span>ANDROID APP · TURN-MAPPER · TURN STUDIO · .TURNMAP FORMAT · FIELD STUDY · REPORT + DEMO</div>
  <div class="tools"><span class="lab">BUILT WITH</span>KOTLIN · JETPACK COMPOSE · PYTHON · OPENCV · TESSERACT OCR · PYTORCH U-NET · SHAPELY · NETWORKX · FASTAPI · PARTICLE FILTER · PDR · A* · GIT</div>
</div>

<div class="foot">
  <div class="cs">COMING TO A CORRIDOR NEAR YOU<small>FAST NUCES, Islamabad Campus · FYP 2026–27</small></div>
  <div>{PID} · TURN</div>
</div>
</body></html>"""

(HERE / "poster2.html").write_text(HTML)


async def main():
    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        b = await p.chromium.launch()
        pg = await b.new_page(viewport={"width": 2160, "height": 3312})
        await pg.goto(f"file://{HERE / 'poster2.html'}")
        await pg.evaluate("document.fonts.ready")
        info = await pg.evaluate(
            """() => { const r = s => document.querySelector(s).getBoundingClientRect();
              return {credits_bottom: r('.credits').bottom, foot_top: r('.foot').top, page: 3312,
                      fonts: [...document.fonts].map(f => f.family + ':' + f.status)} }"""
        )
        print(info)
        await pg.pdf(path=str(OUT), width="22.5in", height="34.5in", print_background=True, prefer_css_page_size=True)
        await b.close()


asyncio.run(main())
print(OUT)
