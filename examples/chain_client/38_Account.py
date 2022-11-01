import asyncio
import logging

from pyinjective.async_client import AsyncClient
from pyinjective.constant import Network

async def main() -> None:
    network = Network.testnet()
    client = AsyncClient(network, insecure=False)
    address = "inj1knhahceyp57j5x7xh69p7utegnnnfgxavmahjr"
    acc = await client.get_account(address=address)
    print(acc)

if __name__ == '__main__':
    logging.basicConfig(level=logging.INFO)
    asyncio.get_event_loop().run_until_complete(main())
