
import sys
sys.path.append('./module')
import asyncio
from self_trader import SelfTrader
from config import Config

async def main():
    from BTSEREST import Spot
    #from credentials import key_testnet, secret_testnet
    from credentials import key_production, secret_production
    from config import Config

    configs = Config()
    btse = Spot(key=key_production, secret=secret_production, mode='production')
    maker = SelfTrader(btse, configs)
    await maker.execute()

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main()) 