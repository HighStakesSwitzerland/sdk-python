from abc import ABC, abstractmethod
from decimal import Decimal
from typing import List, Optional

import math
from google.protobuf import any_pb2

from pyinjective import PrivateKey, Transaction, PublicKey
from pyinjective.async_client import AsyncClient
from pyinjective.composer import Composer
from pyinjective.constant import Network
from pyinjective.core.gas_limit_estimator import GasLimitEstimator


class BroadcasterAccountConfig(ABC):

    @property
    @abstractmethod
    def trading_injective_address(self) -> str:
        ...

    @property
    @abstractmethod
    def trading_private_key(self) -> PrivateKey:
        ...

    @property
    @abstractmethod
    def trading_public_key(self) -> PublicKey:
        ...

    @abstractmethod
    def messages_prepared_for_transaction(self, messages: List[any_pb2.Any]) -> List[any_pb2.Any]:
        ...


class TransactionFeeCalculator (ABC):
    DEFAULT_GAS_PRICE = 500_000_000

    @abstractmethod
    async def configure_gas_fee_for_transaction(
            self,
            transaction: Transaction,
            private_key: PrivateKey,
            public_key: PublicKey,
    ):
        ...


class MsgBroadcasterWithPk:

    def __init__(
            self,
            network: Network,
            account_config: BroadcasterAccountConfig,
            client: AsyncClient,
            composer: Composer,
            fee_calculator: TransactionFeeCalculator):
        self._network = network
        self._account_config = account_config
        self._client = client
        self._composer = composer
        self._fee_calculator = fee_calculator

    @classmethod
    def new_using_simulation(
            cls,
            network: Network,
            private_key: str,
            use_secure_connection: bool = True,
            client: Optional[AsyncClient] = None,
            composer: Optional[Composer] = None,
    ):
        client = client or AsyncClient(network=network, insecure=not(use_secure_connection))
        composer = composer or Composer(network=client.network.string())
        account_config = StandardAccountBroadcasterConfig(private_key=private_key)
        fee_calculator = SimulatedTransactionFeeCalculator(
            client=client,
            composer=composer
        )
        instance = cls(
            network=network,
            account_config=account_config,
            client=client,
            composer=composer,
            fee_calculator=fee_calculator,
        )
        return instance

    @classmethod
    def new_without_simulation(
            cls,
            network: Network,
            private_key: str,
            use_secure_connection: bool = True,
            client: Optional[AsyncClient] = None,
            composer: Optional[Composer] = None,
    ):
        client = client or AsyncClient(network=network, insecure=not (use_secure_connection))
        composer = composer or Composer(network=client.network.string())
        account_config = StandardAccountBroadcasterConfig(private_key=private_key)
        fee_calculator = MessageBasedTransactionFeeCalculator(
            client=client,
            composer=composer
        )
        instance = cls(
            network=network,
            account_config=account_config,
            client=client,
            composer=composer,
            fee_calculator=fee_calculator,
        )
        return instance

    @classmethod
    def new_for_grantee_account_using_simulation(
            cls,
            network: Network,
            grantee_private_key: str,
            use_secure_connection: bool = True,
            client: Optional[AsyncClient] = None,
            composer: Optional[Composer] = None,
    ):
        client = client or AsyncClient(network=network, insecure=not (use_secure_connection))
        composer = composer or Composer(network=client.network.string())
        account_config = GranteeAccountBroadcasterConfig(grantee_private_key=grantee_private_key, composer=composer)
        fee_calculator = SimulatedTransactionFeeCalculator(
            client=client,
            composer=composer
        )
        instance = cls(
            network=network,
            account_config=account_config,
            client=client,
            composer=composer,
            fee_calculator=fee_calculator,
        )
        return instance

    @classmethod
    def new_for_grantee_account_without_simulation(
            cls,
            network: Network,
            grantee_private_key: str,
            use_secure_connection: bool = True,
            client: Optional[AsyncClient] = None,
            composer: Optional[Composer] = None,
    ):
        client = client or AsyncClient(network=network, insecure=not (use_secure_connection))
        composer = composer or Composer(network=client.network.string())
        account_config = GranteeAccountBroadcasterConfig(grantee_private_key=grantee_private_key, composer=composer)
        fee_calculator = MessageBasedTransactionFeeCalculator(
            client=client,
            composer=composer
        )
        instance = cls(
            network=network,
            account_config=account_config,
            client=client,
            composer=composer,
            fee_calculator=fee_calculator,
        )
        return instance

    async def broadcast(self, messages: List[any_pb2.Any]):
        await self._client.sync_timeout_height()
        await self._client.get_account(self._account_config.trading_injective_address)

        messages_for_transaction = self._account_config.messages_prepared_for_transaction(messages=messages)

        transaction = Transaction()
        transaction.with_messages(*messages_for_transaction)
        transaction.with_sequence(self._client.get_sequence())
        transaction.with_account_num(self._client.get_number())
        transaction.with_chain_id(self._network.chain_id)

        await self._fee_calculator.configure_gas_fee_for_transaction(
            transaction=transaction,
            private_key=self._account_config.trading_private_key,
            public_key=self._account_config.trading_public_key,
        )
        transaction.with_memo("")
        transaction.with_timeout_height(timeout_height=self._client.timeout_height)

        sign_doc = transaction.get_sign_doc(self._account_config.trading_public_key)
        sig = self._account_config.trading_private_key.sign(sign_doc.SerializeToString())
        tx_raw_bytes = transaction.get_tx_data(sig, self._account_config.trading_public_key)

        # broadcast tx: send_tx_async_mode, send_tx_sync_mode
        transaction_result = await self._client.send_tx_sync_mode(tx_raw_bytes)

        return transaction_result


class StandardAccountBroadcasterConfig(BroadcasterAccountConfig):

    def __init__(self, private_key: str):
        self._private_key = PrivateKey.from_hex(private_key)
        self._public_key = self._private_key.to_public_key()
        self._address = self._public_key.to_address()

    @property
    def trading_injective_address(self) -> str:
        return self._address.to_acc_bech32()

    @property
    def trading_private_key(self) -> PrivateKey:
        return self._private_key

    @property
    def trading_public_key(self) -> PublicKey:
        return self._public_key

    def messages_prepared_for_transaction(self, messages: List[any_pb2.Any]) -> List[any_pb2.Any]:
        # For standard account the messages do not need to be addapted
        return messages


class GranteeAccountBroadcasterConfig(BroadcasterAccountConfig):

    def __init__(self, grantee_private_key: str, composer: Composer):
        self._grantee_private_key = PrivateKey.from_hex(grantee_private_key)
        self._grantee_public_key = self._grantee_private_key.to_public_key()
        self._grantee_address = self._grantee_public_key.to_address()
        self._composer = composer

    @property
    def trading_injective_address(self) -> str:
        return self._grantee_address.to_acc_bech32()

    @property
    def trading_private_key(self) -> PrivateKey:
        return self._grantee_private_key

    @property
    def trading_public_key(self) -> PublicKey:
        return self._grantee_public_key

    def messages_prepared_for_transaction(self, messages: List[any_pb2.Any]) -> List[any_pb2.Any]:
        exec_message = self._composer.MsgExec(
            grantee=self.trading_injective_address,
            msgs=messages,
        )

        return [exec_message]


class SimulatedTransactionFeeCalculator(TransactionFeeCalculator):

    def __init__(
            self,
            client: AsyncClient,
            composer: Composer,
            gas_price: Optional[int] = None,
            gas_limit_adjustment_multiplier: Optional[Decimal] = None):
        self._client = client
        self._composer = composer
        self._gas_price = gas_price or self.DEFAULT_GAS_PRICE
        self._gas_limit_adjustment_multiplier = gas_limit_adjustment_multiplier or Decimal("1.3")

    async def configure_gas_fee_for_transaction(
            self,
            transaction: Transaction,
            private_key: PrivateKey,
            public_key: PublicKey,
    ):
        sim_sign_doc = transaction.get_sign_doc(public_key)
        sim_sig = private_key.sign(sim_sign_doc.SerializeToString())
        sim_tx_raw_bytes = transaction.get_tx_data(sim_sig, public_key)

        # simulate tx
        (sim_res, success) = await self._client.simulate_tx(sim_tx_raw_bytes)
        if not success:
            raise RuntimeError(f"Transaction simulation error: {sim_res}")

        gas_limit = math.ceil(Decimal(str(sim_res.gas_info.gas_used)) * self._gas_limit_adjustment_multiplier)

        fee = [
            self._composer.Coin(
                amount=self._gas_price * gas_limit,
                denom=self._client.network.fee_denom,
            )
        ]

        transaction.with_gas(gas=gas_limit)
        transaction.with_fee(fee=fee)


class MessageBasedTransactionFeeCalculator(TransactionFeeCalculator):
    TRANSACTION_GAS_LIMIT = 60_000

    def __init__(
            self,
            client: AsyncClient,
            composer: Composer,
            gas_price: Optional[int] = None):
        self._client = client
        self._composer = composer
        self._gas_price = gas_price or self.DEFAULT_GAS_PRICE

    async def configure_gas_fee_for_transaction(
            self,
            transaction: Transaction,
            private_key: PrivateKey,
            public_key: PublicKey,
    ):
        messages_gas_limit = math.ceil(self._calculate_gas_limit(messages=transaction.msgs))
        transaction_gas_limit = messages_gas_limit + self.TRANSACTION_GAS_LIMIT

        fee = [
            self._composer.Coin(
                amount=math.ceil(self._gas_price * transaction_gas_limit),
                denom=self._client.network.fee_denom,
            )
        ]

        transaction.with_gas(gas=transaction_gas_limit)
        transaction.with_fee(fee=fee)

    def _message_type(self, message: any_pb2.Any) -> str:
        if isinstance(message, any_pb2.Any):
            message_type = message.type_url
        else:
            message_type = message.DESCRIPTOR.full_name
        return message_type

    def _calculate_gas_limit(self, messages: List[any_pb2.Any]) -> int:
        total_gas_limit = Decimal("0")

        for message in messages:
            estimator = GasLimitEstimator.for_message(message=message)
            total_gas_limit += estimator.gas_limit()

        return math.ceil(total_gas_limit)
