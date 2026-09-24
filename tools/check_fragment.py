"""Validate section fragments / pages: tag balance, math delimiters, KaTeX parse.

    python3 tools/check_fragment.py FILE.html [FILE.html ...]

KaTeX auto-render works per text node, so every \\( … \\) / \\[ … \\] must sit
inside a single text node (no tags inside maths). Each formula is parsed with
the real KaTeX: `npm i katex@0.16.9` somewhere and point KATEX_DIR at that folder.
"""
import html, json, os, re, subprocess, sys
from html.parser import HTMLParser

VOID = {"area", "base", "br", "col", "embed", "hr", "img", "input", "link", "meta",
        "source", "track", "wbr"}
SVG_VOID_OK = True
KATEX_DIR = os.environ.get("KATEX_DIR", ".")  # a folder containing node_modules/katex
DELIMS = [(r"\[", r"\]", True), (r"\(", r"\)", False), ("$$", "$$", True)]


class P(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.stack, self.errors, self.texts = [], [], []
        self.in_svg = 0

    def handle_starttag(self, tag, attrs):
        if tag == "svg":
            self.in_svg += 1
        if tag not in VOID:
            self.stack.append((tag, self.getpos()[0]))

    def handle_startendtag(self, tag, attrs):
        pass

    def handle_endtag(self, tag):
        if tag in VOID:
            return
        if not self.stack:
            self.errors.append(f"line {self.getpos()[0]}: stray </{tag}>")
            return
        if self.stack[-1][0] == tag:
            self.stack.pop()
        else:
            names = [t for t, _ in self.stack]
            if tag in names:
                while self.stack and self.stack[-1][0] != tag:
                    t, ln = self.stack.pop()
                    if t not in ("p", "li"):
                        self.errors.append(f"line {ln}: <{t}> not closed before </{tag}> (line {self.getpos()[0]})")
                self.stack.pop()
            else:
                self.errors.append(f"line {self.getpos()[0]}: </{tag}> without matching open tag")
        if tag == "svg":
            self.in_svg -= 1

    def handle_data(self, data):
        self.texts.append((self.getpos()[0], data, self.in_svg > 0))


def scan_math(line, text, errors):
    out, i = [], 0
    while i < len(text):
        hit = None
        for l, r, disp in DELIMS:
            if text.startswith(l, i):
                hit = (l, r, disp)
                break
        if hit:
            l, r, disp = hit
            j = text.find(r, i + len(l))
            if j < 0:
                errors.append(f"line {line}: unclosed {l} … (math must not contain tags): {text[i:i+60]!r}")
                return out
            out.append((line, text[i + len(l):j], disp))
            i = j + len(r)
            continue
        for l, r, _ in DELIMS[:2]:
            if text.startswith(r, i):
                errors.append(f"line {line}: stray {r} with no opening {l}: {text[max(0,i-40):i+10]!r}")
        if text.startswith("$", i) and not text.startswith("$$", i):
            pass
        i += 1
    return out


def check(path):
    src = open(path, encoding="utf-8").read()
    p = P()
    p.feed(src)
    p.close()
    errors = list(p.errors)
    for t, ln in p.stack:
        if t not in ("p", "li"):
            errors.append(f"line {ln}: <{t}> never closed")
    maths = []
    for line, data, in_svg in p.texts:
        found = scan_math(line, data, errors)
        if found and in_svg:
            errors.append(f"line {line}: KaTeX delimiters inside <svg> text will not render — use plain unicode there")
        maths += found
    if maths:
        js = """
const katex=require('katex');let out=[];const items=JSON.parse(require('fs').readFileSync(0,'utf8'));
for(const [line,tex,disp] of items){try{katex.renderToString(tex,{displayMode:disp,throwOnError:true,strict:false});}
catch(e){out.push(`line ${line}: KaTeX: ${e.message.split('\\n')[0]} in: ${tex.slice(0,90)}`);}}
console.log(JSON.stringify(out));"""
        r = subprocess.run(["node", "-e", js], input=json.dumps(maths), capture_output=True,
                           text=True, cwd=KATEX_DIR)
        if r.returncode != 0:
            errors.append("could not run KaTeX: " + r.stderr[-300:])
        else:
            errors += json.loads(r.stdout)
    if not re.search(r"<!--\s*title:", src) and "<!DOCTYPE" not in src:
        errors.append("missing <!-- title: … --> line")
    return errors, len(maths)


if __name__ == "__main__":
    bad = 0
    for f in sys.argv[1:]:
        errs, n = check(f)
        status = "OK" if not errs else f"{len(errs)} problem(s)"
        print(f"{f}: {n} formulas, {status}")
        for e in errs[:60]:
            print("   ", e)
        bad += bool(errs)
    sys.exit(1 if bad else 0)
