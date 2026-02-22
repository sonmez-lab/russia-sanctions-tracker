"""FastAPI application for Russia Sanctions Tracker."""

from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Query, Depends
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import structlog

from .config import get_settings, Settings
from .sanctions import MultiSourceSanctionsFetcher, SanctionsSource
from .monitors import RussiaMonitor, EvasionPattern

logger = structlog.get_logger()

# Initialize FastAPI app
app = FastAPI(
    title="Russia Sanctions Tracker",
    description="Multi-source sanctions tracking with evasion pattern detection for Russia-linked crypto",
    version="0.1.0",
    docs_url="/docs",
    redoc_url="/redoc"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# Pydantic models for API
class EntityInfo(BaseModel):
    name: str
    entity_type: str
    sources: list[str]
    ofac_id: Optional[str] = None
    eu_reference: Optional[str] = None
    uk_reference: Optional[str] = None
    is_exchange: bool = False
    exchange_name: Optional[str] = None
    estimated_volume_usd: Optional[float] = None
    crypto_addresses_count: int = 0


class AddressInfo(BaseModel):
    address: str
    blockchain: str
    entity_name: Optional[str] = None
    exchange_name: Optional[str] = None
    designation_source: Optional[str] = None
    is_a7a5_related: bool = False


class TransactionInfo(BaseModel):
    tx_hash: str
    blockchain: str
    from_address: str
    to_address: str
    value: str
    value_usd: Optional[str] = None
    block_timestamp: Optional[datetime] = None
    evasion_pattern: Optional[str] = None
    risk_score: float = 0.0
    is_a7a5: bool = False


class RiskProfile(BaseModel):
    address: str
    blockchain: str
    total_volume_usd: str
    tx_count: int
    risk_score: float
    layering_events: int
    mixing_events: int
    counterparty_count: int


class EvasionNetworkNode(BaseModel):
    address: str
    hop: int


class EvasionNetworkEdge(BaseModel):
    from_address: str
    to_address: str
    value: str
    evasion_pattern: Optional[str] = None


class EvasionNetwork(BaseModel):
    seed_address: str
    nodes: list[EvasionNetworkNode]
    edges: list[EvasionNetworkEdge]
    high_risk_txs: list[str]


class MonitoringStats(BaseModel):
    total_entities: int
    total_addresses: int
    by_source: dict
    exchanges_count: int
    a7a5_related_count: int
    last_updated: datetime


# Global instances
sanctions_fetcher: Optional[MultiSourceSanctionsFetcher] = None
russia_monitor: Optional[RussiaMonitor] = None


@app.on_event("startup")
async def startup():
    """Initialize services on startup."""
    global sanctions_fetcher, russia_monitor
    sanctions_fetcher = MultiSourceSanctionsFetcher()
    russia_monitor = RussiaMonitor()
    logger.info("Russia Sanctions Tracker started")


@app.on_event("shutdown")
async def shutdown():
    """Cleanup on shutdown."""
    if sanctions_fetcher:
        await sanctions_fetcher.close()
    if russia_monitor:
        await russia_monitor.close()
    logger.info("Russia Sanctions Tracker stopped")


# Health check
@app.get("/health")
async def health_check():
    """Health check endpoint."""
    return {"status": "healthy", "timestamp": datetime.utcnow()}


# Sanctions endpoints
@app.get("/api/v1/sanctions/entities", response_model=list[EntityInfo])
async def get_sanctioned_entities(
    source: Optional[str] = Query(None, description="Filter by source (ofac, eu, uk)"),
    exchanges_only: bool = Query(False, description="Only exchange entities"),
    limit: int = Query(100, le=1000)
):
    """Get list of sanctioned Russia-linked entities from all sources."""
    
    entities = await sanctions_fetcher.fetch_all()
    
    # Apply filters
    if source:
        try:
            src = SanctionsSource(source)
            entities = [e for e in entities if src in e.sources]
        except ValueError:
            raise HTTPException(status_code=400, detail=f"Invalid source: {source}")
    
    if exchanges_only:
        entities = [e for e in entities if e.is_exchange]
    
    return [
        EntityInfo(
            name=e.name,
            entity_type=e.entity_type,
            sources=[s.value for s in e.sources],
            ofac_id=e.ofac_id,
            eu_reference=e.eu_reference,
            uk_reference=e.uk_reference,
            is_exchange=e.is_exchange,
            exchange_name=e.exchange_name,
            estimated_volume_usd=e.estimated_volume_usd,
            crypto_addresses_count=len(e.crypto_addresses)
        )
        for e in entities[:limit]
    ]


@app.get("/api/v1/sanctions/addresses", response_model=list[AddressInfo])
async def get_designated_addresses(
    blockchain: Optional[str] = Query(None),
    exchange: Optional[str] = Query(None, description="Filter by exchange name"),
    a7a5_only: bool = Query(False),
    limit: int = Query(100, le=1000)
):
    """Get list of designated crypto addresses."""
    
    entities = await sanctions_fetcher.fetch_all()
    
    addresses = []
    for entity in entities:
        for addr in entity.crypto_addresses:
            addr_info = AddressInfo(
                address=addr["address"],
                blockchain=addr["blockchain"],
                entity_name=entity.name,
                exchange_name=entity.exchange_name,
                designation_source=entity.sources[0].value if entity.sources else None,
                is_a7a5_related=False  # Would need specific A7A5 detection
            )
            addresses.append(addr_info)
    
    # Apply filters
    if blockchain:
        addresses = [a for a in addresses if a.blockchain == blockchain]
    if exchange:
        addresses = [a for a in addresses if a.exchange_name and exchange.lower() in a.exchange_name.lower()]
    if a7a5_only:
        addresses = [a for a in addresses if a.is_a7a5_related]
    
    return addresses[:limit]


@app.get("/api/v1/sanctions/exchanges")
async def get_sanctioned_exchanges():
    """Get summary of sanctioned Russian crypto exchanges."""
    
    entities = await sanctions_fetcher.fetch_all()
    exchanges = [e for e in entities if e.is_exchange]
    
    return {
        "total_exchanges": len(exchanges),
        "exchanges": [
            {
                "name": e.exchange_name or e.name,
                "sources": [s.value for s in e.sources],
                "estimated_volume_usd": e.estimated_volume_usd,
                "addresses_count": len(e.crypto_addresses)
            }
            for e in exchanges
        ],
        "known_exchanges": ["garantex", "grinex", "cryptex", "suex", "chatex", "bitpapa"]
    }


@app.get("/api/v1/sanctions/refresh")
async def refresh_sanctions_lists():
    """Force refresh of all sanctions lists."""
    try:
        entities = await sanctions_fetcher.fetch_all()
        
        source_counts = {}
        for e in entities:
            for src in e.sources:
                source_counts[src.value] = source_counts.get(src.value, 0) + 1
        
        return {
            "status": "success",
            "total_entities": len(entities),
            "by_source": source_counts,
            "timestamp": datetime.utcnow()
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


# Monitoring endpoints
@app.get("/api/v1/monitor/address/{address}", response_model=list[TransactionInfo])
async def monitor_address(
    address: str,
    blockchain: str = Query("ethereum"),
    limit: int = Query(50, le=200)
):
    """Get recent transactions for a specific address with evasion analysis."""
    
    from .models import BlockchainType
    
    try:
        bc_type = BlockchainType(blockchain)
    except ValueError:
        raise HTTPException(status_code=400, detail=f"Invalid blockchain: {blockchain}")
    
    transactions = await russia_monitor.monitor_address(address, bc_type)
    
    return [
        TransactionInfo(
            tx_hash=tx.tx_hash,
            blockchain=tx.blockchain.value,
            from_address=tx.from_address,
            to_address=tx.to_address,
            value=str(tx.value),
            value_usd=str(tx.value_usd) if tx.value_usd else None,
            block_timestamp=tx.block_timestamp,
            evasion_pattern=tx.evasion_pattern.value if tx.evasion_pattern else None,
            risk_score=tx.risk_score,
            is_a7a5=tx.is_a7a5
        )
        for tx in transactions[:limit]
    ]


@app.get("/api/v1/monitor/risk-profiles", response_model=list[RiskProfile])
async def get_risk_profiles(
    min_score: float = Query(0, description="Minimum risk score"),
    limit: int = Query(50, le=200)
):
    """Get risk profiles for monitored addresses."""
    
    profiles = russia_monitor.get_high_risk_addresses(threshold=min_score)
    
    return [
        RiskProfile(
            address=p.address,
            blockchain=p.blockchain.value,
            total_volume_usd=str(p.total_volume_usd),
            tx_count=p.tx_count,
            risk_score=p.risk_score,
            layering_events=p.layering_events,
            mixing_events=p.mixing_events,
            counterparty_count=len(p.counterparties)
        )
        for p in profiles[:limit]
    ]


@app.post("/api/v1/monitor/trace-network", response_model=EvasionNetwork)
async def trace_evasion_network(
    seed_address: str,
    max_hops: int = Query(3, le=5, description="Maximum hops to trace")
):
    """Trace transaction network to detect evasion patterns."""
    
    network = await russia_monitor.detect_evasion_network(seed_address, max_hops)
    
    return EvasionNetwork(
        seed_address=seed_address,
        nodes=[EvasionNetworkNode(address=n["address"], hop=n["hop"]) for n in network["nodes"]],
        edges=[
            EvasionNetworkEdge(
                from_address=e["from"],
                to_address=e["to"],
                value=e["value"],
                evasion_pattern=e.get("evasion")
            )
            for e in network["edges"]
        ],
        high_risk_txs=network["high_risk"]
    )


# Statistics endpoints
@app.get("/api/v1/stats", response_model=MonitoringStats)
async def get_stats():
    """Get current monitoring statistics."""
    
    entities = await sanctions_fetcher.fetch_all()
    
    source_counts = {}
    address_count = 0
    a7a5_count = 0
    
    for e in entities:
        for src in e.sources:
            source_counts[src.value] = source_counts.get(src.value, 0) + 1
        address_count += len(e.crypto_addresses)
    
    return MonitoringStats(
        total_entities=len(entities),
        total_addresses=address_count,
        by_source=source_counts,
        exchanges_count=len([e for e in entities if e.is_exchange]),
        a7a5_related_count=a7a5_count,
        last_updated=datetime.utcnow()
    )


# Dashboard data endpoint
@app.get("/api/v1/dashboard")
async def get_dashboard_data():
    """Get aggregated data for dashboard visualization."""
    
    entities = await sanctions_fetcher.fetch_all()
    
    exchanges = [e for e in entities if e.is_exchange]
    total_volume = sum(e.estimated_volume_usd or 0 for e in exchanges)
    
    return {
        "total_entities": len(entities),
        "total_exchanges": len(exchanges),
        "estimated_total_volume_usd": total_volume,
        "top_exchanges": [
            {
                "name": e.exchange_name or e.name,
                "volume": e.estimated_volume_usd
            }
            for e in sorted(exchanges, key=lambda x: x.estimated_volume_usd or 0, reverse=True)[:5]
        ],
        "sources_breakdown": {
            "ofac": len([e for e in entities if SanctionsSource.OFAC in e.sources]),
            "eu": len([e for e in entities if SanctionsSource.EU in e.sources]),
            "uk": len([e for e in entities if SanctionsSource.UK in e.sources])
        },
        "evasion_patterns_detected": {
            "layering": sum(p.layering_events for p in russia_monitor.risk_profiles.values()),
            "mixing": sum(p.mixing_events for p in russia_monitor.risk_profiles.values())
        },
        "high_risk_addresses": len(russia_monitor.get_high_risk_addresses(50)),
        "last_updated": datetime.utcnow()
    }


def create_app() -> FastAPI:
    """Factory function for creating the app."""
    return app
