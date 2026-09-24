"""Locate and crop figures from a section PDF.

    python3 tools/pdf_figure.py list  SECTION.pdf
        prints every page's size plus the bounding boxes of embedded images and
        clusters of vector drawings, in PDF points (origin top-left).

    python3 tools/pdf_figure.py crop  SECTION.pdf PAGE X0 Y0 X1 Y1 OUT.webp [--scale 3]
        renders that region of page PAGE (1-based) to OUT (.webp or .png).
        Use it for photographs / portraits that cannot sensibly be redrawn as SVG.
"""
import sys, io
import fitz


def cluster(rects, gap=12):
    out = []
    for r in sorted(rects, key=lambda r: (r.y0, r.x0)):
        for i, c in enumerate(out):
            if (r.x0 <= c.x1 + gap and r.x1 >= c.x0 - gap and
                    r.y0 <= c.y1 + gap and r.y1 >= c.y0 - gap):
                out[i] = c | r
                break
        else:
            out.append(fitz.Rect(r))
    return out


def cmd_list(pdf):
    doc = fitz.open(pdf)
    for pno, page in enumerate(doc, 1):
        print(f"page {pno}: {page.rect.width:.0f} x {page.rect.height:.0f}")
        for info in page.get_image_info():
            b = fitz.Rect(info["bbox"])
            print(f"   image    {b.x0:6.1f} {b.y0:6.1f} {b.x1:6.1f} {b.y1:6.1f}  ({b.width:.0f}x{b.height:.0f})")
        rects = [d["rect"] for d in page.get_drawings() if d["rect"].width < page.rect.width * 0.95]
        for c in cluster(rects):
            if c.width > 25 and c.height > 25:
                print(f"   drawing  {c.x0:6.1f} {c.y0:6.1f} {c.x1:6.1f} {c.y1:6.1f}  ({c.width:.0f}x{c.height:.0f})")


def cmd_crop(pdf, pno, x0, y0, x1, y1, out, scale=3.0):
    doc = fitz.open(pdf)
    page = doc[int(pno) - 1]
    clip = fitz.Rect(float(x0), float(y0), float(x1), float(y1))
    pix = page.get_pixmap(matrix=fitz.Matrix(scale, scale), clip=clip, alpha=False)
    if out.lower().endswith(".webp"):
        from PIL import Image
        img = Image.open(io.BytesIO(pix.tobytes("png")))
        img.save(out, "WEBP", quality=84, method=6)
    else:
        pix.save(out)
    print(f"wrote {out} ({pix.width}x{pix.height})")


if __name__ == "__main__":
    a = sys.argv[1:]
    if a and a[0] == "list":
        cmd_list(a[1])
    elif a and a[0] == "crop":
        scale = 3.0
        if "--scale" in a:
            i = a.index("--scale"); scale = float(a[i + 1]); a = a[:i] + a[i + 2:]
        cmd_crop(*a[1:8], scale=scale)
    else:
        print(__doc__)
