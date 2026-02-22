#!/usr/bin/env python3
"""
Russia Sanctions Tracker - CLI Entry Point

Multi-source sanctions tracking with evasion pattern detection
for Russia-linked cryptocurrency entities.

Usage:
    python main.py serve            # Start API server
    python main.py fetch            # Fetch all sanctions lists
    python main.py monitor <addr>   # Monitor specific address
    python main.py trace <addr>     # Trace evasion network
    python main.py exchanges        # List sanctioned exchanges
    python main.py stats            # Show current stats
"""

import asyncio
import argparse
import sys
import json
from datetime import datetime

import structlog
import uvicorn

from src.config import get_settings
from src.sanctions import MultiSourceSanctionsFetcher, SanctionsSource
from src.monitors import RussiaMonitor, EvasionPattern
from src.models import BlockchainType

# Configure structured logging
structlog.configure(
    processors=[
        structlog.stdlib.filter_by_level,
        structlog.stdlib.add_logger_name,
        structlog.stdlib.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.dev.ConsoleRenderer()
    ],
    wrapper_class=structlog.stdlib.BoundLogger,
    context_class=dict,
    logger_factory=structlog.stdlib.LoggerFactory(),
)

logger = structlog.get_logger()


async def cmd_serve(args):
    """Start the API server."""
    settings = get_settings()
    
    logger.info(
        "Starting Russia Sanctions Tracker",
        host=settings.host,
        port=settings.port,
        debug=settings.debug
    )
    
    config = uvicorn.Config(
        "src.api:app",
        host=settings.host,
        port=settings.port,
        reload=settings.debug,
        log_level="info" if not settings.debug else "debug"
    )
    server = uvicorn.Server(config)
    await server.serve()


async def cmd_fetch(args):
    """Fetch and display sanctions from all sources."""
    logger.info("Fetching sanctions from OFAC, EU, and UK sources...")
    
    fetcher = MultiSourceSanctionsFetcher()
    try:
        entities = await fetcher.fetch_all()
        
        print(f"\n{'='*60}")
        print(f"Russia-Linked Sanctioned Entities")
        print(f"{'='*60}")
        print(f"Total entities: {len(entities)}")
        
        # Count by source
        source_counts = {}
        for e in entities:
            for src in e.sources:
                source_counts[src.value] = source_counts.get(src.value, 0) + 1
        
        print(f"\nBy Source:")
        for src, count in sorted(source_counts.items()):
            print(f"  • {src.upper()}: {count}")
        
        # Exchanges
        exchanges = [e for e in entities if e.is_exchange]
        print(f"\nSanctioned Exchanges: {len(exchanges)}")
        for ex in exchanges:
            volume_str = f"${ex.estimated_volume_usd/1e9:.2f}B" if ex.estimated_volume_usd else "Unknown"
            sources = ", ".join(s.value.upper() for s in ex.sources)
            print(f"  • {ex.exchange_name or ex.name} ({sources}) - Volume: {volume_str}")
        
        # Crypto addresses
        total_addresses = sum(len(e.crypto_addresses) for e in entities)
        print(f"\nTotal crypto addresses: {total_addresses}")
        
        if args.json:
            output = [
                {
                    "name": e.name,
                    "sources": [s.value for s in e.sources],
                    "is_exchange": e.is_exchange,
                    "exchange_name": e.exchange_name,
                    "volume_usd": e.estimated_volume_usd,
                    "crypto_addresses": e.crypto_addresses
                }
                for e in entities
            ]
            print(f"\n{json.dumps(output, indent=2)}")
            
    finally:
        await fetcher.close()


async def cmd_monitor(args):
    """Monitor a specific address with evasion detection."""
    logger.info(f"Monitoring address: {args.address}")
    
    try:
        bc_type = BlockchainType(args.blockchain)
    except ValueError:
        print(f"Error: Invalid blockchain '{args.blockchain}'")
        print(f"Valid options: {', '.join(e.value for e in BlockchainType)}")
        sys.exit(1)
    
    monitor = RussiaMonitor()
    try:
        transactions = await monitor.monitor_address(args.address, bc_type)
        
        print(f"\n{'='*60}")
        print(f"Transaction Analysis for {args.address[:20]}...")
        print(f"Blockchain: {bc_type.value}")
        print(f"{'='*60}")
        print(f"Total transactions: {len(transactions)}\n")
        
        # Count evasion patterns
        patterns = {}
        for tx in transactions:
            if tx.evasion_pattern:
                patterns[tx.evasion_pattern.value] = patterns.get(tx.evasion_pattern.value, 0) + 1
        
        if patterns:
            print("Evasion Patterns Detected:")
            for pattern, count in sorted(patterns.items(), key=lambda x: -x[1]):
                print(f"  • {pattern}: {count}")
            print()
        
        print("Recent Transactions:")
        for tx in transactions[:args.limit]:
            direction = "↑ OUT" if tx.from_address.lower() == args.address.lower() else "↓ IN"
            timestamp = tx.block_timestamp.strftime("%Y-%m-%d %H:%M") if tx.block_timestamp else "N/A"
            pattern = f" [{tx.evasion_pattern.value}]" if tx.evasion_pattern else ""
            risk = f" ⚠️{tx.risk_score:.0f}" if tx.risk_score > 30 else ""
            
            print(f"{direction} | {timestamp} | {tx.value:.6f} | Risk:{tx.risk_score:.0f}{pattern}")
        
        # Show risk profile
        if args.address in monitor.risk_profiles:
            profile = monitor.risk_profiles[args.address]
            print(f"\nRisk Profile:")
            print(f"  Overall Risk Score: {profile.risk_score:.1f}/100")
            print(f"  Layering Events: {profile.layering_events}")
            print(f"  Mixing Events: {profile.mixing_events}")
            print(f"  Unique Counterparties: {len(profile.counterparties)}")
            
    finally:
        await monitor.close()


async def cmd_trace(args):
    """Trace evasion network from a seed address."""
    logger.info(f"Tracing evasion network from: {args.address}")
    
    monitor = RussiaMonitor()
    try:
        network = await monitor.detect_evasion_network(
            args.address,
            max_hops=args.hops
        )
        
        print(f"\n{'='*60}")
        print(f"Evasion Network Analysis")
        print(f"Seed: {args.address[:20]}...")
        print(f"{'='*60}\n")
        
        print(f"Network Size:")
        print(f"  Nodes (addresses): {len(network['nodes'])}")
        print(f"  Edges (transactions): {len(network['edges'])}")
        print(f"  High-risk transactions: {len(network['high_risk'])}")
        
        print(f"\nNodes by hop distance:")
        for hop in range(args.hops + 1):
            hop_nodes = [n for n in network['nodes'] if n['hop'] == hop]
            print(f"  Hop {hop}: {len(hop_nodes)} addresses")
        
        if network['high_risk']:
            print(f"\nHigh-risk transactions (mixing/layering):")
            for tx_hash in network['high_risk'][:10]:
                print(f"  • {tx_hash[:32]}...")
        
        if args.json:
            print(f"\n{json.dumps(network, indent=2)}")
            
    finally:
        await monitor.close()


async def cmd_exchanges(args):
    """List sanctioned Russian crypto exchanges."""
    fetcher = MultiSourceSanctionsFetcher()
    
    try:
        entities = await fetcher.fetch_all()
        exchanges = [e for e in entities if e.is_exchange]
        
        print(f"\n{'='*60}")
        print(f"Sanctioned Russian Crypto Exchanges")
        print(f"{'='*60}\n")
        
        # Sort by volume
        exchanges.sort(key=lambda x: x.estimated_volume_usd or 0, reverse=True)
        
        total_volume = sum(e.estimated_volume_usd or 0 for e in exchanges)
        print(f"Total exchanges: {len(exchanges)}")
        print(f"Combined estimated volume: ${total_volume/1e9:.2f}B\n")
        
        for ex in exchanges:
            sources = ", ".join(s.value.upper() for s in ex.sources)
            volume = f"${ex.estimated_volume_usd/1e9:.2f}B" if ex.estimated_volume_usd else "Unknown"
            
            print(f"📛 {ex.exchange_name or ex.name}")
            print(f"   Sources: {sources}")
            print(f"   Volume: {volume}")
            print(f"   Addresses: {len(ex.crypto_addresses)}")
            print()
            
    finally:
        await fetcher.close()


async def cmd_stats(args):
    """Show current monitoring statistics."""
    fetcher = MultiSourceSanctionsFetcher()
    
    try:
        entities = await fetcher.fetch_all()
        
        print(f"\n{'='*60}")
        print(f"Russia Sanctions Tracker - Statistics")
        print(f"Generated: {datetime.utcnow().isoformat()}")
        print(f"{'='*60}\n")
        
        print("Sanctioned Entities:")
        print(f"  Total: {len(entities)}")
        
        # By source
        print(f"\nBy Source:")
        source_counts = {}
        multi_source = 0
        for e in entities:
            if len(e.sources) > 1:
                multi_source += 1
            for src in e.sources:
                source_counts[src.value] = source_counts.get(src.value, 0) + 1
        
        for src, count in sorted(source_counts.items()):
            print(f"  • {src.upper()}: {count}")
        print(f"  • Multi-source: {multi_source}")
        
        # Exchanges
        exchanges = [e for e in entities if e.is_exchange]
        print(f"\nExchanges:")
        print(f"  Total: {len(exchanges)}")
        total_volume = sum(e.estimated_volume_usd or 0 for e in exchanges)
        print(f"  Combined volume: ${total_volume/1e9:.2f}B")
        
        # Crypto addresses
        total_addresses = sum(len(e.crypto_addresses) for e in entities)
        print(f"\nCrypto Addresses:")
        print(f"  Total designated: {total_addresses}")
        
        # Known exchanges detail
        print(f"\nKnown Sanctioned Exchanges:")
        known = ["garantex", "grinex", "cryptex", "suex", "chatex", "bitpapa"]
        for ex_name in known:
            matching = [e for e in exchanges if ex_name in (e.exchange_name or "").lower()]
            status = "✓ Listed" if matching else "○ Not in current data"
            print(f"  • {ex_name.title()}: {status}")
            
    finally:
        await fetcher.close()


def main():
    parser = argparse.ArgumentParser(
        description="Russia Sanctions Tracker CLI",
        formatter_class=argparse.RawDescriptionHelpFormatter
    )
    
    subparsers = parser.add_subparsers(dest="command", help="Commands")
    
    # serve command
    serve_parser = subparsers.add_parser("serve", help="Start API server")
    
    # fetch command
    fetch_parser = subparsers.add_parser("fetch", help="Fetch all sanctions lists")
    fetch_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    # monitor command
    monitor_parser = subparsers.add_parser("monitor", help="Monitor specific address")
    monitor_parser.add_argument("address", help="Crypto address to monitor")
    monitor_parser.add_argument(
        "--blockchain", "-b",
        default="ethereum",
        help="Blockchain type"
    )
    monitor_parser.add_argument(
        "--limit", "-l",
        type=int,
        default=20,
        help="Number of transactions to show"
    )
    
    # trace command
    trace_parser = subparsers.add_parser("trace", help="Trace evasion network")
    trace_parser.add_argument("address", help="Seed address to trace from")
    trace_parser.add_argument(
        "--hops", "-H",
        type=int,
        default=3,
        help="Maximum hops to trace (default: 3)"
    )
    trace_parser.add_argument("--json", action="store_true", help="Output as JSON")
    
    # exchanges command
    exchanges_parser = subparsers.add_parser("exchanges", help="List sanctioned exchanges")
    
    # stats command
    stats_parser = subparsers.add_parser("stats", help="Show current statistics")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
    
    # Run the appropriate command
    commands = {
        "serve": cmd_serve,
        "fetch": cmd_fetch,
        "monitor": cmd_monitor,
        "trace": cmd_trace,
        "exchanges": cmd_exchanges,
        "stats": cmd_stats
    }
    
    asyncio.run(commands[args.command](args))


if __name__ == "__main__":
    main()
