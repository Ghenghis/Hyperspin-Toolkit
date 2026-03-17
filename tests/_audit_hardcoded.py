"""One-shot audit: find hardcoded drive letters and broken cross-references."""
import os, re, sys, importlib, traceback
sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SKIP = {".pytest_cache", "__pycache__", ".git", "node_modules"}

hardcoded = []
broken_imports = []

for dirpath, dirnames, filenames in os.walk(ROOT):
    dirnames[:] = [d for d in dirnames if d not in SKIP]
    for fname in filenames:
        if not fname.endswith(".py"):
            continue
        fp = os.path.join(dirpath, fname)
        rel = os.path.relpath(fp, ROOT)
        try:
            with open(fp, encoding="utf-8", errors="replace") as fh:
                lines = fh.readlines()
        except Exception:
            continue

        for i, line in enumerate(lines, 1):
            # Hardcoded drive letters used as defaults/fallbacks
            for m in re.finditer(r'["\']([A-Z]):\\\\', line):
                letter = m.group(1)
                if letter in ("D", "E", "F", "G", "H"):
                    hardcoded.append((rel, i, line.strip()[:120]))

        # Check imports resolve
        for i, line in enumerate(lines, 1):
            m2 = re.match(r"^(?:from|import)\s+([\w.]+)", line.strip())
            if m2:
                mod = m2.group(1).split(".")[0]
                if mod in ("core", "engines", "plugins", "dashboard", "agents", "setup"):
                    full = m2.group(1)
                    try:
                        importlib.import_module(full)
                    except Exception as exc:
                        broken_imports.append((rel, i, full, str(exc)[:80]))

print("=" * 70)
print(f"HARDCODED DRIVE PATHS: {len(hardcoded)}")
print("=" * 70)
for rel, lineno, text in hardcoded:
    print(f"  {rel}:{lineno}  {text}")

print()
print("=" * 70)
print(f"BROKEN CROSS-REFERENCES / IMPORTS: {len(broken_imports)}")
print("=" * 70)
for rel, lineno, mod, err in broken_imports:
    print(f"  {rel}:{lineno}  import {mod}  -> {err}")

if not broken_imports:
    print("  (none — all cross-references resolve)")
print()
