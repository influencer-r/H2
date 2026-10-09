"""
build.py — Haven Stays
Property Management & Automated Billing System
Engineered by READON ADOLA DEVs (Support: +254 798 792 730)
Copyright (c) 2026 READON ADOLA. All rights reserved.

PyInstaller packaging script.

Usage:
    python build.py [--onefile] [--debug]

Flags:
    --onefile   Compile into a single .exe (slower startup, but easier distribution)
    --debug     Keep console window visible for troubleshooting

Requirements (install before running):
    pip install pyinstaller pywebview flask waitress reportlab requests twilio

Place ngrok.exe inside the  ./bin/  directory before building.
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# ─────────────────────────────────────────────────────────────────────────────
# Configuration
# ─────────────────────────────────────────────────────────────────────────────
ROOT        = Path(__file__).parent.resolve()
DIST_DIR    = ROOT / "dist"
BUILD_DIR   = ROOT / "build"
ENTRY       = ROOT / "main.py"
APP_NAME    = "HavenStays"
ICON_PATH   = ROOT / "static" / "images" / "icon.ico"

ONE_FILE    = "--onefile" in sys.argv
DEBUG_MODE  = "--debug"  in sys.argv

# ─────────────────────────────────────────────────────────────────────────────
# Helper: collect (source, dest) tuples for PyInstaller --add-data
# ─────────────────────────────────────────────────────────────────────────────
SEP = ";" if sys.platform == "win32" else ":"

def data_arg(src: Path, dest: str) -> str:
    return f"{src}{SEP}{dest}"


# Resolve webview GUI framework DLL path for pywebview
def _webview_dlls() -> list[str]:
    """Return --add-binary entries for pywebview on Windows."""
    try:
        import webview  # type: ignore
        wv_dir = Path(webview.__file__).parent
        dlls = []
        for pattern in ("*.dll", "*.pyd"):
            for f in wv_dir.rglob(pattern):
                rel = f.relative_to(wv_dir.parent)
                dlls.append(f"{f}{SEP}{rel.parent}")
        return dlls
    except ImportError:
        print("[build.py] WARNING: pywebview not installed — skipping DLL collection.")
        return []


# ─────────────────────────────────────────────────────────────────────────────
# Build data / binary lists
# ─────────────────────────────────────────────────────────────────────────────
add_data = [
    # Templates
    data_arg(ROOT / "templates",               "templates"),
    # Static assets
    data_arg(ROOT / "static",                  "static"),
    # Background WhatsApp bridge
    data_arg(ROOT / "wa_bridge",               "wa_bridge"),
    # Pre-created empty storage dirs (PyInstaller will include them)
    # actual DB is created at runtime so we only need the directory hint
    data_arg(ROOT / "storage" / "receipts",    "storage/receipts"),
    data_arg(ROOT / "storage" / "assets",      "storage/assets"),
]

add_binaries = []

# Bundle ngrok.exe if present
ngrok_src = ROOT / "bin" / "ngrok.exe"
if ngrok_src.exists():
    add_binaries.append(data_arg(ngrok_src, "bin"))
    print(f"[build.py] [OK] Bundling ngrok.exe from {ngrok_src}")
else:
    print(
        f"[build.py] [WARN] ngrok.exe not found at {ngrok_src}.\n"
        "  Tunnel functionality will require ngrok to be on the system PATH.\n"
        "  Download from https://ngrok.com/download and place in ./bin/ngrok.exe"
    )

# pywebview DLLs
add_binaries.extend(_webview_dlls())

# ─────────────────────────────────────────────────────────────────────────────
# Hidden imports — libraries that PyInstaller's static analyser misses
# ─────────────────────────────────────────────────────────────────────────────
hidden_imports = [
    # Flask internals
    "flask", "flask.templating", "flask.json", "jinja2",
    "werkzeug", "werkzeug.serving", "werkzeug.routing",
    "werkzeug.middleware.proxy_fix",
    # WSGI server
    "waitress", "waitress.server",
    # Database
    "sqlite3",
    # PDF
    "reportlab", "reportlab.lib", "reportlab.lib.colors",
    "reportlab.lib.pagesizes", "reportlab.lib.styles",
    "reportlab.lib.units", "reportlab.platypus",
    "reportlab.platypus.paragraph", "reportlab.platypus.tables",
    "reportlab.platypus.flowables", "reportlab.graphics",
    "reportlab.pdfgen", "reportlab.pdfbase", "reportlab.pdfbase.ttfonts",
    "reportlab.pdfbase._fontdata",
    # HTTP / tunnel
    "requests", "urllib3", "certifi", "charset_normalizer", "idna",
    # WebView
    "webview", "webview.platforms.winforms",
    # Optional: Twilio
    "twilio", "twilio.rest",
    # Standard lib extras
    "logging.handlers", "email.mime.text", "email.mime.multipart",
    "threading", "queue", "json", "pathlib", "contextlib",
    "datetime", "uuid",
    # Encodings often missed
    "encodings.utf_8", "encodings.ascii",
]

# ─────────────────────────────────────────────────────────────────────────────
# Assemble PyInstaller command
# ─────────────────────────────────────────────────────────────────────────────
cmd = [
    sys.executable, "-m", "PyInstaller",
    str(ENTRY),
    "--name", APP_NAME,
    "--distpath", str(DIST_DIR),
    "--workpath", str(BUILD_DIR),
    "--clean",
    "--noconfirm",
]

# Windowed (no console) vs debug
if not DEBUG_MODE:
    cmd += ["--noconsole", "--windowed"]
else:
    print("[build.py] Debug mode: console window will be visible.")

# One-file vs one-dir
if ONE_FILE:
    cmd.append("--onefile")
    print("[build.py] Building single-file .exe  (slower first launch)")
else:
    print("[build.py] Building one-dir bundle  (faster startup)")

# Icon — skip if file is empty/invalid stub
if ICON_PATH.exists() and ICON_PATH.stat().st_size > 100:
    cmd += ["--icon", str(ICON_PATH)]
else:
    print(f"[build.py] Skipping icon (missing or empty stub) — using default.")

# Add data / binaries
for d in add_data:
    cmd += ["--add-data", d]

for b in add_binaries:
    cmd += ["--add-binary", b]

# Hidden imports
for hi in hidden_imports:
    cmd += ["--hidden-import", hi]

# Exclude chardet — broken src/ layout incompatible with PyInstaller;
# requests uses charset_normalizer by default so chardet is not needed.
cmd += ["--exclude-module", "chardet"]

# Runtime hook to fix working directory inside frozen bundle
runtime_hook = ROOT / "_pyi_rthook.py"
runtime_hook.write_text(
    """
import os, sys
if getattr(sys, 'frozen', False):
    os.chdir(os.path.dirname(sys.executable))
""",
    encoding="utf-8",
)
cmd += ["--runtime-hook", str(runtime_hook)]

# ─────────────────────────────────────────────────────────────────────────────
# Pre-build: ensure the placeholder storage dirs exist
# ─────────────────────────────────────────────────────────────────────────────
(ROOT / "storage" / "receipts").mkdir(parents=True, exist_ok=True)
(ROOT / "storage" / "assets").mkdir(parents=True, exist_ok=True)

# Ensure placeholder images exist (empty PNGs so PyInstaller has something to bundle)
placeholder_dir = ROOT / "storage" / "assets"
for i in range(1, 6):
    ph = placeholder_dir / f"placeholder{i}.jpg"
    if not ph.exists():
        # Create a minimal 1-byte stub; replace with real images before distribution
        ph.write_bytes(b"")

# ─────────────────────────────────────────────────────────────────────────────
# Run PyInstaller
# ─────────────────────────────────────────────────────────────────────────────
print("\n" + "=" * 60)
print(f"  Building {APP_NAME}.exe …")
print("=" * 60)
print("Command:\n  " + " \\\n    ".join(cmd) + "\n")

# Back up existing database from dist if present so data/settings are not lost
db_in_dist = DIST_DIR / APP_NAME / "storage" / "haven_stays.db"
temp_db_backup = None
if db_in_dist.exists():
    temp_db_backup = ROOT / "haven_stays_backup.db"
    shutil.copy2(db_in_dist, temp_db_backup)

result = subprocess.run(cmd, check=False)

# ─────────────────────────────────────────────────────────────────────────────
# Post-build: copy README and storage stubs into dist folder
# ─────────────────────────────────────────────────────────────────────────────
if result.returncode == 0:
    exe_dir = DIST_DIR / APP_NAME if not ONE_FILE else DIST_DIR
    (exe_dir / "storage" / "receipts").mkdir(parents=True, exist_ok=True)
    (exe_dir / "storage" / "assets").mkdir(parents=True, exist_ok=True)

    # Restore saved database
    if temp_db_backup and temp_db_backup.exists():
        shutil.copy2(temp_db_backup, exe_dir / "storage" / "haven_stays.db")
        temp_db_backup.unlink(missing_ok=True)
    elif (ROOT / "storage" / "haven_stays.db").exists():
        shutil.copy2(ROOT / "storage" / "haven_stays.db", exe_dir / "storage" / "haven_stays.db")

    # Ensure bin directory with ngrok.exe is also copied right next to the executable
    bin_src = ROOT / "bin"
    if bin_src.exists() and not ONE_FILE:
        bin_dest = exe_dir / "bin"
        bin_dest.mkdir(parents=True, exist_ok=True)
        for item in bin_src.iterdir():
            if item.is_file():
                shutil.copy2(item, bin_dest / item.name)

    # Ensure wa_bridge directory is copied next to executable
    wa_bridge_src = ROOT / "wa_bridge"
    if wa_bridge_src.exists() and not ONE_FILE:
        wa_bridge_dest = exe_dir / "wa_bridge"
        if not wa_bridge_dest.exists():
            shutil.copytree(wa_bridge_src, wa_bridge_dest, dirs_exist_ok=True)

    readme_src = ROOT / "README.md"
    if readme_src.exists():
        shutil.copy(readme_src, exe_dir / "README.md")

    print("\n" + "=" * 60)
    print(f"  [SUCCESS] Build successful!")
    print(f"  Output: {exe_dir}")
    if not ONE_FILE:
        print(f"  Executable: {exe_dir / (APP_NAME + '.exe')}")
    else:
        print(f"  Executable: {DIST_DIR / (APP_NAME + '.exe')}")
    print("=" * 60)
else:
    print("\n" + "=" * 60)
    print("  [FAIL] Build FAILED — see output above for errors.")
    print("=" * 60)
    sys.exit(result.returncode)

# Clean up temp hook
runtime_hook.unlink(missing_ok=True)
