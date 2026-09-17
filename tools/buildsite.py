"""Build the HTML book site from the split section PDFs."""
import os, sys, re, json, html, shutil, time, argparse, traceback

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import catalog, extract, theme

OUT_ROOT = "/Users/apple/lesson-ws/robogebra-books/gen-books/legacybooks/tn-cbse"
KATEX = "https://cdn.jsdelivr.net/npm/katex@0.16.11/dist"


def e(s):
    return html.escape(s or "", quote=True)


def head(title, depth, desc="", extra=""):
    up = "../" * depth
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{e(title)}</title>
<meta name="description" content="{e(desc)}">
<link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📘</text></svg>">
<link rel="stylesheet" href="{up}assets/book.css">
<link rel="stylesheet" href="{KATEX}/katex.min.css" crossorigin="anonymous">
{extra}</head>
<body>
"""


def tail(depth, katex=True):
    up = "../" * depth
    k = ""
    if katex:
        k = f"""<script defer src="{KATEX}/katex.min.js" crossorigin="anonymous"></script>
<script defer src="{KATEX}/contrib/auto-render.min.js" crossorigin="anonymous"
  onload="renderMathInElement(document.body,{{delimiters:[
    {{left:'\\\\(',right:'\\\\)',display:false}},
    {{left:'$$',right:'$$',display:true}},
    {{left:'\\\\[',right:'\\\\]',display:true}}],throwOnError:false,ignoredTags:['script','noscript','style','textarea','pre','code']}})"></script>
"""
    return f"""{k}<script src="{up}assets/book.js"></script>
</body>
</html>
"""


def theme_btn():
    return ('<button class="tb-btn" data-theme-toggle title="Toggle light / dark" '
            'aria-label="Toggle light or dark theme">◐</button>')


def topbar(depth, c1, c1href, c2, prev, nxt, drawer_html="", progress=None):
    up = "../" * depth
    def navbtn(item, kind, label):
        if not item:
            return f'<span class="tb-btn" aria-disabled="true">{label}</span>'
        return (f'<a class="tb-btn" data-nav="{kind}" href="{e(item["href"])}" '
                f'title="{e(item["title"])}">{label}</a>')
    bar = ''
    if progress is not None:
        bar = f'<div class="progress"><span style="width:{progress:.1f}%"></span></div>'
    crumb1 = (f'<a href="{up}index.html">Library</a>' if c1 == "Library"
              else f'<a href="{up}index.html">Library</a> · <a href="{e(c1href)}">{e(c1)}</a>')
    return f"""<header class="topbar">
<div class="topbar-in">
  <div class="crumb">
    <span class="c1">{crumb1}</span>
    <span class="c2">{e(c2)}</span>
  </div>
  {navbtn(prev,'prev','←')}
  {drawer_html}
  {navbtn(nxt,'next','→')}
  {theme_btn()}
</div>
{bar}
</header>
"""


def drawer(sections, current_slug, chapter_title):
    items = []
    for s in sections:
        cur = ' aria-current="page"' if s["slug"] == current_slug else ''
        items.append(f'<a href="{e(s["href"])}"{cur}>{e(s["title"])}</a>')
    return f"""<details class="drawer"><summary class="tb-btn" title="Sections in this chapter">☰</summary>
<div class="drawer-panel"><div class="dh">{e(chapter_title)}</div>{''.join(items)}</div></details>"""


def pager(prev, nxt):
    def card(item, kind):
        if not item:
            return '<span></span>'
        cls = 'nx' if kind == 'next' else ''
        dirn = 'Next →' if kind == 'next' else '← Previous'
        return (f'<a class="{cls}" data-nav="{kind}" href="{e(item["href"])}">'
                f'<span class="dir">{dirn}</span>'
                f'<span class="t">{e(item["title"])}</span>'
                f'<span class="ch">{e(item.get("chapter",""))}</span></a>')
    return f'<nav class="pager">{card(prev,"prev")}{card(nxt,"next")}</nav>'


def site_footer(note=""):
    return (f'<footer class="site">{e(note)}</footer>' if note else
            '<footer class="site">Generated from the source textbook PDFs · '
            'text, figures and exercises belong to their respective publishers.</footer>')


# ------------------------------------------------------------------ builders
def build_section(book, chapter, sec, idx, flat, out_dir, stats):
    os.makedirs(out_dir, exist_ok=True)
    imgdir = os.path.join(out_dir, "img")
    if os.path.isdir(imgdir):
        shutil.rmtree(imgdir)
    os.makedirs(imgdir, exist_ok=True)

    nxt_title = flat[idx + 1]["title"] if idx + 1 < len(flat) else ""
    if idx + 1 < len(flat) and flat[idx + 1]["chapter_slug"] != chapter["slug"]:
        nxt_title = ""
    first = idx == 0 or flat[idx - 1]["chapter_slug"] != chapter["slug"]
    try:
        items, npages = extract.extract_section(
            sec["pdf"], imgdir, "fig", sec["title"], nxt_title, first)
        body_html = extract.items_to_html(items, sec["title"])
    except Exception:
        stats["failed"].append(sec["pdf"])
        body_html = '<p class="lead">This section could not be converted automatically.</p>'
        npages = 0
    nfigs = len([f for f in os.listdir(imgdir)]) if os.path.isdir(imgdir) else 0
    if nfigs == 0:
        os.rmdir(imgdir)

    prev = flat[idx - 1] if idx > 0 else None
    nxt = flat[idx + 1] if idx + 1 < len(flat) else None
    def link(o, updepth=2):
        if not o:
            return None
        return {"href": "../../" + o["chapter_slug"] + "/" + o["slug"] + "/index.html",
                "title": o["title"], "chapter": o["chapter_title"]}
    sibs = [{"slug": s["slug"], "title": s["title"], "href": "../" + s["slug"] + "/index.html"}
            for s in chapter["sections"]]
    progress = 100.0 * (idx + 1) / max(len(flat), 1)

    chap_label = "Chapter %d" % chapter["number"] if 0 < chapter["number"] < 90 else "Appendix"
    title = "%s — %s" % (sec["title"], chapter["title"])
    out = [head(title, 3, desc="%s · %s · %s" % (book["title"], chapter["title"], sec["title"]))]
    out.append(topbar(3, book["title"], "../../index.html",
                      "%s · %s" % (chapter["title"], sec["title"]),
                      link(prev), link(nxt), drawer(sibs, sec["slug"], chapter["title"]), progress))
    meta_bits = []
    if sec.get("pages"):
        meta_bits.append("Textbook pages %s" % sec["pages"])
    if nfigs:
        meta_bits.append("%d figure%s" % (nfigs, "" if nfigs == 1 else "s"))
    out.append(f"""<main class="wrap">
<div class="sec-head">
  <p class="eyebrow"><a href="../index.html">{chap_label} · {e(chapter['title'])}</a></p>
  <h1>{e(sec['title'])}</h1>
  <p class="sec-meta">{e(' · '.join(meta_bits))}</p>
</div>
<article class="prose">
{body_html}
</article>
{pager(link(prev), link(nxt))}
</main>""")
    out.append(site_footer())
    out.append(tail(3))
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write("".join(out))
    stats["sections"] += 1
    stats["figures"] += nfigs
    return nfigs


def build_chapter_index(book, chapter, out_dir):
    rows = []
    for s in chapter["sections"]:
        rows.append(f"""<li><a href="{e(s['slug'])}/index.html">
      <span class="n">{s['index']:02d}</span>
      <span class="t">{e(s['title'])}</span>
      <span class="p">{e(s.get('pages',''))}</span></a></li>""")
    out = [head("%s — %s" % (chapter["title"], book["title"]), 2,
                desc="Sections of %s" % chapter["title"])]
    out.append(topbar(2, book["title"], "../index.html", chapter["title"], None, None))
    out.append(f"""<div class="hero">
  <p class="eyebrow">{"Chapter %d" % chapter['number'] if 0 < chapter['number'] < 90 else "Appendix"}</p>
  <h1>{e(chapter['title'])}</h1>
  <p>{len(chapter['sections'])} sections · {e(book['title'])} · {e(book['board'])}</p>
</div>
<main class="wrap">
<ul class="seclist">{''.join(rows)}</ul>
</main>""")
    out.append(site_footer())
    out.append(tail(2, katex=False))
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write("".join(out))


def build_book_index(book, out_dir):
    cards = []
    for c in book["chapters"]:
        cards.append(f"""<a class="card" href="{e(c['slug'])}/index.html">
      <span class="num">{c['number'] if 0 < c['number'] < 90 else 'A'}</span>
      <span class="body"><span class="t">{e(c['title'])}</span>
      <span class="s">{len(c['sections'])} sections</span></span>
      <span class="go">→</span></a>""")
    nsec = sum(len(c["sections"]) for c in book["chapters"])
    out = [head(book["title"] + " — " + book["board"], 1, desc=book["board"])]
    out.append(topbar(1, "Library", "../index.html", book["title"], None, None))
    out.append(f"""<div class="hero">
  <p class="eyebrow">{e(book['board'])}</p>
  <h1>{e(book['title'])}</h1>
  <p>{len(book['chapters'])} chapters · {nsec} sections</p>
</div>
<main class="wrap">
<div class="grid">{''.join(cards)}</div>
</main>""")
    out.append(site_footer())
    out.append(tail(1, katex=False))
    with open(os.path.join(out_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write("".join(out))


def build_library(books, out_root):
    groups = {}
    for b in books:
        groups.setdefault(b["board"], []).append(b)
    blocks = []
    for board, bs in groups.items():
        cards = []
        for b in bs:
            nsec = sum(len(c["sections"]) for c in b["chapters"])
            cards.append(f"""<a class="card" href="{e(b['slug'])}/index.html">
        <span class="num">{b['grade']}</span>
        <span class="body"><span class="t">{e(b['title'])}</span>
        <span class="s">{len(b['chapters'])} chapters · {nsec} sections</span></span>
        <span class="go">→</span></a>""")
        blocks.append(f'<h2 class="group-h">{e(board)}</h2><div class="grid two">{"".join(cards)}</div>')
    total_sec = sum(len(c["sections"]) for b in books for c in b["chapters"])
    out = [head("Mathematics Library", 0, desc="Tamil Nadu and NCERT mathematics textbooks, section by section.")]
    out.append(f"""<header class="topbar"><div class="topbar-in">
  <div class="crumb"><span class="c2">Mathematics Library</span></div>{theme_btn()}
</div></header>
<div class="hero">
  <p class="eyebrow">Legacy Books</p>
  <h1>Mathematics, section by section</h1>
  <p>{len(books)} textbooks · {sum(len(b['chapters']) for b in books)} chapters · {total_sec} readable sections,
  each with its figures and KaTeX-rendered mathematics.</p>
</div>
<main class="wrap">{''.join(blocks)}</main>""")
    out.append(site_footer())
    out.append(tail(0, katex=False))
    with open(os.path.join(out_root, "index.html"), "w", encoding="utf-8") as f:
        f.write("".join(out))


def write_assets(out_root):
    d = os.path.join(out_root, "assets")
    os.makedirs(d, exist_ok=True)
    open(os.path.join(d, "book.css"), "w", encoding="utf-8").write(theme.CSS)
    open(os.path.join(d, "book.js"), "w", encoding="utf-8").write(theme.JS)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--books", default="", help="comma separated book slugs (default: all)")
    ap.add_argument("--chapters", default="", help="comma separated chapter slugs")
    ap.add_argument("--out", default=OUT_ROOT)
    args = ap.parse_args()

    books = catalog.discover()
    if args.books:
        want = set(args.books.split(","))
        books = [b for b in books if b["slug"] in want]
    os.makedirs(args.out, exist_ok=True)
    write_assets(args.out)

    stats = {"sections": 0, "figures": 0, "failed": []}
    t0 = time.time()
    for b in books:
        bdir = os.path.join(args.out, b["slug"])
        os.makedirs(bdir, exist_ok=True)
        chapters = b["chapters"]
        if args.chapters:
            want = set(args.chapters.split(","))
            chapters = [c for c in chapters if c["slug"] in want]
        flat = []
        for c in b["chapters"]:
            for s in c["sections"]:
                flat.append(dict(s, chapter_slug=c["slug"], chapter_title=c["title"]))
        pos = {(f["chapter_slug"], f["slug"]): i for i, f in enumerate(flat)}
        for c in chapters:
            cdir = os.path.join(bdir, c["slug"])
            os.makedirs(cdir, exist_ok=True)
            build_chapter_index(b, c, cdir)
            for s in c["sections"]:
                i = pos[(c["slug"], s["slug"])]
                build_section(b, c, s, i, flat, os.path.join(cdir, s["slug"]), stats)
            print("  %-14s %-36s %3d sections  (%.0fs)" %
                  (b["slug"], c["slug"], len(c["sections"]), time.time() - t0), flush=True)
        build_book_index(b, bdir)
    build_library(catalog.discover(), args.out)
    print("done: %d sections, %d figures, %d failed, %.0fs"
          % (stats["sections"], stats["figures"], len(stats["failed"]), time.time() - t0))
    if stats["failed"]:
        print("failed:", *stats["failed"][:20], sep="\n  ")


if __name__ == "__main__":
    main()
