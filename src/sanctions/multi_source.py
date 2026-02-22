"""Multi-source sanctions list aggregation (OFAC, EU, UK)."""

import asyncio
import csv
import io
import xml.etree.ElementTree as ET
from datetime import datetime
from typing import Optional
import httpx
import structlog
from dataclasses import dataclass, field
from enum import Enum

from ..config import get_settings

logger = structlog.get_logger()


class SanctionsSource(str, Enum):
    OFAC = "ofac"
    EU = "eu"
    UK = "uk"


@dataclass
class SanctionedEntity:
    """Unified sanctioned entity from multiple sources."""
    name: str
    entity_type: str  # "individual", "entity", "exchange"
    sources: list[SanctionsSource] = field(default_factory=list)
    
    # Source-specific IDs
    ofac_id: Optional[str] = None
    eu_reference: Optional[str] = None
    uk_reference: Optional[str] = None
    
    # Details
    aliases: list[str] = field(default_factory=list)
    country: str = "Russia"
    programs: list[str] = field(default_factory=list)
    
    # Crypto-specific
    crypto_addresses: list[dict] = field(default_factory=list)
    
    # Exchange info
    is_exchange: bool = False
    exchange_name: Optional[str] = None
    estimated_volume_usd: Optional[float] = None
    
    designation_date: Optional[datetime] = None
    remarks: str = ""


class MultiSourceSanctionsFetcher:
    """Aggregate sanctions from OFAC, EU, and UK sources."""
    
    RUSSIA_PROGRAMS = [
        "RUSSIA", "RUSSIA-EO14024", "RUSSIA-EO14039", "UKRAINE-EO13661",
        "RUSSIA-UKRAINE", "CYBER2"
    ]
    
    KNOWN_EXCHANGES = {
        "garantex": {"aliases": ["grinex"], "volume": 6_000_000_000},
        "cryptex": {"aliases": [], "volume": 5_880_000_000},
        "suex": {"aliases": [], "volume": 370_000_000},
        "chatex": {"aliases": [], "volume": 200_000_000},
        "bitpapa": {"aliases": [], "volume": None}
    }
    
    def __init__(self):
        self.settings = get_settings()
        self.client = httpx.AsyncClient(timeout=120.0)
        
    async def fetch_ofac(self) -> list[SanctionedEntity]:
        """Fetch and parse OFAC SDN list for Russia-related entries."""
        logger.info("Fetching OFAC SDN list")
        
        response = await self.client.get(self.settings.ofac_sdn_url)
        response.raise_for_status()
        
        return self._parse_ofac_xml(response.text)
    
    def _parse_ofac_xml(self, xml_content: str) -> list[SanctionedEntity]:
        """Parse OFAC XML for Russia-linked entities."""
        root = ET.fromstring(xml_content)
        ns = {"sdn": "http://www.un.org/sanctions/1.0"}
        
        entities = []
        
        for entry in root.findall(".//sdnEntry", ns):
            programs = [p.text for p in entry.findall(".//program", ns) if p.text]
            russia_programs = [p for p in programs if any(rp in p for rp in self.RUSSIA_PROGRAMS)]
            
            if not russia_programs:
                continue
            
            uid = entry.find("uid", ns)
            first_name = entry.find("firstName", ns)
            last_name = entry.find("lastName", ns)
            name = " ".join(filter(None, [
                first_name.text if first_name is not None else "",
                last_name.text if last_name is not None else ""
            ]))
            
            sdn_type = entry.find("sdnType", ns)
            remarks = entry.find("remarks", ns)
            
            # Extract crypto addresses
            crypto_addresses = []
            id_list = entry.find("idList", ns)
            if id_list is not None:
                for id_entry in id_list.findall("id", ns):
                    id_type = id_entry.find("idType", ns)
                    id_number = id_entry.find("idNumber", ns)
                    
                    if id_type is not None and "Digital Currency" in (id_type.text or ""):
                        crypto_addresses.append({
                            "address": id_number.text if id_number is not None else "",
                            "blockchain": self._parse_blockchain(id_type.text)
                        })
            
            # Check for known exchanges
            name_lower = name.lower()
            is_exchange = False
            exchange_name = None
            volume = None
            
            for ex_name, ex_info in self.KNOWN_EXCHANGES.items():
                if ex_name in name_lower or any(alias in name_lower for alias in ex_info["aliases"]):
                    is_exchange = True
                    exchange_name = ex_name
                    volume = ex_info["volume"]
                    break
            
            entity = SanctionedEntity(
                name=name,
                entity_type="exchange" if is_exchange else (sdn_type.text if sdn_type is not None else "entity"),
                sources=[SanctionsSource.OFAC],
                ofac_id=uid.text if uid is not None else None,
                programs=russia_programs,
                crypto_addresses=crypto_addresses,
                is_exchange=is_exchange,
                exchange_name=exchange_name,
                estimated_volume_usd=volume,
                remarks=remarks.text if remarks is not None else ""
            )
            
            entities.append(entity)
        
        logger.info(f"Parsed {len(entities)} Russia-linked OFAC entries")
        return entities
    
    async def fetch_eu(self) -> list[SanctionedEntity]:
        """Fetch and parse EU sanctions list."""
        logger.info("Fetching EU sanctions list")
        
        try:
            response = await self.client.get(
                self.settings.eu_sanctions_url,
                follow_redirects=True
            )
            response.raise_for_status()
            return self._parse_eu_xml(response.text)
        except Exception as e:
            logger.warning(f"Failed to fetch EU sanctions: {e}")
            return []
    
    def _parse_eu_xml(self, xml_content: str) -> list[SanctionedEntity]:
        """Parse EU sanctions XML for Russia-linked entities."""
        # EU XML structure is different - simplified parser
        entities = []
        
        try:
            root = ET.fromstring(xml_content)
            # EU uses different namespace and structure
            # Find all sanctioned entities with Russia connection
            
            for entry in root.iter():
                if "russia" in ET.tostring(entry, encoding='unicode').lower():
                    # Extract name and create entity
                    name_elem = entry.find(".//wholeName") or entry.find(".//nameAlias")
                    if name_elem is not None and name_elem.text:
                        entity = SanctionedEntity(
                            name=name_elem.text,
                            entity_type="entity",
                            sources=[SanctionsSource.EU],
                            country="Russia"
                        )
                        entities.append(entity)
        except ET.ParseError as e:
            logger.warning(f"EU XML parse error: {e}")
        
        logger.info(f"Parsed {len(entities)} Russia-linked EU entries")
        return entities
    
    async def fetch_uk(self) -> list[SanctionedEntity]:
        """Fetch and parse UK sanctions list (CSV format)."""
        logger.info("Fetching UK sanctions list")
        
        try:
            response = await self.client.get(self.settings.uk_sanctions_url)
            response.raise_for_status()
            return self._parse_uk_csv(response.text)
        except Exception as e:
            logger.warning(f"Failed to fetch UK sanctions: {e}")
            return []
    
    def _parse_uk_csv(self, csv_content: str) -> list[SanctionedEntity]:
        """Parse UK sanctions CSV for Russia-linked entities."""
        entities = []
        
        reader = csv.DictReader(io.StringIO(csv_content))
        
        for row in reader:
            # Check for Russia connection
            country = row.get("Country of Origin", "").lower()
            regime = row.get("Regime", "").lower()
            
            if "russia" not in country and "russia" not in regime:
                continue
            
            name = row.get("Name 6", "") or row.get("Name 1", "")
            if not name:
                continue
            
            entity = SanctionedEntity(
                name=name,
                entity_type=row.get("Group Type", "entity").lower(),
                sources=[SanctionsSource.UK],
                uk_reference=row.get("Group ID"),
                country="Russia"
            )
            
            entities.append(entity)
        
        logger.info(f"Parsed {len(entities)} Russia-linked UK entries")
        return entities
    
    async def fetch_all(self) -> list[SanctionedEntity]:
        """Fetch and merge sanctions from all sources."""
        ofac_entities, eu_entities, uk_entities = await asyncio.gather(
            self.fetch_ofac(),
            self.fetch_eu(),
            self.fetch_uk()
        )
        
        # Merge entities by name similarity
        merged = self._merge_entities(ofac_entities + eu_entities + uk_entities)
        
        logger.info(
            "Merged sanctions lists",
            total=len(merged),
            ofac=len(ofac_entities),
            eu=len(eu_entities),
            uk=len(uk_entities)
        )
        
        return merged
    
    def _merge_entities(self, entities: list[SanctionedEntity]) -> list[SanctionedEntity]:
        """Merge entities from different sources by name matching."""
        # Simple merge by exact name match (could be improved with fuzzy matching)
        merged = {}
        
        for entity in entities:
            name_key = entity.name.lower().strip()
            
            if name_key in merged:
                # Merge sources and info
                existing = merged[name_key]
                existing.sources = list(set(existing.sources + entity.sources))
                
                if entity.ofac_id and not existing.ofac_id:
                    existing.ofac_id = entity.ofac_id
                if entity.eu_reference and not existing.eu_reference:
                    existing.eu_reference = entity.eu_reference
                if entity.uk_reference and not existing.uk_reference:
                    existing.uk_reference = entity.uk_reference
                    
                existing.crypto_addresses.extend(entity.crypto_addresses)
                existing.aliases.extend(entity.aliases)
            else:
                merged[name_key] = entity
        
        return list(merged.values())
    
    def _parse_blockchain(self, id_type: str) -> str:
        """Parse blockchain type from ID type string."""
        if "XBT" in id_type or "BTC" in id_type:
            return "bitcoin"
        elif "ETH" in id_type:
            return "ethereum"
        elif "TRX" in id_type:
            return "tron"
        elif "USDT" in id_type:
            return "usdt_trc20"
        return "unknown"
    
    async def close(self):
        await self.client.aclose()


# Pre-populated data for known Russian exchanges
RUSSIAN_EXCHANGE_ADDRESSES = {
    "garantex": [
        # Known Garantex/Grinex addresses (add actual addresses)
    ],
    "cryptex": [
        # Known Cryptex addresses
    ],
    "a7a5": [
        # A7A5 stablecoin related addresses
    ]
}


async def main():
    """Test the multi-source fetcher."""
    fetcher = MultiSourceSanctionsFetcher()
    try:
        entities = await fetcher.fetch_all()
        print(f"Found {len(entities)} Russia-linked sanctioned entities")
        
        exchanges = [e for e in entities if e.is_exchange]
        print(f"\nKnown exchanges: {len(exchanges)}")
        for ex in exchanges:
            print(f"  - {ex.name} ({', '.join(str(s.value) for s in ex.sources)})")
            if ex.crypto_addresses:
                print(f"    Crypto addresses: {len(ex.crypto_addresses)}")
    finally:
        await fetcher.close()


if __name__ == "__main__":
    asyncio.run(main())
