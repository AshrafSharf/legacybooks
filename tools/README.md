# tn-cbse book builder

Converts the split section PDFs under `robogebra-books/tn_cbse/` into a static,
section-per-page HTML library at `gen-books/legacybooks/tn-cbse/`.

```
tn-cbse/
  index.html                 library (all books, grouped by board)
  assets/book.css|book.js    shared theme + keyboard nav
  <book>/index.html          chapters of one book
    <chapter>/index.html     sections of one chapter
      <section>/index.html   the section itself
      <section>/img/*.webp   its figures
```

## Running it

```bash
python3 -m venv .venv && .venv/bin/pip install pymupdf pillow
.venv/bin/python tools/buildsite.py                       # everything
.venv/bin/python tools/buildsite.py --books tn-6-term1     # one book
.venv/bin/python tools/buildsite.py --books tn-9 --chapters 03-algebra
.venv/bin/python tools/buildsite.py --out /tmp/preview     # somewhere else
.venv/bin/python tools/prune.py                            # drop unreferenced crops
.venv/bin/python tools/check.py                            # broken links / empty sections
```

Sections that share a boundary page with their neighbour have the neighbour's
content trimmed away, which can leave a crop nothing references; `prune.py`
deletes those. Run it after every build.

`tools/catalog.py` prints the discovered structure when run on its own.

## How the conversion works

`catalog.py` walks every `*-sections` directory, reads its `CONTENTS.md` for the
chapter number and the per-file section titles, and adds any loose PDFs beside
the chapter folders as an "Appendix" chapter.

`extract.py` turns one section PDF into ordered content items:

* **Text** comes from PyMuPDF spans. The dominant character size in the document
  is the body size; larger/bold runs become headings, `(i)`/`1.`/bullets become
  list items, and running heads, page numbers and print marks are dropped by
  margin position plus a junk pattern.
* **Figures** are almost all vector art, so they are rendered as clipped page
  regions rather than extracted image streams. Drawings are clustered, parts of
  one illustration sitting side by side or stacked are merged, coloured panels
  (NOTE / activity boxes) stay separate and float as margin figures, stray point
  labels (A, B, (i)) are pulled into the nearest crop, and every crop is trimmed
  back so it never slices through prose. Grid-like regions are kept whole as
  table images instead of being linearised into scrambled text.
* **Mathematics** is rebuilt into LaTeX and rendered by KaTeX: stacked
  numerator/rule/denominator triples become `\frac{}{}` (a rule only counts when
  it hugs and centres its digits, so table borders are not mistaken for fraction
  bars), raised/lowered small spans become `^{}`/`_{}`, unicode operators map to
  their LaTeX names, and runs of mathematical tokens are wrapped in `\( \)`.

`buildsite.py` renders the pages: sticky breadcrumb bar, previous/next buttons
(also bound to the ← → keys), a drawer listing the sibling sections, a reading
progress bar across the whole book, and the light/dark theme.

Figures are written as WebP — lossless for line art, quality 84 for photographs.
