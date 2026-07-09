"""Pulse-test dealer lock flag candidates live on PCSX2.

Run this while the dealer screen is open with the cursor on a known vehicle.

Usage:
  python tools/pulse_dealer_lock.py scan     # scan for dealer objects
  python tools/pulse_dealer_lock.py pulse <addr> <value>  # write value to addr, wait 8s, restore
  python tools/pulse_dealer_lock.py test-flag <addr>      # test if addr is the lock flag
"""

import struct, time, sys
from mc3api import MC3Game

def connect():
    return MC3Game.connect(timeout=10)

def cmd_scan():
    game = connect()
    try:
        # Read the tagged object region (0x00711F00-0x00713000)
        base = 0x00710000
        data = game.read(0x00711F00, 0x2000)
        print('=== Dealer UI State Objects ===')
        print('Looking for 0x200D/0x400E type-tagged objects with 0/1 flags\n')
        found_objects = []
        for off in range(0, len(data)-16, 4):
            tag = struct.unpack('<I', data[off:off+4])[0]
            tag_hi = (tag >> 24) & 0xFF
            if tag_hi in [0x20, 0x40]:
                f1 = struct.unpack('<I', data[off+4:off+8])[0]
                f2 = struct.unpack('<I', data[off+8:off+12])[0]
                if f1 < 256:  # small integer = potential flag
                    addr = 0x00711F00 + off
                    print(f'  0x{addr:08X}: tag=0x{tag:08X} [f1={f1} f2=0x{f2:08X}]')
                    found_objects.append((addr, tag, f1, f2))
        print(f'\nFound {len(found_objects)} candidate objects')
        if len(found_objects) >= 2:
            for a, t, f1, f2 in found_objects[:5]:
                print(f'  -> test: python tools/pulse_dealer_lock.py test-flag 0x{a+4:08X}')
    finally:
        game.close()

def cmd_pulse(addr, value):
    game = connect()
    try:
        orig = game.read_u32(addr)
        print(f'Writing 0x{value:08X} to 0x{addr:08X} (was 0x{orig:08X})')
        game.write_u32(addr, value)
        verify = game.read_u32(addr)
        print(f'Verified: 0x{verify:08X}')
        print('Holding for 8 seconds... watch the dealer screen')
        time.sleep(8)
        game.write_u32(addr, orig)
        restored = game.read_u32(addr)
        print(f'Restored: 0x{restored:08X}')
        if restored == orig:
            print('Restore verified.')
    finally:
        game.close()

def cmd_test_flag(addr):
    """Test if addr is a lock flag by writing 1 then 0."""
    game = connect()
    try:
        orig = game.read_u32(addr)
        print(f'Original value at 0x{addr:08X}: 0x{orig:08X} ({orig})')
        print(f'Test 1: Writing 0x00000001')
        game.write_u32(addr, 1)
        print('Holding for 6 seconds...')
        time.sleep(6)
        print(f'Test 2: Writing 0x00000000') 
        game.write_u32(addr, 0)
        print('Holding for 6 seconds...')
        time.sleep(6)
        game.write_u32(addr, orig)
        print(f'Restored to 0x{orig:08X}')
        print('If the lock state changed in the dealer UI during either write, this is THE FLAG.')
    finally:
        game.close()

if __name__ == '__main__':
    cmd = sys.argv[1] if len(sys.argv) > 1 else 'scan'
    if cmd == 'scan': cmd_scan()
    elif cmd == 'pulse': cmd_pulse(int(sys.argv[2],16), int(sys.argv[3],16))
    elif cmd == 'test-flag': cmd_test_flag(int(sys.argv[2],16))
    else: print(f'Unknown: {cmd}')