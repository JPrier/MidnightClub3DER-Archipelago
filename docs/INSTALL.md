# Installing MC3 Archipelago

## Prerequisites (you provide these)

- **PCSX2** (stock, v2.x) — https://pcsx2.net
- A **legal dump** of *Midnight Club 3: DUB Edition Remix* (NTSC-U, `SLUS-21355`)
- **Python 3.10+** on your PATH

The mod never ships or touches the game ISO.

## One click (Windows)

Double-click **`install.bat`**. It will:

1. `pip install` the client package
2. Copy the MC3AP payload into PCSX2's `cheats/` folder
3. Turn on **Enable Cheats** in `PCSX2.ini`

If PCSX2 isn't found automatically, run from a terminal with the path:

```bash
python install.py --pcsx2 "E:/Emulator/PCSX2"
```

To also install the Archipelago world into your Archipelago folder:

```bash
python install.py --archipelago "C:/ProgramData/Archipelago"
```

## Verify it worked

1. Launch PCSX2, boot your MC3 Remix disc/ISO.
2. In a terminal:

   ```bash
   python -m mc3api
   ```

   You should see `Connected: MC3Game(... build=13)` and live money/stats.

## Playing an Archipelago seed

1. Generate a seed with the MC3 world (see the APWorld setup guide).
2. Boot the game in PCSX2.
3. Start the client (`python -m mc3ap`), enter the AP server address + slot.
4. Race — wins, tournaments, and collectibles are detected automatically and
   sent as location checks; received items apply in-game.

## Uninstall

Delete `<PCSX2>/cheats/60A42FF5.pnach` (a `.bak` of any prior file is kept),
and `pip uninstall mc3api`.
