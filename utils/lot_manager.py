# utils/lot_manager.py
# Aligned with Bro_gaurd_SILVERMINI.py reference logic

from logzero import logger
from live_trading.models import TradeStats


class LotManager:
    LOT_QTY = 5        # 1 lot = 5 quantity
    BASE_LOTS = 2

    def __init__(self, user, margin_per_lot):
        self.user = user
        self.margin_per_lot = margin_per_lot

        stats, _ = TradeStats.objects.get_or_create(user=user)
        self.stats = stats

    # ─── Dynamic max lots (50% cash rule, matches reference) ──
    def dynamic_max_lots(self, cash):
        half_cash = max(0.0, 0.5 * cash)
        return max(1, int(half_cash // self.margin_per_lot))

    # ─── Update after trade exit (matches reference exactly) ──
    def update_after_trade(self, pnl):
        """
        Reference Bro_gaurd_SILVERMINI.py exit logic:

        WIN:
          consecutive_win++, consecutive_loss = 0
          if pending_reward & boost_count > 0:
              position_size = min(dynamic_max_lots, position_size * 2)
              boost_count -= 1
          if consecutive_win == 3: boost_next_entry = True
          else: halve position_size

        LOSS:
          consecutive_loss++, consecutive_win = 0
          if consecutive_loss == 3: pending_reward, boost_count = True, 1
          elif consecutive_loss == 5: pending_reward, boost_count = True, 2
          double position_size
        """
        if pnl >= 0:
            self.stats.wins += 1
            self.stats.losses = 0     # consecutive_loss = 0

            if self.stats.pending_reward and self.stats.boost_count > 0:
                self.stats.position_size = min(
                    self.dynamic_max_lots(500000),  # fallback
                    self.stats.position_size * 2
                )
                self.stats.boost_count -= 1
                if self.stats.boost_count == 0:
                    self.stats.pending_reward = False
                    self.stats.losses = 0

            if self.stats.wins == 3:
                self.stats.boost_next_entry = True
            else:
                self.stats.position_size = max(1, self.stats.position_size // 2)

            logger.info(
                "WIN → position_size=%s wins=%s boost_next=%s",
                self.stats.position_size, self.stats.wins,
                self.stats.boost_next_entry
            )
        else:
            self.stats.losses += 1
            self.stats.wins = 0       # consecutive_win = 0

            if self.stats.losses == 3:
                self.stats.pending_reward = True
                self.stats.boost_count = 1
            elif self.stats.losses == 5:
                self.stats.pending_reward = True
                self.stats.boost_count = 2

            self.stats.position_size = max(1, self.stats.position_size * 2)

            logger.info(
                "LOSS → position_size=%s losses=%s pending_reward=%s boost_count=%s",
                self.stats.position_size, self.stats.losses,
                self.stats.pending_reward, self.stats.boost_count
            )

        self.stats.save()

    # ─── Calculate final lots (matches reference enter_now) ──
    def calculate_lots(self, cash_balance):
        """
        Reference:
          lots_by_cash  = usable // margin
          dyn_cap       = 50% cash // margin
          desired_cap   = dyn_cap if boost_next_entry else position_size
          lots          = min(lots_by_cash, desired_cap, dyn_cap)
        """
        reserve = 1000.0
        usable = max(0.0, cash_balance - reserve)
        lots_by_cash = max(int(usable // self.margin_per_lot), 1)
        dyn_cap = self.dynamic_max_lots(cash_balance)

        desired = dyn_cap if self.stats.boost_next_entry else self.stats.position_size
        final_lots = max(1, min(lots_by_cash, desired, dyn_cap))

        # Clear boost flag
        if self.stats.boost_next_entry:
            self.stats.boost_next_entry = False
            self.stats.save()

        logger.info(
            "Lot Calc → lots_by_cash=%s dyn_cap=%s desired=%s final=%s",
            lots_by_cash, dyn_cap, desired, final_lots
        )

        return final_lots

    # ─── Lot → Quantity ──────────────────────────────────────
    def lots_to_quantity(self, lots):
        return lots * self.LOT_QTY
