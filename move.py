
import sys
sys.path.append('./module')
import asyncio
from bookmover import BookMover
from config import Config

async def main():
    from BTSEREST import Spot
    from credentials import key, secret
    from config import Config

    configs = Config()
    btse = Spot(key=key, secret=secret, mode='production')
    mover = BookMover(btse, configs)
    await mover.execute()

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main()) 
