"""Extract structured content from a section PDF.

Produces an ordered list of content items (headings, paragraphs, lists,
figures, panels) plus cropped PNGs for every figure region found on the page.
Figures in these textbooks are mostly vector drawings, so they are rendered as
clipped page regions rather than pulled out as embedded image streams.
"""
import re, os, math, json
from collections import Counter
import pymupdf

# ---------------------------------------------------------------- constants
JUNK_RE = re.compile(
    r'(\.indd\b'
    r'|Reprint\s+\d{4}'
    r'|^\s*\d{1,2}/\d{1,2}/\d{2,4}\s*$'
    r'|^\s*\d{1,2}:\d{2}(:\d{2})?\s*(AM|PM)\s*$'
    r'|www\.|http'
    r'|^\s*XXX\s*$)', re.I)

RUNNING_HEAD_RE = re.compile(
    r'^\s*(\d{1,3}\s*)?('
    r'\d+\s*th\s+Standard\s+Mathematics|Mathematics|Maths'
    r'|Ganita\s+Prakash(\s*\|\s*Grade\s*\d+)?'
    r'|Grade\s*\d+)\s*(\d{1,3})?\s*$', re.I)

LIST_RE = re.compile(r'^\s*('
                     r'\(\s*[ivxlcIVXLC]{1,5}\s*\)'      # (i) (ii)
                     r'|\(\s*[a-zA-Z]\s*\)'              # (a)
                     r'|\d{1,2}\s*[.)]'                  # 1. 1)
                     r'|[ivx]{1,4}\s*[.)]'               # i. ii)
                     r'|[a-z]\s*[.)]'                    # a.
                     r'|[•▪●■◆✤➤*]'                      # bullets
                     r')\s+')

CALLOUT_RE = re.compile(
    r'^\s*(exercise|example|solution|activity|try\s+(these|this|it)|note|notes|think|'
    r'summary|points\s+to\s+remember|miscellaneous[\w\s]*|challenging\s+problems|'
    r'ict\s+corner|figure\s+it\s+out|math\s+talk|do\s+you\s+know|recall|'
    r'objectives?|situation|aim|procedure|observation|conclusion|step[s]?\b|'
    r'let\s+us\s+(think|try|do|learn)|problems?\s+based\s+on)\b', re.I)

FIG_CAPTION_RE = re.compile(r'^\s*(fig(ure)?\.?\s*\d|table\s*\d|graph\s*\d)', re.I)

# a callout *heading* is the keyword standing alone, optionally numbered
CALLOUT_HEAD_RE = re.compile(
    r'^\s*(exercise|example|solution|activity|try\s+(these|this|it)|note|notes|think|'
    r'summary|points\s+to\s+remember|miscellaneous(\s+\w+){0,3}|challenging\s+problems|'
    r'ict\s+corner|figure\s+it\s+out|math\s+talk|do\s+you\s+know|recall|objectives?|'
    r'aim|procedure|observation|conclusion|let\s+us\s+(think|try|do|learn)|'
    r'step\s*\d*|situation\s*\d*)'
    r'\s*[:.\-]?\s*(\d+(\.\d+)*)?\s*[:.\-]?\s*$', re.I)

# label-ish text that belongs to a diagram rather than the prose flow
LABEL_TXT_RE = re.compile(r'^[\sA-Z0-9°\'\u2032\u2033()\[\].,\-+×÷=/∠△∆]{1,7}$')


def rect_gap(a, b):
    dx = max(a.x0 - b.x1, b.x0 - a.x1, 0)
    dy = max(a.y0 - b.y1, b.y0 - a.y1, 0)
    return (dx * dx + dy * dy) ** 0.5


POINT_LABEL_RE = re.compile(
    r'^(?:'
    r"[A-Z][A-Z0-9]{0,3}'?"                 # A, AB, P1, A'
    r'|[a-z]'                               # a
    r'|\(?[ivxIVX]{1,4}\)?'                 # (i) (iv)
    r'|\(?[a-zA-Z]\)'                       # (a)
    r'|\d{1,3}(?:\.\d)?\s*(?:°|\^\{\\circ\})?'  # 45, 45°, 7.5
    r'|\\angle\s*[A-Z]{1,3}'
    r'|O|cm|m|mm|km'
    r')$')


def is_label_text(t):
    t = clean_ws(t)
    if not t or len(t) > 8:
        return False
    return bool(POINT_LABEL_RE.match(t))

# unicode -> latex for the math pass
UNI_MATH = {
    '×': r'\times', '÷': r'\div', '−': '-', '–': '-', '—': '-',
    '≤': r'\le', '≥': r'\ge', '≠': r'\ne', '≈': r'\approx', '≅': r'\cong',
    '∠': r'\angle', '°': r'^{\circ}', '√': r'\sqrt', 'π': r'\pi', '∞': r'\infty',
    '∴': r'\therefore', '∵': r'\because', '⇒': r'\Rightarrow', '→': r'\to',
    '↔': r'\leftrightarrow', '∥': r'\parallel', '⊥': r'\perp', '∆': r'\triangle',
    '△': r'\triangle', '∈': r'\in', '∉': r'\notin', '⊂': r'\subset',
    '⊆': r'\subseteq', '∪': r'\cup', '∩': r'\cap', '∅': r'\emptyset',
    '±': r'\pm', '∑': r'\sum', '≡': r'\equiv', '·': r'\cdot',
    'º': r'^{\circ}', '′': r"'", '″': r"''",
    '½': r'\tfrac{1}{2}', '¼': r'\tfrac{1}{4}', '¾': r'\tfrac{3}{4}',
    '⅓': r'\tfrac{1}{3}', '⅔': r'\tfrac{2}{3}',
}
SUP_DIGITS = {'²': '2', '³': '3', '¹': '1', '⁰': '0', '⁴': '4', '⁵': '5',
              '⁶': '6', '⁷': '7', '⁸': '8', '⁹': '9'}


def clean_ws(s):
    s = s.replace('\t', ' ').replace(' ', ' ').replace(' ', ' ')
    s = s.replace(' ', ' ').replace('​', '')
    return re.sub(r'\s+', ' ', s).strip()


# ---------------------------------------------------------------- span layer
def collect_spans(page):
    out = []
    for blk in page.get_text("dict")["blocks"]:
        if blk["type"] != 0:
            continue
        for line in blk["lines"]:
            d = line.get("dir", (1, 0))
            if abs(d[1]) > 0.2:          # rotated / vertical text (spine labels)
                continue
            for s in line["spans"]:
                if not s["text"].strip():
                    continue
                r = pymupdf.Rect(s["bbox"])
                out.append({
                    "text": s["text"], "bbox": r, "size": round(s["size"], 1),
                    "font": s["font"], "flags": s["flags"],
                    "bold": bool(s["flags"] & 16) or "bold" in s["font"].lower()
                            or "black" in s["font"].lower(),
                    "italic": bool(s["flags"] & 2) or "italic" in s["font"].lower()
                              or "-it" in s["font"].lower(),
                    "sup": bool(s["flags"] & 1),
                    "origin": s["origin"], "line": id(line), "used": False,
                })
    return out


def body_size_of(doc):
    c = Counter()
    for page in doc:
        for s in collect_spans(page):
            c[s["size"]] += len(s["text"].strip())
    if not c:
        return 12.0
    # ignore very small print (captions / credits) when picking the body size
    big = Counter({k: v for k, v in c.items() if k >= 7})
    return (big or c).most_common(1)[0][0]


# ------------------------------------------------------------- graphics layer
def is_frac_bar(r):
    return r.height <= 2.6 and 2.5 < r.width < 90


def graphic_rects(page, spans, body):
    """Rects of every drawing/image that could be part of a figure."""
    W, H = page.rect.width, page.rect.height
    PA = W * H
    rects, panels, bars = [], [], []
    for dr in page.get_drawings():
        d = dr["rect"]
        # clip by hand: Rect & Rect reports zero-height rules (fraction bars) as empty
        r = pymupdf.Rect(max(d.x0, 0), max(d.y0, 0), min(d.x1, W), min(d.y1, H))
        if r.x1 <= r.x0 - 0.01 or r.y1 <= r.y0 - 0.01:
            continue
        a = r.width * r.height
        if r.width < 0.8 and r.height < 0.8:
            continue
        if a > 0.60 * PA:                              # page frame / full bleed
            continue
        if is_frac_bar(r):
            bars.append(r)
            continue
        if r.height <= 2.0 and r.width > 0.45 * W:     # horizontal separator
            continue
        if r.y0 > 0.90 * H or r.y1 < 0.088 * H:        # decorative header/footer band
            continue
        if r.height < 0.6:                             # hairline rules: give them substance
            r.y1 = r.y0 + 0.6
        if r.width < 0.6:
            r.x1 = r.x0 + 0.6
        if dr.get("fill") is not None and a > 0.012 * PA:
            panels.append(r)
        rects.append(r)
    for im in page.get_image_info():
        r = pymupdf.Rect(im["bbox"]) & page.rect
        if not r.is_empty and r.width > 6 and r.height > 6 and r.width * r.height < 0.85 * PA:
            rects.append(r)
    return rects, panels, bars


def cluster(rects, pad=11.0, page_rect=None, rounds=8):
    """Merge nearby rects into figure regions (sweep-pruned, repeated to a fixed point)."""
    boxes = [pymupdf.Rect(r) for r in rects]
    for _ in range(rounds):
        boxes.sort(key=lambda b: (b.x0, b.y0))
        out, changed = [], False
        alive = [True] * len(boxes)
        for i, a in enumerate(boxes):
            if not alive[i]:
                continue
            cur = pymupdf.Rect(a)
            alive[i] = False
            j = i + 1
            while j < len(boxes):
                b = boxes[j]
                if b.x0 > cur.x1 + pad:
                    break
                if alive[j] and (cur.y0 - pad) < b.y1 and (cur.y1 + pad) > b.y0 \
                        and (cur.x0 - pad) < b.x1 and (cur.x1 + pad) > b.x0:
                    cur |= b
                    alive[j] = False
                    changed = True
                    j = i + 1          # the box grew: rescan
                    continue
                j += 1
            out.append(cur)
        boxes = out
        if not changed:
            break
    if page_rect is not None:
        boxes = [b & page_rect for b in boxes]
    return boxes


# ------------------------------------------------------------ fraction fusing
def _nearest_band(cands, key):
    """Keep only the candidates sitting on the row closest to the rule."""
    if not cands:
        return []
    best = min(cands, key=lambda c: c[0])
    return [c[1] for c in cands if abs(c[0] - best[0]) <= 3.0]


def fuse_fractions(spans, bars, body):
    """Replace numerator/denominator span pairs sitting around a rule with
    a single \\frac{..}{..} math span."""
    made = []
    for bar in sorted(bars, key=lambda b: (b.y0, b.x0)):
        above, below = [], []
        for s in spans:
            if s["used"]:
                continue
            r = s["bbox"]
            scx = (r.x0 + r.x1) / 2
            if not (bar.x0 - 4 <= scx <= bar.x1 + 4):
                continue
            if r.x0 > bar.x1 + 6 or r.x1 < bar.x0 - 6:
                continue
            h = max(r.height, 6)
            if r.y1 <= bar.y0 + 2.5 and bar.y0 - r.y1 < 1.5 * h:
                above.append((abs(bar.y0 - r.y1), s))
            elif r.y0 >= bar.y1 - 2.5 and r.y0 - bar.y1 < 1.5 * h:
                below.append((abs(r.y0 - bar.y1), s))
        num = _nearest_band(above, None)
        den = _nearest_band(below, None)
        ntxt = clean_ws("".join(s["text"] for s in sorted(num, key=lambda s: s["bbox"].x0)))
        dtxt = clean_ws("".join(s["text"] for s in sorted(den, key=lambda s: s["bbox"].x0)))
        if not ntxt or not dtxt or len(ntxt) > 12 or len(dtxt) > 12:
            continue
        nbox = num[0]["bbox"]
        for s in num[1:]:
            nbox |= s["bbox"]
        dbox = den[0]["bbox"]
        for s in den[1:]:
            dbox |= s["bbox"]
        widest = max(nbox.width, dbox.width)
        if bar.width > widest + 9:            # a cell border, not a fraction rule
            continue
        bcx = (bar.x0 + bar.x1) / 2
        if abs((nbox.x0 + nbox.x1) / 2 - bcx) > 5 or abs((dbox.x0 + dbox.x1) / 2 - bcx) > 5:
            continue
        if dbox.y0 - nbox.y1 > 1.4 * body:
            continue
        for s in num + den:
            s["used"] = True
        box = pymupdf.Rect(bar)
        for s in num + den:
            box |= s["bbox"]
        made.append({
            "text": r"\frac{%s}{%s}" % (ntxt, dtxt), "bbox": box, "size": body,
            "font": "math", "flags": 0, "bold": False, "italic": False,
            "sup": False, "origin": (box.x0, box.y1), "line": None,
            "used": False, "math": True,
        })
    live = [s for s in spans if not s["used"]]
    return live + made


# ------------------------------------------------------------------ line pass
def build_lines(spans, body):
    """Group spans into visual lines, applying sup/sub and math markers."""
    spans = sorted(spans, key=lambda s: (round(s["bbox"].y1, 1), s["bbox"].x0))
    lines, cur = [], []
    for s in spans:
        if not cur:
            cur = [s]
            continue
        prev = cur[-1]
        tol = max(3.0, 0.45 * min(prev["bbox"].height, s["bbox"].height))
        same = abs(s["bbox"].y1 - prev["bbox"].y1) <= tol or (
            s["bbox"].y0 < prev["bbox"].y1 - 0.45 * prev["bbox"].height
            and s["bbox"].y1 > prev["bbox"].y0 + 0.45 * prev["bbox"].height
            and abs(s["size"] - prev["size"]) < 0.1)
        if same:
            cur.append(s)
        else:
            lines.append(cur)
            cur = [s]
    if cur:
        lines.append(cur)
    out = []
    for grp in lines:
        grp.sort(key=lambda s: s["bbox"].x0)
        box = grp[0]["bbox"]
        for s in grp[1:]:
            box |= s["bbox"]
        sizes = Counter()
        for s in grp:
            sizes[s["size"]] += max(len(s["text"].strip()), 1)
        out.append({
            "spans": grp, "bbox": box,
            "size": sizes.most_common(1)[0][0],
            "bold": all(s["bold"] for s in grp if s["text"].strip()),
            "italic": all(s["italic"] for s in grp if s["text"].strip()),
            "text": clean_ws("".join(s["text"] for s in grp)),
        })
    return [l for l in out if l["text"]]


# ------------------------------------------------------------------ math pass
OPS = set('=+-<>/') | {'×', '÷', '≤', '≥', '≠', '±', '·', '≈', '≡', '⇒', '→'}
LATEX_OPS = {r'\times', r'\div', r'\le', r'\ge', r'\ne', r'\pm', r'\cdot',
             r'\approx', r'\equiv', r'\Rightarrow', r'\to'}
NUM_RE = re.compile(r'^[+-]?\d[\d,]*(\.\d+)?$')
VAR_RE = re.compile(r'^[a-zA-Z](\^\{[^}]*\})?$')
GEO_RE = re.compile(r'^(\\(angle|triangle))?\s*[A-Z]{1,4}$')
MATH_TOKEN_RE = re.compile(r'^[\dA-Za-z().,;:\[\]{}\\^_+\-=×÷<>≤≥≠±·√∠∆△°/*%\'"]+$')


def _is_math_token(t):
    if not t:
        return False
    if t.startswith('\\'):
        return True
    if '\\frac' in t or '^{' in t or '_{' in t:
        return True
    if t in OPS:
        return True
    if NUM_RE.match(t) or VAR_RE.match(t):
        return True
    if GEO_RE.match(t):
        return True
    if MATH_TOKEN_RE.match(t) and re.search(r'[\d×÷=+<>≤≥≠]', t) and not re.search(r'[a-z]{3}', t):
        return True
    return False


MATH_TRIGGER = {r'\angle', r'\triangle', r'\perp', r'\parallel', r'\sqrt',
                r'\pi', r'\cong', r'\in', r'\cup', r'\cap', r'\therefore',
                r'\because', r'\subset', r'\subseteq', r'\notin', r'\emptyset'}


def _has_operator(t):
    if t in OPS or t in LATEX_OPS or t in MATH_TRIGGER:
        return True
    return bool(re.search(r'[×÷=≤≥≠±]', t)) or ('\\frac' in t) or ('^{' in t) \
        or any(k in t for k in MATH_TRIGGER)


def mathify(text):
    """Wrap runs of mathematical tokens in KaTeX \\( \\) delimiters."""
    for u, l in UNI_MATH.items():
        if u in text:
            text = text.replace(u, ' %s ' % l)
    for u, d in SUP_DIGITS.items():
        text = text.replace(u, '^{%s}' % d)
    text = re.sub(r'\s+', ' ', text).strip()
    if not text:
        return text
    toks = text.split(' ')
    out, i = [], 0
    n = len(toks)
    while i < n:
        if not _is_math_token(toks[i].rstrip('.,;:?')):
            out.append(toks[i])
            i += 1
            continue
        j = i
        run, tail = [], ''
        while j < n:
            tok = toks[j]
            core = tok.rstrip('.,;:?')
            if not _is_math_token(core):
                break
            j += 1
            if core != tok:                    # punctuation ends the expression
                if core:
                    run.append(core)
                tail = tok[len(core):]
                break
            run.append(tok)
        run = [r for r in run if r]
        if j == i:                               # never stall on a token we cannot consume
            out.append(toks[i])
            i += 1
            continue
        if run and any(_has_operator(r) for r in run) and (len(run) > 1 or '\\' in run[0] or '^{' in run[0]):
            out.append(r'\(' + ' '.join(run) + r'\)' + tail)
        else:
            out.append(' '.join(run) + tail)
        i = j
    return ' '.join(x for x in out if x != '')


def esc(s):
    return (s.replace('&', '&amp;').replace('<', '&lt;').replace('>', '&gt;'))


def line_text(line, body):
    """Line -> string with sup/sub already expressed in latex."""
    spans = line["spans"]
    sizes = Counter()
    for s in spans:
        if not s.get("math"):
            sizes[s["size"]] += max(len(s["text"].strip()), 1)
    line_size = sizes.most_common(1)[0][0] if sizes else body
    bases = [s["origin"][1] for s in spans
             if not s.get("math") and abs(s["size"] - line_size) < 0.3]
    baseline = max(bases) if bases else (spans[0]["origin"][1] if spans else 0)

    parts, prev = [], None
    for s in spans:
        t = s["text"]
        if s.get("math"):
            parts.append(' ' + t + ' ')
            prev = s
            continue
        core = t.strip()
        raised = lowered = False
        if s["size"] < 0.88 * line_size and core and len(core) <= 4:
            dy = baseline - s["origin"][1]
            if dy > 0.16 * line_size:
                raised = True
            elif dy < -0.12 * line_size:
                lowered = True
        if parts and prev is not None:      # keep words apart when the PDF kerns them together
            gap = s["bbox"].x0 - prev["bbox"].x1
            if gap > 0.16 * max(s["size"], 6) and not parts[-1].endswith(' ') and not t.startswith(' '):
                parts.append(' ')
        if (raised or lowered) and re.fullmatch(r'[\dA-Za-z+\-()]{1,4}', core):
            parts.append('^{%s}' % core if raised else '_{%s}' % core)
        else:
            parts.append(t)
        prev = s
    return clean_ws(''.join(parts))


# ------------------------------------------------------------- figure export
def save_crop(page, rect, path, dpi=170):
    from PIL import Image
    import io
    rect = pymupdf.Rect(rect) & page.rect
    pix = page.get_pixmap(clip=rect, dpi=dpi, colorspace=pymupdf.csRGB, alpha=False)
    img = Image.open(io.BytesIO(pix.tobytes("png"))).convert("RGB")
    if max(img.size) > 1400:
        sc = 1400 / max(img.size)
        img = img.resize((max(1, int(img.width * sc)), max(1, int(img.height * sc))), Image.LANCZOS)
    colors = img.getcolors(maxcolors=4096)
    if colors and len(colors) <= 512:          # line art -> lossless, tiny
        img.convert("P", palette=Image.ADAPTIVE, colors=256).save(
            path, "WEBP", lossless=True, quality=90, method=6)
    else:
        img.save(path, "WEBP", quality=84, method=6)
    return img.size


def trim_white(page, rect, dpi=72):
    """Shrink a figure rect to its inked area so crops are not mostly margin."""
    from PIL import Image
    r = pymupdf.Rect(rect) & page.rect
    if r.is_empty or r.width < 4 or r.height < 4:
        return r
    try:
        pix = page.get_pixmap(clip=r, dpi=dpi, colorspace=pymupdf.csGRAY, alpha=False)
        img = Image.frombytes("L", (pix.width, pix.height), pix.samples)
    except Exception:
        return r
    if img.width == 0 or img.height == 0:
        return r
    ink = img.point(lambda v: 255 if v < 246 else 0).getbbox()
    if not ink:
        return r
    sx, sy = r.width / img.width, r.height / img.height
    out = pymupdf.Rect(r.x0 + ink[0] * sx - 2, r.y0 + ink[1] * sy - 2,
                       r.x0 + ink[2] * sx + 2, r.y0 + ink[3] * sy + 2)
    return out & page.rect


# ------------------------------------------------------------- page -> items
def page_items(page, pno, body, imgdir, imgprefix, drop_margins=True):
    W, H = page.rect.width, page.rect.height
    PA = W * H
    spans = collect_spans(page)

    kept = []
    for s in spans:
        t = s["text"].strip()
        r = s["bbox"]
        if JUNK_RE.search(t):
            continue
        if drop_margins and ((r.y1 < 0.088 * H) or (r.y0 > 0.905 * H)):
            if s["size"] <= body + 0.6 or RUNNING_HEAD_RE.match(t) or len(t) < 4:
                continue
        kept.append(s)
    spans = kept

    rects, panels, bars = graphic_rects(page, spans, body)
    spans = fuse_fractions(spans, bars, body)

    boxes = cluster(rects, pad=16.0, page_rect=page.rect)
    boxes = [b for b in boxes if b.width >= 12 and b.height >= 10]
    # a coloured panel (NOTE / activity box) is its own figure and never absorbs a neighbour
    def is_panel(b):
        ba = b.get_area()
        if ba < 0.012 * PA:
            return False
        return any((b & pm).get_area() > 0.55 * ba for pm in panels)

    panel_flag = [is_panel(b) for b in boxes]
    # parts of one illustration usually sit side by side in a band -> one figure
    changed = True
    while changed:
        changed = False
        for i in range(len(boxes)):
            if boxes[i] is None or panel_flag[i]:
                continue
            for j in range(i + 1, len(boxes)):
                if boxes[j] is None or panel_flag[j]:
                    continue
                a, b = boxes[i], boxes[j]
                ovy = min(a.y1, b.y1) - max(a.y0, b.y0)
                ovx = min(a.x1, b.x1) - max(a.x0, b.x0)
                gapx = max(a.x0 - b.x1, b.x0 - a.x1, 0)
                gapy = max(a.y0 - b.y1, b.y0 - a.y1, 0)
                side_by_side = ovy > 0.4 * min(a.height, b.height) and gapx <= 45
                stacked = ovx > 0.55 * min(a.width, b.width) and gapy <= 16
                if not (side_by_side or stacked):
                    continue
                if stacked and not side_by_side:
                    lo, hi = min(a.y1, b.y1), max(a.y0, b.y0)
                    x0, x1 = max(a.x0, b.x0), min(a.x1, b.x1)
                    if any(len(sp["text"].strip()) >= 3
                           and sp["bbox"].y0 >= lo - 1 and sp["bbox"].y1 <= hi + 1
                           and sp["bbox"].x1 > x0 and sp["bbox"].x0 < x1
                           for sp in spans):
                        continue          # prose runs between them: two figures
                boxes[i] = a | b
                boxes[j] = None
                changed = True
        boxes = [b for b in boxes if b is not None]
        if changed:
            panel_flag = [is_panel(b) for b in boxes]

    figs = []
    for box in boxes:
        if box.width < 26 or box.height < 22:
            continue
        if box.width * box.height < 0.0022 * PA:
            continue
        inside = [s for s in spans
                  if box.contains(pymupdf.Point((s["bbox"].x0 + s["bbox"].x1) / 2,
                                                (s["bbox"].y0 + s["bbox"].y1) / 2))]
        chars = sum(len(s["text"].strip()) for s in inside)
        members = [r for r in rects if box.intersects(r)]
        gridish = sum(1 for r in members
                      if (r.height <= 2.8 or r.width <= 2.8) and max(r.width, r.height) >= 24)
        table_like = gridish >= 5
        if chars > (3000 if table_like else 170):
            continue
        if box.width * box.height > 0.62 * PA and chars > 90 and not table_like:
            continue
        for sp in inside:                  # never clip text the crop swallows
            box |= sp["bbox"]
        box = box & page.rect
        figs.append({"box": box, "spans": inside, "table": table_like})

    line_chars = {}
    for s_ in spans:
        line_chars[s_["line"]] = line_chars.get(s_["line"], 0) + len(s_["text"].strip())

    # pull stray diagram labels (A, B, (i) ...) into the nearest figure box.
    # a label already owned by another figure must never drag one box over another.
    claimed = {id(s) for f in figs for s in f["spans"]}
    for _ in range(4):
        grew = False
        for f in figs:
            for s in spans:
                if s["used"] or id(s) in claimed:
                    continue
                if not is_label_text(s["text"]):
                    continue
                if line_chars.get(s["line"], 0) > 10:
                    continue
                if rect_gap(f["box"], s["bbox"]) > 22:
                    continue
                grown = f["box"] | s["bbox"]
                if any(o is not f and grown.intersects(o["box"]) for o in figs):
                    continue
                f["box"] = grown
                f["spans"].append(s)
                claimed.add(id(s))
                grew = True
        if not grew:
            break

    # figures that now overlap describe one picture -> merge them
    merged = []
    for f in sorted(figs, key=lambda f: -(f["box"].width * f["box"].height)):
        hit = None
        for m in merged:
            inter = pymupdf.Rect(m["box"]) & f["box"]
            if not inter.is_empty and inter.get_area() > 0.45 * min(
                    m["box"].get_area(), f["box"].get_area()):
                hit = m
                break
        if hit:
            hit["box"] |= f["box"]
            hit["spans"].extend(f["spans"])
            hit["table"] = hit["table"] or f["table"]
        else:
            merged.append(f)
    figs = sorted(merged, key=lambda f: (f["box"].y0, f["box"].x0))

    for f in figs:
        for s in f["spans"]:
            s["used"] = True
    spans = [s for s in spans if not s["used"]]

    # a crop must not slice through prose that stayed in the flow: trim the box
    # back along whichever edge needs the smallest cut
    for f in figs:
        box = f["box"]
        for s_ in sorted(spans, key=lambda s: -len(s["text"])):
            r = s_["bbox"]
            if len(s_["text"].strip()) < 3 or not box.intersects(r):
                continue
            opts = []
            if r.y1 - box.y0 > 0:
                opts.append(("y0", r.y1 - box.y0, r.y1 + 1.5))
            if box.y1 - r.y0 > 0:
                opts.append(("y1", box.y1 - r.y0, r.y0 - 1.5))
            if r.x1 - box.x0 > 0:
                opts.append(("x0", r.x1 - box.x0, r.x1 + 1.5))
            if box.x1 - r.x0 > 0:
                opts.append(("x1", box.x1 - r.x0, r.x0 - 1.5))
            if not opts:
                continue
            axis, cost, value = min(opts, key=lambda o: o[1])
            span_limit = 0.55 * (box.height if axis[0] == "y" else box.width)
            if cost > span_limit:
                continue
            setattr(box, axis, value)
        f["box"] = box

    items = []
    for i, f in enumerate(figs):
        limit = pymupdf.Rect(f["box"])
        box = trim_white(page, limit + (-3, -3, 3, 3))
        box = pymupdf.Rect(max(box.x0, limit.x0 - 3), max(box.y0, limit.y0),
                           min(box.x1, limit.x1 + 3), min(box.y1, limit.y1))
        if box.width < 20 or box.height < 16:
            continue
        name = "%s-p%d-%d.webp" % (imgprefix, pno + 1, i + 1)
        try:
            w, h = save_crop(page, box, os.path.join(imgdir, name))
        except Exception:
            continue
        items.append({"kind": "figure", "src": "img/" + name, "w": w, "h": h,
                      "table": f["table"], "bbox": box, "caption": "",
                      "page": pno, "wide": box.width > 0.55 * W,
                      "side": box.x0 > 0.55 * W and box.width < 0.45 * W})

    lines = build_lines(spans, body)
    for l in lines:
        l["raw"] = line_text(l, body)
        l["mathy"] = line_is_mathy(l)
    lines = [l for l in lines if l["raw"]]

    xs = [l["bbox"].x0 for l in lines if abs(l["size"] - body) < 1.2]
    left = min(xs) if xs else 0.08 * W
    x1s = [l["bbox"].x1 for l in lines if abs(l["size"] - body) < 1.2]
    right = max(x1s) if x1s else 0.92 * W

    items.extend(group_paragraphs(lines, body, left, right, W))
    items.sort(key=lambda it: (round(it["bbox"].y0 / 7.0), it["bbox"].x0))
    attach_captions(items)
    return items


WORD_RE = re.compile(r'[A-Za-z]{3,}')


def line_is_mathy(l):
    t = l.get("raw") or l["text"]
    if len(t) > 90:
        return False
    words = len(WORD_RE.findall(t))
    if words > 2:
        return False
    if any(s.get("math") for s in l["spans"]):
        return True
    ops = len(re.findall(r'[=+×÷<>≤≥≠]', t))
    return ops >= 1 and words <= 1 and bool(re.search(r'\d', t))


def group_paragraphs(lines, body, left, right, W):
    if not lines:
        return []
    heights = sorted(l["bbox"].height for l in lines)
    lh = heights[len(heights) // 2] or 12
    groups, cur = [], [lines[0]]
    for prev, l in zip(lines, lines[1:]):
        gap = l["bbox"].y0 - prev["bbox"].y1
        newpara = False
        if gap > 0.62 * lh:
            newpara = True
        if abs(l["size"] - prev["size"]) > 0.6 or l["bold"] != prev["bold"]:
            newpara = True
        if l["mathy"] != prev["mathy"]:
            newpara = True
        if LIST_RE.match(l["raw"]) or LIST_RE.match(prev["raw"]):
            newpara = True
        if abs(l["bbox"].x0 - prev["bbox"].x0) > 26 and gap > 0.1 * lh:
            newpara = True
        if (prev["bbox"].x1 < right - 0.28 * (right - left)
                and l["bbox"].x0 <= prev["bbox"].x0 + 4 and gap > 0.35 * lh):
            newpara = True
        if l["bbox"].y0 > prev["bbox"].y1 + 2.2 * lh:
            newpara = True
        if newpara:
            groups.append(cur)
            cur = [l]
        else:
            cur.append(l)
    groups.append(cur)

    out = []
    for g in groups:
        box = g[0]["bbox"]
        for l in g[1:]:
            box |= l["bbox"]
        text = clean_ws(" ".join(l["raw"] for l in g))
        if not text:
            continue
        size = max(l["size"] for l in g)
        bold = all(l["bold"] for l in g)
        italic = all(l["italic"] for l in g)
        side = box.x0 > left + 0.46 * (right - left) and box.width < 0.42 * W
        mathy = all(l["mathy"] for l in g)
        out.append(classify(text, size, bold, italic, box, body, side, mathy))
    return out


NUMBERED_RE = re.compile(r'^(\d{1,2})\.(\d{1,2})(\.(\d{1,2}))?\s*[.:)]?\s+\S')


def classify(text, size, bold, italic, box, body, side, mathy=False):
    base = {"bbox": box, "size": size, "bold": bold, "italic": italic, "side": side}
    m = NUMBERED_RE.match(text)
    if m and (bold or size > body + 0.4) and len(text) < 110 and not mathy:
        lvl = 3 if m.group(4) else 2
        return dict(base, kind="heading", level=lvl, text=text)
    if bold and size >= body + 1.4 and len(text) < 120 and not mathy:
        return dict(base, kind="heading", level=2, text=text)
    if bold and size >= body + 0.4 and len(text) < 120 and not mathy:
        return dict(base, kind="heading", level=3, text=text)
    if bold and len(text) < 90 and CALLOUT_HEAD_RE.match(text):
        return dict(base, kind="heading", level=4, text=text)
    if FIG_CAPTION_RE.match(text) and len(text) < 90:
        return dict(base, kind="caption", text=text)
    if LIST_RE.match(text):
        mk = LIST_RE.match(text)
        return dict(base, kind="li", marker=clean_ws(mk.group(1)),
                    text=text[mk.end():].strip(), full=text)
    if CALLOUT_HEAD_RE.match(text) and len(text) < 60 and size >= body:
        return dict(base, kind="heading", level=4, text=text)
    if mathy:
        return dict(base, kind="mathline", text=text)
    return dict(base, kind="para", text=text)


def attach_captions(items):
    for i, it in enumerate(items):
        if it["kind"] != "caption":
            continue
        best, bd = None, 1e9
        for j in range(max(0, i - 4), min(len(items), i + 4)):
            f = items[j]
            if f["kind"] != "figure":
                continue
            d = abs(f["bbox"].y1 - it["bbox"].y0)
            if f["bbox"].y1 <= it["bbox"].y0 + 6:
                d *= 0.5
            if d < bd:
                best, bd = f, d
        if best is not None and bd < 90 and not best["caption"]:
            best["caption"] = it["text"]
            it["kind"] = "dropped"
    items[:] = [i for i in items if i["kind"] != "dropped"]


# ---------------------------------------------------------- section assembly
def norm(s):
    return re.sub(r'[^a-z0-9]', '', (s or '').lower())


def title_matches(text, title):
    n, t = norm(text), norm(title)
    if not t:
        return False
    if n.startswith(t[:max(8, min(len(t), 26))]):
        return True
    m = re.match(r'^\s*(\d{1,2}\.\d{1,2}(\.\d{1,2})?)', title)
    if m:
        want = m.group(1)
        return bool(re.match(r'^\s*' + re.escape(want) + r'(?![\d.])', text))
    return False


def extract_section(pdf_path, imgdir, imgprefix, title, next_title, first_in_chapter):
    doc = pymupdf.open(pdf_path)
    body = body_size_of(doc)
    os.makedirs(imgdir, exist_ok=True)
    pages = []
    for pno, page in enumerate(doc):
        try:
            pages.append(page_items(page, pno, body, imgdir, imgprefix))
        except Exception as e:
            pages.append([{"kind": "para", "text": "", "bbox": pymupdf.Rect(0, 0, 1, 1),
                           "size": body, "bold": False, "italic": False, "side": False}])
    # --- trim content that belongs to the neighbouring sections
    if pages and not first_in_chapter and title:
        idx = None
        for i, it in enumerate(pages[0]):
            if it["kind"] == "heading" and title_matches(it.get("text", ""), title):
                idx = i
                break
        if idx is None:
            for i, it in enumerate(pages[0]):
                if it.get("text") and title_matches(it["text"], title):
                    idx = i
                    break
        if idx:
            pages[0] = pages[0][idx:]
    if pages and next_title:
        last = pages[-1]
        for i, it in enumerate(last):
            if i == 0 and len(pages) == 1:
                continue
            if it.get("text") and title_matches(it["text"], next_title):
                pages[-1] = last[:i]
                break
    items = [it for pg in pages for it in pg]
    doc.close()
    return items, len(pages)


# ------------------------------------------------------------- items -> html
def items_to_html(items, section_title):
    out, i, n = [], 0, len(items)
    first_heading_done = False
    while i < n:
        it = items[i]
        k = it["kind"]
        if k == "li":
            group, marker_kind = [], None
            while i < n and items[i]["kind"] == "li":
                group.append(items[i])
                i += 1
            out.append('<ul class="qlist">')
            for g in group:
                mk = esc(g["marker"])
                out.append('<li><span class="mk">%s</span><span class="lt">%s</span></li>'
                           % (mk, esc(mathify(g["text"]))))
            out.append('</ul>')
            continue
        if k == "figure":
            cls = "fig table-fig" if it.get("table") else "fig"
            if it.get("side"):
                cls += " side-fig"
            elif it.get("wide"):
                cls += " wide"
            cap = ('<figcaption>%s</figcaption>' % esc(it["caption"])) if it.get("caption") else ''
            out.append('<figure class="%s"><img src="%s" alt="%s" loading="lazy" width="%d" height="%d">%s</figure>'
                       % (cls, it["src"], esc(it["caption"] or "Figure from the textbook page"),
                          it["w"], it["h"], cap))
            i += 1
            continue
        if k == "heading":
            txt = it["text"]
            lvl = it["level"]
            if not first_heading_done and title_matches(txt, section_title):
                first_heading_done = True
                i += 1
                continue                      # the page header repeats the section title
            tag = {2: "h2", 3: "h3", 4: "h4"}[lvl]
            cls = ' class="callout-h"' if (lvl == 4 or CALLOUT_HEAD_RE.match(txt)) else ''
            out.append('<%s%s id="%s">%s</%s>' % (tag, cls, slug_anchor(txt), esc(mathify(txt)), tag))
            i += 1
            continue
        if k == "mathline":
            group = []
            while i < n and items[i]["kind"] == "mathline":
                group.append(items[i]["text"])
                i += 1
            out.append('<div class="mathblock">%s</div>'
                       % ''.join('<p>%s</p>' % esc(mathify(t)) for t in group))
            continue
        if k == "caption":
            out.append('<p class="caption">%s</p>' % esc(it["text"]))
            i += 1
            continue
        txt = it.get("text", "")
        if len(txt.strip()) <= 1 or is_all_labels(txt):
            i += 1
            continue
        if it.get("side"):
            group = []
            while i < n and items[i]["kind"] in ("para", "li") and items[i].get("side"):
                group.append(items[i].get("text", ""))
                i += 1
            out.append('<aside class="sidenote">%s</aside>'
                       % ''.join('<p>%s</p>' % esc(mathify(t)) for t in group if t.strip()))
            continue
        cls = ' class="lead"' if it.get("italic") else ''
        out.append('<p%s>%s</p>' % (cls, esc(mathify(txt))))
        i += 1
    return "\n".join(out)


def is_all_labels(txt):
    t = clean_ws(txt)
    if not t or len(t) > 26:
        return False
    toks = t.split(' ')
    return all(is_label_text(x) for x in toks)


def slug_anchor(s):
    s = re.sub(r'[^A-Za-z0-9]+', '-', s.lower()).strip('-')
    return ('s-' + s)[:60]
