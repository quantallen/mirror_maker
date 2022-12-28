import requests
import asyncio
import aiohttp
import hashlib
import datetime
import time
import traceback
from random import uniform
from json import JSONDecodeError

URL='https://u21.800b.co'
#URL='https://admin.oa.btse.io'

url = URL + '/api/engine/funding'

# Sets a funding rate relative to binance
# Bias is expressed in hourly terms, so 125 millibps corresponds to 0.01% per 8 hours
BTSE_FUNDING_PARAMS = {
    'BTCPFC-USD': {'binance_symbol': 'BTCUSD_PERP', 'bias_millibps': -20},
    'ETHPFC-USD': {'binance_symbol': 'ETHUSD_PERP', 'bias_millibps': -20},
    'LTCPFC-USD': {'binance_symbol': 'LTCUSD_PERP', 'bias_millibps': -20},
    'XRPPFC-USD': {'binance_symbol': 'XRPUSD_PERP', 'bias_millibps': -20},
    'LINKPFC-USD':{'binance_symbol': 'LINKUSD_PERP', 'bias_millibps': -20},
    'XTZPFC-USD': {'binance_symbol': 'XTZUSD_PERP', 'bias_millibps': -20},
    'DOGEPFC-USD': {'binance_symbol': 'DOGEUSD_PERP', 'bias_millibps': -20}
}
FIXED_FUNDING_PARAMS = [
    # Base rate is 0.0000125
    {'market': 'USDTPFC-USD', 'fundingRate': 0.0000000},
#     {'market': 'BTCPFC-USD',  'fundingRate': -0.0000055},
#     {'market': 'ETHPFC-USD',  'fundingRate': 0.0000125},
]

async def async_post(*args, **kwargs):
    """
    Session can be moved outside, but should be fine for this scale...
    """
    async with aiohttp.ClientSession() as session:
        async with session.post(*args, **kwargs) as resp:
            try:
                result = await resp.json()
                return result
            except JSONDecodeError:
                text = await resp.text()
                print(f"Couldn't parse {text}")
                raise
            except Exception as e:
                raise

def hashmod(s, mod):
    return int(hashlib.sha1(s.encode("utf-8")).hexdigest(), 16) % mod

def make_funding_rate(d0, bias_millibps):
    """
    1 millibps = 0.0000001 = 1e-7
    0.01% per 8h = 125 millibps

    d0 is an entry from Binance premiumIndex
    containing symbol, nextFundingTime, lastFundingRate (8h)
    Add two random parts:
        1. hash modulo 30 of symbol+fundingtime
        2. pure randomness, (-10, 10) millibps, divided by current minute of hour
    Returns 1h funding rate
    """
    mod_millibps = 30
    funding_rate = float(d0['lastFundingRate'])/8
    s = '{symbol}{nextFundingTime}'.format(**d0)
    hash_randomness = (hashmod(s, mod_millibps)-mod_millibps/2)
    rand_randomness = uniform(-10, 10) / (datetime.datetime.now().minute+1)
    funding_rate += (hash_randomness+rand_randomness+bias_millibps) * 1e-7
    return funding_rate

def make_payload(market, fundingRate):
    fundingRate8Hr = fundingRate * 8

    condition1 = fundingRate8Hr + 0.0005
    condition2 = fundingRate8Hr - 0.0005

    params = {
        'market': market,
        'auto': 'false',
        'val': f'{fundingRate:.8f}',
    }

    if (condition1 > 0.0006):
        params['fundingRate'] = f'{condition1:.8f}'

    elif (condition2 < -0.0004):
        params['fundingRate'] = f'{condition2:.8f}'

    else:
        params['fundingRate'] = 0

    return params

async def run_once():

    with open('usdd.txt') as f:
       rate = f.readlines()
    print(rate[0])
    payload = {'market': 'USDDPFC-USD', 'auto': 'false', 'val': '0', 'fundingRate':'0'}
    payload = make_payload("USDDPFC-USD", float(rate[0]))
    #asks = [async_post(url, params=payload0, timeout=10, verify_ssl=False) for payload0 in payloads]
    tasks = [async_post(url, params=payload, timeout=10, verify_ssl=False)]
    result = await asyncio.gather(*tasks)
    print(result)
    print(f'Submitted {payload}')

    #return result

async def main():
    while True:
        try:
            await run_once()
        except:
            print(traceback.format_exc())
        finally:
            await asyncio.sleep(30)

if __name__ == '__main__':
    loop = asyncio.get_event_loop()
    loop.run_until_complete(main())
