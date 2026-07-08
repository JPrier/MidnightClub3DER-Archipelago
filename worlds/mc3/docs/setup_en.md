# Midnight Club 3: DUB Edition Remix Setup Guide

## Required Software

- [PCSX2](https://pcsx2.net) (stock, v2.x) — a PlayStation 2 emulator
- A legal dump of **Midnight Club 3: DUB Edition Remix** (NTSC-U, `SLUS-21355`)
- [Python 3.10+](https://python.org)
- The MC3 Archipelago client + payload:
  <https://github.com/JPrier/MidnightClub3DER-Archipelago>

This integration does **not** modify or distribute the game. It runs stock
PCSX2 with a small memory patch (`.pnach`) and an external Python client that
reads/writes emulator memory.

## Installation

1. Install PCSX2 and confirm the game boots normally.
2. Download or clone the MC3 Archipelago repo.
3. Run the one-click installer:
   - Windows: double-click **`install.bat`**, or
   - Any OS: `python install.py --pcsx2 "<path to PCSX2 folder>"`

   This installs the Python client, copies the payload into PCSX2's `cheats`
   folder, and enables cheats.
4. Verify: boot the game in PCSX2, then run `python -m mc3api`. You should see a
   live connection with your money and career stats.

## Joining a Multiworld

1. Get the server address and your slot name from the host.
2. Boot Midnight Club 3 in PCSX2.
3. Start the client:

   ```bash
   python -m mc3ap --server <address> --slot <YourName>
   ```

4. Play. Winning races, completing tournaments, and collecting Rockstar logos
   are sent automatically as location checks; items you receive are applied in
   your game.

## What is randomized

- **Locations (checks):** race wins, tournament wins, and collectible pickups.
- **Items:** money, and — as gating support lands — vehicles, performance/visual
  parts, city access, and abilities.

See the world's options page for the full, up-to-date list.

## Troubleshooting

- **`python -m mc3api` says the mailbox isn't found** — make sure the game is
  actually booted (not at the BIOS), cheats are enabled in
  Settings → Emulation, and `60A42FF5.pnach` is in PCSX2's `cheats` folder.
- **Nothing happens when I win a race** — confirm the client console shows
  `[GAME] connected`. Checks are detected on a ~1s poll after the result.
- **Run as Administrator** if memory reads fail (PCSX2 may be elevated).
