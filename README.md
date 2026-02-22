# Russia Sanctions Tracker

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.109+-green.svg)](https://fastapi.tiangolo.com/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Multi-source sanctions tracking with evasion pattern detection for Russia-linked cryptocurrency entities.**

## 🎯 Purpose

Russia's crypto sanctions evasion has reached industrial scale, with the A7A5 stablecoin alone processing $93.3B in its first year. This tool tracks:

- OFAC/EU/UK-designated Russian crypto exchanges
- A7A5 stablecoin transaction patterns
- Sanctioned entity wallet activity
- Turkey-Russia crypto corridor flows
- Evasion patterns (layering, mixing, P2P)

## 🚨 Key Designated Entities

| Entity | Status | Volume Processed |
|--------|--------|------------------|
| Garantex | Designated (rebranded to Grinex) | $6B+ |
| Cryptex | Designated Oct 2024 | $5.88B |
| SUEX | Designated Sep 2021 | $370M+ |
| Chatex | Designated Nov 2021 | $200M+ |
| Bitpapa | Designated Feb 2024 | Unknown |
| A7A5 (via Promsvyazbank) | Sanctioned bank | $93.3B |

## 📋 Features

- ✅ Multi-source sanctions aggregation (OFAC, EU, UK)
- ✅ Blockchain activity monitoring for designated addresses
- ✅ Evasion pattern detection (layering, mixing, P2P)
- ✅ Risk scoring for addresses and transactions
- ✅ Network tracing for connected wallets
- ✅ RESTful API with FastAPI
- ✅ Advanced CLI with network tracing

## 🛠️ Tech Stack

- **Python 3.10+**
- **FastAPI** - API framework
- **SQLAlchemy** - Database ORM
- **PostgreSQL** - Entity/transaction storage
- **Redis** - Caching
- **httpx** - Async HTTP client
- **Etherscan/TronGrid APIs** - Blockchain data

## 🚀 Quick Start

### Installation

```bash
# Clone the repository
cd russia-sanctions-tracker

# Create virtual environment
python -m venv venv
source venv/bin/activate  # Windows: venv\Scripts\activate

# Install dependencies
pip install -r requirements.txt

# Copy environment file
cp .env.example .env
# Edit .env with your API keys
```

### CLI Usage

```bash
# Fetch sanctions from all sources (OFAC, EU, UK)
python main.py fetch

# List sanctioned exchanges
python main.py exchanges

# Monitor a specific address with evasion detection
python main.py monitor 0x742d35Cc6634C0532925a3b844Bc9e7595f2bD4e

# Trace evasion network from seed address
python main.py trace 0x742d35Cc6634C0532925a3b844Bc9e7595f2bD4e --hops 3

# Show statistics
python main.py stats

# Start API server
python main.py serve
```

### API Usage

```bash
# Start the server
python main.py serve

# API available at http://localhost:8001
# Docs at http://localhost:8001/docs
```

#### Key Endpoints

| Endpoint | Description |
|----------|-------------|
| `GET /api/v1/sanctions/entities` | List sanctioned entities |
| `GET /api/v1/sanctions/addresses` | List designated addresses |
| `GET /api/v1/sanctions/exchanges` | Sanctioned exchanges summary |
| `GET /api/v1/monitor/address/{addr}` | Monitor with evasion analysis |
| `GET /api/v1/monitor/risk-profiles` | Get address risk profiles |
| `POST /api/v1/monitor/trace-network` | Trace evasion network |
| `GET /api/v1/dashboard` | Dashboard data |

## 📁 Project Structure

```
russia-sanctions-tracker/
├── main.py                 # CLI entry point
├── requirements.txt
├── .env.example
├── src/
│   ├── __init__.py
│   ├── config.py          # Settings management
│   ├── models.py          # Database models
│   ├── api.py             # FastAPI application
│   ├── sanctions/
│   │   ├── __init__.py
│   │   └── multi_source.py # OFAC/EU/UK aggregator
│   └── monitors/
│       ├── __init__.py
│       └── blockchain.py  # Evasion-aware monitoring
└── tests/
    └── test_sanctions.py
```

## 🔍 Evasion Pattern Detection

The tracker identifies these evasion patterns:

| Pattern | Description | Risk Level |
|---------|-------------|------------|
| **Direct** | Direct transfer to/from sanctioned address | Medium |
| **Layering** | Multiple hops to obscure origin | High |
| **Mixing** | Use of mixers/tumblers (Tornado Cash, etc.) | Critical |
| **P2P** | Peer-to-peer exchange | Medium |
| **Chain-hopping** | Cross-chain transfers | High |

## 📊 Example Output

```
$ python main.py exchanges

============================================================
Sanctioned Russian Crypto Exchanges
============================================================

Total exchanges: 6
Combined estimated volume: $12.45B

📛 Garantex
   Sources: OFAC
   Volume: $6.00B
   Addresses: 15

📛 Cryptex
   Sources: OFAC
   Volume: $5.88B
   Addresses: 12

📛 SUEX
   Sources: OFAC, EU, UK
   Volume: $0.37B
   Addresses: 8
```

```
$ python main.py trace 0x742d35... --hops 2

============================================================
Evasion Network Analysis
Seed: 0x742d35Cc6634C0532...
============================================================

Network Size:
  Nodes (addresses): 47
  Edges (transactions): 123
  High-risk transactions: 8

Nodes by hop distance:
  Hop 0: 1 addresses
  Hop 1: 18 addresses
  Hop 2: 28 addresses

High-risk transactions (mixing/layering):
  • 0x8f2a3b4c5d6e7f8a9b0c1d2e...
  • 0x1a2b3c4d5e6f7a8b9c0d1e2f...
```

## 🔮 Roadmap

- [ ] A7A5 stablecoin direct monitoring
- [ ] Real-time WebSocket updates
- [ ] D3.js network visualization
- [ ] Email/Slack/Telegram alerts
- [ ] Turkey-Russia corridor analysis
- [ ] Machine learning evasion detection

## 📄 License

MIT License - See [LICENSE](LICENSE) for details.

## ⚠️ Disclaimer

This tool is for research and compliance purposes only. Sanctions data accuracy depends on official sources (OFAC, EU, UK OFSI). Always verify with official sources for compliance decisions.
