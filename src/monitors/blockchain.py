"""Blockchain monitoring for Russia-linked addresses with evasion detection."""

import asyncio
from datetime import datetime, timedelta
from decimal import Decimal
from typing import Optional, AsyncIterator
import httpx
import structlog
from dataclasses import dataclass, field
from enum import Enum

from ..config import get_settings
from ..models import BlockchainType

logger = structlog.get_logger()


class EvasionPattern(str, Enum):
    """Detected sanctions evasion patterns."""
    DIRECT = "direct"           # Direct transfer to/from sanctioned address
    LAYERING = "layering"       # Multiple hops to obscure origin
    MIXING = "mixing"           # Use of mixers/tumblers
    P2P = "p2p"                 # Peer-to-peer exchange
    NESTED = "nested"           # Nested exchange/service
    CHAIN_HOPPING = "chain_hopping"  # Cross-chain transfers


@dataclass
class Transaction:
    """Parsed blockchain transaction with evasion analysis."""
    tx_hash: str
    blockchain: BlockchainType
    from_address: str
    to_address: str
    value: Decimal
    value_usd: Optional[Decimal] = None
    block_number: int = 0
    block_timestamp: Optional[datetime] = None
    raw_data: dict = None
    
    # Evasion analysis
    evasion_pattern: Optional[EvasionPattern] = None
    risk_score: float = 0.0
    hop_count: int = 0
    
    # A7A5 specific
    is_a7a5: bool = False


@dataclass
class AddressRiskProfile:
    """Risk profile for a monitored address."""
    address: str
    blockchain: BlockchainType
    total_volume_usd: Decimal = Decimal(0)
    tx_count: int = 0
    
    # Time analysis
    first_seen: Optional[datetime] = None
    last_seen: Optional[datetime] = None
    
    # Pattern counts
    direct_transfers: int = 0
    layering_events: int = 0
    mixing_events: int = 0
    
    # Connected addresses
    counterparties: set = field(default_factory=set)
    
    @property
    def risk_score(self) -> float:
        """Calculate overall risk score 0-100."""
        score = 0.0
        
        # Volume-based risk
        if self.total_volume_usd > 1_000_000:
            score += 30
        elif self.total_volume_usd > 100_000:
            score += 20
        elif self.total_volume_usd > 10_000:
            score += 10
        
        # Activity-based risk
        if self.tx_count > 1000:
            score += 20
        elif self.tx_count > 100:
            score += 10
        
        # Pattern-based risk
        if self.layering_events > 0:
            score += 25
        if self.mixing_events > 0:
            score += 25
        
        return min(score, 100)


class EtherscanMonitor:
    """Monitor Ethereum addresses via Etherscan API."""
    
    # Known mixer contracts
    MIXER_CONTRACTS = [
        "0xd90e2f925da726b50c4ed8d0fb90ad053324f31b",  # Tornado Cash Router
        "0x722122df12d4e14e13ac3b6895a86e84145b6967",  # Tornado Cash 0.1 ETH
        # Add more mixer addresses
    ]
    
    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=30.0)
        self.base_url = self.settings.etherscan_base_url
        self.api_key = self.settings.etherscan_api_key
        
    async def get_transactions(
        self, 
        address: str, 
        start_block: int = 0,
        end_block: int = 99999999
    ) -> list[Transaction]:
        """Fetch transactions with evasion analysis."""
        
        params = {
            "module": "account",
            "action": "txlist",
            "address": address,
            "startblock": start_block,
            "endblock": end_block,
            "sort": "desc",
            "apikey": self.api_key or ""
        }
        
        response = await self.client.get(self.base_url, params=params)
        data = response.json()
        
        if data.get("status") != "1":
            return []
        
        transactions = []
        for tx in data.get("result", []):
            # Analyze for evasion patterns
            evasion_pattern = self._detect_evasion(tx)
            
            transactions.append(Transaction(
                tx_hash=tx["hash"],
                blockchain=BlockchainType.ETHEREUM,
                from_address=tx["from"],
                to_address=tx["to"],
                value=Decimal(tx["value"]) / Decimal(10**18),
                block_number=int(tx["blockNumber"]),
                block_timestamp=datetime.fromtimestamp(int(tx["timeStamp"])),
                evasion_pattern=evasion_pattern,
                risk_score=self._calculate_tx_risk(tx, evasion_pattern),
                raw_data=tx
            ))
        
        return transactions
    
    def _detect_evasion(self, tx: dict) -> Optional[EvasionPattern]:
        """Detect potential evasion pattern in transaction."""
        to_addr = tx.get("to", "").lower()
        
        # Check for mixer usage
        if to_addr in [m.lower() for m in self.MIXER_CONTRACTS]:
            return EvasionPattern.MIXING
        
        # Check for contract interaction patterns
        if tx.get("input", "0x") != "0x":
            # Complex contract interaction - could be layering
            if len(tx.get("input", "")) > 200:
                return EvasionPattern.LAYERING
        
        return EvasionPattern.DIRECT
    
    def _calculate_tx_risk(self, tx: dict, evasion: Optional[EvasionPattern]) -> float:
        """Calculate risk score for a transaction."""
        score = 0.0
        
        value_wei = int(tx.get("value", 0))
        value_eth = value_wei / 10**18
        
        # Value-based risk
        if value_eth > 100:
            score += 30
        elif value_eth > 10:
            score += 20
        elif value_eth > 1:
            score += 10
        
        # Pattern-based risk
        if evasion == EvasionPattern.MIXING:
            score += 40
        elif evasion == EvasionPattern.LAYERING:
            score += 30
        
        return min(score, 100)
    
    async def close(self):
        await self.client.aclose()


class TrongridMonitor:
    """Monitor Tron addresses with focus on USDT-TRC20."""
    
    USDT_CONTRACT = "TR7NHqjeKQxGTCi8q8ZY4pL8otSzgjLj6t"
    
    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=30.0)
        self.base_url = self.settings.trongrid_base_url
        self.api_key = self.settings.trongrid_api_key
        
    async def get_trc20_transfers(self, address: str, limit: int = 100) -> list[Transaction]:
        """Fetch TRC-20 (USDT) transfers - primary Russia evasion vector."""
        
        headers = {}
        if self.api_key:
            headers["TRON-PRO-API-KEY"] = self.api_key
        
        url = f"{self.base_url}/v1/accounts/{address}/transactions/trc20"
        params = {"limit": limit, "only_confirmed": "true"}
        
        response = await self.client.get(url, params=params, headers=headers)
        data = response.json()
        
        transactions = []
        for tx in data.get("data", []):
            token_info = tx.get("token_info", {})
            decimals = int(token_info.get("decimals", 6))
            
            transactions.append(Transaction(
                tx_hash=tx["transaction_id"],
                blockchain=BlockchainType.USDT_TRC20,
                from_address=tx.get("from", ""),
                to_address=tx.get("to", ""),
                value=Decimal(tx.get("value", 0)) / Decimal(10**decimals),
                block_timestamp=datetime.fromtimestamp(tx.get("block_timestamp", 0) / 1000),
                raw_data=tx
            ))
        
        return transactions
    
    async def close(self):
        await self.client.aclose()


class A7A5Monitor:
    """Monitor A7A5 Russian stablecoin transactions."""
    
    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=30.0)
        
    async def get_a7a5_transactions(self, address: str) -> list[Transaction]:
        """
        Monitor A7A5 stablecoin.
        Note: A7A5 may require custom blockchain/API integration
        as it operates on proprietary infrastructure.
        """
        # A7A5 operates via Promsvyazbank and may not be publicly traceable
        # This is a placeholder for when/if API access becomes available
        logger.warning("A7A5 monitoring requires specialized access")
        return []
    
    async def close(self):
        await self.client.aclose()


class RussiaMonitor:
    """Combined monitor for Russia-linked addresses with evasion detection."""
    
    def __init__(self):
        self.etherscan = EtherscanMonitor()
        self.trongrid = TrongridMonitor()
        self.a7a5 = A7A5Monitor()
        self.settings = get_settings()
        
        # Track address risk profiles
        self.risk_profiles: dict[str, AddressRiskProfile] = {}
        
    async def monitor_address(
        self, 
        address: str, 
        blockchain: BlockchainType
    ) -> list[Transaction]:
        """Monitor a single address."""
        
        txs = []
        
        if blockchain in [BlockchainType.ETHEREUM, BlockchainType.USDT_ERC20]:
            txs = await self.etherscan.get_transactions(address)
        elif blockchain in [BlockchainType.TRON, BlockchainType.USDT_TRC20]:
            txs = await self.trongrid.get_trc20_transfers(address)
        elif blockchain == BlockchainType.A7A5:
            txs = await self.a7a5.get_a7a5_transactions(address)
        
        # Update risk profile
        self._update_risk_profile(address, blockchain, txs)
        
        return txs
    
    def _update_risk_profile(
        self, 
        address: str, 
        blockchain: BlockchainType,
        transactions: list[Transaction]
    ):
        """Update risk profile for an address."""
        
        if address not in self.risk_profiles:
            self.risk_profiles[address] = AddressRiskProfile(
                address=address,
                blockchain=blockchain
            )
        
        profile = self.risk_profiles[address]
        
        for tx in transactions:
            profile.tx_count += 1
            
            if tx.value_usd:
                profile.total_volume_usd += tx.value_usd
            
            if tx.evasion_pattern == EvasionPattern.LAYERING:
                profile.layering_events += 1
            elif tx.evasion_pattern == EvasionPattern.MIXING:
                profile.mixing_events += 1
            else:
                profile.direct_transfers += 1
            
            # Track counterparties
            counterparty = tx.to_address if tx.from_address.lower() == address.lower() else tx.from_address
            profile.counterparties.add(counterparty)
            
            # Update timestamps
            if tx.block_timestamp:
                if not profile.first_seen or tx.block_timestamp < profile.first_seen:
                    profile.first_seen = tx.block_timestamp
                if not profile.last_seen or tx.block_timestamp > profile.last_seen:
                    profile.last_seen = tx.block_timestamp
    
    async def detect_evasion_network(
        self, 
        seed_address: str,
        max_hops: int = 3
    ) -> dict:
        """
        Trace transaction network from a seed address to detect evasion patterns.
        Useful for finding Garantex/Cryptex connected wallets.
        """
        
        visited = set()
        network = {"nodes": [], "edges": [], "high_risk": []}
        
        async def trace(address: str, hop: int):
            if hop > max_hops or address in visited:
                return
            
            visited.add(address)
            network["nodes"].append({"address": address, "hop": hop})
            
            # Get transactions
            txs = await self.etherscan.get_transactions(address)
            
            for tx in txs[:20]:  # Limit to avoid rate limits
                counterparty = tx.to_address if tx.from_address.lower() == address.lower() else tx.from_address
                
                network["edges"].append({
                    "from": address,
                    "to": counterparty,
                    "value": str(tx.value),
                    "evasion": tx.evasion_pattern.value if tx.evasion_pattern else None
                })
                
                if tx.evasion_pattern in [EvasionPattern.MIXING, EvasionPattern.LAYERING]:
                    network["high_risk"].append(tx.tx_hash)
                
                # Continue tracing if high risk
                if tx.risk_score > 50:
                    await trace(counterparty, hop + 1)
        
        await trace(seed_address, 0)
        
        logger.info(
            "Evasion network traced",
            seed=seed_address[:10],
            nodes=len(network["nodes"]),
            high_risk=len(network["high_risk"])
        )
        
        return network
    
    async def monitor_all(
        self, 
        addresses: list[dict]
    ) -> dict[str, list[Transaction]]:
        """Monitor multiple addresses concurrently."""
        
        results = {}
        
        for addr_info in addresses:
            address = addr_info["address"]
            blockchain = BlockchainType(addr_info["blockchain"])
            
            try:
                results[address] = await self.monitor_address(address, blockchain)
            except Exception as e:
                logger.error(f"Failed to monitor {address}: {e}")
                results[address] = []
        
        return results
    
    def get_high_risk_addresses(self, threshold: float = 50.0) -> list[AddressRiskProfile]:
        """Get addresses exceeding risk threshold."""
        return [
            profile for profile in self.risk_profiles.values()
            if profile.risk_score >= threshold
        ]
    
    async def close(self):
        await asyncio.gather(
            self.etherscan.close(),
            self.trongrid.close(),
            self.a7a5.close()
        )


async def main():
    """Test the Russia monitor."""
    monitor = RussiaMonitor()
    
    # Test with sample Ethereum address
    test_addresses = [
        {"address": "0x742d35Cc6634C0532925a3b844Bc9e7595f2bD4e", "blockchain": "ethereum"}
    ]
    
    try:
        results = await monitor.monitor_all(test_addresses)
        
        for addr, txs in results.items():
            print(f"\n{addr[:20]}...: {len(txs)} transactions")
            for tx in txs[:3]:
                print(f"  - {tx.tx_hash[:20]}... | {tx.value} | {tx.evasion_pattern}")
        
        # Show risk profiles
        print("\nRisk Profiles:")
        for profile in monitor.risk_profiles.values():
            print(f"  {profile.address[:20]}... | Score: {profile.risk_score}")
            
    finally:
        await monitor.close()


if __name__ == "__main__":
    asyncio.run(main())
