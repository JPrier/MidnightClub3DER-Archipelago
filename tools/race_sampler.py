"""Rapid race-state sampler — finds exact transition moments and diffs them.

Polls position at 10ms intervals, captures full snapshot at each transition,
then diffs to find ALL fields that changed.

Usage: python tools/race_sampler.py 7   (state 7 — position changes at ~7s, 8s, 17s)
"""

import sys
import time
import struct
import json
import subprocess
import os

sys.path.insert(0, os.path.dirname(__file__) or ".")
from action_driver import MC3LiveAPI

# Regions to capture at each transition
REGIONS = [
    ("globals",      0x00600000, 0x20000),
    ("race_area",    0x007CA000, 0x1000),
    ("position_area", 0x006BE000, 0x1000),
]


def main(state):
    # Boot
    subprocess.run(["taskkill", "/F", "/IM", "pcsx2-qt.exe"], capture_output=True)
    time.sleep(2)

    if state.isdigit():
        subprocess.Popen([
            r"E:\Emulator\PCSX2\pcsx2-qt.exe", "-fastboot", "-state", state,
            r"E:\Emulator\PCSX2\ps2games\MC3.iso",
        ])
    else:
        subprocess.Popen([
            r"E:\Emulator\PCSX2\pcsx2-qt.exe", "-fastboot", "-statefile", state,
            r"E:\Emulator\PCSX2\ps2games\MC3.iso",
        ])

    time.sleep(15)

    api = MC3LiveAPI()
    print(f"State {state} loaded. Polling position at 10ms...\n")

    prev_pos = api._rd(0x006BE4F0)
    prev_status = api._rd(0x007CA10C)
    prev_snap = None  # full snapshot at last stable moment
    transition_count = 0
    t0 = time.time()

    try:
        while transition_count < 10:
            time.sleep(0.01)
            t = time.time() - t0

            pos = api._rd(0x006BE4F0)
            status = api._rd(0x007CA10C)

            changed = False
            reason = ""

            if pos != prev_pos:
                reason = f"POSITION: {prev_pos} -> {pos}"
                changed = True
            if status != prev_status:
                reason = f"STATUS: {prev_status} -> {status}"
                changed = True

            if changed:
                transition_count += 1
                print(f"\n[{t:.2f}s] TRANSITION #{transition_count}: {reason}")

                # Capture AFTER snapshot
                after_snap = {}
                for name, start, size in REGIONS:
                    try:
                        after_snap[name] = api._mc3.read(start, min(size, 0x2000)).hex()
                    except:
                        after_snap[name] = ""

                # Diff against previous stable snapshot
                if prev_snap:
                    print(f"  Changed fields (vs snapshot at ~{prev_snap_time:.1f}s):")
                    changes = 0
                    for name in REGIONS:
                        rname = name
                        if rname not in prev_snap or rname not in after_snap:
                            continue
                        ba = bytes.fromhex(prev_snap[rname])
                        bb = bytes.fromhex(after_snap[rname])
                        if len(ba) != len(bb):
                            continue
                        for off in range(0, len(ba), 4):
                            va = struct.unpack_from("<I", ba, off)[0]
                            vb = struct.unpack_from("<I", bb, off)[0]
                            if va != vb:
                                # Find the region start address
                                for rn, rs, rz in REGIONS:
                                    if rn == rname:
                                        addr = rs + off
                                        break
                                else:
                                    addr = off
                                delta = vb - va
                                note = ""
                                if 1 <= vb <= 6 and 1 <= va <= 6:
                                    note = " [position candidates]"
                                elif delta == 1:
                                    note = " [+1]"
                                print(f"    0x{addr:08X} [{rname}]: {va} -> {vb}{note}")
                                changes += 1
                                if changes >= 30:
                                    break
                        if changes >= 30:
                            break
                    if changes == 0:
                        print("    (no changed fields in monitored regions)")
                    print(f"    {changes} total changed dwords")

                # Take a new stable snapshot AFTER the transition settles
                time.sleep(0.5)
                prev_snap = {}
                for name, start, size in REGIONS:
                    try:
                        prev_snap[name] = api._mc3.read(start, min(size, 0x2000)).hex()
                    except:
                        prev_snap[name] = ""
                prev_snap_time = time.time() - t0

                prev_pos = api._rd(0x006BE4F0)
                prev_status = api._rd(0x007CA10C)

            # Take initial snapshot after 1 second of stability
            if prev_snap is None and t > 1.0:
                prev_snap = {}
                for name, start, size in REGIONS:
                    try:
                        prev_snap[name] = api._mc3.read(start, min(size, 0x2000)).hex()
                    except:
                        prev_snap[name] = ""
                prev_snap_time = t
                prev_pos = api._rd(0x006BE4F0)
                prev_status = api._rd(0x007CA10C)
                print(f"[{t:.1f}s] Initial snapshot captured")

            # Progress indicator
            if transition_count == 0 and int(t) % 5 == 0 and int(t) != int(t - 0.02):
                print(f"  [{t:.0f}s] waiting for change... pos={prev_pos}", end="\r")

    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        api.close()


if __name__ == "__main__":
    state = sys.argv[1] if len(sys.argv) > 1 else "7"
    main(state)