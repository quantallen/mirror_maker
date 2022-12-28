import time
import websockets
import socket
import asyncio
from decimal import Decimal
import json
import random
from log_format import SaveLog
import datetime as dt

HEDGE_MAPPING = {
    "BUY": "SELL",
    "SELL": "BUY"
}

class BookMover:
    ws_endpoint = "wss://wsaws.okx.com:8443/ws/v5/public"
    def __init__(self, BTSE, config):
        self.btse = BTSE
        self.order = None
        self.config = config
        self.logger = SaveLog("Stan", "BookMover", "FODL", "./logs/")

    async def ws_subscribe(self, websocket, topics):
        await websocket.send(json.dumps({
            "op": "subscribe",
            "args": topics
        }))
        response = await websocket.recv()
            

    async def amend(self, books):
        for book in books:
            print(self.order['price'])
            print(self.order['size'])
            print(book)
            if self.order['price'] == book[0] and self.order['size'] != book[1]:
                print(dt.datetime.now().strftime("%Y-%M-%D %H:%M:%S"))
                order = await self.btse.amend_order(self.config.BTSE_SYMBOL, SIZE, book[1], order_id = self.order['orderID'])
                if order is not None:
                    self.order = order
                    print(order)
                    break

    async def move(self, okex_book):
        random_factor = random.uniform(self.config.RANDOM_FACTOR[0], self.config.RANDOM_FACTOR[1])
        price = Decimal(okex_book[0]).quantize(self.config.PRICE_PRECISION)
        size = float(okex_book[1]) * random_factor
        size = Decimal(size).quantize(self.config.SIZE_PRECISION)
        if self.config.SIDE == "bids":
            side = "BUY"
        else:
            side = "SELL"

        order = await self.btse.submit_order(
            self.config.BTSE_SYMBOL,
            side=side,
            price=price,
            size=size,
            order_type='LIMIT',
            post_only=True
        )
        if order is not None:
            self.order = order
            print(order)

    async def execute(self):
        while True:
            try:
                async with websockets.connect(self.ws_endpoint) as websocket:
                    topics = [
                        {"channel":"books",
                         "instId":self.config.MARKET_SYMBOL
                        }
                    ]    
                    await self.ws_subscribe(websocket, topics)
                    while True:
                        try:
                            resp = await websocket.recv()
                            resp = json.loads(resp)
                            okex_book = resp['data'][0][self.config.SIDE]
                            if self.order is None:
                                if len(okex_book) > self.config.LEVEL:
                                    await self.move(okex_book=okex_book[self.config.LEVEL])
                            else:
                                await self.amend(okex_book)
                        except websockets.exceptions.ConnectionClosed as e:
                            print(e)
                            break

            except socket.gaierror:
                self.logger.debug(
                    'Socket error - retrying connection in {} sec (Ctrl-C to quit)'.format(self.config.RETRY_TIME))

                await asyncio.sleep(self.config.RETRY_TIME)
                continue
            except ConnectionRefusedError:
                self.logger.debug(
                    'Nobody seems to listen to this endpoint. Please check the URL.')
                self.logger.debug(
                    'Retrying connection in {} sec (Ctrl-C to quit)'.format(self.config.RETRY_TIME))
                await asyncio.sleep(self.config.RETRY_TIME)
                continue

