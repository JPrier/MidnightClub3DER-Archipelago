"""Set or read money in the running PCSX2 game.

Usage:
  python tools/money.py             # read current money
  python tools/money.py 100000      # set money to $100,000
  python tools/money.py +5000       # add $5,000
  python tools/money.py -5000       # subtract $5,000
"""

import sys
from mc3api import MC3Game

MONEY_ADDR = 0x00800870

def main():
    game = MC3Game.connect(timeout=15)
    try:
        current = game.bridge.read_u32(MONEY_ADDR)
        
        if len(sys.argv) < 2:
            print(f"${current:,}")
            return
        
        arg = sys.argv[1]
        if arg.startswith("+"):
            value = current + int(arg[1:])
        elif arg.startswith("-"):
            value = current - int(arg[1:])
        else:
            value = int(arg)
        
        value = max(0, min(value, 999999999))
        game.bridge.write_u32(MONEY_ADDR, value)
        print(f"${current:,} -> ${value:,}")
    finally:
        game.close()

if __name__ == "__main__":
    main()