# utils/strategies_live.py

import pandas as pd

from backtest_runner.models import AngelOneKey
from utils.angel_one import logger
from utils.placeorder import buy_order, sell_order

EMA_SHORT = 27
EMA_LONG  = 78
BREAKOUT_BUFFER = 0.0012  # 0.12% buffer beyond C2 extreme (matches reference)

import pandas as pd


def c3_strategy(df: pd.DataFrame):
    """
    SAFE C3 STRATEGY (NO REPAINT)

    Rules (LONG):
    - EMA 27 > EMA 78
    - C1.close < C2.close < C3.close
    - C3 must be fully CLOSED candle

    LONG:
    - Candle 1 green
    - Candle 2 green
    - C2 high > C1 high
    - Candle 3 close > C2 high * (1 + buffer)
    - EMA27 > EMA78

    SHORT:
    - Candle 1 red
    - Candle 2 red
    - C2 low < C1 low
    - Candle 3 close < C2 low * (1 - buffer)
    - EMA27 < EMA78

    NOTE:
    - df MUST be sorted by timestamp ASC
    - Strategy evaluates last 3 CLOSED candles
    - Entry should be done on NEXT candle open
    """
    logger.info("Running C3 strategy...")
    result = {
        "action": "HOLD",
        "reason": "No signal",
        "price": None
    }

    if df is None or len(df) < EMA_LONG + 3:
        result["reason"] = "Not enough candles"
        return result

    df = df.copy().reset_index(drop=True)

    # Ensure numeric values
    for col in ["open", "high", "low", "close"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    df.dropna(inplace=True)

    if len(df) < EMA_LONG + 3:
        result["reason"] = "Insufficient candles after cleanup"
        return result

    # EMA calculation
    df["ema_27"] = df["close"].ewm(span=EMA_SHORT, adjust=False).mean()
    df["ema_78"] = df["close"].ewm(span=EMA_LONG, adjust=False).mean()
    # print("ema_27", df["ema_27"].tail(3), "  && ema_78", df["ema_78"].tail(3))
    # 🔒 LAST 3 *CLOSED* candles
    c1 = df.iloc[-3]
    c2 = df.iloc[-2]
    c3 = df.iloc[-1]
    logger.info(
        "[C3 CANDLES] "
        "C1: O=%.0f H=%.0f L=%.0f C=%.0f (%s) | "
        "C2: O=%.0f H=%.0f L=%.0f C=%.0f (%s) | "
        "C3: O=%.0f H=%.0f L=%.0f C=%.0f",
        c1.open, c1.high, c1.low, c1.close, "GREEN" if c1.close > c1.open else "RED",
        c2.open, c2.high, c2.low, c2.close, "GREEN" if c2.close > c2.open else "RED",
        c3.open, c3.high, c3.low, c3.close,
    )
    # Candle colors
    c1_green = c1.close > c1.open
    c2_green = c2.close > c2.open
    c3_green = c3.close > c3.open

    c1_red = c1.close < c1.open
    c2_red = c2.close < c2.open
    c3_red = c3.close < c3.open

    # EMA trend
    ema_long = c3.ema_27 > c3.ema_78
    ema_short = c3.ema_27 < c3.ema_78

    # ---- LONG CONDITIONS (matches reference Bro_gaurd_SILVERMINI.py) ----
    long_pattern = (
            c1_green and
            c2_green and
            c2.high > c1.high and
            c3.close > c2.high * (1 + BREAKOUT_BUFFER)
    )
    logger.info(
        "[LONG CHECK] c1_green=%s c2_green=%s c2.h>c1.h=%s c3.c>c2.h*buf=%s",
        c1_green, c2_green, c2.high > c1.high,
        c3.close > c2.high * (1 + BREAKOUT_BUFFER)
    )

    # ---- SHORT CONDITIONS (matches reference Bro_gaurd_SILVERMINI.py) ----
    short_pattern = (
            c1_red and
            c2_red and
            c2.low < c1.low and
            c3.close < c2.low * (1 - BREAKOUT_BUFFER)
    )
    logger.info(
        "[SHORT CHECK] c1_red=%s c2_red=%s c2.l<c1.l=%s c3.c<c2.l*buf=%s",
        c1_red, c2_red, c2.low < c1.low,
        c3.close < c2.low * (1 - BREAKOUT_BUFFER)
    )
    # print("short_pattern", short_pattern, "  || ema_short", ema_short)

    if ema_long and long_pattern:
        return {
            "action": "BUY",
            "reason": "C3 LONG BREAKOUT CONFIRMED",
            "price": float(c3.close)
        }

    if ema_short and short_pattern:
        return {
            "action": "SELL",
            "reason": "C3 SHORT BREAKOUT CONFIRMED",
            "price": float(c3.close)
        }

    return {
        "action": "HOLD",
        "reason": (
            f"ema_long={ema_long}, long_pattern={long_pattern}, "
            f"ema_short={ema_short}, short_pattern={short_pattern}"
        ),
        "price": float(c3.close)
    }

def should_run_strategy(engine, candle_time):
    if engine.last_strategy_candle == candle_time:
        return False
    engine.last_strategy_candle = candle_time
    return True


import re

def to_float(x):
    if x is None:
        return None
    x = str(x)

    # Remove EVERYTHING except digits, decimal point, minus sign
    x = re.sub(r"[^0-9.\-]", "", x)

    # Handle cases like ".123" or "123."
    if x in ["", ".", "-"]:
        return None

    return pd.to_numeric(x, errors="coerce")