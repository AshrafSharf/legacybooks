"""Discover books / chapters / sections from the split-PDF tree."""
import os, re, json

SRC_ROOT = "/Users/apple/lesson-ws/robogebra-books/tn_cbse"

SMALL = {"a", "an", "and", "as", "at", "by", "for", "from", "in", "of", "on",
         "or", "the", "to", "with", "into", "using"}


def titlecase(slug):
    words = slug.replace("_", " ").replace("-", " ").split()
    out = []
    for i, w in enumerate(words):
        lw = w.lower()
        if lw in ("ict", "hcf", "lcm", "tn", "cbse"):
            out.append(lw.upper())
        elif i and lw in SMALL:
            out.append(lw)
        else:
            out.append(lw[:1].upper() + lw[1:])
    return " ".join(out)


def book_meta(parent_rel):
    """Map the folder holding the *-sections dirs to book identity."""
    p = parent_rel.replace("\\", "/")
    m = re.match(r'^TN/(\d+)(?:/term(\d))?$', p)
    if m:
        grade, term = m.group(1), m.group(2)
        slug = "tn-%s" % grade + ("-term%s" % term if term else "")
        title = "Class %s Mathematics" % grade + (" · Term %s" % term if term else "")
        return dict(slug=slug, title=title, board="Tamil Nadu State Board",
                    board_short="TN", grade=int(grade), term=int(term) if term else 0)
    m = re.match(r'.*?/(\d+)(?:th|st|nd|rd)_[Cc][Bb][Ss][Ee](?:_part_(\d))?_chapters$', p)
    if m:
        grade, part = m.group(1), m.group(2)
        slug = "cbse-%s" % grade + ("-part%s" % part if part else "")
        title = "Class %s Mathematics" % grade + (" · Part %s" % part if part else "")
        return dict(slug=slug, title=title, board="NCERT / CBSE — Ganita Prakash",
                    board_short="CBSE", grade=int(grade), term=int(part) if part else 0)
    slug = re.sub(r'[^a-z0-9]+', '-', p.lower()).strip('-')
    return dict(slug=slug, title=titlecase(os.path.basename(p)), board="Other",
                board_short="", grade=0, term=0)


ROW_RE = re.compile(r'^\|\s*([^|]+?)\s*\|\s*([^|]*?)\s*\|\s*([^|]*?)\s*\|\s*$')


def read_contents(path):
    """-> (chapter_number, chapter_slug, {filename: (title, pages)})"""
    num, cslug, rows = None, None, {}
    if not os.path.exists(path):
        return num, cslug, rows
    for line in open(path, encoding="utf-8"):
        line = line.rstrip("\n")
        m = re.match(r'^#\s*ch(\d+)-(\S+)\s+—', line)
        if m:
            num, cslug = int(m.group(1)), m.group(2)
            continue
        m = ROW_RE.match(line)
        if m:
            f, title, pages = m.group(1), m.group(2), m.group(3)
            if not f.endswith(".pdf"):
                continue
            rows[f.strip('`')] = (title.strip(), pages.strip())
    return num, cslug, rows


def discover():
    books = {}
    for dirpath, dirnames, filenames in os.walk(SRC_ROOT):
        if not dirpath.endswith("-sections"):
            continue
        pdfs = sorted(f for f in filenames if f.lower().endswith(".pdf"))
        if not pdfs:
            continue
        parent_rel = os.path.relpath(os.path.dirname(dirpath), SRC_ROOT)
        meta = book_meta(parent_rel)
        book = books.setdefault(meta["slug"], dict(meta, chapters=[], src=parent_rel))
        num, cslug, rows = read_contents(os.path.join(dirpath, "CONTENTS.md"))
        folder = os.path.basename(dirpath)[: -len("-sections")]
        cslug = cslug or folder
        chapter = {
            "number": num or 0,
            "slug": "%02d-%s" % (num, folder) if num else folder,
            "title": titlecase(folder),
            "src_dir": dirpath,
            "sections": [],
        }
        for i, f in enumerate(pdfs, 1):
            title, pages = rows.get(f, ("", ""))
            sslug = re.sub(r'\.pdf$', '', f)
            if not title:
                title = titlecase(re.sub(r'^\d+-', '', sslug))
            chapter["sections"].append({
                "index": i, "slug": sslug, "title": title, "pages": pages,
                "pdf": os.path.join(dirpath, f),
            })
        book["chapters"].append(chapter)

    # loose PDFs sitting beside the chapter folders (front matter, answers, glossary)
    for b in books.values():
        src = os.path.join(SRC_ROOT, b["src"])
        extras = sorted(f for f in os.listdir(src)
                        if f.lower().endswith(".pdf") and os.path.isfile(os.path.join(src, f)))
        if not extras:
            continue
        secs = []
        for i, f in enumerate(extras, 1):
            sslug = re.sub(r'\.pdf$', '', f)
            secs.append({"index": i, "slug": sslug,
                         "title": titlecase(re.sub(r'^\d+-', '', sslug)),
                         "pages": "", "pdf": os.path.join(src, f)})
        b["chapters"].append({"number": 90, "slug": "90-appendix", "title": "Appendix",
                              "src_dir": src, "sections": secs})

    out = []
    for slug, b in books.items():
        b["chapters"].sort(key=lambda c: (c["number"] or 99, c["slug"]))
        out.append(b)
    out.sort(key=lambda b: (b["board_short"], b["grade"], b["term"]))
    return out


if __name__ == "__main__":
    bs = discover()
    tot_s = sum(len(c["sections"]) for b in bs for c in b["chapters"])
    print("books %d  chapters %d  sections %d" %
          (len(bs), sum(len(b["chapters"]) for b in bs), tot_s))
    for b in bs:
        print("  %-14s %-32s %2d chapters, %3d sections" %
              (b["slug"], b["title"], len(b["chapters"]),
               sum(len(c["sections"]) for c in b["chapters"])))
        for c in b["chapters"][:2]:
            print("      ch%s %s -> %s" % (c["number"], c["slug"], [s["title"] for s in c["sections"]][:3]))
