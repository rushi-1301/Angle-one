# compare_outputs.py
# Runs BOTH the reference Bro_gaurd_SILVERMINI.py backtest engine AND
# the project's utils/backtest.py on the SAME data, then compares outputs.

import sys, os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

if sys.stdout.encoding.lower() != 'utf-8':
    sys.stdout.reconfigure(encoding='utf-8')

import pandas as pd
import numpy as np

# ═══════════════════════════════════════════════════════
# 1) Load common data
# ═══════════════════════════════════════════════════════
CSV_PATH = os.path.join("utils", "test", "SILVERM_2year_15_MIN.csv")
if not os.path.exists(CSV_PATH):
    # try media uploads
    CSV_PATH = os.path.join("media", "uploads", "SILVERM_15M_max.csv")

print(f"📂 Loading data from: {CSV_PATH}")
raw_df = pd.read_csv(CSV_PATH)
print(f"   Rows: {len(raw_df)}, Columns: {raw_df.columns.tolist()}")

# ═══════════════════════════════════════════════════════
# 2) Run REFERENCE backtest (Bro_gaurd_SILVERMINI.py)
# ═══════════════════════════════════════════════════════
print("\n" + "="*60)
print("🔵 REFERENCE: Bro_gaurd_SILVERMINI.py")
print("="*60)

# The reference has its own load_data that handles column names
# We need to import its functions. But it uses global constants,
# so we import it as a module.
import importlib.util
spec = importlib.util.spec_from_file_location(
    "bro_ref", os.path.join(os.path.dirname(__file__), "Bro_gaurd_SILVERMINI.py")
)
bro_ref = importlib.util.module_from_spec(spec)

# Patch DATA_FILE to use our CSV
bro_ref.DATA_FILE = CSV_PATH
spec.loader.exec_module(bro_ref)

# Run reference backtest
ref_df = bro_ref.load_data(CSV_PATH)
ref_events, ref_trades, ref_stats = bro_ref.backtest(ref_df, bro_ref.STARTING_CASH)

print(f"\n📊 Reference Results:")
print(f"   Total trades: {len(ref_trades)}")
print(f"   Wins: {ref_stats['wins']}")
print(f"   Losses: {ref_stats['losses']}")
print(f"   Net P&L: ₹{ref_stats['realized_pnl_sum']:,.2f}")
print(f"   Ending Cash: ₹{ref_stats['ending_cash']:,.2f}")

# ═══════════════════════════════════════════════════════
# 3) Run PROJECT backtest (utils/backtest.py)
# ═══════════════════════════════════════════════════════
print("\n" + "="*60)
print("🟢 PROJECT: utils/backtest.py")
print("="*60)

from utils.backtest import backtest as project_backtest

# Use same starting cash as reference
proj_events, proj_trades, proj_stats = project_backtest(
    raw_df.copy(),
    strategy=None,  # uses DEFAULTS which match reference
    starting_cash=2_500_000
)

print(f"\n📊 Project Results:")
print(f"   Total trades: {len(proj_trades)}")
print(f"   Wins: {proj_stats['wins']}")
print(f"   Losses: {proj_stats['losses']}")
print(f"   Net P&L: ₹{proj_stats['realized_pnl_sum']:,.2f}")
print(f"   Ending Cash: ₹{proj_stats['ending_cash']:,.2f}")

# ═══════════════════════════════════════════════════════
# 4) COMPARE
# ═══════════════════════════════════════════════════════
print("\n" + "="*60)
print("🔍 COMPARISON")
print("="*60)

matches = True

def compare(label, ref_val, proj_val, tolerance=0.01):
    global matches
    if isinstance(ref_val, (int, np.integer)):
        if ref_val != proj_val:
            print(f"   ❌ {label}: REF={ref_val} vs PROJ={proj_val}")
            matches = False
        else:
            print(f"   ✅ {label}: {ref_val}")
    elif isinstance(ref_val, float):
        diff = abs(ref_val - proj_val)
        pct_diff = (diff / abs(ref_val) * 100) if ref_val != 0 else 0
        if pct_diff > tolerance:
            print(f"   ❌ {label}: REF=₹{ref_val:,.2f} vs PROJ=₹{proj_val:,.2f} (diff={pct_diff:.4f}%)")
            matches = False
        else:
            print(f"   ✅ {label}: ₹{ref_val:,.2f} (diff={pct_diff:.6f}%)")
    else:
        if str(ref_val) != str(proj_val):
            print(f"   ❌ {label}: REF={ref_val} vs PROJ={proj_val}")
            matches = False
        else:
            print(f"   ✅ {label}: {ref_val}")

compare("Trade Count", len(ref_trades), len(proj_trades))
compare("Wins", ref_stats["wins"], proj_stats["wins"])
compare("Losses", ref_stats["losses"], proj_stats["losses"])
compare("Net P&L", ref_stats["realized_pnl_sum"], proj_stats["realized_pnl_sum"])
compare("Ending Cash", ref_stats["ending_cash"], proj_stats["ending_cash"])

# Compare trade-by-trade
if len(ref_trades) == len(proj_trades) and len(ref_trades) > 0:
    print(f"\n   📋 Trade-by-trade comparison (first 20):")
    for i in range(min(20, len(ref_trades))):
        r = ref_trades.iloc[i]
        p = proj_trades.iloc[i]
        r_pnl = r["realized_pnl"]
        p_pnl = p["realized_pnl"]
        diff = abs(r_pnl - p_pnl)
        status = "✅" if diff < 0.01 else "❌"
        print(f"      {status} T{i+1}: REF pnl=₹{r_pnl:,.2f} | PROJ pnl=₹{p_pnl:,.2f} | dir={r['direction']} | diff=₹{diff:.2f}")

    # Check last few trades too
    if len(ref_trades) > 20:
        print(f"\n   📋 Last 5 trades:")
        for i in range(len(ref_trades)-5, len(ref_trades)):
            r = ref_trades.iloc[i]
            p = proj_trades.iloc[i]
            r_pnl = r["realized_pnl"]
            p_pnl = p["realized_pnl"]
            diff = abs(r_pnl - p_pnl)
            status = "✅" if diff < 0.01 else "❌"
            print(f"      {status} T{i+1}: REF pnl=₹{r_pnl:,.2f} | PROJ pnl=₹{p_pnl:,.2f} | dir={r['direction']} | diff=₹{diff:.2f}")

elif len(ref_trades) != len(proj_trades):
    print(f"\n   ⚠️ Trade count mismatch — comparing events to find divergence point...")
    
    # Find first divergence
    ref_entries = ref_events[ref_events["event"]=="ENTRY"].reset_index(drop=True)
    proj_entries = proj_events[proj_events["event"]=="ENTRY"].reset_index(drop=True)
    
    min_len = min(len(ref_entries), len(proj_entries))
    for i in range(min_len):
        r = ref_entries.iloc[i]
        p = proj_entries.iloc[i]
        if r["bar_index"] != p["bar_index"] or r["direction"] != p["direction"]:
            print(f"      ❌ First divergence at entry #{i+1}:")
            print(f"         REF: bar={r['bar_index']} dir={r['direction']} price={r['price']} @ {r['time']}")
            print(f"         PROJ: bar={p['bar_index']} dir={p['direction']} price={p['price']} @ {p['time']}")
            break
    else:
        if len(ref_entries) != len(proj_entries):
            print(f"      ℹ️ All {min_len} shared entries match, but REF has {len(ref_entries)} entries vs PROJ has {len(proj_entries)}")

print("\n" + "="*60)
if matches:
    print("🎉 OUTPUTS ARE IDENTICAL — both engines produce the same results!")
else:
    print("⚠️ OUTPUTS DIFFER — see mismatches above")
print("="*60)
