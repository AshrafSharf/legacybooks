#!/usr/bin/env python3
"""
Build a search index JSON from all HTML content pages.
Output: assets/search-index.json

Structure per entry:
  { id, title, book, bookPath, chapter, chapterPath, path, body, tags }

The index is consumed by MiniSearch on the client side.
"""
import os
import re
import json
import html
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent

# ── helpers ──

def strip_html(s):
    """Remove HTML tags and decode entities."""
    s = re.sub(r'<[^>]+>', ' ', s)
    s = html.unescape(s)
    s = re.sub(r'\s+', ' ', s).strip()
    return s

def strip_math(s):
    """Remove KaTeX delimiters and their contents for cleaner body text,
    but keep a simplified version for searchability."""
    # Replace display math with the inner text (strip \frac, etc.)
    s = re.sub(r'\$\$(.*?)\$\$', lambda m: simplify_math(m.group(1)), s, flags=re.DOTALL)
    s = re.sub(r'\\\[(.*?)\\\]', lambda m: simplify_math(m.group(1)), s, flags=re.DOTALL)
    s = re.sub(r'\\\((.*?)\\\)', lambda m: simplify_math(m.group(1)), s, flags=re.DOTALL)
    return s

def simplify_math(tex):
    """Extract readable words/symbols from TeX."""
    # Remove common TeX commands but keep text content
    t = re.sub(r'\\(?:text|mathrm|textbf|textit)\{([^}]*)\}', r'\1', tex)
    t = re.sub(r'\\(?:frac|dfrac|tfrac)\{([^}]*)\}\{([^}]*)\}', r'\1 over \2', t)
    t = re.sub(r'\\(?:sqrt)\{([^}]*)\}', r'square root of \1', t)
    t = re.sub(r'\\[a-zA-Z]+', ' ', t)  # strip remaining commands
    t = re.sub(r'[{}\\^_]', ' ', t)
    t = re.sub(r'\s+', ' ', t).strip()
    return t

def extract_title(content):
    m = re.search(r'<title>(.*?)</title>', content, re.DOTALL)
    if m:
        t = strip_html(m.group(1))
        # Remove trailing " | Book Name" or " — Book Name"
        t = re.split(r'\s*[|—–]\s*(?:Practical Algebra|Modern Algebra|Mathematics Library)', t)[0]
        return t.strip()
    return ""

def extract_body(content):
    """Extract main text content from the page."""
    # Pages built by assemble_sections.py mark their content explicitly
    marked = re.search(r'<!-- content:start -->(.*?)<!-- content:end -->', content, re.DOTALL)
    # Try to get just the main content area
    main = marked or re.search(r'<(?:main|article|div\s+class="container")[^>]*>(.*?)</(?:main|article|div)>', content, re.DOTALL | re.IGNORECASE)
    if main:
        text = main.group(1)
    else:
        # Fall back to body
        body = re.search(r'<body[^>]*>(.*?)</body>', content, re.DOTALL | re.IGNORECASE)
        text = body.group(1) if body else content

    # Remove script, style, nav, header, footer
    text = re.sub(r'<(?:script|style|nav|header|footer)[^>]*>.*?</(?:script|style|nav|header|footer)>', '', text, flags=re.DOTALL | re.IGNORECASE)
    # Remove the pager nav
    text = re.sub(r'<nav class="pager">.*?</nav>', '', text, flags=re.DOTALL)
    # Remove nav-footer
    text = re.sub(r'<div class="nav-footer">.*?</div>', '', text, flags=re.DOTALL)

    text = strip_math(text)
    text = strip_html(text)

    # Truncate to ~500 words to keep index small
    words = text.split()
    if len(words) > 500:
        text = ' '.join(words[:500])

    return text

def extract_headings(content):
    """Extract h2, h3 headings as additional searchable text."""
    headings = re.findall(r'<h[23][^>]*>(.*?)</h[23]>', content, re.DOTALL)
    return ' '.join(strip_html(h) for h in headings)

def extract_tags(title, headings, body):
    """Extract topic tags from content for pseudo-semantic matching."""
    combined = (title + ' ' + headings + ' ' + body).lower()
    tags = set()
    TOPIC_KEYWORDS = {
        'algebra': ['algebra', 'algebraic', 'expression', 'equation'],
        'geometry': ['geometry', 'geometric', 'triangle', 'circle', 'angle', 'polygon', 'quadrilateral', 'parallelogram', 'rectangle'],
        'trigonometry': ['trigonometry', 'trigonometric', 'sine', 'cosine', 'tangent', 'sin ', 'cos ', 'tan '],
        'fractions': ['fraction', 'fractions', 'numerator', 'denominator', 'rational'],
        'decimals': ['decimal', 'decimals'],
        'integers': ['integer', 'integers', 'negative number', 'positive number'],
        'exponents': ['exponent', 'exponents', 'power', 'powers', 'index notation'],
        'polynomials': ['polynomial', 'polynomials', 'monomial', 'binomial', 'trinomial'],
        'factoring': ['factor', 'factoring', 'factorization', 'factorisation', 'hcf', 'lcm', 'gcd'],
        'equations': ['equation', 'equations', 'solving', 'linear equation', 'quadratic equation'],
        'inequalities': ['inequality', 'inequalities'],
        'graphs': ['graph', 'graphs', 'coordinate', 'plotting', 'cartesian', 'axis'],
        'functions': ['function', 'functions', 'domain', 'range', 'mapping'],
        'ratio': ['ratio', 'proportion', 'variation', 'direct proportion', 'inverse proportion'],
        'statistics': ['statistics', 'mean', 'median', 'mode', 'probability', 'data handling', 'frequency'],
        'mensuration': ['mensuration', 'area', 'volume', 'perimeter', 'surface area'],
        'sets': ['set ', 'sets', 'union', 'intersection', 'venn diagram', 'subset'],
        'numbers': ['number system', 'real number', 'natural number', 'whole number', 'prime', 'composite'],
        'matrices': ['matrix', 'matrices', 'determinant'],
        'sequences': ['sequence', 'series', 'arithmetic progression', 'geometric progression', 'ap ', 'gp '],
        'roots': ['root', 'roots', 'radical', 'radicals', 'square root', 'cube root', 'surd'],
        'measurement': ['measurement', 'measurements', 'unit', 'units', 'conversion'],
        'symmetry': ['symmetry', 'reflection', 'rotation', 'transformation'],
    }
    for tag, keywords in TOPIC_KEYWORDS.items():
        for kw in keywords:
            if kw in combined:
                tags.add(tag)
                break
    return sorted(tags)


# ── book definitions ──

BOOKS = {
    'peter-selby': {
        'name': 'Practical Algebra',
        'indexPath': 'peter-selby/index.html',
    },
    'dociani': {
        'name': 'Modern Algebra: Structure and Method',
        'indexPath': 'dociani/dociani/index.html',
    },
    'tn-cbse': {
        'name': 'School Mathematics Library',
        'indexPath': 'tn-cbse/index.html',
    },
}


def process_peter_selby():
    """Process peter-selby chapters (flat structure)."""
    entries = []
    base = ROOT / 'peter-selby'
    chapters = sorted(base.glob('[0-9]*/index.html'))

    for ch_path in chapters:
        rel = ch_path.relative_to(ROOT)
        content = ch_path.read_text(encoding='utf-8')
        title = extract_title(content)
        headings = extract_headings(content)
        body = extract_body(content)
        tags = extract_tags(title, headings, body)

        entries.append({
            'id': str(rel),
            'title': title,
            'book': 'Practical Algebra',
            'bookPath': 'peter-selby/index.html',
            'chapter': title,
            'chapterPath': str(rel),
            'section': '',
            'path': str(rel),
            'headings': headings,
            'body': body,
            'tags': ' '.join(tags),
        })

    return entries


def process_dociani():
    """Process dociani chapters (flat structure inside dociani/dociani/)."""
    entries = []
    base = ROOT / 'dociani' / 'dociani'
    chapters = sorted(base.glob('[0-9]*/index.html'))

    for ch_path in chapters:
        rel = ch_path.relative_to(ROOT)
        content = ch_path.read_text(encoding='utf-8')
        title = extract_title(content)
        headings = extract_headings(content)
        body = extract_body(content)
        tags = extract_tags(title, headings, body)

        entries.append({
            'id': str(rel),
            'title': title,
            'book': 'Modern Algebra',
            'bookPath': 'dociani/dociani/index.html',
            'chapter': title,
            'chapterPath': str(rel),
            'section': '',
            'path': str(rel),
            'headings': headings,
            'body': body,
            'tags': ' '.join(tags),
        })

    return entries


def process_tn_cbse():
    """Process tn-cbse (hierarchical: sub-book → chapter → section)."""
    entries = []
    base = ROOT / 'tn-cbse'

    # Find sub-books (e.g., tn-7-term1, cbse-6, etc.)
    subbooks = sorted([d for d in base.iterdir() if d.is_dir() and d.name != 'assets'])

    for sb in subbooks:
        sb_index = sb / 'index.html'
        if not sb_index.exists():
            continue
        sb_content = sb_index.read_text(encoding='utf-8')
        sb_title = extract_title(sb_content) or sb.name

        # Find chapters
        chapters = sorted([d for d in sb.iterdir() if d.is_dir()])

        for ch in chapters:
            ch_index = ch / 'index.html'
            if not ch_index.exists():
                continue
            ch_content = ch_index.read_text(encoding='utf-8')
            ch_title = extract_title(ch_content) or ch.name

            # Find sections
            sections = sorted([d for d in ch.iterdir() if d.is_dir()])

            for sec in sections:
                sec_index = sec / 'index.html'
                if not sec_index.exists():
                    continue
                sec_content = sec_index.read_text(encoding='utf-8')
                sec_title = extract_title(sec_content) or sec.name
                headings = extract_headings(sec_content)
                body = extract_body(sec_content)
                tags = extract_tags(sec_title, headings, body)
                rel = sec_index.relative_to(ROOT)

                entries.append({
                    'id': str(rel),
                    'title': sec_title,
                    'book': sb_title,
                    'bookPath': str(sb_index.relative_to(ROOT)),
                    'chapter': ch_title,
                    'chapterPath': str(ch_index.relative_to(ROOT)),
                    'section': sec_title,
                    'path': str(rel),
                    'headings': headings,
                    'body': body,
                    'tags': ' '.join(tags),
                })

            # Also index the chapter index page itself
            ch_headings = extract_headings(ch_content)
            ch_body = extract_body(ch_content)
            ch_tags = extract_tags(ch_title, ch_headings, ch_body)
            ch_rel = ch_index.relative_to(ROOT)

            entries.append({
                'id': str(ch_rel),
                'title': ch_title,
                'book': sb_title,
                'bookPath': str(sb_index.relative_to(ROOT)),
                'chapter': ch_title,
                'chapterPath': str(ch_rel),
                'section': '',
                'path': str(ch_rel),
                'headings': ch_headings,
                'body': ch_body,
                'tags': ' '.join(ch_tags),
            })

    return entries


def main():
    all_entries = []
    all_entries.extend(process_peter_selby())
    all_entries.extend(process_dociani())
    all_entries.extend(process_tn_cbse())

    out_path = ROOT / 'assets' / 'search-index.json'
    out_path.parent.mkdir(exist_ok=True)
    with open(out_path, 'w', encoding='utf-8') as f:
        json.dump(all_entries, f, ensure_ascii=False, separators=(',', ':'))

    size_mb = out_path.stat().st_size / (1024 * 1024)
    print(f"Indexed {len(all_entries)} pages → {out_path} ({size_mb:.2f} MB)")


if __name__ == '__main__':
    main()
