import time
import websockets
import socket
import asyncio
from decimal import Decimal
import json
import random
import uuid
import decimal
from datetime import timedelta, datetime
import numpy as np
import requests
from order_book import OrderBook
import asyncio, ssl, websockets

#todo kluge
#HIGHLY INSECURE
ssl_context = ssl.SSLContext()
ssl_context.check_hostname = False
ssl_context.verify_mode = ssl.CERT_NONE
url = 'http://www.btse.com/api/price/update/markprice'
def round_price(x,PRECISION_PRICE):
    return float(Decimal(x).quantize(PRECISION_PRICE))
def trunc_amount(x,PRECISION_AMOUNT):
    with decimal.localcontext() as c:
        #        c.rounding = 'ROUND_DOWN'
        return float(Decimal(x).quantize(PRECISION_AMOUNT))
class BTSE_funding_rate:
    ws_spot_endpoint = "wss://aws-ws.btse.com/ws/spot"
    ws_future_endpoint = "wss://ws.btse.com/ws/oss/futures"
    ws_trade_endpoint = 'wss://aws-ws.btse.com/ws/futures'
    Future_SeqNum = 0
    future_timestamp = 0
    timestamp = 0
    def __init__(self,config):
        self.config = config
        self.spot_data = {}
        self.future_data = {}
        self.funding_rate = []
        self.future_orderbook = OrderBook(max_depth=6)
        self.spot_last_price = 0
        self.future_last_price = 0
    async def ws_subscribe(self, endpoint, symbol):
        websocket = await websockets.connect(endpoint,ssl=ssl_context)
        await websocket.send(json.dumps({
            "op": "subscribe",
            "args": symbol
        }))
        return websocket
    def ob_snapshot(self, data,ob):
        if data['bids']:
            ob.bids = {Decimal(price):Decimal(size) for price, size in data['bids']}
        if data['asks']:
            ob.asks = {Decimal(price):Decimal(size) for price, size in data['asks']}
    def ob_update(self, data, ob):
        if data['bids']:
            for bid in data['bids']:
                if bid[1] != '0':
                    ob['bids'][Decimal(bid[0])] = Decimal(bid[1])
                else:
                    del ob['bids'][Decimal(bid[0])]
        if data['asks']:
            for ask in data['asks']:
                if ask[1] != '0':
                    ob['asks'][Decimal(ask[0])] = Decimal(ask[1])
                else:
                    del ob['asks'][Decimal(ask[0])]
    async def listen_trade(self, web):
        while True:
            await asyncio.sleep(0.1)
            resp = await web.recv()
            resp = json.loads(resp)
            print("trade history",resp)
            if 'event' in resp:
                    continue
            btse_trades = resp['data']

            btse_trades = btse_trades[0]
            print("btse_trades",btse_trades)
            if btse_trades['symbol'] == self.config.FUTURE_SYMBOL:
                self.future_last_price = btse_trades['price']
            if self.future_last_price != 0 and self.future_orderbook:
                    mark_price = np.median([self.future_orderbook.bids.index(0)[0],self.future_orderbook.asks.index(0)[0],self.future_last_price])
                    url = 'http://192.168.206.7:8888/api/price/update/markprice'
                    headers = {'Content-Type': 'application/json','authkey': '16d3e1bd5ead364924f8e8fe00d9c46ba333c970'}
                    m_price  = str(float(mark_price))
                    data = '{"market": "USDDPFC-USD","mark_price": '+m_price+'}'
                    x = requests.post(url,headers= headers, data = data)
                    print(x.content)
    async def listen_ws(self,web):
        while True :
                await asyncio.sleep(0.1)
                resp = await web.recv()
                resp = json.loads(resp)
                print(resp)
                if 'event' in resp:
                    continue
                data = resp['data']
                if data['type'] == "snapshot":
                        self.ob_snapshot(data,self.future_orderbook)
                        self.Future_SeqNum = data['seqNum']
                elif data['type'] == 'delta':
                        if data['prevSeqNum'] != self.Future_SeqNum:
                            raise ValueError("The Reference Symbol packages is lost , Resubscribe the websockets")
                        else :
                            self.Future_SeqNum = data['seqNum']
                            self.ob_update(data,self.future_orderbook)
                if self.future_last_price != 0 and self.future_orderbook:
                    mark_price = np.median([self.future_orderbook.bids.index(0)[0],self.future_orderbook.asks.index(0)[0],self.future_last_price])
                    url = 'http://192.168.206.7:8888/api/price/update/markprice'
                    headers = {'Content-Type': 'application/json','authkey': '16d3e1bd5ead364924f8e8fe00d9c46ba333c970'}
                    m_price  = str(float(mark_price))
                    data = '{"market": "USDDPFC-USD","mark_price": '+m_price+'}'
                    x = requests.post(url,headers= headers, data = data)
                    print(x.content)
    '''  
    async def calculate_funding_rate(self,):
        while True :
            await asyncio.sleep(0.5)
            #print(self.spot_last_price,self.future_last_price )
            print(self.future_orderbook.bids.index(0)[0],self.future_orderbook.asks.index(0)[0],self.future_last_price)
            if self.future_last_price != 0 :
                    mark_price = np.median([self.future_orderbook.bids.index(0)[0],self.future_orderbook.asks.index(0)[0],self.future_last_price])
                    
                    url = 'http://192.168.206.7:8888/api/price/update/markprice'
                    headers = {'Content-Type': 'application/json','authkey': '16d3e1bd5ead364924f8e8fe00d9c46ba333c970'}
                    m_price  = str(float(mark_price))
                    data = '{"market": "USDDPFC-USD","mark_price": '+m_price+'}'
                    x = requests.post(url,headers= headers, data = data)
                    print(x.content)
    '''                


    async def execute(self):
        while True:
            self.future_orderbook = OrderBook(max_depth=10)
            try:
                    future_topics = ["update:{}".format(self.config.FUTURE_SYMBOL)]
                    trade_future_topics = ["tradeHistoryApi:{}".format(self.config.FUTURE_SYMBOL)]
                    future_web = await self.ws_subscribe(self.ws_future_endpoint, future_topics)
                    trade_future_ws = await self.ws_subscribe(self.ws_trade_endpoint, trade_future_topics)
                    tasks =  []
                    task2 = asyncio.create_task(self.listen_ws(future_web))
                    await asyncio.sleep(0.1)
                    trade_future_task = asyncio.create_task(self.listen_trade(trade_future_ws))
                    await asyncio.sleep(0.1)
                    #funding_rate_task = asyncio.create_task(self.calculate_funding_rate())
                   # await asyncio.sleep(0.1)
                    tasks = [task2, trade_future_task]
                    #tasks = [task2,trade_spot_task,trade_future_task]
                    r = await asyncio.gather(*asyncio.all_tasks())
                    print(r)
            except Exception as e:
                    print(e)
                    self.future_orderbook = OrderBook(max_depth=6)
                    task2.cancel()
                    trade_future_task.cancel()
                    #trade_spot_task.cancel()
                    #funding_rate_task.cancel()
                    await asyncio.sleep(60)
                    continue

