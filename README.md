# Midnight Club 3: DUB Edition Remix — Archipelago Integration

Full-coverage Archipelago randomizer for Midnight Club 3: DUB Edition Remix (PS2, NTSC-U, SLUS-21355).

## Status

🚧 **Phase 0 — Architecture & contracts** — domain model, reducer, invariants, fake E2E

| Layer | Status |
|---|---|
| Domain (pure Python) | ✅ 16/16 invariant tests passing |
| APWorld skeleton | ✅ generated |
| Client application | 🚧 service stubs in place |
| Port interfaces | ✅ defined |
| Fake AP server | ✅ |
| Fake game runtime | ✅ |
| SQLite persistence | ✅ schema + adapter |
| Scenario runner | ✅ |
| Payload (C) | ⬜ pending EE toolchain setup |
| PCSX2 bridge (stock) | ⬜ pending emulator setup |
| Reverse engineering | ⬜ pending game/emulator access |

## Quick Start

```bash
# Run domain tests
python -m pytest client/mc3ap/domain/invariants.py -v

# Install for APWorld development
pip install -e .
```

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