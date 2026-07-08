"""Full Memory Differential Explorer — persists raw snapshots and diffs.

Method validated: 64KB chunks read in <1ms, full 32MB dump in ~0.5s.

Usage:
  python full_diff.py 1          # Explore state 1 (snap every 1s, 10 snaps)
  python full_diff.py 1 5 0.5    # State 1, 5 snaps, 0.5s interval
  python full_diff.py --batch    # Run all 10 states
"""

import sys, time, struct, json, os, subprocess
from pathlib import Path

PROJECT = Path(__file__).parent.parent
DUMP_DIR = PROJECT / "dumps"

STATES = [
    (1, "slot", "s1_free_roam"),
    (2, "slot", "s2_event_prompt"),
    (3, "slot", "s3_race_start"),
    (4, "slot", "s4_race_finish_1st"),
    (5, "slot", "s5_post_vanessa"),
    (10, "slot", "s10_post_race"),
    (12, "file", r"D:\Development\archipelago\mc3\savestates\s12-garage.p2s"),
    (13, "file", r"D:\Development\archipelago\mc3\savestates\s13-collectablefroms6.p2s"),
    (14, "file", r"D:\Development\archipelago\mc3\savestates\s14-tournamentpluslexusafters13.p2s"),
]


def boot_state(state_id, state_type):
    subprocess.run(["taskkill", "/F", "/IM", "pcsx2-qt.exe"], capture_output=True)
    time.sleep(2)
    exe = r"E:\Emulator\PCSX2\pcsx2-qt.exe"
    iso = r"E:\Emulator\PCSX2\ps2games\MC3.iso"
    if state_type == "slot":
        subprocess.Popen([exe, "-fastboot", "-state", str(state_id), iso])
    else:
        subprocess.Popen([exe, "-fastboot", "-statefile", state_id, iso])

    for _ in range(15):
        time.sleep(2)
        try:
            from action_driver import MC3LiveAPI
            api = MC3LiveAPI()
            api.close()
            return True
        except:
            pass
    return False


def capture_full_snapshot(api):
    """Read full 32MB EE RAM. Returns dict of hex strings, one per 64KB chunk."""
    snap = {}
    for start in range(0, 0x02000000, 0x10000):
        key = f"{start:08X}"
        try:
            snap[key] = api._mc3.read(start, 0x10000).hex()
        except:
            snap[key] = ""
    return snap


def diff_snapshots(prev, curr):
    """Return list of [addr_hex, old_val, new_val] for changed dwords."""
    changes = []
    for key in prev:
        if key not in curr: continue
        hp, hc = prev[key], curr[key]
        if hp == hc or not hp or not hc: continue
        bp, bc = bytes.fromhex(hp), bytes.fromhex(hc)
        for off in range(0, len(bp), 4):
            vp = struct.unpack_from("<I", bp, off)[0]
            vc = struct.unpack_from("<I", bc, off)[0]
            if vp != vc:
                addr = int(key, 16) + off
                changes.append([f"0x{addr:08X}", vp, vc])
    return changes


def explore(state_id, state_type, label, num_snaps=10, interval=1.0):
    print(f"\n{'='*60}")
    print(f"STATE: {label}  ({num_snaps} snaps @ {interval}s)")
    print(f"{'='*60}")

    if not boot_state(state_id, state_type):
        print("  FAILED to boot")
        return

    from action_driver import MC3LiveAPI
    api = MC3LiveAPI()

    out = DUMP_DIR / label
    out.mkdir(parents=True, exist_ok=True)

    prev = None
    for i in range(num_snaps):
        t0 = time.time()
        snap = capture_full_snapshot(api)
        dt = time.time() - t0

        # Save raw snapshot
        snap_file = out / f"snap_{i:03d}.json"
        with open(snap_file, "w") as f:
            json.dump(snap, f)

        msg = f"  Snap {i+1}/{num_snaps} ({dt:.1f}s, {len(snap)} chunks)"

        if prev is not None:
            changes = diff_snapshots(prev, snap)
            diff_file = out / f"diff_{i-1:03d}_{i:03d}.json"
            with open(diff_file, "w") as f:
                json.dump(changes, f)
            msg += f"  diff: {len(changes)} changes"
        else:
            msg += "  (baseline)"

        print(msg)
        prev = snap

        if i < num_snaps - 1:
            time.sleep(max(0, interval - dt))

    # Final summary
    total_diffs = sum(1 for f in out.iterdir() if f.name.startswith("diff_"))
    print(f"  Done. {total_diffs} diffs saved to {out}")
    api.close()


if __name__ == "__main__":
    args = sys.argv[1:]

    if not args:
        print(__doc__)
        sys.exit(0)

    if args[0] == "--batch":
        for sid, stype, label in STATES:
            explore(sid, stype, label, 5)
    else:
        sid = int(args[0]) if args[0].isdigit() else args[0]
        stype = "slot" if isinstance(sid, int) and sid <= 10 else "file"
        snaps = int(args[1]) if len(args) > 1 else 10
        interval = float(args[2]) if len(args) > 2 else 1.0
        explore(sid, stype, f"s{sid}", snaps, interval)