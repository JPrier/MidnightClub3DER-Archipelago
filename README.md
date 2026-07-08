# Midnight Club 3: DUB Edition Remix — Archipelago Integration

Full-coverage Archipelago randomizer for Midnight Club 3: DUB Edition Remix (PS2, NTSC-U, SLUS-21355).

## Status

🚧 **Phase 2 — Modding API live** — `mc3api` package connects to stock PCSX2 and
reads/writes confirmed game state; check detection works by polling.

| Layer | Status |
|---|---|
| **mc3api modding API** | ✅ live-verified (money, stats catalog, vehicles, events) |
| Stats catalog decoding | ✅ collectibles/wins/tournaments/routes confirmed |
| Poll-based check detection | ✅ GameWatcher (no hooks needed for detection) |
| PCSX2 bridge (stock) | ✅ mailbox scan + EE-space read/write |
| Unit + emulator tests | ✅ 25 passing |
| Domain (pure Python) | ✅ invariant tests passing |
| APWorld skeleton | ✅ generated |
| Client application | 🚧 service stubs in place |
| Payload (PNACH/MIPS) | ✅ mailbox + SetCarCfg trampoline (build 13) |
| Gating/blocking hooks | ⬜ needs hook discovery (see targets.yaml) |

## Quick Start

```bash
pip install -e .[dev]

# Status dump against a running game
python -m mc3api

# Tests (emulator suite auto-skips if PCSX2 isn't running)
python -m pytest tests/unit tests/emulator
```

Run the Archipelago client against a live game:

```bash
python -m mc3ap --server wss://archipelago.gg:38281 --slot YourName
```

See [docs/api.md](docs/api.md) for the modding API, [docs/INSTALL.md](docs/INSTALL.md)
for setup, [docs/PROJECT_STATUS.md](docs/PROJECT_STATUS.md) for the roadmap, and
[docs/stats_catalog.md](docs/stats_catalog.md) for the check-detection core.

## Architecture

```
APWorld (Python) → AP Server
     ↓ seed contract JSON
Python Client (mc3ap)
     ↓ process-memory mailbox ABI
Stock PCSX2 (no fork)
     ↓
PS2 EE Payload (C) → MC3 Game
```

### PCSX2 Policy

**No PCSX2 fork is required.** The baseline distribution works with stock/current PCSX2.
The Python client discovers the payload via process-memory scanning (magic marker + CRC validation).
Optional `.pnach` patches and ISO/asset patching are game-side only — the emulator is never modified.

A PCSX2 fork/local IPC is only an optional future improvement, not part of the normal installation path.

## Requirements

- Python 3.13+
- **Stock PCSX2** (stable or nightly — no fork needed)
- PS2 EE GCC toolchain (for payload compilation)
- Legal dump of Midnight Club 3: DUB Edition Remix (SLUS-21355)

## License

MIT