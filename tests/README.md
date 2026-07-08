# Test Suite

```bash
python -m pytest                    # everything (emulator tests skip if PCSX2 absent)
python -m pytest -m "not emulator"  # CI selection — no emulator, ~0.2s
python -m pytest tests/emulator     # live game tests (needs PCSX2 + MC3 + pnach)
```

| Suite | What it covers | Emulator? |
|---|---|---|
| `tests/unit` | Pure parsers: stats catalog decode, GameWatcher event detection (fake game) | No |
| `tests/integration` | Runtime bridge: game event → AP location check, idempotent item application | No |
| `client/mc3ap/domain/invariants.py` | Domain reducer invariants (deterministic, idempotent, monotonic, money ledger) | No |
| `tests/emulator` | Live PCSX2: connection, money write roundtrip, stats/vehicle reads | **Yes** (auto-skips) |
| `tests/contract`, `tests/e2e` | Reserved for AP-protocol contract + full seed E2E (fake server) | No |

## Regression against real memory dumps

`tests/unit/test_stats_catalog.py` includes a class that diffs real EE RAM
dumps (`dump_s6/s13/s14.json`) to lock in the collectible / tournament /
route-id discoveries. Those dumps are git-ignored (they contain raw game RAM),
so those tests **skip** on a fresh clone and run only on the RE machine.

## CI

`.github/workflows/ci.yml` runs `pytest -m "not emulator"` on Python
3.10–3.13. The emulator suite is Windows + hardware specific and runs locally.
