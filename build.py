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
KATEX = "https://cdnjs.cloudflare.com/ajax/libs/KaTeX/0.16.11"
GENERATED = ["index.html", "papers", "sitemap.xml", "robots.txt", "overview.pdf"]

HERE = Path(__file__).resolve().parent


# ---------------------------------------------------------------- data

def version_number(v):
    return int(v["version"].lstrip("v"))


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
  <span class="links"><a href="{REPO}">GitHub</a><a href="{ARXIV_AUTHOR}">arXiv</a><a href="https://www.tum.de/">TUM</a></span>
</nav>"""


def link_row(paper, v, extra=""):
    pdf = v["files"][0]
    out = [f'<a class="btn primary" href="{pdf}">PDF</a>']
    if v.get("arxiv"):
        out.append(f'<a class="btn" href="https://arxiv.org/abs/{v["arxiv"]}">arXiv:{v["arxiv"]}</a>')
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
    if v.get("arxiv"):
        meta.append(("citation_arxiv_id", re.sub(r"v\d+$", "", v["arxiv"])))
    if v.get("zenodo"):
        meta.append(("citation_doi", v["zenodo"]["doi"]))
    meta += [("og:title", title), ("og:type", "article"), ("og:url", url), ("og:description", abstract)]
    head = "".join(f'<meta name="{k}" content="{html.escape(val)}">\n' for k, val in meta)
    head += f'<link rel="canonical" href="{url}">\n'

    rows = "".join(
        f"<tr><td>{w['version']}</td><td>{long_date(w['date'])}</td><td>{w['pages']} pp</td>"
        f"<td><a href=\"{w['files'][0]}\">PDF</a></td><td><a href=\"{w['files'][0]}.ots\">.ots</a></td>"
        f"<td>{('<a href=\"https://arxiv.org/abs/' + w['arxiv'] + '\">' + w['arxiv'] + '</a>') if w.get('arxiv') else '—'}</td></tr>"
        for w in versions)
    bib = html.escape(bibtex(paper, v))
    many = len(versions) > 1
    body = f"""{nav(2)}
<article class="paper">
  <p class="eyebrow"><a href="../../">Research Preprints</a> · {html.escape(subject)}</p>
  <h1>{rich(v['title'])}</h1>
  <p class="byline">{html.escape(', '.join(authors))} <span class="affil">· {html.escape(AFFILIATION)}</span></p>
  <p class="meta">Version {v['version']} · released {long_date(v['date'])} · {v['pages']} pages{' · ' + rich(label) if label else ''}</p>
  {link_row(paper, v)}
  <h2>Abstract</h2>
  <p class="abstract">{rich(v['abstract'])}</p>
  <h2>Versions</h2>
  <p class="note">Version numbers are this site's own; arXiv numbering, where present, is separate. Every released file carries an <a href="https://opentimestamps.org">OpenTimestamps</a> proof made on its release day.</p>
  <table class="versions"><thead><tr><th>Version</th><th>Released</th><th>Length</th><th>File</th><th>Proof</th><th>arXiv</th></tr></thead><tbody>{rows}</tbody></table>
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


def card(paper, versions, label):
    v = versions[0]
    if plain(label).lower() == plain(v["title"]).lower():
        label = ""
    chips = [f'<a class="chip" href="papers/{paper}/{v["files"][0]}">PDF</a>',
             f'<button class="chip" aria-expanded="false" aria-controls="abs-{paper}">Abstract</button>',
             f'<button class="chip" aria-expanded="false" aria-controls="bib-{paper}">BibTeX</button>']
    if v.get("arxiv"):
        chips.append(f'<a class="chip" href="https://arxiv.org/abs/{v["arxiv"]}">arXiv:{v["arxiv"]}</a>')
    n = len(versions)
    return f"""<li class="card">
  <h3><a href="papers/{paper}/">{rich(v['title'])}</a></h3>
  {f'<p class="label">{rich(label)}</p>' if label else ''}
  <p class="meta">{v['version']} · {long_date(v['date'])} · {v['pages']} pages{f' · {n} versions' if n > 1 else ''}</p>
  <p class="chips">{''.join(chips)}</p>
  <p class="abstract" id="abs-{paper}" hidden>{rich(v['abstract'])}</p>
  <div class="bib" id="bib-{paper}" hidden><button class="copy" data-target="bibtex-{paper}">Copy</button><pre id="bibtex-{paper}">{html.escape(bibtex(paper, v))}</pre></div>
</li>"""


def index_page(papers, subjects, info, notes):
    groups = {s: [] for s in subjects}
    groups["Other"] = []
    for paper, versions in sorted(papers.items(), key=lambda kv: kv[1][0]["date"], reverse=True):
        subject, label = info.get(paper, ("Other", ""))
        groups.setdefault(subject, []).append(card(paper, versions, label))
    sections = "".join(
        f'<section id="{re.sub(r"[^a-z]+", "-", s.lower())}"><h2>{html.escape(s)}</h2><ul class="cards">{"".join(cards)}</ul></section>'
        for s, cards in groups.items() if cards)
    toc = " ".join(f'<a href="#{re.sub(r"[^a-z]+", "-", s.lower())}">{html.escape(s)}</a>'
                   for s, cards in groups.items() if cards)
    count = len(papers)
    latest = max(v[0]["date"] for v in papers.values())
    notes_html = ""
    if notes:
        items = "".join(f'<li><a href="{href}">{html.escape(t)}</a> <span class="meta">{html.escape(d)}</span></li>'
                        for t, href, d in notes)
        notes_html = f'<section id="notes"><h2>Notes</h2><ul class="plain">{items}</ul></section>'
    head = f'<link rel="canonical" href="{SITE}/">\n<meta property="og:title" content="Research Preprints · Suvrit Sra">\n'
    body = f"""{nav(0)}
<header class="hero">
  <p class="eyebrow">{html.escape(AUTHOR)} · {html.escape(AFFILIATION)}</p>
  <h1>Research Preprints <span class="sub">(Oct 2026 onwards)</span></h1>
  <p class="lede">Papers released version by version, each file timestamped with
  <a href="https://opentimestamps.org">OpenTimestamps</a> on the day it appears. Every version stays
  available. Where a paper is also on arXiv, its page links there.</p>
  <p class="actions"><a class="btn primary" href="overview.pdf">One-paragraph summaries (PDF)</a><a class="btn" href="{REPO}">Source repository</a><a class="btn" href="{ARXIV_AUTHOR}">arXiv listing</a></p>
  <p class="toc">{toc}{' <a href="#notes">Notes</a>' if notes else ''}</p>
</header>
{sections}
{notes_html}
<footer>{count} papers · updated {long_date(latest)} · © {html.escape(AUTHOR)}</footer>
<script>
document.querySelectorAll('.chip[aria-controls]').forEach(b=>b.addEventListener('click',()=>{{
  const open=b.getAttribute('aria-expanded')!=='true';
  b.setAttribute('aria-expanded',open);
  document.getElementById(b.getAttribute('aria-controls')).hidden=!open;
}}));
{COPY_JS}
</script>"""
    return page("Research Preprints · Suvrit Sra", body, head,
                description=f"Mathematics preprints by {AUTHOR} ({AFFILIATION}), released version by version with OpenTimestamps proofs.")


# ---------------------------------------------------------------- build

NOTES = [("Matrix Spencer, twice: a comparison of arXiv:2608.28816 and arXiv:2609.15025",
          "notes/ms-note.pdf", "15 September 2026")]


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
    (HERE / "index.html").write_text(index_page(papers, subjects, info, NOTES))
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
