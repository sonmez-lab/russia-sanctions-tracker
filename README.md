# Russia Sanctions Tracker

[![Python](https://img.shields.io/badge/python-3.10+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](https://opensource.org/licenses/MIT)

**Track and analyze Russia-linked cryptocurrency sanctions evasion patterns and designated entities.**

## 🎯 Purpose

Russia's crypto sanctions evasion has reached industrial scale, with the A7A5 stablecoin alone processing $93.3B in its first year. This tool tracks:

- OFAC/EU-designated Russian crypto exchanges
- A7A5 stablecoin transaction patterns
- Sanctioned entity wallet activity
- Turkey-Russia crypto corridor flows

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

- Multi-source sanctions list aggregation (OFAC, EU, UK, BIS)
- Blockchain activity monitoring for designated addresses
- Time-series analysis correlating sanctions announcements
- Evasion pattern classification
- D3.js visualizations

## 📄 License

MIT License
