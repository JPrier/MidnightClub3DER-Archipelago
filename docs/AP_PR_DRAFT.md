# Draft PR — Add "Midnight Club 3: DUB Edition Remix" to Archipelago

Materials for opening a **draft** pull request against
[ArchipelagoMW/Archipelago](https://github.com/ArchipelagoMW/Archipelago).
Not yet opened — opening it publishes to a third-party repo and needs a
maintainer-ready validation pass on an Archipelago checkout (below).

## Pre-flight checklist (do before opening the PR)

- [ ] Fork ArchipelagoMW/Archipelago, clone your fork.
- [ ] Copy this repo's `worlds/mc3/` into `Archipelago/worlds/mc3/`.
- [ ] From the Archipelago root, confirm the world imports and a seed generates:
      ```bash
      python -m pytest worlds/mc3/test -q
      python Generate.py --weights_file_path <a weights yaml selecting MC3>
      ```
      (These need Archipelago's own deps — `BaseClasses`, etc. — which live in
      that repo, not here.)
- [ ] `python ModuleUpdate.py` / lint per Archipelago's contributor guide.
- [ ] Ensure `worlds/mc3/docs/setup_en.md` renders on the webhost.
- [ ] Fill any remaining catalog gaps (curated events/vehicles) or ship the
      starter catalog and mark options accordingly.

## Suggested PR title

`New game: Midnight Club 3: DUB Edition Remix`

## Suggested PR body

> ### What is this
> Adds an Archipelago world for *Midnight Club 3: DUB Edition Remix* (PS2,
> NTSC-U, SLUS-21355), played on stock PCSX2 with an external Python client.
>
> ### How it works
> - **No emulator fork, no ISO distribution.** A small `.pnach` installs a
>   memory mailbox; the client reads/writes EE RAM to detect checks and apply
>   items.
> - **Checks:** race wins, tournament wins, collectible pickups — detected via
>   the game's career stats registry (documented in the client repo).
> - **Items:** money today; vehicles/parts/city/ability gating as enforcement
>   hooks land.
>
> ### Client
> Client + payload + setup guide:
> https://github.com/JPrier/MidnightClub3DER-Archipelago
>
> ### Testing
> - World unit tests under `worlds/mc3/test`.
> - Client has 73 automated tests (protocol, check-detection, live-emulator).
>
> Marking as **draft** while the curated catalog and gating hooks are finalized.

## Notes for reviewers

- The world currently ships a **starter catalog** (verified static facts) with
  a `catalog_mode` option to switch to curated/generated catalogs.
- Location/item IDs are namespaced from `7160000` (items) / `7161000`
  (locations).
