import asyncio
import logging

from pyinjective.async_client import AsyncClient
from pyinjective.constant import Network

async def main() -> None:
    network = Network.testnet()
    client = AsyncClient(network, insecure=False)
    address = "inj1cml96vmptgw99syqrrz8az79xer2pcgp0a885r"
    all_bank_balances = await client.get_bank_balances(address=address)
    print(all_bank_balances)

if __name__ == '__main__':
    asyncio.get_event_loop().run_until_complete(main())