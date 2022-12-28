import sys
sys.path.append('./module')
import asyncio
from mirror_orderbook import MirrorOrderbook

async def main():
    from BTSEREST import Spot
    #from credentials import key_testnet, secret_testnet
    from credentials import key_production, secret_production
    from config import Config

    configs = Config()
    btse = Spot(key=key_production, secret=secret_production, mode='production')
    mirror = MirrorOrderbook(btse, configs)
    await mirror.execute()

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main()) 