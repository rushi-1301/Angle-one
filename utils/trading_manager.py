import time
from accounts.models import User
from backtest_runner.models import Strategy
from utils.engine_manager import start_live_engine
from logzero import logger


class LiveTradingManager:
    """
    Manages live trading engines for all users with trading enabled.
    """
    def start(self):
        """
        Starts the live trading engines for users.
        """
        logger.info("Starting Live Trading Manager...")
        
        # Get all users with trading enabled
        users_with_trading_enabled = User.objects.filter(trading_enabled=True)
        strategies = Strategy.objects.all()
        
        if not users_with_trading_enabled:
            logger.warning("No users with trading_enabled=True found.")
            return

        if not strategies.exists():
            logger.warning("No strategies defined in the system. Cannot start engines.")
            return

        for user in users_with_trading_enabled:
            for strategy in strategies:
                try:
                    logger.info(f"Starting engine for user {user.id} and strategy {strategy.name} (token {strategy.symbol})")
                    start_live_engine(user.id, strategy.id)
                except Exception as e:
                    logger.error(f"Error starting engine for user {user.id} and strategy {strategy.name}: {e}")

    def stop(self):
        """
        Stops the live trading manager (not used in one-time script).
        """
        pass