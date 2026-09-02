# Diamond National · digital business cards

Static site, hosted free on GitHub Pages. One folder per person, one QR code per person.
No subscription, no vendor: the link on the printed card points here for as long as the repo exists.

## What is here

| Path | What it is |
|---|---|
| `people.json` | The single source of truth: names, titles, phones, emails, addresses, brand |
| `build.py` | Generates everything below from `people.json` |
| `<slug>/index.html` | The card page (DNI or Crystal design system, per person) |
| `<slug>/<slug>.vcf` | vCard behind the "Save contact" button |
| `qr/<slug>.svg` `.png` | QR code that opens the card, in brand colour, for the printed card |
| `qr/<slug>-black.png` | Same QR in black |
| `assets/` | DNI and Crystal logo files |
| `index.html` | Directory of all cards |

## Live URLs

```
https://alejandromtay06.github.io/dn-cards/mehr-eliezer/
https://alejandromtay06.github.io/dn-cards/jennifer-levant/
https://alejandromtay06.github.io/dn-cards/ailin-gava/
```

## Add or edit a person

1. Edit `people.json` (copy an existing entry; `brand` is `dni` or `crystal`; the `slug` becomes the URL).
2. Run `python build.py` (needs `pip install segno` once).
3. Commit and push. GitHub Pages redeploys in about a minute.

Editing a phone number or title never changes the URL, so printed QR codes keep working.
Do not rename a `slug` once its QR has been printed.

## Custom domain (optional, later)

Add a `CNAME` file containing e.g. `cards.dn-investments.com`, point that subdomain's DNS CNAME at
`alejandromtay06.github.io`, and update `base_url` in `people.json`, then rebuild.
Do this **before** printing, because it changes the QR codes.
