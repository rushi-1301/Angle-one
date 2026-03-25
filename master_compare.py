# master_compare.py
# ═══════════════════════════════════════════════════════════════════
# MASTER-LEVEL COMPARISON: Reference vs Dashboard Backtest Engines
# ═══════════════════════════════════════════════════════════════════
# Compares outputs of:
#   1. Bro_gaurd_SILVERMINI.py        (REFERENCE)
#   2. utils/backtest.py              (PROJECT engine A)
#   3. backtest_runner/backtest_engine.py  (PROJECT engine B)
# All run on the EXACT same data with the SAME parameters.

import sys, os

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
if sys.stdout.encoding and sys.stdout.encoding.lower() != "utf-8":
    sys.stdout.reconfigure(encoding="utf-8")

import pandas as pd
import numpy as np
import importlib.util
from datetime import datetime

# ═══════════════════════════════════════════════════════════════════
# 0) LOAD TEST DATA
# ═══════════════════════════════════════════════════════════════════
CSV_PATH = os.path.join("utils", "test", "SILVERM_2year_15_MIN.csv")
if not os.path.exists(CSV_PATH):
    CSV_PATH = os.path.join("media", "uploads", "SILVERM_15M_max.csv")

if not os.path.exists(CSV_PATH):
    print("❌ No test data CSV found!")
    sys.exit(1)

print("=" * 70)
print("  MASTER COMPARISON — Reference vs Dashboard Backtest Engines")
print("=" * 70)
print(f"\n📂 Data: {CSV_PATH}")
raw_df = pd.read_csv(CSV_PATH)
print(f"   Rows: {len(raw_df):,}  |  Columns: {raw_df.columns.tolist()}")

STARTING_CASH = 2_500_000

# ═══════════════════════════════════════════════════════════════════
# 1) REFERENCE ENGINE — Bro_gaurd_SILVERMINI.py
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("🔵 ENGINE 1: Bro_gaurd_SILVERMINI.py (REFERENCE)")
print("=" * 70)

spec = importlib.util.spec_from_file_location(
    "bro_ref", os.path.join(os.path.dirname(__file__), "Bro_gaurd_SILVERMINI.py")
)
bro_ref = importlib.util.module_from_spec(spec)
bro_ref.DATA_FILE = CSV_PATH
spec.loader.exec_module(bro_ref)

ref_df = bro_ref.load_data(CSV_PATH)
ref_events, ref_trades, ref_stats = bro_ref.backtest(ref_df, bro_ref.STARTING_CASH)

print(f"\n📊 Reference Results:")
print(f"   Trades closed : {len(ref_trades)}")
print(f"   Events logged : {len(ref_events)}")
print(f"   Wins          : {ref_stats['wins']}")
print(f"   Losses        : {ref_stats['losses']}")
print(f"   Net P&L       : ₹{ref_stats['realized_pnl_sum']:,.2f}")
print(f"   Ending Cash   : ₹{ref_stats['ending_cash']:,.2f}")

# ═══════════════════════════════════════════════════════════════════
# 2) PROJECT ENGINE A — utils/backtest.py
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("🟢 ENGINE 2: utils/backtest.py (PROJECT)")
print("=" * 70)

from utils.backtest import backtest as project_backtest

proj_events, proj_trades, proj_stats = project_backtest(
    raw_df.copy(),
    strategy=None,  # uses DEFAULTS which match reference
    starting_cash=STARTING_CASH,
)

print(f"\n📊 Project Results:")
print(f"   Trades closed : {len(proj_trades)}")
print(f"   Events logged : {len(proj_events)}")
print(f"   Wins          : {proj_stats['wins']}")
print(f"   Losses        : {proj_stats['losses']}")
print(f"   Net P&L       : ₹{proj_stats['realized_pnl_sum']:,.2f}")
print(f"   Ending Cash   : ₹{proj_stats['ending_cash']:,.2f}")

# ═══════════════════════════════════════════════════════════════════
# 3) RUNNER ENGINE B — backtest_runner/backtest_engine.py
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("🟠 ENGINE 3: backtest_runner/backtest_engine.py (RUNNER)")
print("=" * 70)

runner_engine_ok = True
runner_stats = None
runner_events = None
runner_trades = None

try:
    spec_runner = importlib.util.spec_from_file_location(
        "runner_engine",
        os.path.join(os.path.dirname(__file__), "backtest_runner", "backtest_engine.py"),
    )
    runner_mod = importlib.util.module_from_spec(spec_runner)
    spec_runner.loader.exec_module(runner_mod)

    # Build a mock strategy object with same params as reference
    class MockStrategy:
        ema_short = 27
        ema_long = 78
        fixed_sl_pct = 0.015
        trail_sl_pct = 0.025
        breakout_buffer = 0.0012
        point_value = 5
        margin_factor = 0.15

    # Prepare data: runner engine expects 'datetime' column already parsed
    runner_df = raw_df.copy()
    # Rename commonly used time columns to datetime
    rename_map = {"timestamp": "datetime", "Timestamp": "datetime"}
    runner_df.rename(columns=rename_map, inplace=True)
    
    # Try to parse datetime
    if "datetime" in runner_df.columns:
        runner_df["datetime"] = pd.to_datetime(runner_df["datetime"], errors="coerce")
    elif "date" in runner_df.columns and "time" in runner_df.columns:
        runner_df["datetime"] = pd.to_datetime(
            runner_df["date"].astype(str) + " " + runner_df["time"].astype(str),
            errors="coerce",
        )

    for col in ["open", "high", "low", "close"]:
        if col in runner_df.columns:
            runner_df[col] = pd.to_numeric(runner_df[col], errors="coerce")
        elif col.title() in runner_df.columns:
            runner_df[col] = pd.to_numeric(runner_df[col.title()], errors="coerce")

    runner_df = runner_df.dropna(subset=["datetime", "open", "high", "low", "close"])
    runner_df = runner_df.sort_values("datetime").reset_index(drop=True)

    runner_events, runner_trades, runner_stats = runner_mod.backtest(
        runner_df, MockStrategy(), STARTING_CASH
    )

    print(f"\n📊 Runner Results:")
    print(f"   Trades closed : {len(runner_trades)}")
    print(f"   Events logged : {len(runner_events)}")
    print(f"   Wins          : {runner_stats['wins']}")
    print(f"   Losses        : {runner_stats['losses']}")
    print(f"   Net P&L       : ₹{runner_stats['realized_pnl_sum']:,.2f}")
    print(f"   Ending Cash   : ₹{runner_stats['ending_cash']:,.2f}")

except Exception as e:
    print(f"\n❌ Runner engine failed to execute: {e}")
    runner_engine_ok = False

# ═══════════════════════════════════════════════════════════════════
# 4) COMPARISON TABLE
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("🔍 SIDE-BY-SIDE COMPARISON")
print("=" * 70)

total_checks = 0
total_pass = 0
issues = []


def compare(label, ref_val, proj_val, runner_val=None, tolerance_pct=0.01):
    global total_checks, total_pass

    row = f"   {'  ' + label:<30}"

    # Reference vs Project
    total_checks += 1
    if isinstance(ref_val, (int, np.integer)):
        proj_ok = ref_val == proj_val
    elif isinstance(ref_val, float):
        pct = (abs(ref_val - proj_val) / abs(ref_val) * 100) if ref_val != 0 else 0
        proj_ok = pct <= tolerance_pct
    else:
        proj_ok = str(ref_val) == str(proj_val)

    if proj_ok:
        total_pass += 1

    proj_icon = "✅" if proj_ok else "❌"

    # Format values
    def fmt(v):
        if isinstance(v, float):
            return f"₹{v:,.2f}" if abs(v) > 100 else f"{v:.4f}"
        return str(v)

    row += f" | REF: {fmt(ref_val):>18}"
    row += f" | PROJ: {proj_icon} {fmt(proj_val):>18}"

    # Reference vs Runner
    if runner_val is not None:
        total_checks_local = 1
        if isinstance(ref_val, (int, np.integer)):
            run_ok = ref_val == runner_val
        elif isinstance(ref_val, float):
            pct = (abs(ref_val - runner_val) / abs(ref_val) * 100) if ref_val != 0 else 0
            run_ok = pct <= tolerance_pct
        else:
            run_ok = str(ref_val) == str(runner_val)

        run_icon = "✅" if run_ok else "❌"
        row += f" | RUNNER: {run_icon} {fmt(runner_val):>18}"

        if not run_ok:
            issues.append(
                f"RUNNER {label}: expected {fmt(ref_val)}, got {fmt(runner_val)}"
            )
    elif not runner_engine_ok:
        row += f" | RUNNER: ⚠️ {'N/A':>18}"

    if not proj_ok:
        issues.append(f"PROJECT {label}: expected {fmt(ref_val)}, got {fmt(proj_val)}")

    print(row)


print(f"\n   {'METRIC':<30} | {'REFERENCE':>22} | {'PROJECT':>24} | {'RUNNER':>24}")
print("   " + "-" * 110)

compare(
    "Trade Count",
    len(ref_trades),
    len(proj_trades),
    len(runner_trades) if runner_engine_ok else None,
)
compare(
    "Event Count",
    len(ref_events),
    len(proj_events),
    len(runner_events) if runner_engine_ok else None,
)
compare(
    "Wins",
    ref_stats["wins"],
    proj_stats["wins"],
    runner_stats["wins"] if runner_engine_ok else None,
)
compare(
    "Losses",
    ref_stats["losses"],
    proj_stats["losses"],
    runner_stats["losses"] if runner_engine_ok else None,
)
compare(
    "Net P&L",
    float(ref_stats["realized_pnl_sum"]),
    float(proj_stats["realized_pnl_sum"]),
    float(runner_stats["realized_pnl_sum"]) if runner_engine_ok else None,
)
compare(
    "Ending Cash",
    float(ref_stats["ending_cash"]),
    float(proj_stats["ending_cash"]),
    float(runner_stats["ending_cash"]) if runner_engine_ok else None,
)

# Win rate
ref_total = ref_stats["wins"] + ref_stats["losses"]
ref_wr = (ref_stats["wins"] / ref_total * 100) if ref_total > 0 else 0
proj_total = proj_stats["wins"] + proj_stats["losses"]
proj_wr = (proj_stats["wins"] / proj_total * 100) if proj_total > 0 else 0
if runner_engine_ok:
    run_total = runner_stats["wins"] + runner_stats["losses"]
    run_wr = (runner_stats["wins"] / run_total * 100) if run_total > 0 else 0
else:
    run_wr = None

compare("Win Rate %", ref_wr, proj_wr, run_wr, tolerance_pct=0.1)

# ═══════════════════════════════════════════════════════════════════
# 5) TRADE-BY-TRADE DEEP COMPARISON (Ref vs Project)
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📋 TRADE-BY-TRADE: Reference vs Project (utils/backtest.py)")
print("=" * 70)

if len(ref_trades) == len(proj_trades) and len(ref_trades) > 0:
    mismatches = 0
    first_mismatch = None

    for i in range(len(ref_trades)):
        r = ref_trades.iloc[i]
        p = proj_trades.iloc[i]
        r_pnl = float(r["realized_pnl"])
        p_pnl = float(p["realized_pnl"])
        diff = abs(r_pnl - p_pnl)

        if diff > 0.01:
            mismatches += 1
            if first_mismatch is None:
                first_mismatch = i

    if mismatches == 0:
        print(f"\n   ✅ ALL {len(ref_trades)} trades match perfectly!")
    else:
        print(f"\n   ❌ {mismatches} / {len(ref_trades)} trades have P&L mismatches")
        print(f"\n   First 10 mismatches:")
        shown = 0
        for i in range(len(ref_trades)):
            r = ref_trades.iloc[i]
            p = proj_trades.iloc[i]
            r_pnl = float(r["realized_pnl"])
            p_pnl = float(p["realized_pnl"])
            diff = abs(r_pnl - p_pnl)
            if diff > 0.01:
                print(
                    f"      T{i+1}: REF=₹{r_pnl:,.2f}  PROJ=₹{p_pnl:,.2f}  "
                    f"diff=₹{diff:.2f}  dir={r['direction']}  @ {r['time']}"
                )
                shown += 1
                if shown >= 10:
                    break

    # Show first and last few trades
    print(f"\n   📋 Sample trades (first 5):")
    for i in range(min(5, len(ref_trades))):
        r = ref_trades.iloc[i]
        p = proj_trades.iloc[i]
        status = "✅" if abs(float(r["realized_pnl"]) - float(p["realized_pnl"])) < 0.01 else "❌"
        print(
            f"      {status} T{i+1}: ref_pnl=₹{float(r['realized_pnl']):,.2f} "
            f"proj_pnl=₹{float(p['realized_pnl']):,.2f} | {r['direction']:>5} | {r['time']}"
        )

    if len(ref_trades) > 5:
        print(f"\n   📋 Sample trades (last 5):")
        for i in range(max(0, len(ref_trades) - 5), len(ref_trades)):
            r = ref_trades.iloc[i]
            p = proj_trades.iloc[i]
            status = "✅" if abs(float(r["realized_pnl"]) - float(p["realized_pnl"])) < 0.01 else "❌"
            print(
                f"      {status} T{i+1}: ref_pnl=₹{float(r['realized_pnl']):,.2f} "
                f"proj_pnl=₹{float(p['realized_pnl']):,.2f} | {r['direction']:>5} | {r['time']}"
            )

elif len(ref_trades) != len(proj_trades):
    print(f"\n   ❌ TRADE COUNT MISMATCH: REF={len(ref_trades)} vs PROJ={len(proj_trades)}")

    # Find divergence in events
    ref_entries = ref_events[ref_events["event"] == "ENTRY"].reset_index(drop=True)
    proj_entries = proj_events[proj_events["event"] == "ENTRY"].reset_index(drop=True)

    min_len = min(len(ref_entries), len(proj_entries))
    diverged = False
    for i in range(min_len):
        r = ref_entries.iloc[i]
        p = proj_entries.iloc[i]
        if r["bar_index"] != p["bar_index"] or r["direction"] != p["direction"]:
            print(f"\n   ❌ First divergence at entry #{i+1}:")
            print(f"      REF  : bar={r['bar_index']} dir={r['direction']} price={r['price']} @ {r['time']}")
            print(f"      PROJ : bar={p['bar_index']} dir={p['direction']} price={p['price']} @ {p['time']}")
            diverged = True
            break

    if not diverged:
        extra_side = "REF" if len(ref_entries) > len(proj_entries) else "PROJ"
        print(f"\n   ℹ️ All {min_len} shared entries match. {extra_side} has extra entries.")

# ═══════════════════════════════════════════════════════════════════
# 6) TRADE-BY-TRADE DEEP COMPARISON (Ref vs Runner)
# ═══════════════════════════════════════════════════════════════════
if runner_engine_ok:
    print("\n" + "=" * 70)
    print("📋 TRADE-BY-TRADE: Reference vs Runner (backtest_engine.py)")
    print("=" * 70)

    if len(ref_trades) == len(runner_trades) and len(ref_trades) > 0:
        mismatches = 0
        for i in range(len(ref_trades)):
            r = ref_trades.iloc[i]
            rn = runner_trades.iloc[i]
            r_pnl = float(r["realized_pnl"])
            rn_pnl = float(rn.get("net_pnl", rn.get("realized_pnl", 0)))
            diff = abs(r_pnl - rn_pnl)
            if diff > 0.01:
                mismatches += 1

        if mismatches == 0:
            print(f"\n   ✅ ALL {len(ref_trades)} trades match perfectly!")
        else:
            print(f"\n   ❌ {mismatches} / {len(ref_trades)} trades have P&L mismatches")
            print(f"\n   First 10 mismatches:")
            shown = 0
            for i in range(len(ref_trades)):
                r = ref_trades.iloc[i]
                rn = runner_trades.iloc[i]
                r_pnl = float(r["realized_pnl"])
                rn_pnl = float(rn.get("net_pnl", rn.get("realized_pnl", 0)))
                diff = abs(r_pnl - rn_pnl)
                if diff > 0.01:
                    print(
                        f"      T{i+1}: REF=₹{r_pnl:,.2f}  RUNNER=₹{rn_pnl:,.2f}  "
                        f"diff=₹{diff:.2f}  dir={r['direction']}  @ {r['time']}"
                    )
                    shown += 1
                    if shown >= 10:
                        break

    elif len(ref_trades) != len(runner_trades):
        print(f"\n   ❌ TRADE COUNT MISMATCH: REF={len(ref_trades)} vs RUNNER={len(runner_trades)}")
        print(f"\n   🔬 ROOT CAUSE ANALYSIS:")
        print(f"      The runner engine (backtest_engine.py) differs from the reference in:")
        print(f"      1. C3 ENTRY: Missing 'h2 > h1' check for LONG and 'l2 < l1' check for SHORT")
        print(f"         → This generates EXTRA entries that don't meet full breakout criteria")
        print(f"      2. STOP-LOSS: Uses close price instead of candle low/high")
        print(f"         → Stops trigger at different bars")
        print(f"      3. EMA REVERSAL: Exits immediately on EMA flip without C3 confirmation")
        print(f"         → Exits happen earlier than reference")
        print(f"      4. MONTH-END: No forced close at month end")
        print(f"         → Positions carry over month boundaries")
        print(f"      5. LOT MANAGEMENT: Simple cash//margin instead of dynamic sizing")
        print(f"         → Different position sizes on each trade")

        # Try to find first divergence
        ref_entries = ref_events[ref_events["event"] == "ENTRY"].reset_index(drop=True)

        # Runner events have different column structure
        runner_entries = runner_events[runner_events["event"] == "ENTRY"].reset_index(drop=True)

        min_len = min(len(ref_entries), len(runner_entries))
        if min_len > 0:
            print(f"\n   📋 First 5 entries comparison:")
            for i in range(min(5, min_len)):
                r = ref_entries.iloc[i]
                rn = runner_entries.iloc[i]
                r_time = str(r["time"])[:19]
                rn_time = str(rn["time"])[:19]
                match = "✅" if r_time == rn_time and r["direction"] == rn["direction"] else "❌"
                print(
                    f"      {match} #{i+1}: REF [{r['direction']:>5} @ {r_time} bar={r.get('bar_index','')}] "
                    f"vs RUNNER [{rn['direction']:>5} @ {rn_time}]"
                )

# ═══════════════════════════════════════════════════════════════════
# 7) ENTRY CONDITION DEEP DIVE
# ═══════════════════════════════════════════════════════════════════
if runner_engine_ok and len(ref_trades) != len(runner_trades):
    print("\n" + "=" * 70)
    print("🔬 ENTRY CONDITION DEEP DIVE")
    print("=" * 70)

    # Find entries that exist in runner but NOT in reference
    ref_entry_times = set(ref_events[ref_events["event"] == "ENTRY"]["time"].astype(str).tolist())
    runner_entry_times = set(runner_events[runner_events["event"] == "ENTRY"]["time"].astype(str).tolist())

    extra_in_runner = runner_entry_times - ref_entry_times
    extra_in_ref = ref_entry_times - runner_entry_times

    if extra_in_runner:
        print(f"\n   ⚠️ {len(extra_in_runner)} entries exist in RUNNER but NOT in REFERENCE:")
        for t in sorted(list(extra_in_runner))[:10]:
            rn_entry = runner_events[
                (runner_events["event"] == "ENTRY") &
                (runner_events["time"].astype(str) == t)
            ].iloc[0]
            print(f"      → {rn_entry['direction']} @ {t} reason={rn_entry['reason']}")

    if extra_in_ref:
        print(f"\n   ⚠️ {len(extra_in_ref)} entries exist in REFERENCE but NOT in RUNNER:")
        for t in sorted(list(extra_in_ref))[:10]:
            r_entry = ref_events[
                (ref_events["event"] == "ENTRY") &
                (ref_events["time"].astype(str) == t)
            ].iloc[0]
            print(f"      → {r_entry['direction']} @ {t} reason={r_entry['reason']}")

# ═══════════════════════════════════════════════════════════════════
# 8) EXIT REASON BREAKDOWN
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("📊 EXIT REASON BREAKDOWN")
print("=" * 70)

ref_exit_reasons = ref_events[ref_events["event"] == "EXIT"]["reason"].value_counts()
proj_exit_reasons = proj_events[proj_events["event"] == "EXIT"]["reason"].value_counts()

all_reasons = sorted(set(list(ref_exit_reasons.index) + list(proj_exit_reasons.index)))
if runner_engine_ok:
    runner_exit_reasons = runner_events[runner_events["event"] == "EXIT"]["reason"].value_counts()
    all_reasons = sorted(set(list(all_reasons) + list(runner_exit_reasons.index)))

print(f"\n   {'REASON':<20} | {'REF':>6} | {'PROJ':>6}", end="")
if runner_engine_ok:
    print(f" | {'RUNNER':>6}", end="")
print()
print("   " + "-" * 55)

for reason in all_reasons:
    r = ref_exit_reasons.get(reason, 0)
    p = proj_exit_reasons.get(reason, 0)
    match_rp = "✅" if r == p else "❌"
    print(f"   {reason:<20} | {r:>6} | {match_rp}{p:>5}", end="")
    if runner_engine_ok:
        rn = runner_exit_reasons.get(reason, 0)
        match_rr = "✅" if r == rn else "❌"
        print(f" | {match_rr}{rn:>5}", end="")
    print()

# ═══════════════════════════════════════════════════════════════════
# 9) FINAL VERDICT
# ═══════════════════════════════════════════════════════════════════
print("\n" + "=" * 70)
print("🏁 FINAL VERDICT")
print("=" * 70)

# Check REF vs PROJECT
ref_proj_match = (
    len(ref_trades) == len(proj_trades)
    and ref_stats["wins"] == proj_stats["wins"]
    and ref_stats["losses"] == proj_stats["losses"]
    and abs(float(ref_stats["realized_pnl_sum"]) - float(proj_stats["realized_pnl_sum"])) < 1.0
)

if ref_proj_match:
    print("\n   ✅ REFERENCE vs utils/backtest.py     → IDENTICAL ✓")
    # Additional deep check: every trade P&L
    all_pnl_match = True
    if len(ref_trades) == len(proj_trades):
        for i in range(len(ref_trades)):
            if abs(float(ref_trades.iloc[i]["realized_pnl"]) - float(proj_trades.iloc[i]["realized_pnl"])) > 0.01:
                all_pnl_match = False
                break
    if all_pnl_match:
        print("      Every single trade P&L matches within ₹0.01 tolerance.")
    else:
        print("      ⚠️ Summary stats match, but some individual trade P&Ls differ slightly.")
else:
    print("\n   ❌ REFERENCE vs utils/backtest.py     → DIFFERENT")
    if issues:
        for iss in issues:
            if iss.startswith("PROJECT"):
                print(f"      • {iss}")

if runner_engine_ok:
    ref_runner_match = (
        len(ref_trades) == len(runner_trades)
        and ref_stats["wins"] == runner_stats["wins"]
        and ref_stats["losses"] == runner_stats["losses"]
        and abs(float(ref_stats["realized_pnl_sum"]) - float(runner_stats["realized_pnl_sum"])) < 1.0
    )

    if ref_runner_match:
        print("\n   ✅ REFERENCE vs backtest_engine.py    → IDENTICAL ✓")
    else:
        print("\n   ❌ REFERENCE vs backtest_engine.py    → DIFFERENT")
        print("      ROOT CAUSES:")
        print("      1. Missing C3 condition: h2>h1 (LONG) / l2<l1 (SHORT)")
        print("      2. Stop-loss uses close price, not candle low/high")
        print("      3. EMA reversal exit has no C3 confirmation")
        print("      4. No month-end forced close")
        print("      5. No dynamic lot management (win/loss streaks)")
else:
    print("\n   ⚠️ REFERENCE vs backtest_engine.py    → COULD NOT TEST")

print("\n" + "=" * 70)
print("  COMPARISON COMPLETE")
print("=" * 70)
