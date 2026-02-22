"""Configuration settings for Russia Sanctions Tracker."""

from pydantic_settings import BaseSettings
from pydantic import Field
from typing import Optional
from functools import lru_cache


class Settings(BaseSettings):
    """Application settings loaded from environment variables."""
    
    # App
    app_name: str = "Russia Sanctions Tracker"
    app_version: str = "0.1.0"
    debug: bool = False
    
    # API Server
    host: str = "0.0.0.0"
    port: int = 8001
    
    # Database
    database_url: str = Field(
        default="postgresql+asyncpg://localhost/russia_sanctions_tracker",
        description="PostgreSQL connection URL"
    )
    
    # Redis
    redis_url: str = "redis://localhost:6379/1"
    
    # Multi-source Sanctions Lists
    ofac_sdn_url: str = "https://www.treasury.gov/ofac/downloads/sdn.xml"
    eu_sanctions_url: str = "https://webgate.ec.europa.eu/fsd/fsf/public/files/xmlFullSanctionsList_1_1/content"
    uk_sanctions_url: str = "https://ofsistorage.blob.core.windows.net/publishlive/2022format/ConList.csv"
    
    sanctions_update_interval_hours: int = 12
    
    # Blockchain APIs
    etherscan_api_key: Optional[str] = None
    etherscan_base_url: str = "https://api.etherscan.io/api"
    
    trongrid_api_key: Optional[str] = None
    trongrid_base_url: str = "https://api.trongrid.io"
    
    blockchair_api_key: Optional[str] = None
    blockchair_base_url: str = "https://api.blockchair.com"
    
    # Monitoring
    monitor_interval_minutes: int = 10
    alert_threshold_usd: float = 50000.0
    
    # Russia-specific targets
    russia_designated_exchanges: list[str] = Field(
        default=["garantex", "grinex", "cryptex", "suex", "chatex", "bitpapa"],
        description="Known Russia-linked sanctioned exchanges"
    )
    
    # A7A5 Stablecoin tracking
    a7a5_contract_addresses: list[str] = Field(
        default=[],
        description="A7A5 stablecoin contract addresses"
    )
    
    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"


@lru_cache
def get_settings() -> Settings:
    """Get cached settings instance."""
    return Settings()
