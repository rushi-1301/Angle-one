# utils/position_manager.py
# Aligned with Bro_gaurd_SILVERMINI.py reference logic

from datetime import datetime, timedelta
from logzero import logger
from django.utils import timezone

from utils.placeorder import buy_order, sell_order
from utils.pnl_utils import get_pnl_from_angelone

# ─── Strategy constants (match reference) ────────────────
FIXED_SL_PCT    = 0.015       # 1.5% fixed stop
TRAIL_SL_PCT    = 0.025       # 2.5% trailing stop
BREAKOUT_BUFFER = 0.0012      # 0.12% buffer (for EMA reversal C3 confirm)
COOLDOWN_BARS   = 3           # candles to skip after exit
DAILY_TRADE_CAP = 10          # max entries per calendar day


class PositionManager:
    def __init__(self, user, token):
        self.user = user
        self.token = token
        self.position = None

        # ── Candle-based cooldown (matches reference) ─────────
        self.cooldown_left = 0

        # ── Lot sizing state (matches reference) ─────────────
        self.base_lots = 2
        self.current_lots = 2          # position_size in reference
        self.consecutive_win = 0
        self.consecutive_loss = 0
        self.pending_reward = False
        self.boost_count = 0
        self.boost_next_entry = False
        self.lot_size = 5              # 1 lot = 5 qty

        # ── Daily trade cap (matches reference) ──────────────
        self.trades_today = 0
        self.current_day = None

    # ─── Basic state queries ──────────────────────────────────
    def has_open_position(self):
        return self.position is not None

    def in_cooldown(self):
        """Candle-based cooldown: True if still cooling down."""
        return self.cooldown_left > 0

    def tick_cooldown(self):
        """Call once per candle bar to decrement cooldown counter."""
        if self.cooldown_left > 0:
            self.cooldown_left -= 1

    # ─── Daily trade cap ─────────────────────────────────────
    def check_daily_cap(self):
        """Reset counter on new day, return True if cap reached."""
        today = datetime.now().date()
        if self.current_day is None or today != self.current_day:
            self.current_day = today
            self.trades_today = 0

        if DAILY_TRADE_CAP is not None and self.trades_today >= DAILY_TRADE_CAP:
            return True
        return False

    # ─── Max lots by cash (50% rule) ─────────────────────────
    def _max_lots_by_cash(self, available_cash, margin_per_lot):
        if margin_per_lot <= 0:
            return 1
        half_cash = max(0.0, 0.5 * available_cash)
        return max(1, int(half_cash // margin_per_lot))

    # ─── Calculate lots (matches reference enter_now logic) ──
    def calculate_lots(self, available_cash, margin_per_lot):
        """
        Reference logic:
          lots_by_cash  = usable_cash // margin_per_lot
          dyn_cap       = 50% of cash // margin
          desired_cap   = dyn_cap if boost_next_entry else position_size
          lots          = min(lots_by_cash, desired_cap, dyn_cap)
        """
        if margin_per_lot <= 0:
            return 1

        reserve = 1000.0
        usable = max(0.0, available_cash - reserve)
        lots_by_cash = max(int(usable // margin_per_lot), 1)
        dyn_cap = self._max_lots_by_cash(available_cash, margin_per_lot)

        desired_cap = dyn_cap if self.boost_next_entry else self.current_lots
        lots = max(1, min(lots_by_cash, desired_cap, dyn_cap))

        logger.info(
            "Lot calc → lots_by_cash=%s dyn_cap=%s desired=%s final=%s boost=%s",
            lots_by_cash, dyn_cap, desired_cap, lots, self.boost_next_entry
        )
        return lots

    # ─── Update after trade exit (matches reference exactly) ──
    def update_after_trade(self, pnl):
        """
        Reference Bro_gaurd_SILVERMINI.py exit_now() logic:
        WIN:
          - consecutive_win++, consecutive_loss = 0
          - if pending_reward and boost_count > 0: double position_size (capped), decrement boost
          - if consecutive_win == 3: boost_next_entry = True
          - else: halve position_size
        LOSS:
          - consecutive_loss++, consecutive_win = 0
          - if consecutive_loss == 3: pending_reward, boost_count = True, 1
          - elif consecutive_loss == 5: pending_reward, boost_count = True, 2
          - double position_size
        """
        if pnl >= 0:
            self.consecutive_win += 1
            self.consecutive_loss = 0

            if self.pending_reward and self.boost_count > 0:
                self.current_lots = min(
                    self._max_lots_by_cash(500000, 1),  # fallback max
                    self.current_lots * 2
                )
                self.boost_count -= 1
                if self.boost_count == 0:
                    self.pending_reward = False
                    self.consecutive_loss = 0

            if self.consecutive_win == 3:
                self.boost_next_entry = True
            else:
                self.current_lots = max(1, self.current_lots // 2)

            logger.info(
                "WIN → lots=%s consec_win=%s boost_next=%s",
                self.current_lots, self.consecutive_win, self.boost_next_entry
            )
        else:
            self.consecutive_loss += 1
            self.consecutive_win = 0

            if self.consecutive_loss == 3:
                self.pending_reward, self.boost_count = True, 1
            elif self.consecutive_loss == 5:
                self.pending_reward, self.boost_count = True, 2

            self.current_lots = max(1, self.current_lots * 2)

            logger.info(
                "LOSS → lots=%s consec_loss=%s pending_reward=%s boost_count=%s",
                self.current_lots, self.consecutive_loss,
                self.pending_reward, self.boost_count
            )

    # ─── Open position ───────────────────────────────────────
    def open_position(self, side, price, lots, quantity):
        if self.position:
            return
        self.position = {
            "side": side,
            "entry_price": price,
            "lots": lots,
            "quantity": quantity,
            "fixed_sl": price * (1 - FIXED_SL_PCT) if side == "LONG" else price * (1 + FIXED_SL_PCT),
            "trailing_sl": price * (1 - TRAIL_SL_PCT) if side == "LONG" else price * (1 + TRAIL_SL_PCT),
            "entry_time": timezone.now()
        }

        # Clear boost flag on entry (matches reference)
        if self.boost_next_entry:
            self.boost_next_entry = False

        # Count trade for daily cap
        self.trades_today += 1

        logger.info(
            "[POSITION OPEN] %s | Price=%s Lots=%s Qty=%s | FixedSL=%.2f TrailSL=%.2f",
            side, price, lots, quantity,
            self.position["fixed_sl"], self.position["trailing_sl"]
        )

    # ─── Tick-based SL check (LONG: check price vs SL, SHORT: check price vs SL) ──
    def check_exit_on_tick(self, price):
        """
        In live trading we use LTP (tick price) for SL checks.
        Reference uses l3/h3 (candle low/high), but tick-by-tick is equivalent
        since we're checking the actual traded price.
        """
        if not self.position:
            return

        side = self.position["side"]

        # Check fixed stop-loss
        if side == "LONG" and price <= self.position["fixed_sl"]:
            self._close_position("STOP", price)
            return
        if side == "SHORT" and price >= self.position["fixed_sl"]:
            self._close_position("STOP", price)
            return

        # Check trailing stop-loss
        if side == "LONG":
            if price <= self.position["trailing_sl"]:
                self._close_position("STOP", price)
                return
            # Update trail upward (matches reference: c3 > pos_price → new trail)
            if price > self.position["entry_price"]:
                new_trail = price * (1 - TRAIL_SL_PCT)
                if new_trail > self.position["trailing_sl"]:
                    self.position["trailing_sl"] = new_trail

        if side == "SHORT":
            if price >= self.position["trailing_sl"]:
                self._close_position("STOP", price)
                return
            # Update trail downward
            if price < self.position["entry_price"]:
                new_trail = price * (1 + TRAIL_SL_PCT)
                if new_trail < self.position["trailing_sl"]:
                    self.position["trailing_sl"] = new_trail

    # ─── EMA Reversal exit with C3 confirmation (matches reference) ──
    def check_ema_reversal_exit(self, df, ema_fast, ema_slow):
        """
        Reference Bro_gaurd_SILVERMINI.py EMA_REVERSAL logic:
        - LONG position + ema_s < ema_l → check opposite C3 breakout
        - SHORT position + ema_s > ema_l → check opposite C3 breakout
        - Only exit if opposite C3 confirms the reversal
        """
        if not self.position:
            return False

        side = self.position["side"]

        # Check EMA flip
        if side == "LONG" and ema_fast >= ema_slow:
            return False
        if side == "SHORT" and ema_fast <= ema_slow:
            return False

        # EMA has flipped — now require opposite C3 breakout confirmation
        if len(df) < 3:
            return False

        c1 = df.iloc[-3]
        c2 = df.iloc[-2]
        c3 = df.iloc[-1]

        if side == "LONG":
            # Need SHORT C3 breakout to confirm reversal
            opposite_c3 = (
                c1["close"] < c1["open"] and      # C1 red
                c2["close"] < c2["open"] and      # C2 red
                c2["low"] < c1["low"] and          # lower low
                c3["close"] < c2["low"] * (1 - BREAKOUT_BUFFER)  # buffer breakout
            )
        else:
            # Need LONG C3 breakout to confirm reversal
            opposite_c3 = (
                c1["close"] > c1["open"] and      # C1 green
                c2["close"] > c2["open"] and      # C2 green
                c2["high"] > c1["high"] and        # higher high
                c3["close"] > c2["high"] * (1 + BREAKOUT_BUFFER)  # buffer breakout
            )

        if opposite_c3:
            logger.info(
                "EMA_REVERSAL confirmed with opposite C3 → exiting %s", side
            )
            self._close_position("EMA_REVERSAL", float(c3["close"]))
            return True

        logger.info("EMA flipped but no opposite C3 confirm yet — holding %s", side)
        return False

    # ─── Force exit (month-end, EOD, etc.) ───────────────────
    def force_exit(self, reason, price):
        if self.position:
            self._close_position(reason, price)

    # ─── Close position ──────────────────────────────────────
    def _close_position(self, reason, price):
        if not self.position:
            return

        side = self.position["side"]
        quantity = self.position["quantity"]
        logger.info("[POSITION CLOSE] %s | %s @ %s", side, reason, price)

        if side == "LONG":
            print("SELL ORDER")
            # sell_order(self.user, self.token, quantity)
        elif side == "SHORT":
            print("BUY ORDER")
            # buy_order(self.user, self.token, qty=quantity, exchange="MCX",
            #           tradingsymbol="SILVERM30APR26FUT", symboltoken=457533)

        pnl = get_pnl_from_angelone(self.user)
        self.update_after_trade(pnl)

        self.position = None
        self.cooldown_left = COOLDOWN_BARS  # 3-candle cooldown (matches reference)