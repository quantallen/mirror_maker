import time
import websockets
import socket
import asyncio
from decimal import Decimal
import json
import random
from log_format import SaveLog

HEDGE_MAPPING = {
    "BUY": "SELL",
    "SELL": "BUY"
}

class SelfTrader:
    ws_endpoint = "wss://wsaws.okx.com:8443/ws/v5/public"
    def __init__(self, BTSE, config):
        self.btse = BTSE
        self.config = config
        self.logger = SaveLog("Chun", "SelfTrade", "FODL", "./logs/")

    async def ws_subscribe(self, websocket, topics):
        await websocket.send(json.dumps({
            "op": "subscribe",
            "args": topics
        }))
        response = await websocket.recv()
            

    async def trade(self, okex_trades):
        orders = []
        for trade in okex_trades:
            print(trade)
            
            random_factor = random.uniform(self.config.RANDOM_FACTOR[0], self.config.RANDOM_FACTOR[1])
            price = Decimal(trade['px']).quantize(self.config.PRICE_PRECISION)
            size = float(trade['sz']) * random_factor
            size = Decimal(size).quantize(self.config.SIZE_PRECISION)
            side = trade['side'].upper()

            maker_order = self.btse.submit_order(
                self.config.MARKET_SYMBOL,
                side=HEDGE_MAPPING[side],
                price=price,
                size=size,
                order_type='LIMIT',
                post_only=False
            )
            orders.append(maker_order)
            taker_order = self.btse.submit_order(
                self.config.MARKET_SYMBOL,
                side=side,
                price=price,
                size=size,
                order_type='LIMIT',
                time_in_force='GTC'
            )
            orders.append(taker_order)

        result = await asyncio.gather(*orders)
        await self.btse.cancel_all_orders(self.config.MARKET_SYMBOL)
        for r in result:
            if r is not None and (r['status'] == 4 or r['status'] == 5):
                self.logger.fills("BTSE", r['orderID'], r['symbol'], "LIMIT", r['side'], r['price'], r['fillSize'])


    async def execute(self):
        while True:
            try:
                async with websockets.connect(self.ws_endpoint) as websocket:
                    topics = [
                        {"channel":"trades",
                         "instId":self.config.MARKET_SYMBOL
                        }
                    ]    
                    await self.ws_subscribe(websocket, topics)
                    while True:
                        try:
                            resp = await websocket.recv()
                            resp = json.loads(resp)
                            okex_trades = resp['data']
                            await self.trade(okex_trades=okex_trades)
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

