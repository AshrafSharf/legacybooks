"""Assemble peter-selby style section pages for a PDF-per-section book.

Each section's content is hand-written as an HTML fragment (a run of
<div class="card"> blocks) at  <fragments>/<chapter-slug>/<section-slug>.html.
The fragment may start with metadata comments:

    <!-- title: 7.6.1 Integrals of the type ∫eˣ[f(x)+f′(x)]dx -->
    <!-- subtitle: A shortcut that turns a whole family of integrals into one line -->

This script wraps every fragment in the shared page frame (sticky top bar,
section drawer, hero, prev/next footer, KaTeX, search) and writes
<book>/<chapter>/<section>/index.html, plus the chapter and book index pages.

    python3 tools/assemble_sections.py tn-cbse/cbse-12-part2 FRAGMENT_DIR
"""
import html, os, re, sys, json

BOOKS = {
    "cbse-12-part2": {
        "title": "Class 12 Mathematics · Part 2",
        "board": "NCERT / CBSE",
        "subtitle": "Integrals, differential equations, vectors, 3-D geometry, "
                    "linear programming and probability",
    },
}
KATEX = "https://cdn.jsdelivr.net/npm/katex@0.16.9/dist"
SEARCH = 'assets/search.js?v=1789782771'
SHOT = 'assets/screenshot.js?v=2'
SMALL = {"a", "an", "and", "as", "at", "by", "for", "in", "of", "on", "or", "the", "to", "with"}


def e(s):
    # combining arrows only render through KaTeX; plain-text spots drop them
    return html.escape((s or "").replace("\u20d7", ""), quote=True)

SUB = str.maketrans("₀₁₂₃₄₅₆₇₈₉", "0123456789")
VEC_RE = re.compile(r"([A-Za-z])\u20d7([₀-₉]?)")
TEX_VEC_RE = re.compile(r"\\\(\\vec\{([A-Za-z])\}(?:_\{(\d)\})?\\\)")


def to_math(text):
    """Combining-arrow vectors (b⃗₁) → KaTeX, for text shown in the page body."""
    return VEC_RE.sub(lambda m: "\\(\\vec{%s}%s\\)" % (
        m.group(1), "_{%s}" % m.group(2).translate(SUB) if m.group(2) else ""), text)


def from_math(text):
    """Inverse of to_math, used when recovering titles from built pages."""
    return TEX_VEC_RE.sub(lambda m: m.group(1) + "\u20d7" + (
        "₀₁₂₃₄₅₆₇₈₉"[int(m.group(2))] if m.group(2) else ""), text)


def plain(text):
    """Drop combining arrows where KaTeX does not run (tab title, crumbs, buttons)."""
    return text.replace("\u20d7", "")


def slug_title(slug):
    s = re.sub(r"^\d+-", "", slug)
    num = ""
    m = re.search(r"-(\d+(?:\.\d+)+)$", s)
    if m:
        num, s = m.group(1), s[:m.start()]
    words = s.split("-")
    words = [w if (i and w in SMALL) else w.capitalize() for i, w in enumerate(words)]
    t = " ".join(words)
    t = re.sub(r"\bExercise (\d+)", r"Exercise \1", t)
    if t.startswith("Exercise") and num:
        return "Exercise " + num
    return (num + " " + t).strip() if num else t


def chapter_meta(slug):
    m = re.match(r"(\d+)-(.*)", slug)
    n = int(m.group(1))
    return n, slug_title(slug)


def read_fragment(path):
    with open(path, encoding="utf-8") as f:
        src = f.read()
    meta = {}
    for k, v in re.findall(r"<!--\s*(title|subtitle)\s*:\s*(.*?)\s*-->", src):
        meta.setdefault(k, v)
    body = re.sub(r"<!--\s*(title|subtitle)\s*:.*?-->\s*", "", src)
    return meta, body.strip()


def from_page(path):
    """Recover title/subtitle/body from an already assembled page."""
    if not os.path.exists(path):
        return {}, None
    src = open(path, encoding="utf-8").read()
    m = re.search(r"<!-- content:start -->\n?(.*?)\n?<!-- content:end -->", src, re.S)
    if not m:
        return {}, None
    meta = {}
    t = re.search(r'<div class="hero">.*?<h1>(.*?)</h1>', src, re.S)
    if t:
        meta["title"] = from_math(html.unescape(t.group(1)))
    st = re.search(r'<p class="subtitle">(.*?)</p>', src, re.S)
    if st:
        meta["subtitle"] = from_math(html.unescape(st.group(1)))
    return meta, m.group(1)


def page(title, depth, body, desc=""):
    up = "../" * depth
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{e(title)}</title>
    <meta name="description" content="{e(desc)}">
    <link rel="icon" href="data:image/svg+xml,<svg xmlns='http://www.w3.org/2000/svg' viewBox='0 0 100 100'><text y='.9em' font-size='90'>📘</text></svg>">
    <link rel="stylesheet" href="{KATEX}/katex.min.css">
    <link rel="stylesheet" href="{up}assets/style.css">
</head>
<body>
{body}
<script src="{KATEX}/katex.min.js"></script>
<script src="{KATEX}/contrib/auto-render.min.js"></script>
<script src="{up}assets/section.js"></script>
<script defer src="{up}../../{SEARCH}"></script>
<script defer src="{up}../../{SHOT}"></script>
</body>
</html>
"""


def topbar(crumb1, crumb2, prev=None, nxt=None, drawer=""):
    def btn(item, kind, label):
        if not item:
            return f'<span class="tb-btn" aria-disabled="true">{label}</span>'
        return (f'<a class="tb-btn" data-nav="{kind}" href="{e(item["href"])}" '
                f'title="{e(item["title"])}">{label}</a>')
    return f"""<header class="topbar">
<div class="topbar-in">
  {btn(prev, "prev", "←")}
  <div class="crumb">
    <span class="c1">{crumb1}</span>
    <span class="c2">{e(crumb2)}</span>
  </div>
  {drawer}
  {btn(nxt, "next", "→")}
</div>
</header>"""


def hero(num, eyebrow, title, subtitle):
    numdiv = f'<div class="chapter-num">{e(str(num))}</div>' if num != "" else ""
    sub = f'<p class="subtitle">{e(to_math(subtitle))}</p>' if subtitle else ""
    return f"""<div class="hero">
    {numdiv}
    <div class="inner">
        <p class="eyebrow">{eyebrow}</p>
        <h1>{e(to_math(title))}</h1>
        {sub}
    </div>
</div>"""


def nav_footer(prev, nxt, prev_none, next_none):
    p = (f'<a href="{e(prev["href"])}" class="nav-btn">&larr; {e(prev["title"])}</a>' if prev
         else f'<span class="nav-btn disabled">{prev_none}</span>')
    n = (f'<a href="{e(nxt["href"])}" class="nav-btn">{e(nxt["title"])} &rarr;</a>' if nxt
         else f'<span class="nav-btn disabled">{next_none}</span>')
    return f'<div class="nav-footer">\n    {p}\n    {n}\n</div>'


def main(book_dir, frag_dir):
    book_dir = book_dir.rstrip("/")
    key = os.path.basename(book_dir)
    book = BOOKS[key]
    chapters = []
    for ch in sorted(d for d in os.listdir(book_dir)
                     if re.match(r"\d+-", d) and os.path.isdir(os.path.join(book_dir, d))):
        n, ctitle = chapter_meta(ch)
        secs = []
        for s in sorted(d for d in os.listdir(os.path.join(book_dir, ch))
                        if re.match(r"\d+-", d) and os.path.isdir(os.path.join(book_dir, ch, d))):
            fp = os.path.join(frag_dir, ch, s + ".html")
            meta, body = read_fragment(fp) if os.path.exists(fp) else from_page(
                os.path.join(book_dir, ch, s, "index.html"))
            pdfs = [f for f in os.listdir(os.path.join(book_dir, ch, s)) if f.endswith(".pdf")]
            secs.append({"slug": s, "chapter": ch, "title": meta.get("title") or slug_title(s),
                         "subtitle": meta.get("subtitle", ""), "body": body,
                         "pdf": pdfs[0] if pdfs else None})
        label = "Appendix" if n >= 90 else "Chapter %d" % n
        chapters.append({"slug": ch, "num": n, "title": "Appendix" if n >= 90 else ctitle,
                         "label": label, "sections": secs})

    flat = [s for c in chapters for s in c["sections"]]
    missing = [s["chapter"] + "/" + s["slug"] for s in flat if s["body"] is None]
    crumb_book = f'<a href="../../../index.html">Library</a> · <a href="../../index.html">{e(book["title"])}</a>'

    for c in chapters:
        for s in c["sections"]:
            i = flat.index(s)
            def link(o):
                if not o:
                    return None
                return {"href": f"../../{o['chapter']}/{o['slug']}/index.html", "title": o["title"]}
            prev = link(flat[i - 1]) if i > 0 else None
            nxt = link(flat[i + 1]) if i + 1 < len(flat) else None
            items = "".join(
                f'<a href="../{x["slug"]}/index.html"{" aria-current=\"page\"" if x is s else ""}>{e(x["title"])}</a>'
                for x in c["sections"])
            drawer = (f'<details class="drawer"><summary class="tb-btn" title="Sections in this chapter">☰</summary>'
                      f'<div class="drawer-panel"><div class="dh">{e(c["label"])} · {e(c["title"])}</div>{items}</div></details>')
            body = s["body"] if s["body"] is not None else (
                '<div class="card"><h2>Coming soon</h2><p>This section has not been written up yet.</p></div>')
            eyebrow = f'<a href="../index.html">{e(c["label"])} · {e(c["title"])}</a>'
            num = "" if c["num"] >= 90 else c["num"]
            out = "\n".join([
                topbar(crumb_book + f' · <a href="../index.html">{e(c["title"])}</a>', s["title"], prev, nxt, drawer),
                hero(num, eyebrow, s["title"], s["subtitle"]),
                '<div class="container">',
                "<!-- content:start -->\n" + body + "\n<!-- content:end -->" if s["body"] is not None else body,
                "\n" + nav_footer(prev, nxt, "Start of book", "End of book"),
                "</div><!-- end container -->",
            ])
            dest = os.path.join(book_dir, c["slug"], s["slug"], "index.html")
            with open(dest, "w", encoding="utf-8") as f:
                f.write(page(f'{s["title"]} — {c["title"]}', 2, out,
                             desc=f'{book["title"]} · {c["title"]} · {s["title"]}'))

        # chapter index
        rows = "".join(
            f'<li><a href="{x["slug"]}/index.html"><span class="n">{j + 1:02d}</span>'
            f'<span class="t">{e(x["title"])}</span></a></li>' for j, x in enumerate(c["sections"]))
        ci = [c2 for c2 in chapters]
        k = ci.index(c)
        prev = {"href": f"../{ci[k-1]['slug']}/index.html", "title": ci[k-1]["title"]} if k > 0 else None
        nxt = {"href": f"../{ci[k+1]['slug']}/index.html", "title": ci[k+1]["title"]} if k + 1 < len(ci) else None
        out = "\n".join([
            topbar(f'<a href="../../index.html">Library</a> · <a href="../index.html">{e(book["title"])}</a>',
                   f'{c["label"]} — {c["title"]}', prev, nxt),
            hero("" if c["num"] >= 90 else c["num"], e(c["label"]), c["title"],
                 f'{len(c["sections"])} sections · {book["title"]}'),
            '<div class="container">',
            f'<div class="card"><h2>Sections</h2><ul class="toc">{rows}</ul></div>',
            nav_footer(prev, nxt, "First chapter", "Last chapter"),
            "</div>",
        ])
        with open(os.path.join(book_dir, c["slug"], "index.html"), "w", encoding="utf-8") as f:
            f.write(page(f'{c["title"]} — {book["title"]}', 1, out,
                         desc=f'Sections of {c["title"]}'))

    # book index
    cards = "".join(
        f'<a class="chapter-card" href="{c["slug"]}/index.html"><span class="num">{e(c["label"])}</span>'
        f'<h3>{e(c["title"])}</h3><p>{len(c["sections"])} sections</p></a>' for c in chapters)
    out = "\n".join([
        topbar('<a href="../index.html">Library</a>', book["title"]),
        hero("12", e(book["board"]), book["title"], book["subtitle"]),
        '<div class="container">',
        f'<div class="chapter-grid">{cards}</div>',
        "</div>",
    ])
    with open(os.path.join(book_dir, "index.html"), "w", encoding="utf-8") as f:
        f.write(page(f'{book["title"]} — {book["board"]}', 0, out, desc=book["subtitle"]))

    print(f"{len(flat)} sections, {len(flat) - len(missing)} written, {len(missing)} missing")
    for m in missing:
        print("  missing:", m)


if __name__ == "__main__":
    main(sys.argv[1], sys.argv[2])
