import time
import websockets
import socket
import asyncio
from decimal import Decimal
import json
import random
from log_format import SaveLog
from order_book import OrderBook
import uuid


class MirrorOrderbook:
    ws_endpoint = "wss://wsaws.okx.com:8443/ws/v5/public"

    def __init__(self, BTSE, config):
        self.btse = BTSE
        self.config = config
        #self.logger = SaveLog("Chun", "MirrorOrderbook", "FODL", "./logs/")
        self.active_bids = {}
        self.active_asks = {}
        self.orderbook = OrderBook(checksum_format='OKEX', max_depth=self.config.START_LEVEL + self.config.MAX_LEVEL_PER_SIDE)


    async def ws_subscribe(self, websocket, topics):
        await websocket.send(json.dumps({
            "op": "subscribe",
            "args": topics
        }))
        response = await websocket.recv()
        ssdf = 0
     
    async def update(self, data):
        order_tasks = []
        ob = self.orderbook.to_dict()
        for idx in range(0, self.config.START_LEVEL - 1):
            del ob['bid'][self.orderbook.bids.index(idx)[0]]
            del ob['ask'][self.orderbook.asks.index(idx)[0]]

        if data['bids']:
            for price_str, size_str, _, _ in data['bids']:
                price = Decimal(price_str)
                size = Decimal(size_str)
                if price not in ob['bid']:
                    continue
                price = price.quantize(self.config.PRICE_PRECISION)
                size = size.quantize(self.config.SIZE_PRECISION)

                if size > 0.0:
                    if price in self.active_bids:
                        order_tasks.append(self.btse.amend_order(
                            symbol=self.config.MARKET_SYMBOL,
                            cl_order_id=self.active_bids[price],
                            type='ALL',
                            price=price,
                            size=size
                        ))
                    else:
                        cl_order_id = uuid.uuid4().hex
                        order_tasks.append(self.btse.submit_order(
                            symbol=self.config.MARKET_SYMBOL,
                            cl_order_id=cl_order_id,
                            side="BUY",
                            price=price,
                            size=size
                        ))
                        self.active_bids[price] = cl_order_id

        if data['asks']:
            for price, size, _, _ in data['asks']:
                price = Decimal(price)
                size = Decimal(size)
                if price not in ob['ask']:
                    continue
                price = price.quantize(self.config.PRICE_PRECISION)
                size = size.quantize(self.config.SIZE_PRECISION)
                if size > 0.0:
                    if price in self.active_asks:
                        order_tasks.append(self.btse.amend_order(
                            symbol=self.config.MARKET_SYMBOL,
                            cl_order_id=self.active_asks[price],
                            type='ALL',
                            price=price,
                            size=size
                        ))
                    else:
                        cl_order_id = uuid.uuid4().hex
                        order_tasks.append(self.btse.submit_order(
                            symbol=self.config.MARKET_SYMBOL,
                            cl_order_id=cl_order_id,
                            side="SELL",
                            price=price,
                            size=size
                        ))
                        self.active_asks[price] = cl_order_id

        del_list = []
        for price in self.active_asks:
            if price not in ob['ask']:
                order_tasks.append(
                    self.btse.cancel_order(self.config.MARKET_SYMBOL, cl_order_id=self.active_asks[price])
                )
                del_list.append(price)
        for p in del_list:
            del self.active_asks[p]

        del_list = []
        for price in self.active_bids:
            if price not in ob['bid']:
                order_tasks.append(
                    self.btse.cancel_order(self.config.MARKET_SYMBOL, cl_order_id=self.active_bids[price])
                )
                del_list.append(price)
        for p in del_list:
            del self.active_bids[p]

        await asyncio.gather(*order_tasks)

    def ob_snapshot(self, data):
        if data['bids']:
            self.orderbook.bids = {Decimal(price):Decimal(size) for price, size, _, _ in data['bids']}

        if data['asks']:
            self.orderbook.asks = {Decimal(price):Decimal(size) for price, size, _, _ in data['asks']}

    def ob_update(self, data):
        if data['bids']:
            for bid in data['bids']:
                if bid[1] != '0':
                    self.orderbook['bids'][Decimal(bid[0])] = Decimal(bid[1])
                else:
                    del self.orderbook.bids[Decimal(bid[0])]
        
        if data['asks']:
            for ask in data['asks']:
                if ask[1] != '0':
                    self.orderbook['asks'][Decimal(ask[0])] = Decimal(ask[1])
                else:
                    del self.orderbook.asks[Decimal(ask[0])]

    async def execute(self):
        await self.btse.cancel_all_orders(self.config.MARKET_SYMBOL)
        
        while True:
            try:
                async with websockets.connect(self.ws_endpoint) as websocket:
                    topics = [
                        {"channel":"books",
                         "instId":"FODL-USDT"
                        }
                    ]    
                    await self.ws_subscribe(websocket, topics)
                    while True:
                        try:
                            resp = await websocket.recv()
                            resp = json.loads(resp)
                            data = resp['data'][0]
                            if resp['action'] == "snapshot":
                                self.ob_snapshot(data)

                            elif resp['action'] == 'update':
                                self.ob_update(data)
                    
                            await self.update(data)
                            
                        except Exception as e:
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
