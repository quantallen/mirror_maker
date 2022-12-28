from distutils.log import error
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
import decimal
import math


def round_price(x,PRECISION_PRICE):
    return float(Decimal(x).quantize(PRECISION_PRICE))


def trunc_amount(x,PRECISION_AMOUNT):

    with decimal.localcontext() as c:
        return float(Decimal(x).quantize(PRECISION_AMOUNT))

class MirrorOrderbook:
    #ws_endpoint = "wss://wsaws.okx.com:8443/ws/v5/public"
    testnet_endpoint = f'wss://testws.btse.io/ws/oss/futures'
    production_endpoint = f'wss://ws.btse.com/ws/oss/futures'
    staging_endpoint = f'wss://ws.oa.btse.io/ws/futures'
    SeqNum = 0

    def __init__(self, BTSE, config):
        self.btse = BTSE
        self.config = config
        #self.logger = SaveLog("Chun", "MirrorOrderbook", "FODL", "./logs/")
        self.active_bids = {}
        self.active_asks = {}
        self.orderbook = OrderBook( max_depth=self.config.START_LEVEL + self.config.MAX_LEVEL_PER_SIDE)


    async def ws_subscribe(self, websocket, topics):
        await websocket.send(json.dumps({
            "op": "subscribe",
            "args": topics
        }))
        #response = await websocket.recv()
        #ssdf = 0
     
    async def update(self, data):

        order_tasks = []
        ob = self.orderbook.to_dict()
        for idx in range(0, self.config.START_LEVEL - 1):
            del ob['bid'][self.orderbook.bids.index(idx)[0]]
            del ob['ask'][self.orderbook.asks.index(idx)[0]]
        
        if data['bids']:
            for price_str, size_str in ob['bid'].items():#data['bids']:
                print("************************")

                print(price_str)
                price = Decimal(price_str)
                #size = Decimal(size_str)
                
                if price not in ob['bid']:
                    continue                
                
                random_factor = random.uniform(self.config.RANDOM_FACTOR[0], self.config.RANDOM_FACTOR[1])
                size = math.ceil(float(size_str) * random_factor)
                size = Decimal(str(size))
                print(size)
                price = price.quantize(self.config.PRICE_PRECISION)
                size = size.quantize(self.config.SIZE_PRECISION)
                print(price)
                print("************************")
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
            for price_str, size_str  in ob['ask'].items():#data['asks']:
                print("************************")
                print(price_str)
                price = Decimal(price_str)
                #size = Decimal(size_str)
                
                if price not in ob['ask']:
                    continue  
                              
                random_factor = random.uniform(self.config.RANDOM_FACTOR[0], self.config.RANDOM_FACTOR[1])
                size = math.ceil(float(size_str) * random_factor)
                size = Decimal(size)
                print(size)
                price = price.quantize(self.config.PRICE_PRECISION)
                size = size.quantize(self.config.SIZE_PRECISION)
                print(price)
                print("************************")
                if size > 0.0:
                    if price in self.active_asks:
                        #print("inininininni")
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
            #print(price)
            if price not in ob['ask']:
                print("innnnnn")
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
        print("等三小")
        r = await asyncio.gather(*order_tasks)
        print(r)
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

    async def execute(self):
        print("山光所有檔案")
        '''
        await self.btse.submit_order(
                            symbol=self.config.MARKET_SYMBOL,
                            cl_order_id="12334",
                            side="BUY",
                            price=19174,
                            size=1
                        )
        
        '''
        await self.btse.cancel_all_orders(self.config.MARKET_SYMBOL)
        
        #print(sd)
        
        while True:
            try:
                
                async with websockets.connect(self.production_endpoint,ping_interval=None) as websocket:
                    topics = ["update:{}".format(self.config.BTSE_SYMBOL) ]  
                    await self.ws_subscribe(websocket, topics)
                    while True:
                            resp = await websocket.recv()
                            resp = json.loads(resp)

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
                            #print(self.orderbook)
                    
                            await self.update(data)

            except Exception as e :
                print(e)
                await asyncio.sleep(60)
                self.orderbook = OrderBook( max_depth=self.config.START_LEVEL + self.config.MAX_LEVEL_PER_SIDE)
                continue
            