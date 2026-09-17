"""Sanity check the generated site: broken links, missing images, thin pages."""
import os, re, sys, html

ROOT = sys.argv[1] if len(sys.argv) > 1 else \
    "/Users/apple/lesson-ws/robogebra-books/gen-books/legacybooks/tn-cbse"

href_re = re.compile(r'(?:href|src)="([^"#:]+?)"')
body_re = re.compile(r'<article class="prose">(.*?)</article>', re.S)
tag_re = re.compile(r'<[^>]+>')

broken, thin, pages, imgs, figs = [], [], 0, 0, 0
for dirpath, dirnames, filenames in os.walk(ROOT):
    for f in filenames:
        if f.endswith(".webp"):
            imgs += 1
        if not f.endswith(".html"):
            continue
        pages += 1
        p = os.path.join(dirpath, f)
        s = open(p, encoding="utf-8").read()
        for h in href_re.findall(s):
            if h.startswith(("http", "data:", "//")):
                continue
            t = os.path.normpath(os.path.join(dirpath, h))
            if not os.path.exists(t):
                broken.append((os.path.relpath(p, ROOT), h))
        m = body_re.search(s)
        if m:
            figs += m.group(1).count("<figure")
            text = html.unescape(tag_re.sub(" ", m.group(1)))
            words = len(text.split())
            if words < 25 and "<figure" not in m.group(1):
                thin.append((os.path.relpath(p, ROOT), words))

print("pages %d · images %d · figures referenced %d" % (pages, imgs, figs))
print("broken links: %d" % len(broken))
for b in broken[:15]:
    print("   ", b)
print("thin sections (<25 words, no figure): %d" % len(thin))
for t in thin[:15]:
    print("   ", t)
