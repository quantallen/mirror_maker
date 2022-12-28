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
import ssl
import traceback
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
        self.future_orderbook = OrderBook(max_depth=50)
        self.spot_last_price = 0
        self.future_last_price = 0
    async def ws_subscribe(self, endpoint, symbol):
        websocket = await websockets.connect(endpoint,ssl=ssl_context)
        await websocket.send(json.dumps({
            "op": "subscribe",
            "args": symbol
        }))
        return websocket
    def ob_snapshot(self, data):
        if data['bids']:
            self.future_orderbook.bids = {Decimal(price):Decimal(size) for price, size in data['bids']}
        if data['asks']:
            self.future_orderbook.asks = {Decimal(price):Decimal(size) for price, size in data['asks']}
    def ob_update(self, data):
        if data['bids']:
            for bid in data['bids']:
                if bid[1] != '0':
                    self.future_orderbook['bids'][Decimal(bid[0])] = Decimal(bid[1])
                else:
                    del self.future_orderbook['bids'][Decimal(bid[0])]
        if data['asks']:
            for ask in data['asks']:
                if ask[1] != '0':
                    self.future_orderbook['asks'][Decimal(ask[0])] = Decimal(ask[1])
                else:
                    del self.future_orderbook['asks'][Decimal(ask[0])]
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
            if btse_trades['symbol'] == self.config.SPOT_SYMBOL:
                print("in")
                self.spot_last_price = btse_trades['price']
            if btse_trades['symbol'] == self.config.FUTURE_SYMBOL:
                self.future_last_price = btse_trades['price']
            print(self.future_last_price)
            #print("btse_trades",btse_trades)
    async def listen_index(self, web):
        while True:
            await asyncio.sleep(0.1)
            resp = await web.recv()
            resp = json.loads(resp)
            #print("trade history",resp)

            if 'event' in resp:
                    continue
            
            btse_index= resp['data']['USDDPFC_1']
            self.spot_last_price = btse_index['price']
            #print("btse_trades",btse_trades)
            
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
                        self.ob_snapshot(data)
                        self.Future_SeqNum = data['seqNum']
                elif data['type'] == 'delta':
                        if data['prevSeqNum'] != self.Future_SeqNum:
                            raise ValueError("The Reference Symbol packages is lost , Resubscribe the websockets")
                        else :
                            self.Future_SeqNum = data['seqNum']
                            self.ob_update(data)
                self.timestamp = datetime.fromtimestamp(resp['data']['timestamp']/1000)
                self.timestamp = self.timestamp.strftime("%Y-%m-%d %H:%M:%S")
                self.timestamp = datetime.now()
                print("現在時間:",datetime.now())
                if self.future_timestamp == 0 :
                        self.future_timestamp = self.timestamp
                print(self.spot_last_price,self.future_last_price)
                
    async def calculate_funding_rate(self,):
        while True :
            await asyncio.sleep(0.1)
            #print(self.spot_last_price,self.future_last_price )
            if self.spot_last_price != 0 and self.future_last_price != 0 :
                    mark_price = np.median([self.future_orderbook.bids.index(0)[0],self.future_orderbook.asks.index(0)[0],self.future_last_price])
                    #print(mark_price,self.spot_last_price)
                    if self.spot_last_price != 0 :
                        premium = (float(mark_price) - self.spot_last_price) / self.spot_last_price
                    else :
                        premium = 0
                    self.funding_rate.append(premium)
                    #print(self.funding_rate)
            #print(datetime.now(), self.future_timestamp)
            if datetime.now() - self.future_timestamp >= timedelta(seconds=60) and self.funding_rate:
                    usdd_funding_rate = np.mean(self.funding_rate)
                    usdd_funding_rate /= 24
                    self.future_timestamp = datetime.now()
                    self.funding_rate = []
                    usdd_funding_rate = format(usdd_funding_rate, '.20f')
                    print("Funding Rate",usdd_funding_rate)
                    
                    with open('./usdd.txt', 'w') as f:
                        f.write(str(usdd_funding_rate))
                        f.close()
                    
    async def execute(self):
        while True:
            try:
                    future_topics = ["update:{}".format(self.config.FUTURE_SYMBOL)]
                    trade_index_topics = ["btseIndex:{}".format(self.config.SPOT_SYMBOL)]
                    trade_future_topics = ["tradeHistoryApi:{}".format(self.config.FUTURE_SYMBOL)]
                    future_web = await self.ws_subscribe(self.ws_future_endpoint, future_topics)
                    trade_spot_ws = await self.ws_subscribe(self.ws_trade_endpoint, trade_index_topics)
                    trade_future_ws = await self.ws_subscribe(self.ws_trade_endpoint, trade_future_topics)
                    task2 = asyncio.create_task(self.listen_ws(future_web))
                    await asyncio.sleep(0.1)
                    trade_spot_task = asyncio.create_task(self.listen_index(trade_spot_ws))
                    await asyncio.sleep(0.1)
                    trade_future_task = asyncio.create_task(self.listen_trade(trade_future_ws))                   
                    await asyncio.sleep(0.1)                   
                    funding_rate_task = asyncio.create_task(self.calculate_funding_rate())
                    tasks = [funding_rate_task, task2, trade_spot_task, trade_future_task]
                    #tasks = [trade_spot_task]
                    r = await asyncio.gather(*asyncio.all_tasks())
                    print(r)
            except Exception as e:
                    print(e)
                    print(traceback.format_exc())
                    self.future_orderbook = OrderBook(max_depth=50)
                    task2.cancel()
                    trade_future_task.cancel()
                    trade_spot_task.cancel()
                    funding_rate_task.cancel()
                    await asyncio.sleep(60)
                    continue
            '''
            except socket.gaierror:
                self.future_orderbook = OrderBook(max_depth=10)
                task2.cancel()
                trade_future_task.cancel()
                trade_spot_task.cancel()
                funding_rate_task.cancel()
                print("socket.gaierror")
                self.logger.debug(
                    'Socket error - retrying connection in {} sec (Ctrl-C to quit)'.format(self.config.RETRY_TIME))
                await asyncio.sleep(self.config.RETRY_TIME)
                continue
            except ConnectionRefusedError:
                self.future_orderbook = OrderBook(max_depth=5)
                task2.cancel()
                trade_future_task.cancel()
                trade_spot_task.cancel()
                funding_rate_task.cancel()
                print("ConnectRefusederror")
                self.logger.debug(
                    'Nobody seems to listen to this endpoint. Please check the URL.')
                self.logger.debug(
                    'Retrying connection in {} sec (Ctrl-C to quit)'.format(self.config.RETRY_TIME))
                await asyncio.sleep(self.config.RETRY_TIME)
                continue
            except websockets.ConnectionClosed as e:
                self.future_orderbook = OrderBook(max_depth=5)
                task2.cancel()
                trade_future_task.cancel()
                trade_spot_task.cancel()
                funding_rate_task.cancel()
                print("websockets.connection erro")
                print(e)           
                await asyncio.sleep(60)
                continue
            except ValueError as e :
                self.future_orderbook = OrderBook(max_depth=5)
                task2.cancel()
                trade_future_task.cancel()
                trade_spot_task.cancel()
                funding_rate_task.cancel()
                await asyncio.sleep(60)
                continue

            '''
            
            


