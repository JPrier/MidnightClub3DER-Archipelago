"""Live game state poller.

Usage:  cd D:\Development\archipelago\mc3\mc3-ap\tools && python watch.py
"""

import sys, time, os
sys.path.insert(0, os.path.dirname(__file__) or ".")
from action_driver import MC3LiveAPI

def main(interval=1.0):
    api = MC3LiveAPI()
    print(f"MC3 Watch | build {api._rd(0x00720004)} | {interval}s\n")

    try:
        while True:
            ts = time.strftime("%H:%M:%S")
            money = api._rd(0x00800870)
            pos = api._rd(0x006BE4F0)
            status = api._rd(0x007CA10C)

            pos_str = str(pos)
            if status == 1:  # racing
                labels = ["?","1st","2nd","3rd","4th","5th","6th"]
                pos_str = labels[min(pos, 6)] if 1 <= pos <= 6 else f"P{pos}"
            elif status == 2:  # finished
                pos_str = "done"

            status_str = ""
            if status == 1: status_str = "RACE"
            elif status == 2: status_str = "DONE"
            elif status == 0xCDCDCDCD: status_str = "idle"

            print(f"{ts} | ${money:<8,} | {pos_str:<6s} | {status_str:<6s}", flush=True)
            time.sleep(interval)

    except KeyboardInterrupt:
        print("stopped")
    finally:
        api.close()

if __name__ == "__main__":
    main(float(sys.argv[1]) if len(sys.argv) > 1 else 1.0)