import sys
sys.path.append('./module')
import asyncio
from fodl_maker import FODLMaker



async def main():
    from BTSEREST import Spot
    #from credentials import key_testnet, secret_testnet
    from credentials import key_production, secret_production
    from config import Config

    configs = Config()
    btse = Spot(key=key_production, secret=secret_production, mode='production')
    maker = FODLMaker(btse, configs)
    await maker.execute()

if __name__ == '__main__':
    asyncio.run(main()) 
