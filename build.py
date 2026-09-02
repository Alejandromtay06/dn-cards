#!/usr/bin/env python3
"""Build the digital business card site.

Reads people.json, then writes for every person:
  <slug>/index.html      the card page (DNI or Crystal design system)
  <slug>/<slug>.vcf      vCard for "Save contact"
  qr/<slug>.svg          QR code -> card URL, brand colour, for the printed card
  qr/<slug>.png          same, 2048 px, transparent background
  qr/<slug>-black.png    same, black, transparent background
and the root index.html directory page.

Usage:  python build.py
Deps:   pip install segno
"""
from __future__ import annotations

import base64
import html
import io
import json
import pathlib
import re

import segno

ROOT = pathlib.Path(__file__).resolve().parent
CFG = json.loads((ROOT / "people.json").read_text(encoding="utf-8"))
BASE = CFG["base_url"].rstrip("/")

BRAND_INK = {"dni": "#263E56", "crystal": "#413C7C"}  # Silk Dark, Deep Midnight


def esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


# ----------------------------------------------------------------------------
# vCard
# ----------------------------------------------------------------------------
def vcard(p: dict, url: str) -> str:
    def v(s):  # escape vCard text values
        return (s or "").replace("\\", "\\\\").replace(",", "\\,").replace(";", "\\;").replace("\n", "\\n")

    lines = ["BEGIN:VCARD", "VERSION:3.0"]
    lines.append(f"N:{v(p['last'])};{v(p['first'])};;;")
    lines.append(f"FN:{v(p['first'] + ' ' + p['last'])}")
    lines.append(f"ORG:{v(p['org'])}" + (f";{v(p['org_parent'])}" if p.get("org_parent") else ""))
    lines.append(f"TITLE:{v(p['title'])}")
    if p.get("phone_e164"):
        lines.append(f"TEL;TYPE=CELL,VOICE:{p['phone_e164']}")
    lines.append(f"EMAIL;TYPE=INTERNET,WORK:{p['email']}")
    if p.get("website"):
        lines.append(f"URL;TYPE=WORK:https://{p['website']}")
    if p.get("address"):
        a = p["address"]
        lines.append(
            f"ADR;TYPE=WORK:;;{v(a['street'])};{v(a['city'])};{v(a['state'])};{v(a['zip'])};{v(a['country'])}"
        )
    lines.append(f"URL;TYPE=PROFILE:{url}")
    if p.get("tagline"):
        lines.append(f"NOTE:{v(p['tagline'])}")
    lines.append("END:VCARD")
    return "\r\n".join(lines) + "\r\n"


# ----------------------------------------------------------------------------
# QR codes
# ----------------------------------------------------------------------------
def make_qr(url: str, slug: str, ink: str) -> str:
    """Write the print files and return an inline SVG (brand colour) for the page."""
    q = segno.make(url, error="q")  # 25% redundancy, plenty for print at card size
    out = ROOT / "qr"
    out.mkdir(exist_ok=True)
    q.save(str(out / f"{slug}.svg"), scale=20, border=2, dark=ink, light=None)
    q.save(str(out / f"{slug}.png"), scale=-(-2048 // (q.symbol_size(border=2)[0])), border=2, dark=ink, light=None)
    q.save(str(out / f"{slug}-black.png"), scale=-(-2048 // (q.symbol_size(border=2)[0])), border=2, dark="#000000", light=None)
    buf = io.BytesIO()
    q.save(buf, kind="svg", scale=1, border=0, dark=ink, light=None, xmldecl=False, svgclass=None, lineclass=None)
    svg = buf.getvalue().decode("utf-8")
    n = q.symbol_size(scale=1, border=0)[0]
    svg = re.sub(r'\s(width|height)="[^"]*"', "", svg, count=2)
    svg = svg.replace(
        "<svg ",
        f'<svg role="img" aria-label="QR code for this card" viewBox="0 0 {n} {n}" width="100%" height="100%" shape-rendering="crispEdges" ',
        1,
    )
    return svg


# ----------------------------------------------------------------------------
# Shared script: Web Share with copy-link fallback
# ----------------------------------------------------------------------------
SHARE_JS = """
(function(){
  var b=document.getElementById('share'); if(!b) return;
  var url=location.href.split('#')[0], title=document.title, label=b.textContent;
  b.addEventListener('click', function(){
    if(navigator.share){ navigator.share({title:title,url:url}).catch(function(){}); return; }
    var done=function(){ b.textContent='Link copied'; setTimeout(function(){ b.textContent=label; },2200); };
    if(navigator.clipboard){ navigator.clipboard.writeText(url).then(done, function(){ prompt('Copy this link', url); }); }
    else { prompt('Copy this link', url); }
  });
})();
"""


def rows_html(p: dict, cls: str) -> str:
    """Contact rows. cls names the design system so the label copy follows its casing rules."""
    rows = []
    lab = (lambda s: s.upper()) if cls == "dni" else (lambda s: s)
    if p.get("tagline"):
        rows.append(f'<li class="row static"><span class="k">{esc(lab("Focus"))}</span><span class="v">{esc(p["tagline"])}</span></li>')
    rows.append(
        f'<li><a class="row" href="mailto:{esc(p["email"])}"><span class="k">{esc(lab("Email"))}</span><span class="v">{esc(p["email"])}</span><span class="go" aria-hidden="true">→</span></a></li>'
    )
    if p.get("phone_e164"):
        rows.append(
            f'<li><a class="row" href="tel:{esc(p["phone_e164"])}"><span class="k">{esc(lab(p.get("phone_label") or "Phone"))}</span><span class="v">{esc(p["phone_display"])}</span><span class="go" aria-hidden="true">→</span></a></li>'
        )
    if p.get("website"):
        rows.append(
            f'<li><a class="row" href="https://{esc(p["website"])}" target="_blank" rel="noopener"><span class="k">{esc(lab("Web"))}</span><span class="v">{esc(p["website"])}</span><span class="go" aria-hidden="true">→</span></a></li>'
        )
    if p.get("address"):
        a = p["address"]
        full = f"{a['street']}, {a['city']}, {a['state']} {a['zip']}"
        maps = "https://maps.google.com/?q=" + full.replace(" ", "+")
        rows.append(
            f'<li><a class="row" href="{esc(maps)}" target="_blank" rel="noopener"><span class="k">{esc(lab("Office"))}</span><span class="v">{esc(a["street"]).replace(", ", "<br>")}<br>{esc(a["city"])}, {esc(a["state"])} {esc(a["zip"])}</span><span class="go" aria-hidden="true">→</span></a></li>'
        )
    return "\n".join(rows)


# ----------------------------------------------------------------------------
# DNI page — dni-style-guide.html tokens (Feb 2026)
# ----------------------------------------------------------------------------
DNI_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex">
<meta name="theme-color" content="#263E56">
<title>{{NAME}} · {{ORG}}</title>
<meta name="description" content="{{NAME}}, {{TITLE}} at {{ORG}}. Save the contact or get in touch.">
<meta property="og:title" content="{{NAME}} · {{ORG}}">
<meta property="og:description" content="{{TITLE}} · {{ORG}}">
<meta property="og:type" content="profile">
<meta property="og:url" content="{{URL}}">
<link rel="icon" href="../assets/dni-mark-light.png">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@125,500;125,700&family=Inter:wght@300;400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root{
    --mine-dark:#0E1014; --mine-medium:#161A20; --mine-light:#1E232B;
    --silk-dark:#263E56; --silk-medium:#3B5D7F; --silk-light:#8CA5BD;
    --sand-light:#F8F3F0; --sand-dark:#F0E7E0; --white:#FFFFFF;
    --leaf-medium:#626C51;
    --rule:rgba(14,16,20,.14); --rule-dark:rgba(248,243,240,.20);
    --font-display:"Aeonik Pro Extended","Archivo","Helvetica Neue",Arial,sans-serif;
    --font-body:"Aeonik Pro","Inter","Helvetica Neue",Arial,sans-serif;
    --font-mono:"Aeonik Mono","JetBrains Mono",ui-monospace,monospace;
    --fast:160ms; --base:320ms; --ease:cubic-bezier(.2,0,0,1);
    --margin:20px;
  }
  *{box-sizing:border-box; margin:0; padding:0}
  html{-webkit-text-size-adjust:100%}
  body{background:var(--sand-dark); color:var(--mine-dark); font-family:var(--font-body); font-size:16px; line-height:1.6; font-weight:400; -webkit-font-smoothing:antialiased; min-height:100vh}
  a{color:inherit; text-decoration:none}
  :where(a,button,[tabindex]):focus-visible{outline:2px solid var(--silk-medium); outline-offset:2px}
  .card{max-width:480px; margin:0 auto; min-height:100vh; background:var(--sand-light); border-left:1px solid var(--rule); border-right:1px solid var(--rule); display:flex; flex-direction:column}
  @media (min-width:520px){ body{padding:48px 0} .card{min-height:0; border:1px solid var(--rule)} }

  .rail{display:flex; align-items:center; justify-content:space-between; gap:16px; padding:18px var(--margin); background:var(--silk-dark); border-bottom:1px solid var(--rule-dark)}
  .rail img{display:block; height:30px; width:auto}
  .rail .idx{font-family:var(--font-mono); font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--silk-light)}

  .hero{background:var(--silk-dark); color:var(--sand-light); padding:40px var(--margin) 36px; position:relative; overflow:hidden}
  .hero .eyebrow{font-family:var(--font-mono); font-weight:500; font-size:12px; letter-spacing:.12em; text-transform:uppercase; color:var(--silk-light); margin-bottom:28px}
  .hero h1{font-family:var(--font-display); font-weight:700; font-variation-settings:"wdth" 125; font-size:40px; line-height:.98; letter-spacing:-.02em; color:var(--sand-light)}
  .hero .title{margin-top:18px; font-size:16px; line-height:1.4; color:var(--sand-light)}
  .hero .org{font-size:14px; color:var(--silk-light); margin-top:4px}
  .hero .mark{position:absolute; right:-6px; bottom:-14px; width:132px; height:132px; fill:var(--sand-light); opacity:.07; pointer-events:none}

  .rows{list-style:none; border-bottom:1px solid var(--rule)}
  .row{display:grid; grid-template-columns:72px 1fr auto; align-items:baseline; gap:16px; padding:18px var(--margin); border-top:1px solid var(--rule); min-height:64px; transition:background var(--fast) var(--ease)}
  a.row:hover{background:var(--sand-dark)}
  .row .k{font-family:var(--font-mono); font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--leaf-medium); padding-top:3px}
  .row .v{font-size:16px; color:var(--mine-dark); overflow-wrap:anywhere}
  .row.static .v{font-family:var(--font-display); font-weight:500; font-variation-settings:"wdth" 125; letter-spacing:-.01em; font-size:17px}
  .row .go{font-family:var(--font-mono); color:var(--silk-medium); font-size:14px}

  .actions{display:grid; grid-template-columns:1fr 1fr; gap:1px; padding:var(--margin); background:var(--sand-light)}
  .btn{font-family:var(--font-body); font-size:14px; font-weight:500; padding:16px 20px; border:1px solid transparent; cursor:pointer; text-align:center; min-height:48px; transition:background var(--fast) var(--ease),color var(--fast) var(--ease)}
  .btn-primary{background:var(--silk-dark); color:var(--sand-light)}
  .btn-primary:hover{background:var(--mine-light)}
  .btn-secondary{background:transparent; color:var(--silk-dark); border-color:var(--silk-dark)}
  .btn-secondary:hover{background:rgba(38,62,86,.08)}

  .share{padding:8px var(--margin) 32px; display:grid; grid-template-columns:1fr 112px; gap:20px; align-items:center; border-top:1px solid var(--rule)}
  .share .eyebrow{font-family:var(--font-mono); font-weight:500; font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--leaf-medium); margin:24px 0 10px}
  .share p{font-size:14px; color:var(--mine-medium); max-width:34ch}
  .share .qr{width:112px; height:112px; margin-top:24px; padding:8px; background:var(--white); border:1px solid var(--rule)}
  .share .qr svg{display:block; width:100%; height:100%}

  footer{margin-top:auto; padding:20px var(--margin) calc(20px + env(safe-area-inset-bottom)); background:var(--silk-dark); color:var(--silk-light); font-size:12px; line-height:1.5; display:flex; flex-direction:column; gap:4px; border-top:1px solid var(--rule-dark)}
  footer .fig{font-family:var(--font-mono); letter-spacing:.06em}
  @media (prefers-reduced-motion: reduce){ *{transition:none !important} }
</style>
</head>
<body>
<svg width="0" height="0" style="position:absolute" aria-hidden="true">
  <symbol id="dni" viewBox="0 0 200 200">
    <path d="M0 0 L0 200 L100 200 C155.23 144.77 155.23 55.23 100 0 Z"/>
    <path fill-rule="evenodd" d="M100 0 L200 100 L100 200 L200 200 L200 0 Z"/>
  </symbol>
</svg>
<main class="card">
  <header class="rail">
    <img src="../assets/dni-lockup-light.png" alt="Diamond National Investments">
    <span class="idx">Contact card</span>
  </header>

  <section class="hero">
    <div class="eyebrow">Digital business card</div>
    <h1>{{FIRST}}<br>{{LAST}}</h1>
    <div class="title">{{TITLE}}</div>
    <div class="org">{{ORG}}</div>
    <svg class="mark" aria-hidden="true"><use href="#dni"/></svg>
  </section>

  <ul class="rows">
{{ROWS}}
  </ul>

  <div class="actions">
    <a class="btn btn-primary" href="{{VCF}}" download="{{VCF}}">Save contact</a>
    <button class="btn btn-secondary" id="share" type="button">Share this card</button>
  </div>

  <section class="share">
    <div>
      <div class="eyebrow">Scan to open</div>
      <p>Point a phone camera at the code to open this card on another device.</p>
    </div>
    <div class="qr">{{QR}}</div>
  </section>

  <footer>
    <span>{{ORG}}</span>
    <span class="fig">{{TAGLINE}}</span>
  </footer>
</main>
<script>{{JS}}</script>
</body>
</html>
"""

# ----------------------------------------------------------------------------
# Crystal page — crystal-tokens.css / crystal-design-system.md (Apr 2026)
# ----------------------------------------------------------------------------
CRYSTAL_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex">
<meta name="theme-color" content="#413C7C">
<title>{{NAME}} · {{ORG}}</title>
<meta name="description" content="{{NAME}}, {{TITLE}} at {{ORG}}. Save the contact or get in touch.">
<meta property="og:title" content="{{NAME}} · {{ORG}}">
<meta property="og:description" content="{{TITLE}} · {{ORG}}">
<meta property="og:type" content="profile">
<meta property="og:url" content="{{URL}}">
<link rel="icon" href="../assets/crystal-icon.svg" type="image/svg+xml">
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root{
    --alabaster:#FAF5EF; --silver:#DBDAE2; --midnight:#413C7C; --obsidian:#24212A; --white:#FFFFFF;
    --periwinkle:#B8B9DE; --midnight-deep:#322E60; --midnight-wash:#EAE9F2; --slate-ink:#6E6A7E; --orchid:#BF77F5;
    --rule:#DBDAE2; --rule-dark:rgba(250,245,239,.20);
    --sans:"Aeonik Pro","Inter","Helvetica Neue",Arial,sans-serif;
    --mono:"Aeonik Mono","JetBrains Mono",ui-monospace,monospace;
    --fast:200ms; --base:400ms; --ease:cubic-bezier(.22,1,.36,1);
    --margin:20px;
  }
  *{box-sizing:border-box; margin:0; padding:0}
  html{-webkit-text-size-adjust:100%}
  body{background:var(--midnight-wash); color:var(--obsidian); font-family:var(--sans); font-size:16px; line-height:1.6; font-weight:400; -webkit-font-smoothing:antialiased; min-height:100vh}
  a{color:inherit; text-decoration:none}
  :where(a,button,[tabindex]):focus-visible{outline:2px solid var(--orchid); outline-offset:2px}
  .card{max-width:480px; margin:0 auto; min-height:100vh; background:var(--alabaster); border-left:1px solid var(--rule); border-right:1px solid var(--rule); display:flex; flex-direction:column}
  @media (min-width:520px){ body{padding:48px 0} .card{min-height:0; border:1px solid var(--rule)} }

  .rail{display:flex; align-items:center; justify-content:space-between; gap:16px; padding:18px var(--margin); background:var(--midnight); border-bottom:1px solid var(--rule-dark)}
  .rail svg{display:block; height:26px; width:auto}
  .rail .idx{font-family:var(--mono); font-size:13px; letter-spacing:.02em; color:var(--periwinkle)}

  .hero{background:var(--midnight); color:var(--alabaster); padding:40px var(--margin) 36px; position:relative; overflow:hidden}
  .hero .eyebrow{font-family:var(--mono); font-size:13px; letter-spacing:.02em; line-height:1.2; color:var(--periwinkle); margin-bottom:28px}
  .hero h1{font-family:var(--sans); font-weight:500; font-size:34px; line-height:1.06; letter-spacing:-.02em; color:var(--alabaster)}
  .hero .title{margin-top:16px; font-size:16px; line-height:1.4; color:var(--alabaster)}
  .hero .org{font-size:14px; color:var(--periwinkle); margin-top:4px}
  .hero .wm{position:absolute; left:58%; bottom:-22px; width:360px; height:auto; pointer-events:none}
  .hero .wm path{fill:var(--alabaster); fill-opacity:.07}

  .rows{list-style:none; border-bottom:1px solid var(--rule)}
  .row{display:grid; grid-template-columns:64px 1fr auto; align-items:baseline; gap:16px; padding:18px var(--margin); border-top:1px solid var(--rule); min-height:64px; transition:background var(--fast) var(--ease)}
  a.row:hover{background:var(--midnight-wash)}
  .row .k{font-family:var(--mono); font-size:13px; letter-spacing:.02em; color:var(--slate-ink); padding-top:2px}
  .row .v{font-size:16px; color:var(--obsidian); overflow-wrap:anywhere}
  .row .go{font-family:var(--mono); color:var(--midnight); font-size:14px}

  .actions{display:grid; grid-template-columns:1fr 1fr; gap:1px; padding:var(--margin)}
  .btn{font-family:var(--sans); font-size:14px; font-weight:500; padding:16px 20px; border:1px solid transparent; cursor:pointer; text-align:center; min-height:48px; transition:background var(--fast) var(--ease),color var(--fast) var(--ease)}
  .btn-primary{background:var(--midnight); color:var(--alabaster)}
  .btn-primary:hover{background:var(--midnight-deep)}
  .btn-secondary{background:transparent; color:var(--midnight); border-color:var(--midnight)}
  .btn-secondary:hover{background:rgba(65,60,124,.08)}

  .share{padding:8px var(--margin) 32px; display:grid; grid-template-columns:1fr 112px; gap:20px; align-items:center; border-top:1px solid var(--rule)}
  .share .eyebrow{font-family:var(--mono); font-size:13px; letter-spacing:.02em; color:var(--slate-ink); margin:24px 0 10px}
  .share p{font-size:14px; color:var(--obsidian); max-width:34ch}
  .share .qr{width:112px; height:112px; margin-top:24px; padding:8px; background:var(--white); border:1px solid var(--rule)}
  .share .qr svg{display:block; width:100%; height:100%}

  footer{margin-top:auto; padding:20px var(--margin) calc(20px + env(safe-area-inset-bottom)); background:var(--midnight); color:var(--periwinkle); font-size:13px; line-height:1.5; display:flex; flex-direction:column; gap:4px; border-top:1px solid var(--rule-dark)}
  footer .fig{font-family:var(--mono); letter-spacing:.02em}
  @media (prefers-reduced-motion: reduce){ *{transition:none !important} }
</style>
</head>
<body>
<main class="card">
  <header class="rail">
    <svg viewBox="0 0 562.24 226.47" role="img" aria-label="Crystal">
      <g><path fill="#FAF5EF" d="M67.68 113.24 L113.24 0 L0 113.24 Z"/><path fill="#B8B9DE" d="M67.68 113.24 L113.24 226.47 L0 113.24 Z"/></g>
      <g fill="#FAF5EF">{{WORDMARK}}</g>
    </svg>
    <span class="idx">Contact card</span>
  </header>

  <section class="hero">
    <div class="eyebrow">Digital business card</div>
    <h1>{{FIRST}}<br>{{LAST}}</h1>
    <div class="title">{{TITLE}}</div>
    <div class="org">{{ORG}}{{ORG_PARENT}}</div>
    <svg class="wm" viewBox="120 30 450 170" aria-hidden="true">{{WORDMARK}}</svg>
  </section>

  <ul class="rows">
{{ROWS}}
  </ul>

  <div class="actions">
    <a class="btn btn-primary" href="{{VCF}}" download="{{VCF}}">Save contact</a>
    <button class="btn btn-secondary" id="share" type="button">Share this card</button>
  </div>

  <section class="share">
    <div>
      <div class="eyebrow">Scan to open</div>
      <p>Point a phone camera at the code to open this card on another device.</p>
    </div>
    <div class="qr">{{QR}}</div>
  </section>

  <footer>
    <span>{{ORG_FOOT}}</span>
    <span class="fig">Where every day feels like a getaway.</span>
  </footer>
</main>
<script>{{JS}}</script>
</body>
</html>
"""

INDEX_TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Diamond National · Contact cards</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap" rel="stylesheet">
<style>
  :root{--ink:#0E1014; --brand:#263E56; --muted:#626C51; --ground:#F8F3F0; --rule:rgba(14,16,20,.14); --sans:"Inter","Helvetica Neue",Arial,sans-serif; --mono:"JetBrains Mono",ui-monospace,monospace}
  *{box-sizing:border-box; margin:0; padding:0}
  body{background:var(--ground); color:var(--ink); font-family:var(--sans); font-size:16px; line-height:1.6; padding:48px 20px}
  main{max-width:480px; margin:0 auto}
  .eyebrow{font-family:var(--mono); font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--muted); margin-bottom:12px}
  h1{font-size:24px; font-weight:500; letter-spacing:-.01em; margin-bottom:24px}
  ul{list-style:none; border-top:1px solid var(--rule)}
  a{display:flex; justify-content:space-between; gap:16px; padding:16px 0; border-bottom:1px solid var(--rule); color:inherit; text-decoration:none}
  a:hover{background:rgba(38,62,86,.05)}
  a .t{color:var(--muted); font-size:14px}
  a .b{font-family:var(--mono); font-size:11px; letter-spacing:.12em; text-transform:uppercase; color:var(--brand); align-self:center}
  p{margin-top:24px; font-size:13px; color:var(--muted)}
</style>
</head>
<body>
<main>
  <div class="eyebrow">Diamond National</div>
  <h1>Contact cards</h1>
  <ul>
{{ITEMS}}
  </ul>
  <p>Each card has its own link and QR code. Scan the code on a printed card to open it.</p>
</main>
</body>
</html>
"""


def wordmark_paths() -> str:
    svg = (ROOT / "assets" / "crystal-lockup.svg").read_text(encoding="utf-8")
    g = re.search(r'<g id="crystal-wordmark"[^>]*>(.*?)</g>', svg, re.S).group(1)
    return g.strip()


def build_person(p: dict) -> dict:
    slug = p["slug"]
    url = f"{BASE}/{slug}/"
    out = ROOT / slug
    out.mkdir(exist_ok=True)
    vcf_name = f"{slug}.vcf"
    (out / vcf_name).write_text(vcard(p, url), encoding="utf-8", newline="")

    ink = BRAND_INK[p["brand"]]
    qr_svg = make_qr(url, slug, ink)
    name = f"{p['first']} {p['last']}"

    tpl = DNI_TEMPLATE if p["brand"] == "dni" else CRYSTAL_TEMPLATE
    page = (
        tpl.replace("{{NAME}}", esc(name))
        .replace("{{FIRST}}", esc(p["first"]))
        .replace("{{LAST}}", esc(p["last"]))
        .replace("{{TITLE}}", esc(p["title"]))
        .replace("{{ORG_PARENT}}", (" · " + esc(p["org_parent"])) if p.get("org_parent") else "")
        .replace("{{ORG_FOOT}}", esc(p.get("org_parent") or p["org"]))
        .replace("{{ORG}}", esc(p["org"]))
        .replace("{{TAGLINE}}", esc(p.get("tagline") or ""))
        .replace("{{URL}}", esc(url))
        .replace("{{VCF}}", esc(vcf_name))
        .replace("{{ROWS}}", rows_html(p, p["brand"]))
        .replace("{{QR}}", qr_svg)
        .replace("{{WORDMARK}}", wordmark_paths())
        .replace("{{JS}}", SHARE_JS.strip())
    )
    (out / "index.html").write_text(page, encoding="utf-8")
    return {"name": name, "title": p["title"], "org": p["org"], "slug": slug, "url": url}


def main() -> None:
    built = [build_person(p) for p in CFG["people"]]
    items = "\n".join(
        f'    <li><a href="{b["slug"]}/"><span><span>{esc(b["name"])}</span><br><span class="t">{esc(b["title"])}</span></span><span class="b">{esc(b["org"])}</span></a></li>'
        for b in built
    )
    (ROOT / "index.html").write_text(INDEX_TEMPLATE.replace("{{ITEMS}}", items), encoding="utf-8")
    for b in built:
        print(f"{b['name']:<22} {b['url']}")


if __name__ == "__main__":
    main()
