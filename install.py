#!/usr/bin/env python3
"""MC3 Archipelago — one-command installer.

Sets up everything a player needs on top of a working PCSX2 + legal MC3 dump:

  1. Installs the mc3api / client Python package (pip install -e .)
  2. Copies the MC3AP payload (60A42FF5.pnach) into PCSX2's cheats folder
  3. Enables cheats in PCSX2.ini
  4. (optional) Installs the Archipelago world into an Archipelago install

Usage:
    python install.py                 # auto-detect PCSX2, interactive prompts
    python install.py --pcsx2 "E:/Emulator/PCSX2" --yes
    python install.py --archipelago "C:/ProgramData/Archipelago"

It never touches the game ISO and never modifies the emulator binary — only
the cheats folder and the ini's cheat flag.
"""

from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parent
PNACH_SRC = REPO / "payload" / "dist" / "60A42FF5.pnach"
GAME_CRC = "60A42FF5"

# Common PCSX2 install locations to probe.
PCSX2_CANDIDATES = [
    Path("E:/Emulator/PCSX2"),
    Path.home() / "AppData/Local/PCSX2",
    Path.home() / "Documents/PCSX2",
    Path("C:/Program Files/PCSX2"),
    Path("C:/Program Files (x86)/PCSX2"),
]


def info(msg): print(f"[*] {msg}")
def ok(msg): print(f"[OK] {msg}")
def warn(msg): print(f"[!] {msg}")
def fail(msg): print(f"[FAIL] {msg}"); sys.exit(1)


def find_pcsx2(explicit: str | None) -> Path:
    if explicit:
        p = Path(explicit)
        if not p.exists():
            fail(f"--pcsx2 path does not exist: {p}")
        return p
    for c in PCSX2_CANDIDATES:
        if (c / "pcsx2-qt.exe").exists() or (c / "cheats").exists() or (c / "inis").exists():
            info(f"Auto-detected PCSX2 at {c}")
            return c
    fail("Could not auto-detect PCSX2. Re-run with --pcsx2 <path-to-PCSX2-folder>.")


def pcsx2_data_dir(root: Path) -> Path:
    """cheats/ and inis/ live either under the install root (portable mode) or
    under the user Documents folder (installed mode). Prefer whichever has inis."""
    for cand in (root, Path.home() / "Documents/PCSX2"):
        if (cand / "inis").exists() or (cand / "cheats").exists():
            return cand
    return root


def install_python_package():
    info("Installing Python package (pip install -e .) ...")
    r = subprocess.run([sys.executable, "-m", "pip", "install", "-e", str(REPO)],
                       capture_output=True, text=True)
    if r.returncode != 0:
        warn("pip install failed:\n" + r.stdout + r.stderr)
        warn("You can still run from source; continuing.")
    else:
        ok("mc3api installed")


def install_pnach(data_dir: Path) -> Path:
    if not PNACH_SRC.exists():
        fail(f"Payload not found: {PNACH_SRC}")
    cheats = data_dir / "cheats"
    cheats.mkdir(parents=True, exist_ok=True)
    dst = cheats / f"{GAME_CRC}.pnach"
    if dst.exists():
        backup = dst.with_suffix(".pnach.bak")
        shutil.copy2(dst, backup)
        info(f"Backed up existing pnach -> {backup.name}")
    shutil.copy2(PNACH_SRC, dst)
    ok(f"Payload installed -> {dst}")
    return dst


def enable_cheats(data_dir: Path):
    ini = data_dir / "inis" / "PCSX2.ini"
    if not ini.exists():
        warn(f"PCSX2.ini not found at {ini}. Enable 'Cheats' manually in "
             "Settings > Emulation.")
        return
    text = ini.read_text(encoding="utf-8", errors="ignore")
    lines = text.splitlines()
    out, in_emucore, done = [], False, False
    for line in lines:
        stripped = line.strip()
        if stripped.startswith("[") and stripped.endswith("]"):
            if in_emucore and not done:
                out.append("EnableCheats = true")
                done = True
            in_emucore = stripped == "[EmuCore]"
        if in_emucore and stripped.lower().startswith("enablecheats"):
            out.append("EnableCheats = true")
            done = True
            continue
        out.append(line)
    if in_emucore and not done:
        out.append("EnableCheats = true")
        done = True
    if not done:
        out.append("[EmuCore]")
        out.append("EnableCheats = true")
    ini.write_text("\n".join(out) + "\n", encoding="utf-8")
    ok("Enabled cheats in PCSX2.ini")


def install_apworld(archipelago: str | None):
    if not archipelago:
        return
    ap = Path(archipelago)
    worlds = ap / "worlds"
    if not worlds.exists():
        warn(f"No worlds/ folder under {ap}; skipping APWorld install.")
        return
    dst = worlds / "mc3"
    if dst.exists():
        shutil.rmtree(dst)
    shutil.copytree(REPO / "worlds" / "mc3", dst)
    ok(f"Installed APWorld -> {dst}")


def main():
    ap = argparse.ArgumentParser(description="MC3 Archipelago installer")
    ap.add_argument("--pcsx2", help="Path to PCSX2 folder")
    ap.add_argument("--archipelago", help="Path to Archipelago install (optional)")
    ap.add_argument("--yes", action="store_true", help="Non-interactive")
    args = ap.parse_args()

    print("=" * 60)
    print(" Midnight Club 3 DUB Edition Remix — Archipelago installer")
    print("=" * 60)

    root = find_pcsx2(args.pcsx2)
    data = pcsx2_data_dir(root)
    info(f"PCSX2 data dir: {data}")

    if not args.yes:
        resp = input(f"Install payload + enable cheats here? [Y/n] ").strip().lower()
        if resp and resp != "y":
            fail("Aborted by user.")

    install_python_package()
    install_pnach(data)
    enable_cheats(data)
    install_apworld(args.archipelago)

    print("\n" + "=" * 60)
    ok("Done. Next steps:")
    print("   1. Launch PCSX2 and boot your MC3 Remix disc/ISO.")
    print("   2. Verify the payload:  python -m mc3api")
    print("   3. Start the AP client: python -m mc3ap  (see docs/api.md)")
    print("=" * 60)


if __name__ == "__main__":
    main()
