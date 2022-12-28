from decimal import Decimal

class Config:
    MARKET_SYMBOL = "FODL-USDT"

    PRICE_PRECISION = Decimal('0.0000')

    SIZE_PRECISION = Decimal('0.000')

    START_LEVEL = 1

    MAX_LEVEL_PER_SIDE = 30

    # RANDOM_FACTOR defines the range of randomness of trade size from OKEX (i.e., from 80% - 100% trade size of OKEX)
    RANDOM_FACTOR = [4.0, 8.0]

    # Mean and Std of random trade volume following normal distribution
    RANDOM_TRADE_VOLUME = [150, 200]
    # Number of seconds to retry if connection to websocket is lost
    RETRY_TIME = 1
