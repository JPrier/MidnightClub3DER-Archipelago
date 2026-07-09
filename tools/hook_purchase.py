"""Dealer purchase hooks: purchase DETECT + Vehicle-Permit DENY gate.

Two JAL call-site trampolines in the shop handler (fn 0x00337610), mapped
statically (see docs/PURCHASE_FLOW_STATIC_ANALYSIS.md):

  DETECT  0x00337A7C  jal SpendMoney(0x00337378)      — non-mutating
      Appends (recptr, amount, wallet_before, ordinal) to a mailbox ring,
      then tail-calls the real SpendMoney. recptr+0xDF is the vehicle name
      c-string; amount = wallet - newTotal.

  DENY    0x003378BC  jal UISet(0x00320848)  a2=oktobuy — enforcing
      The delay slot sets a2=1 (ok-to-buy). Trampoline is gated by an enforce
      flag byte (default 0 = pure forward, vanilla-identical). When enforcing,
      it resolves the selected vehicle's catalog index via 0x004AF870, reads
      permit_table[index]; if 0 it flips a2 to 0 (oktobuy=0, cancel) and clears
      the purchase-pending flag 0x006179BD, then tail-calls the real UISet.

Mailbox layout (EE, base 0x00720000) — free regions only:
  0x007205FC  u8   enforce flag (0 = off / safe)
  0x00720600  96 x u8   permit table, one byte per catalog index (1=allow)
  0x00720920  detect trampoline
  0x00720A00  deny trampoline
  0x00720B00  u32 count | u32 head | ... | records[16] x 16B (recptr,amt,wallet,ord)

Usage:
  python tools/hook_purchase.py install-detect     # safe, non-mutating
  python tools/hook_purchase.py install-deny        # safe (enforce off by default)
  python tools/hook_purchase.py status
  python tools/hook_purchase.py permit allow-all | deny-all
  python tools/hook_purchase.py permit set <index> <0|1>
  python tools/hook_purchase.py enforce <0|1>
  python tools/hook_purchase.py restore-detect
  python tools/hook_purchase.py restore-deny
"""

from __future__ import annotations

import struct
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO))
sys.path.insert(0, str(REPO / "tools"))

from mips_assembler import MIPSAssembler, R  # noqa: E402
from mc3api.purchase_hook import (  # noqa: E402
    DENY_SITE, DENY_TRAMP, DETECT_SITE, DETECT_TRAMP, ENFORCE_FLAG,
    PERMIT_SIZE, PERMIT_TABLE, REC_COUNT, REC_SIZE, RING_BASE, RING_RECS,
    encode_jal,
)

# ── Game call sites (verified original instructions) ────────────────────────
DETECT_ORIG = 0x0C0CDCDE          # jal 0x00337378 (SpendMoney)
SPEND_MONEY = 0x00337378

DENY_ORIG = 0x0C0C8212            # jal 0x00320848 (UISet int)
UI_SET = 0x00320848

CARCFG_INDEX_FN = 0x004AF870      # (carCfg) -> catalog index (leaf lookup)
PENDING_FLAG = 0x006179BD         # u8, purchase-pending
WALLET = 0x00800870

# ctx (shopCtx) field offsets
CTX_RECPTRS = 0x071C              # base of per-showroom record pointer array
CTX_SELECTED = 0x072C             # u32 selected index into that array


# ── Trampoline builders ─────────────────────────────────────────────────────

def build_detect_tramp() -> bytes:
    """Log the purchase, then tail-call SpendMoney. Uses only temp regs, so
    a0/a1/ra reach SpendMoney untouched (a0=ctx set by the site's delay slot,
    a1=newTotal, ra=0x00337A80)."""
    a = MIPSAssembler(base=DETECT_TRAMP)
    # wallet_before (t1) and amount (t2 = wallet - a1)
    a.lui(R.T0, (WALLET >> 16) & 0xFFFF)
    a.lw(R.T1, R.T0, WALLET & 0xFFFF)          # t1 = wallet
    a.subu(R.T2, R.T1, R.A1)                    # t2 = wallet - newTotal
    # recptr = [ctx + 0x71C + sel*4]
    a.lw(R.T3, R.A0, CTX_SELECTED)              # t3 = selected
    a.sll(R.T3, R.T3, 2)
    a.addu(R.T4, R.A0, R.T3)
    a.lw(R.T4, R.T4, CTX_RECPTRS)               # t4 = recptr (name at +0xDF)
    # ring append at 0x00720B00
    a.lui(R.T0, 0x0072)
    a.lw(R.T5, R.T0, RING_BASE & 0xFFFF)        # count
    a.addiu(R.T5, R.T5, 1)
    a.sw(R.T5, R.T0, RING_BASE & 0xFFFF)
    a.lw(R.T6, R.T0, (RING_BASE + 4) & 0xFFFF)  # head
    a.addiu(R.T6, R.T6, 1)
    a.andi(R.T6, R.T6, REC_COUNT - 1)
    a.sw(R.T6, R.T0, (RING_BASE + 4) & 0xFFFF)
    a.sll(R.T7, R.T6, 4)                        # head * 16
    a.addu(R.T7, R.T7, R.T0)
    a.sw(R.T4, R.T7, RING_RECS & 0xFFFF)        # +0 recptr
    a.sw(R.T2, R.T7, (RING_RECS + 4) & 0xFFFF)  # +4 amount
    a.sw(R.T1, R.T7, (RING_RECS + 8) & 0xFFFF)  # +8 wallet_before
    a.sw(R.T5, R.T7, (RING_RECS + 12) & 0xFFFF)  # +12 ordinal
    # tail-call SpendMoney (a0/a1/ra untouched)
    a.lui(R.T9, (SPEND_MONEY >> 16) & 0xFFFF)
    a.ori(R.T9, R.T9, SPEND_MONEY & 0xFFFF)
    a.jr(R.T9)
    a.nop()
    return a.link()


def build_deny_tramp() -> bytes:
    """Gated oktobuy override. enforce=0 -> pure forward. enforce=1 -> resolve
    selected vehicle index, deny if permit byte is 0."""
    a = MIPSAssembler(base=DENY_TRAMP)
    # enforce flag
    a.lui(R.T0, 0x0072)
    a.lb(R.T1, R.T0, ENFORCE_FLAG & 0xFFFF)
    a.beq(R.T1, R.ZERO, "forward")             # not enforcing -> forward (a2=1)
    a.nop()
    # enforcing: save args + ra across the game-fn call
    a.addiu(R.SP, R.SP, -32)
    a.sw(R.RA, R.SP, 0)
    a.sw(R.A0, R.SP, 4)
    a.sw(R.A1, R.SP, 8)
    a.sw(R.A2, R.SP, 12)
    # recptr = [s3 + 0x71C + sel*4]   (s3 = shopCtx, preserved by caller)
    a.lw(R.T0, R.S3, CTX_SELECTED)
    a.sll(R.T0, R.T0, 2)
    a.addu(R.T1, R.S3, R.T0)
    a.lw(R.A0, R.T1, CTX_RECPTRS)               # a0 = recptr (arg for index fn)
    a.lui(R.T9, (CARCFG_INDEX_FN >> 16) & 0xFFFF)
    a.ori(R.T9, R.T9, CARCFG_INDEX_FN & 0xFFFF)
    a.jalr(R.T9)                                # v0 = catalog index
    a.nop()
    # permit[index]
    a.lui(R.T0, 0x0072)
    a.addu(R.T0, R.T0, R.V0)
    a.lb(R.T1, R.T0, PERMIT_TABLE & 0xFFFF)     # permit byte
    # restore args
    a.lw(R.A0, R.SP, 4)
    a.lw(R.A1, R.SP, 8)
    a.lw(R.A2, R.SP, 12)
    a.lw(R.RA, R.SP, 0)
    a.addiu(R.SP, R.SP, 32)
    a.bne(R.T1, R.ZERO, "forward")             # permitted -> forward (a2=1)
    a.nop()
    # deny: oktobuy = 0, clear pending flag
    a.addiu(R.A2, R.ZERO, 0)
    a.lui(R.T2, (PENDING_FLAG >> 16) & 0xFFFF)
    a.sb(R.ZERO, R.T2, PENDING_FLAG & 0xFFFF)
    a.lbl("forward")
    a.lui(R.T9, (UI_SET >> 16) & 0xFFFF)
    a.ori(R.T9, R.T9, UI_SET & 0xFFFF)
    a.jr(R.T9)                                  # tail-call UISet (ra intact)
    a.nop()
    return a.link()


# ── Bridge helpers ──────────────────────────────────────────────────────────

def connect():
    from mc3api import MC3Game
    return MC3Game.connect(timeout=20)


def _zero_mailbox_regions(game):
    game.write(ENFORCE_FLAG, b"\x00")
    game.write(PERMIT_TABLE, b"\x01" * PERMIT_SIZE)   # default allow-all
    game.write(RING_BASE, b"\x00" * (0x10 + REC_COUNT * REC_SIZE))


# ── Commands ────────────────────────────────────────────────────────────────

def cmd_install_detect():
    game = connect()
    cur = game.read_u32(DETECT_SITE)
    if cur == encode_jal(DETECT_TRAMP):
        print("detect: already installed")
        return game.close()
    if cur != DETECT_ORIG:
        print(f"[ABORT] detect site 0x{DETECT_SITE:08X} = 0x{cur:08X}, "
              f"expected 0x{DETECT_ORIG:08X}")
        return game.close()
    code = build_detect_tramp()
    game.write(DETECT_TRAMP, code)
    _zero_mailbox_regions(game)
    game.write_u32(DETECT_SITE, encode_jal(DETECT_TRAMP))
    back = game.read_u32(DETECT_SITE)
    ok = back == encode_jal(DETECT_TRAMP)
    print(f"detect: {len(code)}B @0x{DETECT_TRAMP:08X}; JAL@0x{DETECT_SITE:08X} "
          f"-> 0x{DETECT_TRAMP:08X} {'OK' if ok else 'VERIFY-FAILED'}")
    game.close()


def cmd_install_deny():
    game = connect()
    cur = game.read_u32(DENY_SITE)
    if cur == encode_jal(DENY_TRAMP):
        print("deny: already installed")
        return game.close()
    if cur != DENY_ORIG:
        print(f"[ABORT] deny site 0x{DENY_SITE:08X} = 0x{cur:08X}, "
              f"expected 0x{DENY_ORIG:08X}")
        return game.close()
    # ensure enforce is OFF and permits allow-all before arming the site
    game.write(ENFORCE_FLAG, b"\x00")
    game.write(PERMIT_TABLE, b"\x01" * PERMIT_SIZE)
    code = build_deny_tramp()
    game.write(DENY_TRAMP, code)
    game.write_u32(DENY_SITE, encode_jal(DENY_TRAMP))
    back = game.read_u32(DENY_SITE)
    ok = back == encode_jal(DENY_TRAMP)
    print(f"deny: {len(code)}B @0x{DENY_TRAMP:08X}; JAL@0x{DENY_SITE:08X} "
          f"-> 0x{DENY_TRAMP:08X} {'OK' if ok else 'VERIFY-FAILED'} "
          f"(enforce=OFF, permits=allow-all — vanilla-identical)")
    game.close()


def cmd_restore_detect():
    game = connect()
    cur = game.read_u32(DETECT_SITE)
    if cur != encode_jal(DETECT_TRAMP):
        print(f"[skip] detect site not ours: 0x{cur:08X}")
        return game.close()
    game.write_u32(DETECT_SITE, DETECT_ORIG)
    print(f"detect: restored 0x{DETECT_SITE:08X} -> jal SpendMoney")
    game.close()


def cmd_restore_deny():
    game = connect()
    cur = game.read_u32(DENY_SITE)
    if cur != encode_jal(DENY_TRAMP):
        print(f"[skip] deny site not ours: 0x{cur:08X}")
        return game.close()
    game.write_u32(DENY_SITE, DENY_ORIG)
    print(f"deny: restored 0x{DENY_SITE:08X} -> jal UISet")
    game.close()


def cmd_enforce(val: str):
    game = connect()
    b = 1 if val not in ("0", "off", "false") else 0
    game.write(ENFORCE_FLAG, bytes([b]))
    print(f"enforce = {b}")
    game.close()


def cmd_permit(args: list[str]):
    game = connect()
    if not args or args[0] == "allow-all":
        game.write(PERMIT_TABLE, b"\x01" * PERMIT_SIZE)
        print("permit: allow-all")
    elif args[0] == "deny-all":
        game.write(PERMIT_TABLE, b"\x00" * PERMIT_SIZE)
        print("permit: deny-all")
    elif args[0] == "set" and len(args) == 3:
        idx, v = int(args[1]), int(args[2])
        game.write(PERMIT_TABLE + idx, bytes([1 if v else 0]))
        print(f"permit[{idx}] = {1 if v else 0}")
    else:
        print("usage: permit [allow-all|deny-all|set <index> <0|1>]")
    game.close()


def cmd_status():
    game = connect()
    detect_on = game.read_u32(DETECT_SITE) == encode_jal(DETECT_TRAMP)
    deny_on = game.read_u32(DENY_SITE) == encode_jal(DENY_TRAMP)
    enforce = game.read(ENFORCE_FLAG, 1)[0]
    permits = game.read(PERMIT_TABLE, PERMIT_SIZE)
    denied = [i for i, b in enumerate(permits) if b == 0]
    print(f"detect hook: {'INSTALLED' if detect_on else 'off'}")
    print(f"deny hook:   {'INSTALLED' if deny_on else 'off'}   enforce={enforce}")
    print(f"permits: {PERMIT_SIZE - len(denied)}/{PERMIT_SIZE} allowed"
          + (f"; denied idx={denied}" if denied else ""))
    count = game.read_u32(RING_BASE)
    head = game.read_u32(RING_BASE + 4)
    print(f"purchase ring: count={count} head={head}")
    for i in range(REC_COUNT):
        rec = game.read(RING_RECS + i * REC_SIZE, REC_SIZE)
        recptr, amt, wallet, ordn = struct.unpack("<4I", rec)
        if not recptr:
            continue
        name = ""
        if 0x00100000 < recptr < 0x02000000:
            try:
                name = game.bridge.read_cstring(recptr + 0xDF, 32)
            except Exception:
                pass
        print(f"  [{i}] #{ordn} {name!r} amount=${amt} wallet_before=${wallet}")
    game.close()


def main():
    argv = sys.argv[1:]
    cmd = argv[0] if argv else "status"
    dispatch = {
        "install-detect": cmd_install_detect,
        "install-deny": cmd_install_deny,
        "restore-detect": cmd_restore_detect,
        "restore-deny": cmd_restore_deny,
        "status": cmd_status,
    }
    if cmd in dispatch:
        dispatch[cmd]()
    elif cmd == "enforce":
        cmd_enforce(argv[1] if len(argv) > 1 else "1")
    elif cmd == "permit":
        cmd_permit(argv[1:])
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
