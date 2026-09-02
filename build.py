#!/usr/bin/env python3
"""Build the digital business card site.

Reads people.json, then writes for every person:
  <slug>/index.html      the card page (DNI or Crystal tokens, shared layout)
  <slug>/<slug>.vcf      vCard for "Save contact" (with photo when available)
  qr/<slug>.svg          QR code -> card URL, brand colour, for the printed card
  qr/<slug>.png          same, ~2050 px, transparent background
  qr/<slug>-black.png    same, black, transparent background
and the root index.html directory page.

Photos: assets/<slug>.jpg (square hero) and assets/<slug>-vcf.jpg (240 px, embedded in the vCard).

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


def esc(s: str | None) -> str:
    return html.escape(s or "", quote=True)


# ----------------------------------------------------------------------------
# Brand tokens (from dni-style-guide.html and crystal-tokens.css)
# ----------------------------------------------------------------------------
BRANDS = {
    "dni": {
        "ink": "#263E56",  # Silk Dark, used for the QR
        "theme": "#263E56",
        "fonts": "https://fonts.googleapis.com/css2?family=Archivo:wdth,wght@125,500;125,600&family=Inter:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap",
        "favicon": '<link rel="icon" href="../assets/dni-mark-dark.png">',
        "css": """
  :root{
    --page:#F0E7E0; --panel:#FFFFFF; --ink:#0E1014; --muted:rgba(14,16,20,.62);
    --brand:#263E56; --brand-hover:#1E232B; --on-brand:#F8F3F0; --rule:rgba(14,16,20,.14); --focus:#3B5D7F;
    --display:"Aeonik Pro Extended","Archivo","Helvetica Neue",Arial,sans-serif;
    --sans:"Aeonik Pro","Inter","Helvetica Neue",Arial,sans-serif;
    --mono:"Aeonik Mono","JetBrains Mono",ui-monospace,monospace;
    --ease:cubic-bezier(.2,0,0,1); --fast:160ms;
  }
  .name{font-family:var(--display); font-variation-settings:"wdth" 125; font-weight:500; letter-spacing:-.02em; font-size:30px}
  .logo{height:40px}
""",
        "logo": '<img class="logo" src="../assets/dni-lockup-dark.png" alt="Diamond National Investments">',
    },
    "crystal": {
        "ink": "#413C7C",  # Deep Midnight
        "theme": "#413C7C",
        "fonts": "https://fonts.googleapis.com/css2?family=Inter:wght@400;500&family=JetBrains+Mono:wght@400;500&display=swap",
        "favicon": '<link rel="icon" href="../assets/crystal-icon.svg" type="image/svg+xml">',
        "css": """
  :root{
    --page:#EAE9F2; --panel:#FAF5EF; --ink:#24212A; --muted:#6E6A7E;
    --brand:#413C7C; --brand-hover:#322E60; --on-brand:#FAF5EF; --rule:#DBDAE2; --focus:#BF77F5;
    --display:"Aeonik Pro","Inter","Helvetica Neue",Arial,sans-serif;
    --sans:"Aeonik Pro","Inter","Helvetica Neue",Arial,sans-serif;
    --mono:"Aeonik Mono","JetBrains Mono",ui-monospace,monospace;
    --ease:cubic-bezier(.22,1,.36,1); --fast:200ms;
  }
  .name{font-family:var(--display); font-weight:500; letter-spacing:-.02em; font-size:32px}
  .logo{height:34px}
""",
        "logo": '<svg class="logo" viewBox="0 0 562.24 226.47" role="img" aria-label="Crystal"><path fill="#413C7C" d="M67.68 113.24 L113.24 0 L0 113.24 Z"/><path fill="#DBDAE2" d="M67.68 113.24 L113.24 226.47 L0 113.24 Z"/><g fill="#413C7C">{{WORDMARK}}</g></svg>',
    },
}

ICONS = {
    "chat": '<path d="M21 11.5a8.5 8.5 0 0 1-8.5 8.5 8.4 8.4 0 0 1-4-1L3 20l1-5.2A8.5 8.5 0 1 1 21 11.5z"/>',
    "phone": '<path d="M6.6 3h3.2l1.6 4-2 1.4a12 12 0 0 0 6.2 6.2l1.4-2 4 1.6v3.2A2.6 2.6 0 0 1 18.4 20C10.5 19.6 4.4 13.5 4 5.6A2.6 2.6 0 0 1 6.6 3z"/>',
    "mail": '<rect x="3" y="5" width="18" height="14" rx="2"/><path d="m3 7.5 9 6 9-6"/>',
    "linkedin": '<text x="12" y="16.6" text-anchor="middle" font-family="Arial,Helvetica,sans-serif" font-weight="700" font-size="13.5" fill="currentColor" stroke="none">in</text>',
    "globe": '<circle cx="12" cy="12" r="9"/><path d="M3 12h18M12 3a14 14 0 0 1 0 18M12 3a14 14 0 0 0 0 18"/>',
    "pin": '<path d="M12 21s-7-6.2-7-11.5a7 7 0 0 1 14 0C19 14.8 12 21 12 21z"/><circle cx="12" cy="9.5" r="2.5"/>',
    "user-plus": '<circle cx="9" cy="8" r="3.5"/><path d="M3 20a6 6 0 0 1 12 0M18 8v6M15 11h6"/>',
    "share": '<circle cx="18" cy="5" r="2.5"/><circle cx="6" cy="12" r="2.5"/><circle cx="18" cy="19" r="2.5"/><path d="m8.2 10.8 7.6-4.6M8.2 13.2l7.6 4.6"/>',
}


def icon(name: str, size: int = 22) -> str:
    return (
        f'<svg width="{size}" height="{size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
        f'stroke-width="1.8" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">{ICONS[name]}</svg>'
    )


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
    if p.get("linkedin"):
        lines.append(f"X-SOCIALPROFILE;TYPE=linkedin:https://www.linkedin.com/in/{p['linkedin']}")
    if p.get("address"):
        a = p["address"]
        lines.append(
            f"ADR;TYPE=WORK:;;{v(a['street'])};{v(a['city'])};{v(a['state'])};{v(a['zip'])};{v(a['country'])}"
        )
    lines.append(f"URL;TYPE=PROFILE:{url}")
    small = ROOT / "assets" / f"{p['slug']}-vcf.jpg"
    if small.exists():
        b64 = base64.b64encode(small.read_bytes()).decode("ascii")
        line = "PHOTO;ENCODING=b;TYPE=JPEG:" + b64
        # RFC 2425 folding: 75 octets per line, continuation lines start with a space
        lines.append(line[:75])
        lines.extend(" " + line[i:i + 74] for i in range(75, len(line), 74))
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
    px = -(-2048 // q.symbol_size(border=2)[0])  # scale that lands at >= 2048 px
    q.save(str(out / f"{slug}.svg"), scale=20, border=2, dark=ink, light=None)
    q.save(str(out / f"{slug}.png"), scale=px, border=2, dark=ink, light=None)
    q.save(str(out / f"{slug}-black.png"), scale=px, border=2, dark="#000000", light=None)
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
  var b=document.getElementById('share'), note=document.getElementById('scan'); if(!b) return;
  var url=location.href.split('#')[0], title=document.title, orig=note?note.innerHTML:'';
  function done(){ if(!note) return; note.textContent='Link copied'; setTimeout(function(){ note.innerHTML=orig; },2200); }
  b.addEventListener('click', function(){
    if(navigator.share){ navigator.share({title:title,url:url}).catch(function(){}); return; }
    if(navigator.clipboard){ navigator.clipboard.writeText(url).then(done, function(){ prompt('Copy this link', url); }); }
    else { prompt('Copy this link', url); }
  });
})();
"""


def row(href: str, ico: str, value: str, label: str, external: bool = False) -> str:
    target = ' target="_blank" rel="noopener"' if external else ""
    return (
        f'<li><a class="row" href="{esc(href)}"{target}><span class="ico">{icon(ico)}</span>'
        f'<span class="txt"><span class="v">{value}</span><span class="k">{esc(label)}</span></span></a></li>'
    )


def rows_html(p: dict) -> str:
    rows = []
    if p.get("phone_e164"):
        if p.get("whatsapp"):
            rows.append(row("https://wa.me/" + p["phone_e164"].lstrip("+"), "chat", esc(p["phone_display"]), "WhatsApp", True))
        else:
            rows.append(row("tel:" + p["phone_e164"], "phone", esc(p["phone_display"]), p.get("phone_label") or "Phone"))
    rows.append(row("mailto:" + p["email"], "mail", esc(p["email"]), "Work"))
    if p.get("linkedin"):
        rows.append(row("https://www.linkedin.com/in/" + p["linkedin"], "linkedin", "in/" + esc(p["linkedin"]), "LinkedIn", True))
    if p.get("website"):
        rows.append(row("https://" + p["website"], "globe", esc(p["website"]), "Website", True))
    if p.get("address"):
        a = p["address"]
        full = f"{a['street']}, {a['city']}, {a['state']} {a['zip']}"
        maps = "https://maps.google.com/?q=" + full.replace(" ", "+")
        value = f'{esc(a["street"])}<br>{esc(a["city"])}, {esc(a["state"])} {esc(a["zip"])}'
        rows.append(row(maps, "pin", value, "Office", True))
    return "\n".join(rows)


# ----------------------------------------------------------------------------
# Page template: full-bleed portrait, logo, name, contact rows, save, QR
# ----------------------------------------------------------------------------
TEMPLATE = """<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="robots" content="noindex">
<meta name="theme-color" content="{{THEME}}">
<title>{{NAME}} · {{ORG}}</title>
<meta name="description" content="{{NAME}}, {{TITLE}} at {{ORG}}. Save the contact or get in touch.">
<meta property="og:title" content="{{NAME}} · {{ORG}}">
<meta property="og:description" content="{{TITLE}} · {{ORG}}">
<meta property="og:type" content="profile">
<meta property="og:url" content="{{URL}}">{{OG_IMAGE}}
{{FAVICON}}
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="{{FONTS}}" rel="stylesheet">
<style>{{BRAND_CSS}}
  *{box-sizing:border-box; margin:0; padding:0}
  html{-webkit-text-size-adjust:100%}
  body{background:var(--page); color:var(--ink); font-family:var(--sans); font-size:16px; line-height:1.5; -webkit-font-smoothing:antialiased; min-height:100vh}
  a{color:inherit; text-decoration:none}
  :where(a,button,[tabindex]):focus-visible{outline:2px solid var(--focus); outline-offset:2px}
  .card{max-width:430px; margin:0 auto; min-height:100vh; background:var(--panel); display:flex; flex-direction:column}
  @media (min-width:480px){ body{padding:40px 0} .card{min-height:0; border:1px solid var(--rule); border-radius:28px; overflow:hidden} }

  .hero{position:relative; aspect-ratio:1/1; max-height:460px; background:var(--brand); overflow:hidden}
  .hero img{display:block; width:100%; height:100%; object-fit:cover; object-position:50% 25%}
  .hero .fallback{position:absolute; inset:0; display:grid; place-items:center; padding:24%}
  .hero .fallback img{width:100%; height:auto; object-fit:contain}

  .panel{padding:20px 24px 28px; display:flex; flex-direction:column; flex:1}
  .head{display:flex; justify-content:flex-end; min-height:40px}
  .logo{display:block; width:auto}
  .who{margin-top:14px}
  .name{color:var(--ink); line-height:1.1}
  .title{margin-top:10px; font-size:16px; color:var(--muted); line-height:1.45}
  .org{font-size:16px; color:var(--muted); line-height:1.45}

  .rows{list-style:none; margin-top:22px; display:flex; flex-direction:column; gap:6px}
  .row{display:flex; align-items:center; gap:16px; padding:8px 0; min-height:60px; transition:opacity var(--fast) var(--ease)}
  .row:hover{opacity:.78}
  .ico{flex:none; width:52px; height:52px; border-radius:50%; background:var(--brand); color:var(--on-brand); display:grid; place-items:center}
  .txt{min-width:0}
  .v{display:block; font-size:17px; color:var(--ink); overflow-wrap:anywhere; line-height:1.3}
  .k{display:block; font-size:13px; color:var(--muted); margin-top:2px}

  .actions{margin-top:24px; display:grid; grid-template-columns:1fr 52px; gap:10px; align-items:stretch}
  .btn{display:flex; align-items:center; justify-content:center; gap:10px; background:var(--brand); color:var(--on-brand); padding:16px 20px; border-radius:12px; font-size:16px; font-weight:500; min-height:52px; transition:background var(--fast) var(--ease)}
  .btn:hover{background:var(--brand-hover)}
  .share{width:52px; min-height:52px; border-radius:12px; border:1px solid var(--brand); background:transparent; color:var(--brand); display:grid; place-items:center; cursor:pointer; transition:background var(--fast) var(--ease)}
  .share:hover{background:var(--page)}
  .note{margin-top:12px; font-size:13px; color:var(--muted); text-align:center; line-height:1.5}

  .tag{margin-top:26px; font-size:12px; color:var(--muted); text-align:center}
  @media (prefers-reduced-motion: reduce){ *{transition:none !important} }
</style>
</head>
<body>
<main class="card">
  <figure class="hero">{{HERO}}</figure>
  <section class="panel">
    <div class="head">{{LOGO}}</div>
    <div class="who">
      <h1 class="name">{{NAME}}</h1>
      <p class="title">{{TITLE}}</p>
      <p class="org">{{ORG_LINE}}</p>
    </div>
    <ul class="rows">
{{ROWS}}
    </ul>
    <div class="actions">
      <a class="btn" href="{{VCF}}" download="{{VCF}}">{{ICON_SAVE}}Save contact</a>
      <button class="share" id="share" type="button" aria-label="Share this card">{{ICON_SHARE}}</button>
    </div>
    <p class="note" id="scan">Saves name, {{SAVES}} to your contacts.</p>
    {{TAGLINE}}
  </section>
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
    return re.search(r'<g id="crystal-wordmark"[^>]*>(.*?)</g>', svg, re.S).group(1).strip()


def hero_html(p: dict, name: str, brand: dict) -> str:
    photo = ROOT / "assets" / f"{p['slug']}.jpg"
    if photo.exists():
        return f'<img src="../assets/{p["slug"]}.jpg" alt="Portrait of {esc(name)}" width="960" height="960">'
    # no photo yet: brand-coloured panel with the reversed lockup
    if p["brand"] == "dni":
        return '<div class="fallback"><img src="../assets/dni-lockup-light.png" alt=""></div>'
    return '<div class="fallback"><svg viewBox="0 0 562.24 226.47" aria-hidden="true"><path fill="#FAF5EF" d="M67.68 113.24 L113.24 0 L0 113.24 Z"/><path fill="#B8B9DE" d="M67.68 113.24 L113.24 226.47 L0 113.24 Z"/><g fill="#FAF5EF">{{WORDMARK}}</g></svg></div>'


def saves_text(p: dict, has_photo: bool) -> str:
    """'phone, email and photo' — what the vCard actually carries."""
    items = [s for s, ok in (("phone", p.get("phone_e164")), ("email", True), ("LinkedIn", p.get("linkedin")),
                             ("website", p.get("website")), ("office address", p.get("address")),
                             ("photo", has_photo)) if ok]
    return ", ".join(items[:-1]) + " and " + items[-1] if len(items) > 1 else items[0]


def build_person(p: dict) -> dict:
    slug = p["slug"]
    url = f"{BASE}/{slug}/"
    out = ROOT / slug
    out.mkdir(exist_ok=True)
    vcf_name = f"{slug}.vcf"
    (out / vcf_name).write_text(vcard(p, url), encoding="utf-8", newline="")

    brand = BRANDS[p["brand"]]
    qr_svg = make_qr(url, slug, brand["ink"])
    name = f"{p['first']} {p['last']}"
    has_photo = (ROOT / "assets" / f"{slug}.jpg").exists()
    org_line = esc(p["org"]) + (f' · {esc(p["org_parent"])}' if p.get("org_parent") else "")

    page = (
        TEMPLATE.replace("{{BRAND_CSS}}", brand["css"])
        .replace("{{FONTS}}", brand["fonts"])
        .replace("{{FAVICON}}", brand["favicon"])
        .replace("{{THEME}}", brand["theme"])
        .replace("{{LOGO}}", brand["logo"])
        .replace("{{HERO}}", hero_html(p, name, brand))
        .replace("{{OG_IMAGE}}", f'\n<meta property="og:image" content="{BASE}/assets/{slug}.jpg">' if has_photo else "")
        .replace("{{NAME}}", esc(name))
        .replace("{{TITLE}}", esc(p["title"]))
        .replace("{{ORG_LINE}}", org_line)
        .replace("{{ORG}}", esc(p["org"]))
        .replace("{{URL}}", esc(url))
        .replace("{{VCF}}", esc(vcf_name))
        .replace("{{ROWS}}", rows_html(p))
        .replace("{{QR}}", qr_svg)
        .replace("{{SAVES}}", saves_text(p, has_photo))
        .replace("{{ICON_SAVE}}", icon("user-plus", 20))
        .replace("{{ICON_SHARE}}", icon("share", 20))
        .replace("{{TAGLINE}}", f'<p class="tag">{esc(p["tagline"])}</p>' if p.get("tagline") else "")
        .replace("{{WORDMARK}}", wordmark_paths())
        .replace("{{JS}}", SHARE_JS.strip())
    )
    (out / "index.html").write_text(page, encoding="utf-8")
    return {"name": name, "title": p["title"], "org": p["org"], "slug": slug, "url": url, "photo": has_photo}


def main() -> None:
    built = [build_person(p) for p in CFG["people"]]
    items = "\n".join(
        f'    <li><a href="{b["slug"]}/"><span><span>{esc(b["name"])}</span><br><span class="t">{esc(b["title"])}</span></span><span class="b">{esc(b["org"])}</span></a></li>'
        for b in built
    )
    (ROOT / "index.html").write_text(INDEX_TEMPLATE.replace("{{ITEMS}}", items), encoding="utf-8")
    for b in built:
        print(f"{b['name']:<22} {'photo' if b['photo'] else 'NO PHOTO':<9} {b['url']}")


if __name__ == "__main__":
    main()
