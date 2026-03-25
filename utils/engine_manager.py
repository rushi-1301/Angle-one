import threading

from logzero import logger

from utils.live_data_runner import candle_and_strategy_thread, db_writer_thread, UserEngine, websocket_thread
from backtest_runner.models import Strategy

ENGINES = {}   # "user_id_strategy_id" → engine
user_engines = {}  # Global dictionary

def start_live_engine(user_id, strategy_id):
    engine_key = f"{user_id}_{strategy_id}"
    if engine_key in ENGINES and ENGINES[engine_key].running.is_set():
        logger.info("Engine already running for user %s, strategy %s", user_id, strategy_id)
        return

    try:
        strategy = Strategy.objects.get(id=strategy_id)
    except Strategy.DoesNotExist:
        logger.error(f"Strategy {strategy_id} not found")
        return

    engine = UserEngine(user_id, strategy_id)
    ENGINES[engine_key] = engine

    logger.info(f"Starting engine for user {user_id}, strategy {strategy_id}")

    engine.thread_ws = threading.Thread(
        target=websocket_thread,
        args=(engine,),
        daemon=True,
        name=f"ws-{user_id}-{strategy_id}"
    )
    engine.thread_ws.start()

    engine.thread_db = threading.Thread(
        target=db_writer_thread,
        args=(engine,),
        daemon=True,
        name=f"db-{user_id}-{strategy_id}"
    )
    engine.thread_db.start()

    engine.thread_candle = threading.Thread(
        target=candle_and_strategy_thread,
        args=(engine,),
        daemon=True,
        name=f"candle-{user_id}-{strategy_id}"
    )
    engine.thread_candle.start()

    logger.info(f"Engine started for user {user_id}, strategy {strategy_id}")


def stop_live_engine(user_id, strategy_id=None):
    if strategy_id:
        engine_key = f"{user_id}_{strategy_id}"
        if engine_key in ENGINES:
            engine = ENGINES[engine_key]
            engine.stop()
            del ENGINES[engine_key]
            print(f"Stopped engine for user {user_id}, strategy {strategy_id}")
        else:
            print(f"No live engine found for user {user_id}, strategy {strategy_id}")
    else:
        # Stop all engines for this user
        keys_to_remove = []
        for key, engine in ENGINES.items():
            if key.startswith(f"{user_id}_"):
                engine.stop()
                keys_to_remove.append(key)
                print(f"Stopped engine {key} for user {user_id}")
        for key in keys_to_remove:
            del ENGINES[key]