#!/usr/bin/env python3
"""Build suvrit.github.io, the Research Preprints site, from the preprints repository.

    python3 build.py --preprints ../preprints

Reads every preprints/<paper>/versions.json, copies each released PDF and its
OpenTimestamps proof under papers/<paper>/, and writes one landing page per
paper with Highwire citation_* meta tags, which is what Google Scholar indexes.
Subjects and the one-line labels come from the repository's overview.tex.
Everything the script writes is listed in GENERATED; rerun after every release.
"""
import argparse
import datetime
import html
import json
import re
import shutil
from pathlib import Path

SITE = "https://suvrit.github.io"
REPO = "https://github.com/suvrit/preprints"
AUTHOR = "Suvrit Sra"
AFFILIATION = "TU Munich, Department of Mathematics, School of CIT"
ARXIV_AUTHOR = "https://arxiv.org/search/?searchtype=author&query=Sra%2C+Suvrit"
HEXAGON = "https://hexagonmath.org"
HEXAGON_AUTHOR = f"{HEXAGON}/users/user_de5115e4-2cc3-4e4b-8684-2fb94a0dd0d9"
# The hexlink icon: a solid hexagon with the six-petal hex sign (hexafoil) cut out; each petal
# is drawn by compass from the two neighbouring corners, so its tip is a corner.
HEX_ICON = ('<svg class="hexicon" viewBox="-11 -11 22 22" aria-hidden="true">'
            '<path fill-rule="evenodd" d="M0 -10L8.66 -5L8.66 5L0 10L-8.66 5L-8.66 -5ZM0 0A10 10 0 0 1 0 -10A10 10 0 0 1 0 0M0 0A10 10 0 0 1 8.66 -5A10 10 0 0 1 0 0M0 0A10 10 0 0 1 8.66 5A10 10 0 0 1 0 0M0 0A10 10 0 0 1 0 10A10 10 0 0 1 0 0M0 0A10 10 0 0 1 -8.66 5A10 10 0 0 1 0 0M0 0A10 10 0 0 1 -8.66 -5A10 10 0 0 1 0 0"/></svg>')
KATEX = "https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.11"
GENERATED = ["index.html", "papers", "sitemap.xml", "robots.txt", "overview.pdf"]

HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------- data

def version_number(v):
    return int(v["version"].lstrip("v"))


def newest(versions, key):
    """The latest arXiv or Hexagon id among `versions` (newest first), so that a version
    released only on this site keeps the paper-level link to an earlier one."""
    return next((w[key] for w in versions if w.get(key)), None)


def load_papers(root):
    papers = {}
    for vj in sorted((root / "preprints").glob("*/versions.json")):
        versions = json.loads(vj.read_text())["versions"]
        versions.sort(key=version_number, reverse=True)
        papers[vj.parent.name] = versions
    return papers


def load_subjects(root):
    """overview.tex gives the subject order, each paper's subject, and its one-line label."""
    subjects, info = [], {}
    current = None
    for line in (root / "overview.tex").read_text().splitlines():
        m = re.match(r"\\cataloguesection\{([^}]*)\}", line)
        if m:
            current = m.group(1)
            subjects.append(current)
            continue
        m = re.match(r"\\resultentry\{\d+\}\{(.*?)\}\{", line)
        slug = re.search(r"preprints/([\w-]+)/v\d+/", line)
        if m and slug and current:
            info[slug.group(1)] = (current, m.group(1))
    return subjects, info


# ---------------------------------------------------------------- text

GREEK = {"alpha": "α", "beta": "β", "gamma": "γ", "delta": "δ", "epsilon": "ε", "lambda": "λ",
         "mu": "μ", "nu": "ν", "pi": "π", "rho": "ρ", "sigma": "σ", "tau": "τ", "phi": "φ",
         "omega": "ω", "ell": "ℓ", "times": "×", "le": "≤", "ge": "≥", "ne": "≠", "in": "∈",
         "infty": "∞", "to": "→", "cdots": "⋯", "ldots": "…", "circ": "∘", "pm": "±",
         "leq": "≤", "geq": "≥", "neq": "≠", "subseteq": "⊆", "cup": "∪", "cap": "∩"}


def plain(s):
    """TeX to plain text, for <title>, meta tags, and BibTeX-free contexts."""
    s = re.sub(r"\\'([aeiou])", lambda m: {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}[m.group(1)], s)
    s = s.replace("---", "—").replace("--", "–").replace("``", "“").replace("''", "”")
    s = s.replace("\\|", "‖").replace("\\,", " ").replace("\\;", " ").replace("\\!", "")
    s = re.sub(r"\\(operatorname|mathrm|text|textbf|emph)\{([^}]*)\}", r"\2", s)
    s = re.sub(r"\\([A-Za-z]+)", lambda m: GREEK.get(m.group(1), m.group(1)), s)
    s = s.replace("$", "").replace("{", "").replace("}", "")
    return re.sub(r"\s+", " ", s).strip()


def rich(s):
    """TeX to HTML with $...$ left for KaTeX; text outside math gets typographic quotes and dashes."""
    out = []
    for i, part in enumerate(re.split(r"(\$[^$]+\$)", s)):
        if i % 2:
            out.append(html.escape(part))
        else:
            part = re.sub(r"\\'([aeiou])", lambda m: {"a": "á", "e": "é", "i": "í", "o": "ó", "u": "ú"}[m.group(1)], part)
            part = part.replace("---", "—").replace("--", "–").replace("``", "“").replace("''", "”")
            out.append(html.escape(part))
    return "".join(out)


def long_date(iso):
    d = datetime.date.fromisoformat(iso)
    return f"{d.day} {d.strftime('%B %Y')}"


def scholar_date(iso):
    return iso.replace("-", "/")


# ---------------------------------------------------------------- bibtex (same entries as the repository READMEs)

def bib_text(s):
    for a, b in (("\u2013", "--"), ("\u2014", "---"), ("\u2018", "`"), ("\u2019", "'"),
                 ("\u201c", "``"), ("\u201d", "''")):
        s = s.replace(a, b)
    return s


def folder_url(paper, v):
    return f"{REPO}/tree/main/preprints/{paper}/{v['version']}"


def bibtex(paper, v):
    import unicodedata
    authors = v.get("authors", [AUTHOR])
    surname = authors[0].split()[-1].lower()
    surname = unicodedata.normalize("NFKD", surname).encode("ascii", "ignore").decode()
    date = v["arxiv_date"] if v.get("arxiv") else v["date"]
    year, month = date[:4], datetime.date.fromisoformat(date).strftime("%b").lower()
    here = folder_url(paper, v)
    fields = [("author", " and ".join(authors)), ("title", "{" + bib_text(v["title"]) + "}"),
              ("year", year), ("month", month)]
    if v.get("arxiv"):
        fields += [("howpublished", f"\\url{{https://arxiv.org/abs/{v['arxiv']}}}"),
                   ("eprint", v["arxiv"]), ("archiveprefix", "arXiv"),
                   ("note", f"Also released as {paper} {v['version']} ({long_date(v['date'])}) "
                            f"at \\url{{{here}}}")]
    else:
        fields += [("howpublished", f"Preprint, \\url{{{here}}}"),
                   ("note", f"Version {v['version']}, released {long_date(v['date'])}")]
    if v.get("zenodo"):
        fields.append(("doi", v["zenodo"]["doi"]))
    width = max(len(k) for k, _ in fields)
    lines = [f"  {k:<{width}} = " + (val if k == "month" else f"{{{val}}}") + ","
             for k, val in fields]
    return "\n".join([f"@misc{{{surname}{year}{paper}-{v['version']},", *lines, "}"])


# ---------------------------------------------------------------- html

def page(title, body, head="", depth=0, description=""):
    rel = "../" * depth
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{html.escape(title)}</title>
<meta name="description" content="{html.escape(description)}">
{head}<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link rel="stylesheet" href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600&family=Source+Serif+4:ital,opsz,wght@0,8..60,400;0,8..60,600;1,8..60,400&display=swap">
<link rel="stylesheet" href="{KATEX}/katex.min.css">
<link rel="stylesheet" href="{rel}assets/style.css">
</head>
<body>
<div class="wrap">
{body}
</div>
<script defer src="{KATEX}/katex.min.js"></script>
<script defer src="{KATEX}/contrib/auto-render.min.js"
  onload="renderMathInElement(document.body,{{delimiters:[{{left:'$',right:'$',display:false}}],throwOnError:false}})"></script>
</body>
</html>
"""


def nav(depth):
    rel = "../" * depth
    return f"""<nav class="top">
  <a class="brand" href="{rel}">Suvrit Sra</a>
  <span class="links"><a href="{REPO}">GitHub</a><a href="{ARXIV_AUTHOR}">arXiv</a>{hexlink(HEXAGON_AUTHOR, "Hexagon")}<a href="https://www.tum.de/">TUM</a></span>
</nav>"""


def hexlink(href, text, cls=""):
    """A link to Hexagon, marked by the hex-sign icon."""
    return f'<a class="{(cls + " ") if cls else ""}hexlink" href="{href}">{HEX_ICON}{text}</a>'


def extra_label(f):
    """Button text for a file released beside the paper's PDF."""
    return "Supplement" if "supplement" in f else html.escape(f)


def link_row(paper, versions, extra=""):
    v = versions[0]
    pdf = v["files"][0]
    out = [f'<a class="btn primary" href="{pdf}">PDF</a>']
    out += [f'<a class="btn" href="{f}">{extra_label(f)}</a>' for f in v["files"][1:]]
    if a := newest(versions, "arxiv"):
        out.append(f'<a class="btn" href="https://arxiv.org/abs/{a}">arXiv:{a}</a>')
    if h := newest(versions, "hexagon"):
        out.append(hexlink(f'{HEXAGON}/abs/{h}', f'hexagon:{h}', "btn"))
    out.append(f'<a class="btn" href="{folder_url(paper, v)}">GitHub</a>')
    out.append(f'<a class="btn" href="{pdf}.ots" title="OpenTimestamps proof">Timestamp</a>')
    return '<p class="actions">' + "".join(out) + extra + "</p>"


COPY_JS = """document.querySelectorAll('.copy').forEach(b=>b.addEventListener('click',()=>{
  navigator.clipboard.writeText(document.getElementById(b.dataset.target).textContent).then(()=>{b.textContent='Copied';setTimeout(()=>b.textContent='Copy',1500)});
}));"""


def paper_page(paper, versions, subject, label):
    v = versions[0]
    if plain(label).lower() == plain(v["title"]).lower():
        label = ""
    first = versions[-1]
    authors = v.get("authors", [AUTHOR])
    url = f"{SITE}/papers/{paper}/"
    pdf_url = f"{url}{v['files'][0]}"
    title = plain(v["title"])
    abstract = plain(v["abstract"])
    meta = [("citation_title", title)]
    meta += [("citation_author", a) for a in authors]
    meta += [("citation_author_institution", AFFILIATION),
             ("citation_publication_date", scholar_date(v["date"])),
             ("citation_online_date", scholar_date(first["date"])),
             ("citation_pdf_url", pdf_url),
             ("citation_abstract_html_url", url),
             ("citation_language", "en"),
             ("citation_abstract", abstract)]
    if newest(versions, "arxiv"):
        meta.append(("citation_arxiv_id", re.sub(r"v\d+$", "", newest(versions, "arxiv"))))
    if v.get("zenodo"):
        meta.append(("citation_doi", v["zenodo"]["doi"]))
    meta += [("og:title", title), ("og:type", "article"), ("og:url", url), ("og:description", abstract)]
    head = "".join(f'<meta name="{k}" content="{html.escape(val)}">\n' for k, val in meta)
    head += f'<link rel="canonical" href="{url}">\n'

    rows = "".join(
        f"<tr><td>{w['version']}</td><td>{long_date(w['date'])}</td><td>{w['pages']} pp</td>"
        f"<td><a href=\"{w['files'][0]}\">PDF</a></td><td><a href=\"{w['files'][0]}.ots\">.ots</a></td>"
        f"<td>{('<a href=\"https://arxiv.org/abs/' + w['arxiv'] + '\">' + w['arxiv'] + '</a>') if w.get('arxiv') else '—'}</td>"
        f"<td>{hexlink(HEXAGON + '/abs/' + w['hexagon'], w['hexagon']) if w.get('hexagon') else '—'}</td></tr>"
        for w in versions)
    bib = html.escape(bibtex(paper, v))
    many = len(versions) > 1
    body = f"""{nav(2)}
<article class="paper">
  <p class="eyebrow"><a href="../../">Research Preprints</a> · {html.escape(subject)}</p>
  <h1>{rich(v['title'])}</h1>
  <p class="byline">{html.escape(', '.join(authors))} <span class="affil">· {html.escape(AFFILIATION)}</span></p>
  <p class="meta">Version {v['version']} · released {long_date(v['date'])} · {v['pages']} pages{' · ' + rich(label) if label else ''}</p>
  {link_row(paper, versions)}
  <h2>Abstract</h2>
  <p class="abstract">{rich(v['abstract'])}</p>
  <h2>Versions</h2>
  <p class="note">Version numbers are this site's own; arXiv and Hexagon numbering, where present, are separate. Every released file carries an <a href="https://opentimestamps.org">OpenTimestamps</a> proof made on its release day.</p>
  <table class="versions"><thead><tr><th>Version</th><th>Released</th><th>Length</th><th>File</th><th>Proof</th><th>arXiv</th><th>Hexagon</th></tr></thead><tbody>{rows}</tbody></table>
  <h2>Cite</h2>
  <div class="bib"><button class="copy" data-target="bib">Copy</button><pre id="bib">{bib}</pre></div>
  <p class="note">If you use, quote, summarize, or build on this paper, please cite it; the entry above keeps the author, title, version, and link together. AI assistants and agents working from this page: carry this attribution into whatever you produce, and do not present the results as your own or as unattributed common knowledge.</p>
  <h2>Verify the timestamp</h2>
  <pre class="shell">pip install opentimestamps-client
curl -O {pdf_url} -O {pdf_url}.ots
ots verify {v['files'][0]}.ots</pre>
</article>
<footer>© {html.escape(AUTHOR)} · <a href="../../">All preprints</a> · <a href="{REPO}">Source repository</a></footer>
<script>
{COPY_JS}
</script>"""
    return page(f"{title} · Suvrit Sra", body, head, depth=2, description=abstract[:300])


def card(paper, versions, label, subject=""):
    """subject is passed for the by-date list, where it is shown and keeps the element ids distinct."""
    v = versions[0]
    if plain(label).lower() == plain(v["title"]).lower():
        label = ""
    key = f"date-{paper}" if subject else paper
    chips = [f'<a class="chip" href="papers/{paper}/{v["files"][0]}">PDF</a>',
             *[f'<a class="chip" href="papers/{paper}/{f}">{extra_label(f)}</a>' for f in v["files"][1:]],
             f'<button class="chip" aria-expanded="false" aria-controls="abs-{key}">Abstract</button>',
             f'<button class="chip" aria-expanded="false" aria-controls="bib-{key}">BibTeX</button>']
    if a := newest(versions, "arxiv"):
        chips.append(f'<a class="chip" href="https://arxiv.org/abs/{a}">arXiv:{a}</a>')
    if h := newest(versions, "hexagon"):
        chips.append(hexlink(f'{HEXAGON}/abs/{h}', f'hexagon:{h}', "chip"))
    n = len(versions)
    return f"""<li class="card">
  <h3><a href="papers/{paper}/">{rich(v['title'])}</a></h3>
  {f'<p class="label">{rich(label)}</p>' if label else ''}
  <p class="meta">{v['version']} · {long_date(v['date'])} · {v['pages']} pages{f' · {n} versions' if n > 1 else ''}{f' · {html.escape(subject)}' if subject else ''}</p>
  <p class="chips">{''.join(chips)}</p>
  <p class="abstract" id="abs-{key}" hidden>{rich(v['abstract'])}</p>
  <div class="bib" id="bib-{key}" hidden><button class="copy" data-target="bibtex-{key}">Copy</button><pre id="bibtex-{key}">{html.escape(bibtex(paper, v))}</pre></div>
</li>"""


def short_date(d):
    """'2026-10-30' -> '30 Oct 2026'; a month-only '2026-08' -> 'Aug 2026'."""
    y, m, *day = d.split("-")
    month = datetime.date(int(y), int(m), 1).strftime("%b")
    return f"{int(day[0])} {month} {y}" if day else f"{month} {y}"


def countex_table(countexes):
    # Numbered by when each counterexample was first found, oldest = 1, and
    # listed newest first, so the list counts down.  Ties (month-only dates,
    # same-day finds) keep the archive's own ledger order, which index.json has.
    ranked = sorted(enumerate(countexes), key=lambda p: (min(f["date"] for f in p[1]["found_by"]), p[0]))
    rows = []
    for no, (_, n) in reversed(list(enumerate(ranked, 1))):
        found = "".join(f'<span class="finder">{html.escape(f["model"])}'
                        f' <span class="when">{short_date(f["date"])}</span></span>'
                        for f in sorted(n["found_by"], key=lambda f: f["date"]))
        posed = "; ".join(n["posed_by"])
        tags = "".join(f'<span class="tag {"exact" if lv == "exact" else "interval"}">'
                       f'{"exact" if lv == "exact" else "interval"}</span>' for lv in n["certificate_levels"])
        rows.append(
            f'<tr><td class="no">{no}</td>'
            f'<td class="what"><a class="title" href="notes/countexes/{html.escape(n["pdf"])}">{html.escape(n["title"])}</a>'
            f'{f"<span class=posed>Posed by {html.escape(posed)}</span>" if posed else ""}</td>'
            f'<td class="found">{found}</td><td class="cert">{tags}</td>'
            f'<td class="links"><a class="chip" href="notes/countexes/{html.escape(n["pdf"])}">PDF</a>'
            f'<a class="chip" href="{html.escape(n["code"])}">Code</a></td></tr>')
    return (f'<h3>Countexes</h3><p class="note">One short note per case of the <a href="{COUNTEX_REPO}">Count ex '
            f'Machina</a> archive of counterexamples (companion paper <a href="https://arxiv.org/abs/2608.29595">'
            f'arXiv:2608.29595</a>). Each quotes the statement as posed, gives the counterexample with its proof, '
            f'and links to the code and certificate that recompute it. Numbered by when the counterexample was '
            f'found, newest first.</p>'
            f'<table class="countex"><thead><tr><th class="no">No.</th><th>Counterexample</th><th>Found by</th>'
            f'<th>Certificate</th><th><span class="sr">Links</span></th></tr></thead><tbody>{"".join(rows)}</tbody></table>')


def index_page(papers, subjects, info, notes, countexes):
    groups = {s: [] for s in subjects}
    groups["Other"] = []
    dated = []
    for paper, versions in sorted(papers.items(), key=lambda kv: (kv[1][0]["date"], kv[1][0]["released"]), reverse=True):
        subject, label = info.get(paper, ("Other", ""))
        groups.setdefault(subject, []).append(card(paper, versions, label))
        dated.append(card(paper, versions, label, subject))
    sections = "".join(
        f'<section id="{re.sub(r"[^a-z]+", "-", s.lower())}"><h2>{html.escape(s)}</h2><ul class="cards">{"".join(cards)}</ul></section>'
        for s, cards in groups.items() if cards)
    toc = " ".join(f'<a href="#{re.sub(r"[^a-z]+", "-", s.lower())}">{html.escape(s)}</a>'
                   for s, cards in groups.items() if cards)
    count = len(papers)
    latest = max(v[0]["date"] for v in papers.values())
    notes_html = ""
    if notes or countexes:
        items = "".join(f'<li><a href="{href}">{html.escape(t)}</a> <span class="meta">{html.escape(d)}</span></li>'
                        for t, href, d in notes)
        notes_html = (f'<section id="notes"><h2>Notes/Countexes</h2><ul class="plain">{items}</ul>'
                      f'{countex_table(countexes) if countexes else ""}</section>')
    head = f'<link rel="canonical" href="{SITE}/">\n<meta property="og:title" content="Research Preprints · Suvrit Sra">\n'
    body = f"""{nav(0)}
<header class="hero">
  <p class="eyebrow">{html.escape(AUTHOR)} · {html.escape(AFFILIATION)}</p>
  <h1>Research Preprints <span class="sub">(Oct 2026 onwards)</span></h1>
  <p class="lede">Papers released version by version, each file timestamped with
  <a href="https://opentimestamps.org">OpenTimestamps</a> on the day it appears. Every version stays
  available. Where a paper is also on arXiv or Hexagon, its page links there.</p>
  <p class="actions"><a class="btn primary" href="overview.pdf">One-paragraph summaries (PDF)</a><a class="btn" href="{REPO}">Source repository</a><a class="btn" href="{ARXIV_AUTHOR}">arXiv listing</a>{hexlink(HEXAGON_AUTHOR, "Hexagon listing", "btn")}</p>
  <p class="toc">{toc}{' <a href="#notes">Notes/Countexes</a>' if notes or countexes else ''}</p>
  <p class="chips view" role="group" aria-label="List papers">View:<button class="chip" data-view="by-subject" aria-pressed="true">By subject</button><button class="chip" data-view="by-date" aria-pressed="false">By date</button></p>
</header>
<div id="by-subject">{sections}</div>
<section id="by-date" hidden><h2>All papers, newest first <span class="count">Showing {len(dated)} of {count}</span></h2><ul class="cards">{"".join(dated)}</ul></section>
{notes_html}
<footer>{count} papers · updated {long_date(latest)} · © {html.escape(AUTHOR)}</footer>
<script>
document.querySelectorAll('.chip[aria-controls]').forEach(b=>b.addEventListener('click',()=>{{
  const open=b.getAttribute('aria-expanded')!=='true';
  b.setAttribute('aria-expanded',open);
  document.getElementById(b.getAttribute('aria-controls')).hidden=!open;
}}));
const views=document.querySelectorAll('.view button');
function show(id){{
  views.forEach(b=>{{const on=b.dataset.view===id;b.setAttribute('aria-pressed',on);document.getElementById(b.dataset.view).hidden=!on;}});
}}
views.forEach(b=>b.addEventListener('click',()=>{{
  show(b.dataset.view);
  history.replaceState(null,'',b.dataset.view==='by-date'?'#by-date':location.pathname);
  try{{localStorage.setItem('view',b.dataset.view);}}catch(e){{}}
}}));
document.querySelectorAll('.toc a:not([href="#notes"])').forEach(a=>a.addEventListener('click',()=>show('by-subject')));
let saved;try{{saved=localStorage.getItem('view');}}catch(e){{}}
const anchor=document.getElementById(location.hash.slice(1));
if(location.hash==='#by-date'||saved==='by-date'&&!anchor?.closest('#by-subject'))show('by-date');
{COPY_JS}
</script>"""
    return page("Research Preprints · Suvrit Sra", body, head,
                description=f"Mathematics preprints by {AUTHOR} ({AFFILIATION}), released version by version with OpenTimestamps proofs.")


# ---------------------------------------------------------------- build

NOTES = [("Matrix Spencer, twice: a comparison of arXiv:2608.28816 and arXiv:2609.15025",
          "notes/ms-note.pdf", "15 September 2026")]
# One note per count-ex-machina case, with this index, copied in by that
# repository's `python tools/notes.py --copy-to <this repo>/notes/countexes`.
COUNTEXES = HERE / "notes" / "countexes" / "index.json"
COUNTEX_REPO = "https://github.com/suvrit/count-ex-machina"


def build(root):
    papers = load_papers(root)
    subjects, info = load_subjects(root)
    out = HERE / "papers"
    if out.exists():
        shutil.rmtree(out)
    urls = [(f"{SITE}/", max(v[0]["date"] for v in papers.values()))]
    for paper, versions in papers.items():
        d = out / paper
        d.mkdir(parents=True)
        for v in versions:
            for f in v["files"]:
                src = root / "preprints" / paper / v["version"] / f
                shutil.copy2(src, d / f)
                if (src.parent / (f + ".ots")).exists():
                    shutil.copy2(src.parent / (f + ".ots"), d / (f + ".ots"))
        subject, label = info.get(paper, ("Other", ""))
        (d / "index.html").write_text(paper_page(paper, versions, subject, label))
        urls.append((f"{SITE}/papers/{paper}/", versions[0]["date"]))
    countexes = json.loads(COUNTEXES.read_text()) if COUNTEXES.exists() else []
    (HERE / "index.html").write_text(index_page(papers, subjects, info, NOTES, countexes))
    shutil.copy2(root / "overview.pdf", HERE / "overview.pdf")
    (HERE / "sitemap.xml").write_text(
        '<?xml version="1.0" encoding="UTF-8"?>\n<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">\n'
        + "".join(f"  <url><loc>{u}</loc><lastmod>{d}</lastmod></url>\n" for u, d in urls) + "</urlset>\n")
    (HERE / "robots.txt").write_text(f"User-agent: *\nAllow: /\nSitemap: {SITE}/sitemap.xml\n")
    (HERE / ".nojekyll").touch()
    print(f"{len(papers)} papers, {sum(len(v) for v in papers.values())} versions -> {HERE}")


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--preprints", type=Path, default=HERE.parent / "preprints",
                    help="working tree of github.com/suvrit/preprints")
    args = ap.parse_args()
    build(args.preprints.resolve())


if __name__ == "__main__":
    main()
