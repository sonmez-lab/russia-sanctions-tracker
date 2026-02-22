"""Tests for Russia Sanctions Tracker."""

import pytest
import asyncio
from datetime import datetime
from decimal import Decimal

# Test imports
from src.config import get_settings, Settings
from src.models import BlockchainType, SanctionsSource, AlertSeverity
from src.sanctions.multi_source import MultiSourceSanctionsFetcher, SanctionedEntity
from src.monitors.blockchain import EvasionPattern, AddressRiskProfile


class TestConfig:
    """Test configuration module."""
    
    def test_settings_defaults(self):
        """Test default settings values."""
        settings = get_settings()
        
        assert settings.app_name == "Russia Sanctions Tracker"
        assert settings.port == 8001
        assert settings.monitor_interval_minutes == 10
        assert settings.alert_threshold_usd == 50000.0
    
    def test_settings_cached(self):
        """Test that settings are cached."""
        settings1 = get_settings()
        settings2 = get_settings()
        
        assert settings1 is settings2
    
    def test_known_exchanges(self):
        """Test that known exchanges are configured."""
        settings = get_settings()
        
        assert "garantex" in settings.russia_designated_exchanges
        assert "cryptex" in settings.russia_designated_exchanges
        assert "suex" in settings.russia_designated_exchanges


class TestModels:
    """Test database models."""
    
    def test_blockchain_type_enum(self):
        """Test BlockchainType enum values."""
        assert BlockchainType.BITCOIN.value == "bitcoin"
        assert BlockchainType.ETHEREUM.value == "ethereum"
        assert BlockchainType.A7A5.value == "a7a5"
    
    def test_sanctions_source_enum(self):
        """Test SanctionsSource enum values."""
        assert SanctionsSource.OFAC.value == "ofac"
        assert SanctionsSource.EU.value == "eu"
        assert SanctionsSource.UK.value == "uk"


class TestEvasionPatterns:
    """Test evasion pattern detection."""
    
    def test_evasion_pattern_enum(self):
        """Test EvasionPattern enum values."""
        assert EvasionPattern.DIRECT.value == "direct"
        assert EvasionPattern.LAYERING.value == "layering"
        assert EvasionPattern.MIXING.value == "mixing"
        assert EvasionPattern.P2P.value == "p2p"
        assert EvasionPattern.CHAIN_HOPPING.value == "chain_hopping"


class TestAddressRiskProfile:
    """Test risk profile calculations."""
    
    def test_empty_profile_risk_score(self):
        """Test risk score for empty profile."""
        profile = AddressRiskProfile(
            address="0x123",
            blockchain=BlockchainType.ETHEREUM
        )
        
        assert profile.risk_score == 0.0
    
    def test_high_volume_risk_score(self):
        """Test risk score for high volume."""
        profile = AddressRiskProfile(
            address="0x123",
            blockchain=BlockchainType.ETHEREUM,
            total_volume_usd=Decimal("2000000")  # $2M
        )
        
        assert profile.risk_score >= 30
    
    def test_layering_risk_score(self):
        """Test risk score with layering events."""
        profile = AddressRiskProfile(
            address="0x123",
            blockchain=BlockchainType.ETHEREUM,
            layering_events=5
        )
        
        assert profile.risk_score >= 25
    
    def test_mixing_risk_score(self):
        """Test risk score with mixing events."""
        profile = AddressRiskProfile(
            address="0x123",
            blockchain=BlockchainType.ETHEREUM,
            mixing_events=3
        )
        
        assert profile.risk_score >= 25
    
    def test_combined_risk_score(self):
        """Test combined risk factors."""
        profile = AddressRiskProfile(
            address="0x123",
            blockchain=BlockchainType.ETHEREUM,
            total_volume_usd=Decimal("2000000"),
            tx_count=1500,
            layering_events=10,
            mixing_events=5
        )
        
        # Should hit max (100)
        assert profile.risk_score == 100


class TestSanctionedEntity:
    """Test SanctionedEntity dataclass."""
    
    def test_basic_entity(self):
        """Test creating a basic entity."""
        entity = SanctionedEntity(
            name="Test Entity",
            entity_type="company"
        )
        
        assert entity.name == "Test Entity"
        assert entity.sources == []
        assert entity.is_exchange is False
    
    def test_exchange_entity(self):
        """Test exchange entity."""
        from src.sanctions.multi_source import SanctionsSource as MS
        
        entity = SanctionedEntity(
            name="Garantex",
            entity_type="exchange",
            sources=[MS.OFAC, MS.EU],
            is_exchange=True,
            exchange_name="garantex",
            estimated_volume_usd=6_000_000_000
        )
        
        assert entity.is_exchange is True
        assert len(entity.sources) == 2
        assert entity.estimated_volume_usd == 6_000_000_000


class TestMultiSourceFetcher:
    """Test multi-source sanctions fetcher."""
    
    def test_known_exchanges_data(self):
        """Test known exchanges are defined."""
        fetcher = MultiSourceSanctionsFetcher()
        
        assert "garantex" in fetcher.KNOWN_EXCHANGES
        assert "cryptex" in fetcher.KNOWN_EXCHANGES
        assert fetcher.KNOWN_EXCHANGES["garantex"]["volume"] == 6_000_000_000
    
    def test_russia_programs_defined(self):
        """Test Russia programs are defined."""
        assert "RUSSIA" in MultiSourceSanctionsFetcher.RUSSIA_PROGRAMS
        assert "RUSSIA-EO14024" in MultiSourceSanctionsFetcher.RUSSIA_PROGRAMS
    
    def test_blockchain_parsing(self):
        """Test blockchain type parsing."""
        fetcher = MultiSourceSanctionsFetcher()
        
        assert fetcher._parse_blockchain("XBT") == "bitcoin"
        assert fetcher._parse_blockchain("ETH") == "ethereum"
        assert fetcher._parse_blockchain("TRX") == "tron"


# Async tests
@pytest.fixture
def event_loop():
    """Create event loop for async tests."""
    loop = asyncio.new_event_loop()
    yield loop
    loop.close()


class TestAsyncOperations:
    """Test async operations."""
    
    @pytest.mark.asyncio
    async def test_fetcher_initialization(self):
        """Test multi-source fetcher can be initialized."""
        fetcher = MultiSourceSanctionsFetcher()
        assert fetcher.client is not None
        await fetcher.close()


# Integration tests (require network)
class TestIntegration:
    """Integration tests - require network access."""
    
    @pytest.mark.skip(reason="Requires network access")
    @pytest.mark.asyncio
    async def test_fetch_ofac(self):
        """Test fetching OFAC list."""
        fetcher = MultiSourceSanctionsFetcher()
        try:
            entities = await fetcher.fetch_ofac()
            assert isinstance(entities, list)
        finally:
            await fetcher.close()
    
    @pytest.mark.skip(reason="Requires network access")
    @pytest.mark.asyncio
    async def test_fetch_all_sources(self):
        """Test fetching from all sources."""
        fetcher = MultiSourceSanctionsFetcher()
        try:
            entities = await fetcher.fetch_all()
            assert isinstance(entities, list)
        finally:
            await fetcher.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
