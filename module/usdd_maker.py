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
from module.BTSEREST import hex_sign_msg

import decimal
HEDGE_MAPPING = {
    "BUY": "SELL",
    "SELL": "BUY"
}
def round_price(x,PRECISION_PRICE):
    return float(Decimal(x).quantize(PRECISION_PRICE))


def trunc_amount(x,PRECISION_AMOUNT):

    with decimal.localcontext() as c:
        return float(Decimal(x).quantize(PRECISION_AMOUNT))

class USDDMaker:
    fill_endpoint = f'wss://testws.btse.io/ws/spot'
    ws_endpoint = f'wss://aws-ws.btse.com/ws/spot'
    oss_endpoint = 'wss://ws.btse.com/ws/oss/spot'
    testnet_endpoint ='wss://testws.btse.io/ws/oss/spot'
    
    def __init__(self, BTSE, config):
        self.btse = BTSE
        self.config = config
        #self.logger = SaveLog("Chun", "SelfTrade", "FODL", "./")
        self.active_bids = {}
        self.active_asks = {}
        self.orderbook = OrderBook(max_depth=self.config.START_LEVEL + self.config.MAX_LEVEL_PER_SIDE)
        self.markets = [self.config.SPOT_SYMBOL, self.config.FUTURE_SYMBOL]
        self.orders = {}
        self.bid_ask_level = [self.config.START_LEVEL,self.config.START_LEVEL]
        self.latest_trade = ""
    async def ws_authentication(self):
        def _ws_authentication(data=None):
            nonce = str(int(time.time()*1000))
            data = json.dumps(data) if data else ''

            message = f'/ws/spot' + nonce + data
            signature = hex_sign_msg(self.btse.secret, message, 'sha384')

            return {
                'btse-api': self.btse.key,
                'btse-nonce': nonce,
                'btse-sign': signature
            }

        auth = _ws_authentication()
        websocket = await websockets.connect(self.fill_endpoint)
        await websocket.send(json.dumps({
            "op": "authKeyExpires",
            "args": [
                auth['btse-api'], auth['btse-nonce'], auth['btse-sign']
            ]
        }))
        response = await websocket.recv()
        print("Login to BTSE: {}".format(response)) 
    async def ws_subscribe(self, topics,endpoint):
        websocket = await websockets.connect(endpoint)
        await websocket.send(json.dumps({
            "op": "subscribe",
            "args": topics
        }))
        return websocket

    def ob_snapshot(self, data):
        if data['bids']:
            self.orderbook.bids = {Decimal(price):Decimal(size) for price, size in data['bids']}

        if data['asks']:
            self.orderbook.asks = {Decimal(price):Decimal(size) for price, size in data['asks']}

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
    def change_level(self,trades):
        p, s ,side  = 0, 0, None 
        side = trades['side']
        s = trades['size']
        print(side)
        if self.bid_ask_level[0] == 0 and self.bid_ask_level[1] == 6 :
            if side == 'SELL':
                self.bid_ask_level[0] += 1
                self.bid_ask_level[1] -= 1
        elif self.bid_ask_level[0] == 6 and self.bid_ask_level[1] == 0 :
            if side == 'BUY':
                self.bid_ask_level[0] -= 1
                self.bid_ask_level[1] += 1
        else :
            if side == 'BUY' :# and self.bid_ask_level[0] > 0 and self.bid_ask_level[1] > 0 : #and s >= self.orderbook.asks.index(self.bid_ask_level[1])[1] 
                print(self.orderbook.asks.index(self.bid_ask_level[1])[1])
                self.bid_ask_level[0] -= 1
                self.bid_ask_level[1] += 1
            if side == 'SELL' :#and self.bid_ask_level[0] > 0 and self.bid_ask_level[1] > 0: #and s >= self.orderbook.bids.index(self.bid_ask_level[0])[1]
                print(side)
                self.bid_ask_level[0] += 1
                self.bid_ask_level[1] -= 1
               
        print(self.bid_ask_level) 
    async def order_fill(self,fill_web):
        while True :
                #print("order in")
                r = await self.btse.get_trades_histoty(self.config.FUTURE_SYMBOL)
                latest_trade = r[0]
                if latest_trade != self.latest_trade :
                    self.latest_trade = latest_trade
                    self.change_level(self.latest_trade)
                '''
                resp = await fill_web.recv()
                resp = json.loads(resp)
                print(resp)
                if 'event' in resp:
                    continue 
                if resp['topics'] == 'fills':
                    self.trades = resp['data']
                    print("trade information :",self.trades)
                    self.change_level(self.trades)
                '''
                    
    async def mirror(self, data):
        #asyncio.sleep(1)
        order_tasks = []
        ob = self.orderbook.to_dict()
        for idx in range(0, self.bid_ask_level[0] - 1):
            del ob['bid'][self.orderbook.bids.index(idx)[0]]
        for idx in range(0,self.bid_ask_level[1] - 1):
            del ob['ask'][self.orderbook.asks.index(idx)[0]]

        if data['bids']:
            for price_str, size_str in data['bids']:
                price = Decimal(price_str)
                size = Decimal(size_str)
                
                if price not in ob['bid']:
                    continue                
                #random_factor = random.uniform(self.config.RANDOM_FACTOR[0], self.config.RANDOM_FACTOR[1])
                #size = float(size_str) * random_factor
                price = price.quantize(self.config.PRICE_PRECISION)
                size = size.quantize(self.config.SIZE_PRECISION)

                #print("bid data :", price , size)
                if size > 0.0:
                    if price in self.active_bids:
                        order_tasks.append(self.btse.amend_order(
                            symbol=self.config.FUTURE_SYMBOL,
                            cl_order_id=self.active_bids[price],
                            type='ALL',
                            price=price,
                            size=size
                        ))
                    else:
                        cl_order_id = uuid.uuid4().hex
                        order_tasks.append(self.btse.submit_order(
                            symbol=self.config.FUTURE_SYMBOL,
                            cl_order_id=cl_order_id,
                            side="BUY",
                            price=price,
                            size=size
                        ))
                        self.active_bids[price] = cl_order_id

        if data['asks']:
            for price_str, size_str  in data['asks']:
                price = Decimal(price_str)
                size = Decimal(size_str)
                if price not in ob['ask']:
                    continue                
                price = price.quantize(self.config.PRICE_PRECISION)
                size = size.quantize(self.config.SIZE_PRECISION)


                if size > 0.0:
                    if price in self.active_asks:
                        order_tasks.append(self.btse.amend_order(
                            symbol=self.config.FUTURE_SYMBOL,
                            cl_order_id=self.active_asks[price],
                            type='ALL',
                            price=price,
                            size=size
                        ))
                    else:

                        cl_order_id = uuid.uuid4().hex
                        order_tasks.append(self.btse.submit_order(
                            symbol=self.config.FUTURE_SYMBOL,
                            cl_order_id=cl_order_id,
                            side="SELL",
                            price=price,
                            size=size
                        ))
                        self.active_asks[price] = cl_order_id

        del_list = []
        for price in self.active_asks:
            #print(price)
            #print(ob['ask'])
            if price not in ob['ask']:
                #print("why in !!!!!,",price)
                order_tasks.append(
                    self.btse.cancel_order(self.config.FUTURE_SYMBOL, cl_order_id=self.active_asks[price])
                )
                del_list.append(price)

        for p in del_list:
            del self.active_asks[p]

        del_list = []
        for price in self.active_bids:
            if price not in ob['bid']:
                order_tasks.append(
                    self.btse.cancel_order(self.config.FUTURE_SYMBOL, cl_order_id=self.active_bids[price])
                )
                del_list.append(price)
        for p in del_list:
            del self.active_bids[p]

        r = await asyncio.gather(*order_tasks)
        #print(r)
    async def mirror_ob(self, ws):
        while True:
            resp = await ws.recv()
            resp = json.loads(resp)
            #print(resp)
            if 'event' in resp:
                    continue
            data = resp['data']
            if data['type'] == "snapshot":
                self.ob_snapshot(data)
                self.SeqNum = data['seqNum']
            elif data['type'] == 'delta':
                if data['prevSeqNum'] != self.SeqNum: 
                    raise ValueError("The Reference Symbol packages is lost , Resubscribe the websockets")
                else :
                    self.SeqNum = data['seqNum']
                    self.ob_update(data)
            await self.mirror(data)
            
    async def trade(self, btse_trades):
        orders = []
        if len(self.orderbook) <= 10:
            return
        for trade in btse_trades:
            #print(trade)
            #market = "BTC-USD"
            random_factor = random.uniform(self.config.RANDOM_FACTOR[0], self.config.RANDOM_FACTOR[1])
            price = Decimal(self.orderbook.asks.index(self.config.START_LEVEL - 1)[0] - Decimal(0.0001)).quantize(self.config.PRICE_PRECISION)
            size = float(trade['size']) * random_factor
            size = Decimal(size).quantize(self.config.SIZE_PRECISION)
            side = trade['side'].upper()

            price = price + Decimal(0.0001) if HEDGE_MAPPING[side] == "BUY" else price
            #print(price,size,side)
            maker_cl_order_id = uuid.uuid4().hex
            self.orders[maker_cl_order_id] = self.config.FUTURE_SYMBOL
            maker_order = self.btse.submit_order(
                symbol=self.config.FUTURE_SYMBOL,
                cl_order_id=maker_cl_order_id,
                side=HEDGE_MAPPING[side],
                price=price,
                size=size,
                order_type='LIMIT',
                post_only=False
            )
            #print(maker_order)
            orders.append(maker_order)
            
            #market = "BTC-USD"
            taker_cl_order_id = uuid.uuid4().hex
            self.orders[taker_cl_order_id] = self.config.FUTURE_SYMBOL
            price = price + Decimal(0.0001) if side == "BUY" else price
            taker_order = self.btse.submit_order(
                symbol=self.config.FUTURE_SYMBOL,
                cl_order_id=taker_cl_order_id,
                side=side,
                price=price,
                size=size,
                order_type='LIMIT',
                time_in_force='GTC'
            )
            #print(price)
            orders.append(taker_order)
            
        try:
            result = await asyncio.gather(*orders)
            #print(result)
        except:
            pass
        #await self.btse.cancel_all_orders(self.config.MARKET_SYMBOL)
        for r in result:
            if r is not None and (r['status'] == 4 or r['status'] == 5):
                pass
                #self.logger.fills("BTSE", r['orderID'], r['symbol'], "LIMIT", r['side'], r['price'], r['fillSize'])

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
            if 'event' in resp:
                    continue
            btse_trades = resp['data']
            await self.trade(btse_trades=btse_trades)

    async def execute(self):
        await self.btse.cancel_all_orders(self.markets[0])
        await self.btse.cancel_all_orders(self.markets[1])

        while True:
            try:
                self.orderbook = OrderBook( max_depth=self.config.START_LEVEL + self.config.MAX_LEVEL_PER_SIDE)
                ob_topics = ['update:{}_0'.format(self.markets[0]) ]                   
                
                print(ob_topics)
                
                trade_topics = ["tradeHistoryApi:{}".format(self.markets[0])]
                print(trade_topics)
                fill_topics = ['fills']
                await self.ws_authentication()
                ob_ws = await self.ws_subscribe(ob_topics,self.oss_endpoint)
                trade_ws = await self.ws_subscribe(trade_topics,self.ws_endpoint)
                fill_ws = await self.ws_subscribe(fill_topics, self.fill_endpoint)
                mirror_task = asyncio.create_task(self.mirror_ob(ob_ws))
                trade_task = asyncio.create_task(self.self_trade(trade_ws))
                fill_task = asyncio.create_task(self.order_fill(fill_ws))
                tasks = [mirror_task,trade_task,fill_task]
                await asyncio.gather(*tasks)

                #await mirror_queue.join()
                
            except Exception as e:
                    print(e)
                    mirror_task.cancel()
                    trade_task.cancel()
                    fill_task.cancel()
                    #self.logger.debug(e)
                    #continue
                