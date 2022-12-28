from decimal import Decimal

class Config:

    SPOT_SYMBOL = 'USDD-USD'

    FUTURE_SYMBOL = "USDD-USD"

    PRICE_PRECISION = Decimal('0.00000')

    SIZE_PRECISION = Decimal('0.000')

    START_LEVEL = 3

    MAX_LEVEL_PER_SIDE = 5

    # RANDOM_FACTOR defines the range of randomness of trade size from OKEX (i.e., from 80% - 100% trade size of OKEX)
    RANDOM_FACTOR = [1, 1]

    # Number of seconds to retry if connection to websocket is lost
    RETRY_TIME = 1

    SIDE = "bids"

    LEVEL = 5
