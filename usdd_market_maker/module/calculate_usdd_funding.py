import sys
import os
os.chdir(sys.path[0])
#sys.path.append('./module')
import asyncio
from USDD import BTSE_funding_rate
async def main():
    from usdd_config import Config
    configs = Config()
    BTSE_funding = BTSE_funding_rate(configs)
    await BTSE_funding.execute()
if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())