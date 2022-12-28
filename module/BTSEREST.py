import asyncio
import aiohttp
import json
import hmac
import time
import logging

def hex_sign_msg(key, msg, hash):
    signature = hmac.new(bytes(key, 'latin-1'),
                         msg=bytes(msg, 'latin-1'),
                         digestmod=hash)
    return signature.hexdigest()

async def async_get(url, *args, **kwargs):
    async with aiohttp.ClientSession() as session:
        async with session.get(url, *args, **kwargs) as response:
            return await response.text()

async def async_request(method, url, *args, **kwargs):
    async with aiohttp.ClientSession() as session:
        async with session.request(method, url, *args, **kwargs) as response:
            return await response.text()

class Spot:
    version = 'v3.2'
    testnet_endpoint = f'https://testapi.btse.io/spot/api/{version}'
    production_endpoint = f'https://api.btse.com/spot/api/{version}'
    staging_endpoint = f'https://staging.oa.btse.io/api/spot/api/{version}'

    def __init__(self, key=None, secret=None, mode='production'):
        self.key = key
        self.secret = secret

        self.endpoint = {
            'production': self.production_endpoint,
            'testnet': self.testnet_endpoint,
            'staging': self.staging_endpoint
        }[mode]

        self.logger = logging.getLogger('BTSEREST.Spot')
        self.logger.setLevel('INFO')
        self.order_cache = {}

    def _make_headers(self, path, data=None):
        nonce = str(int(time.time()*1000))
        data = json.dumps(data) if data else ''

        message = f'/api/{self.version}' + path + nonce + data
        signature = hex_sign_msg(self.secret, message, 'sha384')

        return {
            'btse-api': self.key,
            'btse-nonce': nonce,
            'btse-sign': signature,
            "Accept": "application/json;charset=UTF-8",
            "Content-Type": "application/json"
        }

    async def _request(self, method, path, params={}, data=None):
        headers = self._make_headers(path, data=data)
        if method in ['GET', 'DELETE']:
            resp = await async_request(method, self.endpoint + path, headers=headers, params=params)
        elif method in ['POST', 'PUT']:
            resp = await async_request(method, self.endpoint + path, headers=headers, data=json.dumps(data))
        try:
            return json.loads(resp)
        except json.decoder.JSONDecodeError:
            self.logger.error(f"{method} {self.endpoint + path}; Could not parse response '{resp}'")
            return resp

    async def get(self, path, params={}):
        return await self._request('GET', path, params=params)

    async def delete(self, path, params):
        return await self._request('DELETE', path, params=params)

    async def post(self, path, data):
        return await self._request('POST', path, data=data)

    async def put(self, path, data):
        return await self._request('PUT', path, data=data)

    async def get_public(self, path, **kwargs):
        resp = await async_get(self.endpoint + path, **kwargs)
        resp = json.loads(resp)
        return resp

    async def get_wallet(self):
        resp = await self.get('/user/wallet')
        return resp

    async def submit_order(self,
        symbol,
        side,
        price,
        size,
        order_type='LIMIT',
        cl_order_id=None,
        deviation=None,
        post_only=None,
        stealth=None,
        stop_price=None,
        time_in_force=None,
        trail_value=None,
        tx_type=None,
        trigger_price=None,
    ):
        """
        v3.2
        symbol: e.g. 'BTC-USD'
        side: BUY|SELL
        price, size: numbers
        order_type: LIMIT|MARKET|OCO
        tx_type: LIMIT|STOP|TRIGGER
        time_in_force: IOC|GTC|FIVEMIN|HOUR|TWELVEHOUR|DAY|WEEK|MONTH
        """
        optionals = {k: v for (k, v) in {
            'clOrderID': cl_order_id,
            'deviation': deviation,
            'postOnly': post_only,
            'stealth': stealth,
            'stopPrice': stop_price,
            'time_in_force': time_in_force,
            'trailValue': trail_value,
            'triggerPrice': trigger_price,
            'txType': tx_type,
        }.items() if v is not None}

        order_form = {
            'price': f'{price:.5f}',
            'side': side,
            'size': f'{size:.5f}',
            'symbol': symbol,
            'type': order_type,
            **optionals
        }
        if order_type == 'MARKET': del order_form['price']

        resp = await self.post('/order', order_form)
        logger_string = f'Submit {symbol} {order_type} {side} {size:.5f} @ {price:.5f}'
        if optionals:
            logger_string += f' with {str(optionals)}'
        # Normal response is a list containing one dict
        try:
            resp0 = resp[0]
            logger_string += f"; ID: {resp0['orderID']}"
            #self.logger.info(logger_string)
            self.order_cache[resp0['orderID']] = {
                'description': f'{symbol} {order_type} {side} {size:.5f} @ {price:.5f}'
            }
            # Seems to return ORDER_INSERTED even if the order is filled
            return resp0
        except KeyError:
            logger_string += f"; Response: {resp}"
            self.logger.info(logger_string)

    async def amend_order(self, symbol, type, value=None, price=None, size=None, order_id=None, cl_order_id=None):
        """
        v2.1
        symbol: e.g. 'BTCPFC'
        type: PRICE|SIZE
        value: number
        """
        optionals = {k: v for (k, v) in {
            'orderID': order_id,
            'clOrderID': cl_order_id,
            'orderPrice': f'{price:.5f}',
            'orderSize': f'{size:.5f}',
            'value' : value
        }.items() if v is not None}

        params = {
            'symbol': symbol,
            'type': type,
            'value': value,
            **optionals
        }
        resp = await self.put('/order', data=params)
        return resp

    async def amend_order_size(self, symbol, cl_order_id, size):
        """
        Example:
            symbol='BTSE-USD',
        v3: Returns a list
        """
        order_form = {'symbol': symbol,
                      'clOrderID': cl_order_id,
                      'type': 'SIZE',
                      'value':  f'{size:.5f}'}
        resp = await self.put('/order', order_form)
        return resp

    async def amend_order_price(self, symbol, cl_order_id, price):
        """
        Example:
            symbol='BTSE-USD',
        v3: Returns a list
        """
        order_form = {'symbol': symbol,
                      'clOrderID': cl_order_id,
                      'type': 'PRICE',
                      'value': f'{price:.5f}'}
        resp = await self.put('/order', order_form)
        return resp

    async def cancel_order(self, symbol, cl_order_id):
        try:
            resp = await self.delete('/order', params={'symbol': symbol, 'clOrderID': cl_order_id})
            resp = resp[0]
        except:
            pass
        try:
            logger_string = f"Cancel {symbol} {self.order_cache.pop(cl_order_id)['description']}"
        except KeyError:
            logger_string = f'Cancel {symbol} order {cl_order_id}'
        try:
            logger_string += f"; Response: {resp['message']}"
        except KeyError:
            logger_string += f"; could not parse response"
        #self.logger.info(logger_string)
        # This seems to always return ALL_ORDER_CANCELLED_SUCCESS
        return resp

    async def cancel_all_orders(self, symbol):
        """
        Example:
            symbol='BTSE-USD',
        v3: Returns a list
        """
        params = {'symbol': symbol}
        resp = await self.delete('/order', params=params)
        return resp

    async def get_open_orders(self, symbol):
        """
        Example:
            symbol='BTSE-USD',
        v3: Returns a list
        """
        params = {'symbol': symbol}
        resp = await self.get('/user/open_orders', params=params)
        return resp

    async def get_open_orders(self, symbol, order_id=None):
        """
        Example:
            symbol='BTSE-USD',
        v3: Returns a list
        """
        optionals = {k: v for (k, v) in {
            'orderID': order_id,
        }.items() if v is not None}
        params = {'symbol': symbol,
                  **optionals}
        resp = await self.get('/user/open_orders', params=params)
        return resp

    async def get_trades(self, symbol, params={}):
        """
        Example:
            symbol='BTSE-USD',
            params={'count': 500}
        v3: Returns a list
        """
        params1 = {'symbol': symbol, 'count': 500}
        params1.update(params)
        resp = await self.get_public('/trades', params=params1)
        return resp

    async def get_trades_histoty(self, symbol, params={}):
        """
        Example:
            symbol='BTSE-USD',
            params={'count': 500}
        v3: Returns a list
        """
        params1 = {'symbol': symbol, 'count': 500}
        params1.update(params)
        resp = await self.get('/user/trade_history', params=params1)
        return resp

    async def get_orderbook(self, 
        symbol,
        limit_bids=1,
        limit_asks=1):
        """
        Example:
            symbol='BTSE-USD',
        v3: Returns a list
        """
        params = {
            'symbol': symbol,
            "limit_bids": limit_bids,
            "limit_asks": limit_asks
        }
        resp = await self.get('/orderbook', params=params)
        return resp

class Future:
    version = 'v2.1'
    testnet_endpoint = f'https://testapi.btse.io/futures/api/{version}'
    production_endpoint = f'https://api.btse.com/futures/api/{version}'
    staging_endpoint = f'https://staging.oa.btse.io/futures/api/{version}'

    def __init__(self, key=None, secret=None, mode='production'):
        self.key = key
        self.secret = secret

        self.endpoint = {
            'production': self.production_endpoint,
            'testnet': self.testnet_endpoint,
            'staging': self.staging_endpoint
        }[mode]

        self.logger = logging.getLogger('BTSEREST.Future')
        #self.logger.setLevel('INFO')
        # logging.basicConfig(
        #     format='[%(asctime)s.%(msecs)03d][%(name)s][%(levelname)s]: %(message)s',
        #     datefmt='%Y-%m-%d %H:%M:%S'
        # )
        # Responses from submitted orders go here
        self.order_cache = {}

    def _make_headers(self, path, data=None):
        nonce = str(int(time.time()*1000))
        data = json.dumps(data) if data else ''

        message = f'/api/{self.version}' + path + nonce + data
        signature = hex_sign_msg(self.secret, message, 'sha384')

        return {
            'btse-api': self.key,
            'btse-nonce': nonce,
            'btse-sign': signature,
            "Accept": "application/json;charset=UTF-8",
            "Content-Type": "application/json"
        }

    async def _request(self, method, path, params={}, data=None):
        headers = self._make_headers(path, data=data)
        if method in ['GET', 'DELETE']:
            resp = await async_request(method, self.endpoint + path, headers=headers, params=params)
        elif method in ['POST', 'PUT']:
            resp = await async_request(method, self.endpoint + path, headers=headers, data=json.dumps(data))
        try:
            return json.loads(resp)
        except json.decoder.JSONDecodeError:
            self.logger.error(f"{method} {self.endpoint + path}; Could not parse response '{resp}'")
            return resp

    async def get(self, path, params={}):
        return await self._request('GET', path, params=params)

    async def delete(self, path, params):
        return await self._request('DELETE', path, params=params)

    async def post(self, path, data):
        return await self._request('POST', path, data=data)
    
    async def put(self, path, data):
        return await self._request('PUT', path, data=data)

    async def get_public(self, path, **kwargs):
        resp = await async_get(self.endpoint + path, **kwargs)
        resp = json.loads(resp)
        return resp

    """
    Example:
        CROSS@: Cross wallet
        ISOLATED@market: Cross wallet, ISOLATED@BTCPFC-USD
    v3: Returns a list
    """
    async def get_wallet(self, params={}):
        params1 = {'wallet': 'CROSS@'}
        params1.update(params)
        resp = await self.get('/user/wallet', params=params1)
        return resp

    async def submit_order(self,
        symbol,
        side,
        price,
        size,
        order_type='LIMIT',
        tx_type='LIMIT',
        cl_order_id=None,
        deviation=None,
        post_only=None,
        stealth=None,
        stop_price=None,
        time_in_force='GTC',
        trail_value=None,
        trigger_price=None,
    ):
        """
        v2.1
        symbol: e.g. 'BTC-USD'
        side: BUY|SELL
        price, size: numbers
        order_type: LIMIT|MARKET|OCO
        tx_type: LIMIT|STOP|TRIGGER
        time_in_force: IOC|GTC|FIVEMIN|HOUR|TWELVEHOUR|DAY|WEEK|MONTH
        """
        optionals = {k: v for (k, v) in {
            'clOrderID': cl_order_id,
            'deviation': deviation,
            'postOnly': post_only,
            'stealth': stealth,
            'stopPrice': stop_price,
            'trailValue': trail_value,
            'triggerPrice': trigger_price
        }.items() if v is not None}

        order_form = {
            'price': price,
            'side': side,
            'size': size,
            'symbol': symbol,
            'type': order_type,
            'txType': tx_type,
            'time_in_force': time_in_force,
            **optionals
        }
        if order_type == 'MARKET': del order_form['price']

        resp = await self.post('/order', order_form)
        logger_string = f'Submit {symbol} {order_type} {side} {size:.5f} @ {price:.5f}'
        if optionals:
            logger_string += f' with {str(optionals)}'
        # Normal response is a list containing one dict
        try:
            resp0 = resp[0]
            logger_string += f"; ID: {resp0['orderID']}"
            #self.logger.info(logger_string)
            self.order_cache[resp0['orderID']] = {
                'description': f'{symbol} {order_type} {side} {size:.5f} @ {price:.5f}'
            }
            # Seems to return ORDER_INSERTED even if the order is filled
            return resp0
        except KeyError:
            logger_string += f"; Response: {resp}"
            #self.logger.error(logger_string)

    async def set_leverage(self, symbol, leverage):
        """
        Example:
            symbol='BTCPFC',
            params={'leverage': integer}
        """
        params = {'symbol': symbol, 'leverage': leverage}
        resp = await self.post('/leverage', data=params)
        return resp

    async def amend_order(self, symbol, type, value, order_id=None, cl_order_id=None,):
        """
        v2.1
        symbol: e.g. 'BTCPFC'
        type: PRICE|SIZE
        value: number
        """
        optionals = {k: v for (k, v) in {
            'orderID': order_id,
            'clOrderID': cl_order_id
        }.items() if v is not None}

        params = {
            'symbol': symbol,
            'type': type,
            'value': value,
            **optionals
        }
        resp = await self.put('/order', data=params)
        return resp

    async def cancel_order(self, symbol, order_id=None):
        resp = await self.delete('/order', params={'symbol': symbol, 'orderID': order_id})
        resp = resp[0]
        try:
            logger_string = f"Cancel {symbol} {self.order_cache.pop(order_id)['description']}"
        except KeyError:
            logger_string = f'Cancel {symbol} order {order_id}'
        try:
            logger_string += f"; Response: {resp['message']}"
        except KeyError:
            logger_string += f"; could not parse response"
        self.logger.info(logger_string)
        # This seems to always return ALL_ORDER_CANCELLED_SUCCESS
        return resp

    async def cancel_all_orders(self, symbol):
        """
        Example:
            symbol='BTSE-USD',
        v3: Returns a list
        """
        params = {'symbol': symbol}
        resp = await self.delete('/order', params=params)
        return resp

    async def get_open_orders(self, symbol):
        """
        Example:
            symbol='BTCPFC',
        v3: Returns a list
        """
        params = {'symbol': symbol}
        resp = await self.get('/user/open_orders', params=params)
        return resp

    async def get_trades(self, symbol, params={}):
        """
        Example:
            symbol='BTCPFC',
            params={'count': 500}
        v3: Returns a list
        """
        params1 = {'symbol': symbol, 'count': 500}
        params1.update(params)
        resp = await self.get_public('/trades', params=params1)
        return resp


async def test():
    from credentials import key, secret
    btse = MarketMaker(key=key, secret=secret)
    open_orders = await btse.get_open_orders('BTSE-USD')
    print(open_orders)
    wallet = await btse.get_wallet()
    print(wallet)
    order = await btse.submit_order(symbol='BTSE-USD', side='BUY', price=1.211, amount=2.255)
    print(order)
    cancel_order = await btse.cancel_order(symbol='BTSE-USD', order_id='7138cd7c-f726-4169-aa5f-eabd53e3ccf2')
    print(cancel_order)

if __name__ == '__main__':
    key = None
    secret = None
    asyncio.get_event_loop().run_until_complete(test())
