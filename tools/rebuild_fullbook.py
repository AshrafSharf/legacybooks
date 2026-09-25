"""Rebuild a whole-book appendix page from the book's corrected section pages.

    python3 tools/rebuild_fullbook.py tn-cbse/tn-9 9th_state_Maths
    python3 tools/rebuild_fullbook.py tn-cbse/tn-8 Class_8_Maths

The TN 8 and TN 9 appendices hold a page that is the whole textbook in one
article.  Rather than maintaining a second copy of every section, its article
is regenerated from the section pages in book order (front matter, chapters,
answers): each chapter becomes an <h2>, each section an <h3> followed by that
section's article content, with figure paths pointing back at the section's
own img/ folder and element ids prefixed so they stay unique.
"""
import re
import sys
from pathlib import Path

ARTICLE = re.compile(r'(<article class="prose">)([\s\S]*?)(</article>)')


def section_title(page):
    m = re.search(r'<h1>([\s\S]*?)</h1>', page)
    return m.group(1).strip() if m else ''


def section_body(sec_dir, rel_from_full):
    page = (sec_dir / 'index.html').read_text(encoding='utf-8')
    body = ARTICLE.search(page).group(2).strip()
    slug = sec_dir.name
    body = re.sub(r'src="img/', f'src="{rel_from_full}/img/', body)
    body = re.sub(r'\bid="([^"]+)"', lambda m: f'id="{slug}-{m.group(1)}"', body)
    body = re.sub(r'href="#([^"]+)"', lambda m: f'href="#{slug}-{m.group(1)}"', body)
    return section_title(page), body


def main(book, name):
    book = Path(book)
    full = book / '90-appendix' / name / 'index.html'
    parts = []

    def add_chapter(ch_dir, heading, skip=()):
        parts.append(f'<h2 id="{ch_dir.name}">{heading}</h2>')
        for sec in sorted(d for d in ch_dir.iterdir() if d.is_dir() and (d / 'index.html').exists()):
            if sec.name in skip:
                continue
            title, body = section_body(sec, f'../../{ch_dir.name}/{sec.name}')
            parts.append(f'<h3 id="{sec.name}">{title}</h3>\n{body}')

    appendix = book / '90-appendix'
    front = appendix / '00-front-matter'
    if front.exists():
        title, body = section_body(front, '../00-front-matter')
        parts.append(f'<h2 id="front-matter">{title}</h2>\n{body}')
    for ch in sorted(d for d in book.iterdir() if d.is_dir() and re.match(r'\d\d-', d.name) and d.name != '90-appendix'):
        idx = (ch / 'index.html').read_text(encoding='utf-8')
        m = re.search(r'<h1>([\s\S]*?)</h1>', idx)
        add_chapter(ch, m.group(1).strip() if m else ch.name)
    answers = appendix / 'answers'
    if answers.exists():
        title, body = section_body(answers, '../answers')
        parts.append(f'<h2 id="answers">{title}</h2>\n{body}')

    page = full.read_text(encoding='utf-8')
    article = '\n'.join(parts)
    n_fig = len(re.findall(r'<figure\b', article))
    page = ARTICLE.sub(lambda m: m.group(1) + '\n' + article + '\n' + m.group(3), page, count=1)
    page = re.sub(r'<p class="sec-meta">[^<]*</p>', f'<p class="sec-meta">{n_fig} figures</p>', page, count=1)
    full.write_text(page, encoding='utf-8')
    print(f'{full}: {len(parts)} blocks, {n_fig} figures')


if __name__ == '__main__':
    main(*sys.argv[1:3])
