"""MC3 Event Listener — detects race start, finish, money changes.

Race detection:
  - Race START: QS%k[0] (0x007CA044) drops to 1-6 (from free roam value of 6+)
  - Race FINISH: 0x007CA10C changes to exactly 2

Usage: python tools/listen.py
"""

import sys, time, os
sys.path.insert(0, os.path.dirname(__file__) or ".")
from action_driver import MC3LiveAPI

class EventListener:
    def __init__(self):
        self.api = MC3LiveAPI()
        self._prev_money = self.api._rd(0x00800870)
        self._prev_qs = self.api._rd(0x007CA044)
        self._prev_status = self.api._rd(0x007CA10C)
        self._prev_pos = self.api._rd(0x006BE4F0)
        self._in_race = self._prev_qs <= 6

    def poll(self):
        events = []
        money = self.api._rd(0x00800870)
        qs = self.api._rd(0x007CA044)
        status = self.api._rd(0x007CA10C)
        pos = self.api._rd(0x006BE4F0)

        # Money
        if money != self._prev_money:
            delta = money - self._prev_money
            events.append({"type": "money", "delta": delta, "old": self._prev_money, "new": money})
            self._prev_money = money

        # Race START: QS%k drops below 6 (free roam has QS=6)
        was_racing = self._in_race
        self._in_race = qs < 6  # 1-5 = racing, 6 = free roam
        if self._in_race and not was_racing:
            events.append({"type": "race_start"})

        # Race FINISH: status becomes exactly 2
        if status == 2 and self._prev_status != 2:
            events.append({"type": "race_finish", "position": pos})
        self._prev_status = status

        # Position change during race
        if pos != self._prev_pos and self._in_race:
            events.append({"type": "position", "old": self._prev_pos, "new": pos})
        self._prev_pos = pos
        self._prev_qs = qs

        return events

    def close(self):
        self.api.close()

def main():
    el = EventListener()
    print("MC3 Event Listener (race start/finish + money)")
    print("Ctrl+C to stop\n")

    try:
        while True:
            for e in el.poll():
                ts = time.strftime("%H:%M:%S")
                if e["type"] == "money":
                    d = e["delta"]
                    s = f"+${d:,}" if d > 0 else f"-${-d:,}"
                    print(f"[{ts}] {s}  (${e['old']:,} -> ${e['new']:,})")
                elif e["type"] == "race_start":
                    print(f"[{ts}] RACE STARTED")
                elif e["type"] == "race_finish":
                    labels = ["?","1st","2nd","3rd","4th","5th","6th"]
                    p = labels[min(e["position"], 6)]
                    print(f"[{ts}] RACE FINISHED: {p}")
                elif e["type"] == "position":
                    labels = ["?","1st","2nd","3rd","4th","5th","6th"]
                    print(f"[{ts}] Position: {labels[min(e['old'],6)]} -> {labels[min(e['new'],6)]}")
                sys.stdout.flush()
            time.sleep(0.25)
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        el.close()

if __name__ == "__main__":
    main()