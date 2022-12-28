import sys
import os
os.chdir(sys.path[0])
sys.path.append('./module')
import asyncio
from usdd_maker import USDDMaker



async def main():
    from BTSEREST import Spot,Future
    from credentials import key_testnet, secret_testnet
    #from credentials import key_production, secret_production
    from usdd_config import Config

    configs = Config()
    btse = Future(key=key_testnet, secret=secret_testnet, mode='testnet')
    maker = USDDMaker(btse, configs)
    await maker.execute()

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())
