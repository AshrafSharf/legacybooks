"""Delete figure crops that no page references (boundary-page duplicates)."""
import os, re, sys

ROOT = sys.argv[1] if len(sys.argv) > 1 else \
    "/Users/apple/lesson-ws/robogebra-books/gen-books/legacybooks/tn-cbse"
src_re = re.compile(r'src="img/([^"]+)"')

removed = bytes_freed = 0
for dirpath, dirnames, filenames in os.walk(ROOT):
    if "img" not in dirnames or "index.html" not in filenames:
        continue
    used = set(src_re.findall(open(os.path.join(dirpath, "index.html"), encoding="utf-8").read()))
    imgdir = os.path.join(dirpath, "img")
    for f in os.listdir(imgdir):
        if f not in used:
            p = os.path.join(imgdir, f)
            bytes_freed += os.path.getsize(p)
            os.remove(p)
            removed += 1
    if not os.listdir(imgdir):
        os.rmdir(imgdir)
print("removed %d orphan figures, freed %.1f MB" % (removed, bytes_freed / 1e6))
