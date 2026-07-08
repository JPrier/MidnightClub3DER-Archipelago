# MC3 Archipelago — Project Status & Roadmap

*Updated 2026-07-08. SLUS-21355 · CRC 0x60A42FF5 · stock PCSX2.*

Single source of truth for where the project stands against the five end-state
deliverables. Supersedes the older `COMPLETE_STATUS.md` snapshot.

## Deliverables scorecard

| # | Deliverable | State | Notes |
|---|---|---|---|
| 1 | Modding API | ✅ **done** | `mc3api` package, live-verified, 25 tests |
| 2 | N-tier Archipelago mod | 🟢 **runnable end-to-end** | AP websocket client + game bridge + `python -m mc3ap` loop, all tested; gating hooks remain for *enforcing* locks |
| 3 | One-click install | ✅ **done** | `install.bat` / `install.py`, verified against local PCSX2 |
| 4 | GitHub + draft PR | 🟡 **repo pushed** | own repo live; official-AP PR needs Archipelago checkout (see below) |
| 5 | Integration tests + validation | ✅ **done** | 73 tests, CI on 3.10–3.13, emulator suite auto-skips |

## What works right now (verified live)

- Connect to stock PCSX2, read/write EE RAM via mailbox scan.
- Wallet money read/write (idempotent AP money-floor application).
- **Career stats catalog fully decoded** (the check-detection core):
  collectibles (per city + total), race wins, tournament wins, races entered,
  career earnings, per-route best times with **stable route ids**.
- Poll-based event stream → AP location checks (won races, collectibles,
  tournaments) with a resolver that surfaces (never drops) unmapped checks.
- Vehicle catalog read (names, ids).
- Last-played-event file path (event identity).

## Key discovery: the stats catalog (see `stats_catalog.md`)

The structure at `0x00800878 → 0x007C9EF0` is a **tag-scanned career stats
registry**, not a fixed table. Entries insert-shift, so everything is accessed
by 4CC tag, not address. This replaced the earlier fragile
`0x007CA044`-style fixed addresses and refuted the guessed collectible/garage
bitset candidates. It gives clean, reliable check detection **without needing
game hooks**.

## Remaining work

### Deliverable 2 — runnable, remaining work is gating enforcement
The full pipeline exists and is tested end-to-end:
- `adapters/archipelago/ap_protocol.py` + `ap_client_adapter.py` — websocket AP
  client with connect/ReceivedItems/LocationChecks/Sync and gap-resync.
- `adapters/pcsx2/mc3api_runtime.py` + `check_mapper.py` — game bridge.
- `runner.py` (`python -m mc3ap --server … --slot …`) — the live loop that
  applies AP items and sends detected checks.

What's left for full coverage:
- **Enforcing** locks (block a locked car/city/part). Detection needs no hooks;
  enforcement needs the gating hooks below. Until then non-money items are
  recorded as `pending_items` (surfaced, not lost).
- Richer item semantics (progressive vehicles/parts) once the curated catalog
  and gating hooks land.

### Deliverable 4 — official Archipelago PR
Own repo is pushed. To open the draft PR against `ArchipelagoMW/Archipelago`:
1. Fork + clone Archipelago, copy `worlds/mc3` into it.
2. Generate a test seed (`python Generate.py`) to validate the world loads.
3. Open a **draft** PR. This publishes to a third-party repo, so it needs an
   explicit go-ahead — materials are ready in `worlds/mc3/`.

### Gating (needed for vehicle/city/part *locks*, task 4 + hook discovery)
Check *detection* needs no hooks. **Enforcing** locks (block a locked car/city)
needs the 5 candidate hook sites dynamically probed and safe deny-paths found.
Candidates are in `targets.yaml`; method in `mc3_automated_discovery_method.md`.
Until then, locked items are recorded as `pending_items` (surfaced, not lost).

### Field discovery still blocked on game progression (task 6)
Needs specific savestates the current save can't reach:
- **Current city id / city-unlock flags** — a free-roam save in Atlanta or
  Detroit (only San Diego exists today).
- **Current *selected* event** (for start-gating) — an event prompt for a
  non-Vanessa event.
- **Part catalog** — the part shop open with categories unlocked.
- **Class unlock flags** — before/after a class unlock.
- **Showroom vehicle state** — current work has isolated `Prize` vs `Locked`
  UI clusters and live showroom text fields, but not the authoritative
  unlock bit yet.
- **Static metadata comparison** — the catalog at `0x007D28B0` and the
  `vp_is300_04_reward` block at `0x00717F88` match between current-state and
  `s15` garage scans, so they look like stable metadata rather than the live
  unlock decision source.

`s17-freeroam-sd-current.p2s` was captured this session (San Diego, $13,900).

## Test / CI

```bash
python -m pytest                    # 58 tests (emulator suite skips w/o PCSX2)
python -m pytest -m "not emulator"  # 50 tests, CI selection, ~0.2s
```

## Map of the codebase

| Path | Role |
|---|---|
| `mc3api/` | **Deliverable 1** — public modding API |
| `client/mc3ap/domain/` | pure AP domain model + reducer + invariants |
| `client/mc3ap/adapters/pcsx2/` | runtime bridge (`mc3api_runtime`, `check_mapper`) |
| `client/mc3ap/adapters/archipelago/` | AP websocket client (stub — next) |
| `worlds/mc3/` | APWorld package (items, locations, options, rules) |
| `payload/dist/60A42FF5.pnach` | deployed EE payload (mailbox + trampoline) |
| `tools/` | RE tooling (mips scanner/assembler, diff, probes) |
| `install.py` / `install.bat` | **Deliverable 3** — one-click installer |
| `docs/stats_catalog.md` | the check-detection core reference |
| `targets.yaml` | discovery targets — single source of truth |
