
from datetime import datetime
import logging
import json
from tabnanny import check


class SaveLog:
    logger = logging.getLogger(__name__)

    def __init__(self, pilot, strategy, token, path):
        self.pilot = pilot
        self.strategy = strategy
        self.token = token
        self.path = path
        self.last = datetime.today().strftime("%Y%m%d")
        logging.basicConfig(level=logging.INFO,
                            filemode='a',
                            format='{"time": "%(asctime)s.%(msecs)03d","level": "%(levelname)s", "msg":%(message)s}',
                            datefmt='%Y-%m-%d %H:%M:%S',
                            filename=f'{self.path}{self.strategy}{self.token}_{self.pilot}_' +
                            self.last + '.log',
                            )

    def check_time(self):
        newest = datetime.today().strftime("%Y%m%d")
        if self.last != newest:
            self.update_date(newest)
            self.last = newest

    def update_date(self, date):
        for handler in logging.root.handlers[:]:
            logging.root.removeHandler(handler)
        logging.basicConfig(level=logging.INFO,
                            filemode='a',
                            format='{"time": "%(asctime)s.%(msecs)03d","level": "%(levelname)s", "msg":%(message)s}',
                            datefmt='%Y-%m-%d %H:%M:%S',
                            filename=f'{self.path}{self.strategy}{self.token}_{self.pilot}_' +
                            date + '.log',
                            )

    def fills(self, exchange, orderId, symbol, type, side, price, size):
        self.check_time()
        msg = json.dumps({"exchange": exchange, "orderId": orderId, "symbol": symbol, "type": type,
                          "side": side, "price": price, "size": size})
        self.logger.info(msg)

    def debug(self, d):
        self.check_time()
        self.logger.debug(d)

    def info(self, i):
        self.check_time()
        self.logger.info(i)

    def warning(self, w):
        self.check_time()
        self.logger.warning(w)

    def error(self, e):
        self.check_time()
        self.logger.error(e)

    def critical(self, c):
        self.check_time()
        self.logger.critical(c)


# log = SaveLog("jack", "Fatfinger", "Test", "")
# msg = json.dumps({"exchange": "exchange", "orderId": 'orderId', "symbol": "symbol", "type": "LIMIT",
#                   "side": 'side', "price": 0.003520, "size": "size"})
# log.info(msg)
