# MC3 Testing Command Reference

## Boot Commands

### Slot Save States (1-10)
```powershell
# GUI
& "E:\Emulator\PCSX2\pcsx2-qt.exe" -fastboot -state 1 "E:\Emulator\PCSX2\ps2games\MC3.iso"
& "E:\Emulator\PCSX2\pcsx2-qt.exe" -fastboot -state 4 "E:\Emulator\PCSX2\ps2games\MC3.iso"

# With debugger
& "E:\Emulator\PCSX2\pcsx2-qt.exe" -debugger -fastboot -state 4 "E:\Emulator\PCSX2\ps2games\MC3.iso"
```

### File Save States (s11+)
```powershell
# GUI
& "E:\Emulator\PCSX2\pcsx2-qt.exe" -fastboot -statefile "D:\Development\archipelago\mc3\savestates\s13-collectablefroms6.p2s" "E:\Emulator\PCSX2\ps2games\MC3.iso"

# Headless (no GUI window)
& "E:\Emulator\PCSX2\pcsx2-qt.exe" -nogui -batch -fastboot -state 1 "E:\Emulator\PCSX2\ps2games\MC3.iso"
```

### Bash Wrappers (from msys2/git-bash in tools/)
```bash
# Kill + boot slot state
taskkill //F //IM pcsx2-qt.exe
sleep 2
cmd //c "start /B E:\Emulator\PCSX2\pcsx2-qt.exe -fastboot -state 4 E:\Emulator\PCSX2\ps2games\MC3.iso" &
sleep 20

# Kill + boot file state
taskkill //F //IM pcsx2-qt.exe
sleep 2
cmd //c "start /B E:\Emulator\PCSX2\pcsx2-qt.exe -fastboot -statefile D:\Development\archipelago\mc3\savestates\s14-tournamentpluslexusafters13.p2s E:\Emulator\PCSX2\ps2games\MC3.iso" &
sleep 25
```

---

## Probe Commands

*All run from `D:\Development\archipelago\mc3\mc3-ap\tools\`*

### Watch & Listen
```bash
python watch.py              # Poll money + position every 1s
python watch.py 0.5          # Poll every 500ms
python listen.py             # Detect race start/finish, money changes
```

### Full Memory Dumps
```bash
python full_diff.py 1           # State 1, 10 snaps, 1s interval
python full_diff.py 1 5 0.5     # State 1, 5 snaps, 500ms interval
python full_diff.py --batch     # All 9 states, 5 snaps each
```

### State Exploration
```bash
python run_explore.py explore 1      # Explore state 1
python run_explore.py diff s1.json s5.json  # Cross-state diff
```

### Mailbox & Memory
```bash
python probe_memory.py                      # Mailbox health check
python probe_memory.py --watch              # Poll heartbeat
python live_inject.py status                # Mailbox status
python live_inject.py read 0x00800870       # Read address
python live_inject.py read 0x007D2310 256   # Read 256 bytes
python live_inject.py write 0x00800870 9999 # Write to address
```

---

## Python API Snippets

```python
cd tools/
python

from action_driver import MC3LiveAPI
api = MC3LiveAPI()

# Read confirmed fields
api._rd(0x00800870)      # money (u32)
api._rd(0x006BE4F0)      # race position (1=1st, 3=3rd, 5=5th)
api._rd(0x007CA10C)      # race status (2=finished)
api._rd(0x007CA044)      # QS%k[0] (<6=racing, 6=free roam)
api._rd(0x00619B14)      # profile pointer
api._rd(0x006E0170)      # vehicle list pointer

# Write
api._wr(0x00800870, 9999)   # set money

# Raw read
api._mc3.read(0x007D2310, 256)          # 256 bytes at profile
api._mc3.read_string(0x0079C070, 32)    # read null-terminated string

api.close()
```

---

## PNACH Management

```bash
# Regenerate PNACH from Python code
cd D:\Development\archipelago\mc3\mc3-ap\tools
python action_driver.py > E:\Emulator\PCSX2\cheats\60A42FF5.pnach

# Check if PNACH loaded
grep "cheat patches active" E:\Emulator\PCSX2\log\emulog.txt

# Check cheats enabled in config
python -c "import configparser; c=configparser.ConfigParser(); c.read(r'E:\Emulator\PCSX2\inis\PCSX2.ini'); print(c['EmuCore']['enablecheats'])"

# Enable cheats
python -c "import configparser; c=configparser.ConfigParser(); c.read(r'E:\Emulator\PCSX2\inis\PCSX2.ini'); c['EmuCore']['enablecheats']='true'; c.write(open(r'E:\Emulator\PCSX2\inis\PCSX2.ini','w'))"
```

---

## Verify Game Running

```bash
# Check process
tasklist //FI "IMAGENAME eq pcsx2-qt.exe"

# Check log
tail -10 E:\Emulator\PCSX2\log\emulog.txt
grep "CRC:\|cheat\|active" E:\Emulator\PCSX2\log\emulog.txt
```

---

## Paths

| Resource | Path |
|---|---|
| Project root | `D:\Development\archipelago\mc3\mc3-ap` |
| Tools | `D:\Development\archipelago\mc3\mc3-ap\tools` |
| PCSX2 exe | `E:\Emulator\PCSX2\pcsx2-qt.exe` |
| Game ISO | `E:\Emulator\PCSX2\ps2games\MC3.iso` |
| PNACH | `E:\Emulator\PCSX2\cheats\60A42FF5.pnach` |
| PCSX2 config | `E:\Emulator\PCSX2\inis\PCSX2.ini` |
| PCSX2 log | `E:\Emulator\PCSX2\log\emulog.txt` |
| Save states (slots) | `E:\Emulator\PCSX2\sstates\` |
| Save states (files) | `D:\Development\archipelago\mc3\savestates\` |
| Memory dumps | `D:\Development\archipelago\mc3\mc3-ap\dumps\` |
| Design docs | `D:\Development\archipelago\mc3\` |
