# Full Memory Differential Exploration Plan

## Goal
Capture every memory change across all save states to definitively identify
collectible bitsets, garage ownership, event IDs, and all other game state.

## Method
1. Boot each save state
2. Poll ENTIRE EE RAM (0x00000000-0x02000000) every 1 second
3. Diff consecutive snapshots, log every changed dword with address+values
4. Aggregate across states to classify fields as:
   - STATIC: never changes (game code, assets)
   - VOLATILE: changes every second (physics, timers)
   - EVENT: changes at specific moments (race start/finish, collect, purchase)
   - DIFFERENTIAL: differs between save states (progression, ownership)

## Save States to Explore
1. s1 — free roam baseline
2. s2 — event prompt
3. s3 — race start trigger
4. s4 — race finish 1st
5. s5 — post-vanessa progression
6. s6 — post-everything
7. s10 — post-race
8. s12 — garage
9. s13 — s6+collectible
10. s14 — s13+lexus+tournament

## Output
- `dumps/{state}/snap_N.json` — each snapshot
- `diffs/{state}/changes.json` — aggregated changes
- `report.json` — final classified field list

## Duration
~10 snapshots per state, ~2 hours total
