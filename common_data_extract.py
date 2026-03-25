# filename: common_data_extract.py
# Purpose: COMMON historical candle extractor for CASH (NSE EQ/INDEX) + F&O (NFO FUT/OPT) via SmartAPI
# Usage: edit ONLY the CONFIG section below, run the script.
#
# Output: One CSV per selected symbol with clean columns:
# datetime, open, high, low, close, volume

import sys
sys.stdout.reconfigure(encoding='utf-8')

import re
import time
import datetime as dt
import os
from decouple import config
from typing import List, Dict, Optional, Tuple, Union

import pyotp
import pandas as pd
from SmartApi.smartConnect import SmartConnect


# ============================
# 0) CREDENTIALS (from .env)
# ============================
CLIENT_CODE = config("ANGEL_SMARTAPI_CLIENT_CODE", default="H63011733")
PASSWORD    = config("ANGEL_SMARTAPI_PASSWORD",    default="0852")
TOTP_SECRET = config("ANGEL_SMARTAPI_TOTP_SECRET", default="UDZGVH3RJFDK55WCWZ4DH667KI")
API_KEY     = config("ANGEL_SMARTAPI_API_KEY",     default="dB0kYJIz")


# ===========================================
# 1) CONFIG — edit these lines only
# ===========================================
# EXCHANGE:
# - CASH:  "NSE" (Equity), "BSE"
# - F&O :  "NFO"
# - INDEX spot: use "NSE" + PRODUCT="INDEX"
# You can also set EXCHANGE="AUTO" and it will pick based on PRODUCT.
EXCHANGE = "MCX"     # "AUTO" | "NSE" | "NFO" | "BSE" | "MCX" | "CDS"

# You can extract one or many. Examples:
# CASH: ["RELIANCE", "TCS", "INFY"]
# FUT : ["BANKNIFTY", "NIFTY", "RELIANCE"]
# OPT : ["BANKNIFTY", "NIFTY"]
INSTRUMENTS: Union[str, List[str]] = ["SILVERM"]

# PRODUCT:
# "EQ"     -> NSE equity delivery symbol (uses -EQ filter)
# "INDEX"  -> NSE index spot (NIFTY 50, NIFTYBANK etc.)
# "FUT"    -> NFO futures
# "OPT"    -> NFO options
# "ANY"    -> no filter, picks best match
PRODUCT = "FUT"   # "EQ" | "INDEX" | "FUT" | "OPT" | "ANY"

# Options settings (only used if PRODUCT="OPT")
OPTION_TYPE: Optional[str] = None     # "CE" | "PE" | None (allow both)
STRIKE: Optional[float] = None        # Example 45000 (optional). None = any strike
STRIKE_TOLERANCE = 0.0                # 0.0 = exact strike match if STRIKE set; else choose closest strike

# Expiry selection (used for FUT/OPT; ignored for EQ/INDEX)
EXPIRY_CHOICE = "nearest"             # "nearest" | "farthest" | "specific"
EXPIRY_DATE: Optional[str] = None     # "YYYY-MM-DD" (only when EXPIRY_CHOICE="specific")

# Interval
INTERVAL = "FIFTEEN_MINUTE"           # ONE_MINUTE|THREE_MINUTE|FIVE_MINUTE|TEN_MINUTE|FIFTEEN_MINUTE|THIRTY_MINUTE|FORTY_FIVE_MINUTE|ONE_HOUR|ONE_DAY

# Date range
BACKFILL_MAX = False                 # True = go back as far as API returns; False = use FROM_DATE..TO_DATE
FROM_DATE: Optional[str] = "2026-03-01 10:22"   # 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD' (ignored if BACKFILL_MAX=True)
TO_DATE:   Optional[str] = "2026-03-25 10:22"   # 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD' (ignored if BACKFILL_MAX=True)

# Save options
SAVE_CSV  = True
SAVE_XLSX = False

# Throttling / chunking
INTRA_CHUNK_DAYS = 60        # used for intraday intervals (<= 1h)
DAILY_CHUNK_DAYS = 365 * 5   # used for ONE_DAY
COOLDOWN_SEC     = 1.25

# Output folder (keep empty for current folder)
OUT_DIR = ""


# ===========================================
# 2) Helpers
# ===========================================
def pick_exchange(exchange_cfg: str, product: str) -> str:
    exchange_cfg = (exchange_cfg or "").upper().strip()
    product = (product or "ANY").upper().strip()

    if exchange_cfg != "AUTO":
        return exchange_cfg

    # AUTO rules (simple + practical)
    if product in ("FUT", "OPT"):
        return "NFO"
    if product in ("EQ", "INDEX"):
        return "NSE"
    return "NSE"

def parse_user_dt(s: Optional[str], default: dt.datetime) -> dt.datetime:
    if not s:
        return default
    for fmt in ("%Y-%m-%d %H:%M", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(s, fmt)
        except ValueError:
            continue
    raise ValueError(f"Bad datetime format: {s!r}. Use 'YYYY-MM-DD HH:MM' or 'YYYY-MM-DD'.")

def ensure_list(x: Union[str, List[str]]) -> List[str]:
    if isinstance(x, list):
        return [str(i).strip() for i in x if str(i).strip()]
    s = str(x).strip()
    return [s] if s else []

def out_path(fname: str) -> str:
    # ✅ fixed f-string backslash issue
    if OUT_DIR:
        cleaned = OUT_DIR.rstrip("/").rstrip("\\")
        return cleaned + "/" + fname
    return fname


# ===========================================
# 3) LOGIN
# ===========================================
print("🔐 Generating TOTP...")
otp = pyotp.TOTP(TOTP_SECRET).now()
print("TOTP:", otp)

print("🔁 Logging in...")
obj = SmartConnect(api_key=API_KEY)
login = obj.generateSession(CLIENT_CODE, PASSWORD, otp)
if not isinstance(login, dict) or not isinstance(login.get("data"), dict) or ("refreshToken" not in login["data"] and "jwtToken" not in login["data"]):
    print("❌ Login failed:", login)
    raise SystemExit(1)
print("✅ Login successful.")


# ===========================================
# 4) SYMBOL/TOKEN Resolution
# ===========================================
def search_all(api: SmartConnect, exchange: str, query: str) -> List[Dict]:
    try:
        res = api.searchScrip(exchange=exchange, searchscrip=query)
        time.sleep(COOLDOWN_SEC)
        return res.get("data") or []
    except Exception as e:
        print(f"⚠️ searchScrip error: {e}")
        return []

def parse_expiry_from_symbol(sym: str) -> Optional[dt.datetime]:
    m = re.search(r"(\d{2}[A-Z]{3}\d{2})(?:FUT|CE|PE)?$", sym)
    if not m:
        return None
    try:
        return dt.datetime.strptime(m.group(1), "%d%b%y")
    except Exception:
        return None

def extract_strike(sym: str) -> Optional[float]:
    m = re.search(r"(\d+)(CE|PE)$", sym)
    if not m:
        return None
    try:
        return float(m.group(1))
    except Exception:
        return None

def filter_by_product(hits: List[Dict], product: str, opt_type: Optional[str]) -> List[Dict]:
    """
    ✅ IMPORTANT FIX:
    - For EQ, we must NOT do ('CE' in sym) because symbols like RELIANCE contain "CE".
    - Always check ONLY suffix for derivatives: endswith("CE"/"PE"/"FUT")
    """
    product = (product or "ANY").upper()
    want_ce = (opt_type or "").upper() == "CE"
    want_pe = (opt_type or "").upper() == "PE"

    out = []
    for h in hits:
        sym = (h.get("tradingsymbol") or "").upper().strip()
        if not sym:
            continue

        if product == "FUT":
            if sym.endswith("FUT"):
                out.append(h)

        elif product == "OPT":
            is_opt = sym.endswith("CE") or sym.endswith("PE")
            if is_opt:
                if want_ce and sym.endswith("CE"):
                    out.append(h)
                elif want_pe and sym.endswith("PE"):
                    out.append(h)
                elif not want_ce and not want_pe:
                    out.append(h)

        elif product == "EQ":
            # NSE cash uses -EQ
            if sym.endswith("-EQ"):
                out.append(h)

        elif product == "INDEX":
            # not derivatives + not -EQ (best-effort)
            if (not sym.endswith("FUT")) and (not sym.endswith("CE")) and (not sym.endswith("PE")):
                out.append(h)

        else:  # ANY
            out.append(h)

    return out

def pick_by_expiry(hits: List[Dict], mode: str, specific: Optional[str]) -> Optional[Dict]:
    mode = (mode or "nearest").lower()

    exp_pairs = []
    for h in hits:
        sym = (h.get("tradingsymbol") or "").upper()
        exp = parse_expiry_from_symbol(sym)
        if exp:
            exp_pairs.append((exp, h))

    if not exp_pairs:
        return hits[0] if hits else None

    if mode == "nearest":
        exp_pairs.sort(key=lambda x: x[0])
        return exp_pairs[0][1]

    if mode == "farthest":
        exp_pairs.sort(key=lambda x: x[0], reverse=True)
        return exp_pairs[0][1]

    if mode == "specific" and specific:
        try:
            want = dt.datetime.strptime(specific, "%Y-%m-%d")
            exp_pairs.sort(key=lambda x: abs((x[0] - want).days))
            return exp_pairs[0][1]
        except Exception:
            exp_pairs.sort(key=lambda x: x[0])
            return exp_pairs[0][1]

    exp_pairs.sort(key=lambda x: x[0])
    return exp_pairs[0][1]

def pick_option_by_strike(hits: List[Dict], strike: float, tol: float) -> Optional[Dict]:
    best = None
    best_diff = None
    strike = float(strike)

    # exact or within tolerance
    for h in hits:
        sym = (h.get("tradingsymbol") or "").upper().strip()
        k = extract_strike(sym)
        if k is None:
            continue
        diff = abs(k - strike)
        if tol == 0.0:
            if diff == 0.0:
                return h
        else:
            if diff <= tol:
                if best is None or diff < best_diff:
                    best = h
                    best_diff = diff

    # if exact not found, choose closest
    if tol == 0.0:
        for h in hits:
            sym = (h.get("tradingsymbol") or "").upper().strip()
            k = extract_strike(sym)
            if k is None:
                continue
            diff = abs(k - strike)
            if best is None or diff < best_diff:
                best = h
                best_diff = diff

    return best

def resolve_symbol_token(api: SmartConnect,
                         exchange: str,
                         instrument_query: str,
                         product: str,
                         option_type: Optional[str],
                         expiry_choice: str,
                         expiry_date: Optional[str],
                         strike: Optional[float],
                         strike_tol: float) -> Tuple[str, str]:
    print(f"\n🔎 Searching: exchange={exchange}, query={instrument_query!r}, product={product}, interval={INTERVAL}")
    hits_raw = search_all(api, exchange, instrument_query)
    if not hits_raw:
        raise RuntimeError("No matches from searchScrip.")

    # keep rows where tradingsymbol starts with query or matches query pattern
    q = instrument_query.upper().replace(" ", "")
    def norm(s: str) -> str:
        return (s or "").upper().replace(" ", "")

    # refined filter to avoid SILVERMIC matching SILVERM
    hits_filtered = []
    for h in hits_raw:
        sym = norm(h.get("tradingsymbol") or "")
        # If query is SILVERM, it must NOT match SILVERMIC
        if q == "SILVERM" and "SILVERMIC" in sym:
            continue
        if q in sym:
            hits_filtered.append(h)

    hits_base = hits_filtered or hits_raw

    hits_product = filter_by_product(hits_base, product, option_type)
    if not hits_product:
        print("❌ Nothing matched your product filter. First few results from API:")
        for r in hits_raw[:20]:
            print(" ", r.get("tradingsymbol"))
        raise RuntimeError("Product filter returned nothing.")

    chosen_pool = hits_product
    if product.upper() in ("FUT", "OPT"):
        chosen = pick_by_expiry(chosen_pool, expiry_choice, expiry_date)

        if product.upper() == "OPT" and strike is not None:
            chosen_sym = (chosen.get("tradingsymbol") or "").upper().strip() if chosen else ""
            chosen_exp = parse_expiry_from_symbol(chosen_sym)
            if chosen_exp:
                same_exp = []
                for h in chosen_pool:
                    sym = (h.get("tradingsymbol") or "").upper().strip()
                    if parse_expiry_from_symbol(sym) == chosen_exp:
                        same_exp.append(h)
                if same_exp:
                    chosen_pool = same_exp
            chosen_strike = pick_option_by_strike(chosen_pool, strike, float(strike_tol))
            if chosen_strike:
                chosen = chosen_strike
    else:
        chosen = chosen_pool[0]

    symbol = (chosen.get("tradingsymbol") or "").strip()
    token  = (chosen.get("symboltoken") or "").strip()
    if not symbol or not token:
        raise RuntimeError(f"Bad chosen row (missing symbol/token): {chosen}")

    print(f"✅ Selected: {symbol} | Token: {token}")
    return symbol, token


# ===========================================
# 5) HISTORICAL FETCH
# ===========================================
def fetch_chunk(api: SmartConnect,
                exch: str,
                token: str,
                interval: str,
                start_dt: dt.datetime,
                end_dt: dt.datetime) -> List[List]:
    params = {
        "exchange": exch,
        "symboltoken": token,
        "interval": interval,
        "fromdate": start_dt.strftime("%Y-%m-%d %H:%M"),
        "todate":   end_dt.strftime("%Y-%m-%d %H:%M"),
    }
    try:
        resp = api.getCandleData(params)
        return resp.get("data") or []
    except Exception as e:
        print(f"⚠️ Fetch error {start_dt:%Y-%m-%d %H:%M} → {end_dt:%Y-%m-%d %H:%M}: {e}")
        return []

def extract_one(api: SmartConnect,
                exchange: str,
                instrument_query: str,
                product: str,
                option_type: Optional[str],
                expiry_choice: str,
                expiry_date: Optional[str],
                strike: Optional[float],
                strike_tol: float) -> Optional[pd.DataFrame]:
    symbol, token = resolve_symbol_token(
        api=api,
        exchange=exchange,
        instrument_query=instrument_query,
        product=product,
        option_type=option_type,
        expiry_choice=expiry_choice,
        expiry_date=expiry_date,
        strike=strike,
        strike_tol=strike_tol
    )

    now = dt.datetime.now()
    intraday = INTERVAL != "ONE_DAY"
    chunk_days = INTRA_CHUNK_DAYS if intraday else DAILY_CHUNK_DAYS

    if BACKFILL_MAX:
        end_dt = now
        start_dt_limit = now - dt.timedelta(days=365 * 15)
    else:
        fd = parse_user_dt(FROM_DATE, default=now - dt.timedelta(days=365))
        td = parse_user_dt(TO_DATE,   default=now)
        if fd >= td:
            raise RuntimeError("FROM_DATE must be earlier than TO_DATE.")
        end_dt = td
        start_dt_limit = fd

    print(f"📈 Fetching {INTERVAL} candles for {symbol} on {exchange} …")
    rows_all: List[List] = []

    while end_dt > start_dt_limit:
        # ✅ FIX: clamp start_dt to start_dt_limit to avoid fetching excess months
        start_dt = max(start_dt_limit, end_dt - dt.timedelta(days=chunk_days))
        print(f"  ⏳ {start_dt:%Y-%m-%d %H:%M} → {end_dt:%Y-%m-%d %H:%M}")
        chunk = fetch_chunk(api, exchange, token, INTERVAL, start_dt, end_dt)
        if not chunk:
            if BACKFILL_MAX:
                print("  ⛔ No more data returned — reached API’s history limit.")
                break
            else:
                print("  ⚠️ Empty chunk; continuing window.")
        else:
            rows_all.extend(chunk)

        end_dt = start_dt
        time.sleep(COOLDOWN_SEC)

    if not rows_all:
        print("❌ No data returned.")
        return None

    print("🧹 Cleaning / sorting …")
    df = pd.DataFrame(rows_all, columns=["datetime", "open", "high", "low", "close", "volume"])
    df["datetime"] = pd.to_datetime(df["datetime"], errors="coerce")
    df.dropna(subset=["datetime"], inplace=True)
    df["datetime"] = df["datetime"].dt.tz_localize(None)

    for c in ["open", "high", "low", "close", "volume"]:
        df[c] = pd.to_numeric(df[c], errors="coerce")

    df.dropna(subset=["open", "high", "low", "close"], inplace=True)
    df.sort_values("datetime", inplace=True)
    df.drop_duplicates(subset=["datetime"], keep="last", inplace=True)

    # ✅ FINAL FILTER: Ensure data is strictly within requested range
    df = df[(df["datetime"] >= start_dt_limit) & (df["datetime"] <= td)]
    df.reset_index(drop=True, inplace=True)

    print(f"📏 Range fetched: {df['datetime'].min()}  →  {df['datetime'].max()}  |  rows: {len(df):,}")

    base = f"{symbol}_{INTERVAL}_{('max' if BACKFILL_MAX else 'custom')}"
    if SAVE_CSV:
        csv_path = out_path(base + ".csv")
        df.to_csv(csv_path, index=False)
        print("✅ CSV saved →", csv_path)
    if SAVE_XLSX:
        xlsx_path = out_path(base + ".xlsx")
        df.to_excel(xlsx_path, index=False)
        print("✅ XLSX saved →", xlsx_path)

    return df


# ===========================================
# 6) RUN (multi-instrument)
# ===========================================
def main():
    product = (PRODUCT or "ANY").upper().strip()
    exchange = pick_exchange(EXCHANGE, product)

    instruments = ensure_list(INSTRUMENTS)
    if not instruments:
        raise SystemExit("❌ INSTRUMENTS is empty.")

    print("\n==============================")
    print("COMMON DATA EXTRACTOR (CASH + F&O)")
    print("==============================")
    print(f"Exchange : {exchange} (CONFIG={EXCHANGE})")
    print(f"Product  : {product}")
    print(f"Interval : {INTERVAL}")
    print(f"Backfill : {BACKFILL_MAX}")
    if not BACKFILL_MAX:
        print(f"From     : {FROM_DATE}")
        print(f"To       : {TO_DATE}")
    if product == "OPT":
        print(f"Opt Type : {OPTION_TYPE}")
        print(f"Strike   : {STRIKE} (tol={STRIKE_TOLERANCE})")
    if product in ("FUT", "OPT"):
        print(f"Expiry   : {EXPIRY_CHOICE}  ({EXPIRY_DATE})")
    print("==============================\n")

    ok = 0
    for inst in instruments:
        try:
            df = extract_one(
                api=obj,
                exchange=exchange,
                instrument_query=inst,
                product=product,
                option_type=OPTION_TYPE,
                expiry_choice=EXPIRY_CHOICE,
                expiry_date=EXPIRY_DATE,
                strike=STRIKE,
                strike_tol=STRIKE_TOLERANCE
            )
            if df is not None and len(df):
                ok += 1
        except Exception as e:
            print(f"\n❌ Failed for {inst!r}: {e}\n")

    print(f"\n🎉 Done. Success: {ok}/{len(instruments)}")


if __name__ == "__main__":
    main()