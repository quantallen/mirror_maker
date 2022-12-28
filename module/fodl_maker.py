import time
import websockets
import socket
import asyncio
from decimal import Decimal
import json
import random
from log_format import SaveLog
import uuid
from order_book import OrderBook
import numpy as np
import traceback
from datetime import datetime as dt

HEDGE_MAPPING = {
    "BUY": "SELL",
    "SELL": "BUY"
}

class FODLMaker:
    ws_endpoint = "wss://wsaws.okx.com:8443/ws/v5/public"

    def __init__(self, BTSE, config):
        self.btse = BTSE
        self.config = config
        self.logger = SaveLog("Chun", "SelfTrade", "FODL", "./")
        self.active_bids = {}
        self.active_asks = {}
        self.orderbook = OrderBook(max_depth=self.config.START_LEVEL + self.config.MAX_LEVEL_PER_SIDE)
        self.orders = {}

    async def ws_subscribe(self, topics):
        websocket = await websockets.connect(self.ws_endpoint)
        await websocket.send(json.dumps({
            "op": "subscribe",
            "args": topics
        }))
        response = await websocket.recv()
        return websocket

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
                    if Decimal(bid[0]) in self.orderbook.bids:
                        del self.orderbook.bids[Decimal(bid[0])]
        
        if data['asks']:
            for ask in data['asks']:
                if ask[1] != '0':
                    self.orderbook['asks'][Decimal(ask[0])] = Decimal(ask[1])
                else:
                    if Decimal(ask[0]) in self.orderbook.asks:
                        del self.orderbook.asks[Decimal(ask[0])]

    async def mirror(self, data):
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
        sdf = 0

    async def mirror_ob(self, ws):
        while True:
            resp = await ws.recv()
            resp = json.loads(resp)
            data = resp['data'][0]
            if resp['action'] == "snapshot":
                self.ob_snapshot(data)
            elif resp['action'] == 'update':
                self.ob_update(data)

            await self.mirror(data)
            
    async def trade(self, okex_trades):
        if len(self.orderbook) <= 10:
            return

        await self.execute_trade(okex_trades=okex_trades, market="FODL-USDT")
        await self.execute_trade(okex_trades=okex_trades, market="FODL-USD")

    async def execute_trade(self, okex_trades, market):
        orders = []
        for trade in okex_trades:
            print(trade)

            random_factor = random.uniform(self.config.RANDOM_FACTOR[0], self.config.RANDOM_FACTOR[1])
            price = Decimal(self.orderbook.asks.index(self.config.START_LEVEL - 1)[0] - Decimal(0.0001)).quantize(self.config.PRICE_PRECISION)
            size = np.clip(float(trade['sz']), 30.0, 10000.0) * random_factor
            size = Decimal(size).quantize(self.config.SIZE_PRECISION)
            side = trade['side'].upper()
            price = price + Decimal(0.0001) if HEDGE_MAPPING[side] == "BUY" else price
            maker_cl_order_id = uuid.uuid4().hex
            self.orders[maker_cl_order_id] = market
            maker_order = self.btse.submit_order(
                market,
                cl_order_id=maker_cl_order_id,
                side=HEDGE_MAPPING[side],
                price=price,
                size=size,
                order_type='LIMIT',
                post_only=False
            )
            orders.append(maker_order)

            taker_cl_order_id = uuid.uuid4().hex
            self.orders[taker_cl_order_id] = market
            price = price + Decimal(0.0001) if side == "BUY" else price
            taker_order = self.btse.submit_order(
                market,
                cl_order_id=taker_cl_order_id,
                side=side,
                price=price,
                size=size,
                order_type='LIMIT',
                time_in_force='GTC'
            )
            orders.append(taker_order)

        try:
            result = await asyncio.gather(*orders)
        except:
            pass
        #await self.btse.cancel_all_orders(self.config.MARKET_SYMBOL)
        for r in result:
            if r is not None and (r['status'] == 4 or r['status'] == 5):
                self.logger.fills("BTSE", r['orderID'], r['symbol'], "LIMIT", r['side'], r['price'], r['fillSize'])

        orders = []
        for id, market in self.orders.items():
            orders.append(
                self.btse.cancel_order(market, cl_order_id=id)
            )
        self.orders = {}
        result = await asyncio.gather(*orders)

    async def self_trade(self, ws):
        while True:
            resp = await ws.recv()
            resp = json.loads(resp)
            okex_trades = resp['data']
            await self.trade(okex_trades=okex_trades)

    async def random_self_trade(self):
        while True:
            points = sorted(random.sample(range(60), 3))
            idx = 0
            while True:
                if idx >= len(points):
                    break
                await asyncio.sleep(0.1)
                current_sec = dt.now().second
                if current_sec == points[idx]:
                    sz = np.random.normal(self.config.RANDOM_TRADE_VOLUME[0], self.config.RANDOM_TRADE_VOLUME[1], 1)[0]
                    fake = [{'instId': 'FODL-USDT', 
                    'tradeId': '1888232', 
                    'px': '0.0604', 
                    'sz': f'{sz:.2f}', 
                    'side': 'buy', 
                    'ts': '1654670172312'}]
                    await self.trade(okex_trades=fake)
                    idx +=1

    async def reload_orderbook(self):
        await asyncio.sleep(60)
        raise Exception('reloading orderbook')



    async def execute(self):
        await self.btse.cancel_all_orders("FODL-USDT")
        await self.btse.cancel_all_orders("FODL-USD")

        while True:
            try:
                self.orderbook = OrderBook(max_depth=self.config.START_LEVEL + self.config.MAX_LEVEL_PER_SIDE)
                ob_topics = [
                    {"channel":"books",
                     "instId":"FODL-USDT"
                    }
                ]
                trade_topics = [
                        {"channel":"trades",
                         "instId":"FODL-USDT"
                        }
                    ]

                ob_ws = await self.ws_subscribe(ob_topics)
                trade_ws = await self.ws_subscribe(trade_topics)
                mirror_task = asyncio.create_task(self.mirror_ob(ob_ws))
                trade_task = asyncio.create_task(self.self_trade(trade_ws))
                random_trade = asyncio.create_task(self.random_self_trade())
                reload = asyncio.create_task(self.reload_orderbook())

                await asyncio.gather(
                    mirror_task,
                    trade_task,
                    random_trade,
                    reload
                )
                #await mirror_queue.join()

            except Exception as e:
                print(traceback.format_exc())
                #print(e)
                mirror_task.cancel()
                trade_task.cancel()
                random_trade.cancel()
                reload.cancel()
                #self.logger.debug(e)
                continue