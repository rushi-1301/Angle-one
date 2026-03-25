# utils/indicator_preprocessor.py
import pandas as pd

from live_trading.models import LivePosition

EMA_FAST = 27
EMA_SLOW = 78


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Non-destructive indicator preprocessor.
    Adds EMA27, EMA78 and month-end marker.
    """

    if df.empty or len(df) < EMA_SLOW:
        return df

    df = df.copy()

    # Ensure timestamp is datetime
    df["timestamp"] = pd.to_datetime(df["timestamp"])

    # --- EMA Calculations ---
    df["ema_27"] = df["close"].ewm(span=EMA_FAST, adjust=False).mean()
    df["ema_78"] = df["close"].ewm(span=EMA_SLOW, adjust=False).mean()

    # --- Month End Detection (matches reference groupby approach) ---
    df["ym"] = df["timestamp"].dt.to_period("M")
    df["is_month_end"] = False
    df.loc[df.groupby("ym").tail(1).index, "is_month_end"] = True

    # Cleanup helper columns
    df.drop(columns=["ym"], inplace=True, errors="ignore")

    return df


def is_last_candle_of_month(ts, df):
    ym = ts.to_period("M")
    return ts == df[df["timestamp"].dt.to_period("M") == ym]["timestamp"].max()
