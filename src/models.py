"""Database models for Russia Sanctions Tracker."""

from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional
from sqlalchemy import (
    Column, String, DateTime, Numeric, Boolean, 
    Integer, ForeignKey, Text, Index, Enum as SQLEnum
)
from sqlalchemy.orm import DeclarativeBase, relationship
from sqlalchemy.dialects.postgresql import JSONB


class Base(DeclarativeBase):
    """Base class for all models."""
    pass


class BlockchainType(str, Enum):
    """Supported blockchain types."""
    BITCOIN = "bitcoin"
    ETHEREUM = "ethereum"
    TRON = "tron"
    USDT_ERC20 = "usdt_erc20"
    USDT_TRC20 = "usdt_trc20"
    A7A5 = "a7a5"  # Russian stablecoin


class SanctionsSource(str, Enum):
    """Source of sanctions designation."""
    OFAC = "ofac"
    EU = "eu"
    UK = "uk"
    BIS = "bis"
    MULTIPLE = "multiple"


class AlertSeverity(str, Enum):
    """Alert severity levels."""
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SanctionedEntity(Base):
    """Sanctioned Russia-linked entities from multiple sources."""
    
    __tablename__ = "sanctioned_entities"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String(512), nullable=False, index=True)
    aliases = Column(JSONB, default=[])
    
    # Multi-source designation
    sources = Column(JSONB, default=[])  # ["ofac", "eu", "uk"]
    primary_source = Column(SQLEnum(SanctionsSource), default=SanctionsSource.OFAC)
    
    # OFAC info
    ofac_sdn_id = Column(String(64))
    ofac_program = Column(String(128))  # e.g., "RUSSIA-EO14024"
    
    # EU info
    eu_reference = Column(String(128))
    
    # UK info
    uk_reference = Column(String(128))
    
    # Entity details
    entity_type = Column(String(64))  # "exchange", "individual", "company"
    country = Column(String(64), default="Russia")
    
    # Russia-specific
    is_exchange = Column(Boolean, default=False)
    exchange_name = Column(String(128))  # garantex, cryptex, etc.
    estimated_volume_usd = Column(Numeric(18, 2))
    
    # Status
    designation_date = Column(DateTime)
    is_active = Column(Boolean, default=True)
    
    # Metadata
    notes = Column(Text)
    metadata = Column(JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    
    # Relationships
    addresses = relationship("DesignatedAddress", back_populates="entity")
    
    __table_args__ = (
        Index("ix_entity_exchange", "is_exchange"),
        Index("ix_entity_source", "primary_source"),
    )


class DesignatedAddress(Base):
    """Cryptocurrency addresses linked to sanctioned entities."""
    
    __tablename__ = "designated_addresses"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    address = Column(String(128), unique=True, nullable=False, index=True)
    blockchain = Column(SQLEnum(BlockchainType), nullable=False)
    
    # Entity link
    entity_id = Column(Integer, ForeignKey("sanctioned_entities.id"))
    entity = relationship("SanctionedEntity", back_populates="addresses")
    
    # Designation info
    designation_source = Column(SQLEnum(SanctionsSource))
    designation_date = Column(DateTime)
    
    # Exchange-specific
    exchange_name = Column(String(128))  # garantex, grinex, cryptex
    is_hot_wallet = Column(Boolean, default=False)
    is_cold_wallet = Column(Boolean, default=False)
    
    # A7A5 specific
    is_a7a5_related = Column(Boolean, default=False)
    
    # Metadata
    notes = Column(Text)
    metadata = Column(JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    is_active = Column(Boolean, default=True)
    
    # Relationships
    transactions = relationship("TrackedTransaction", back_populates="address_record")
    
    __table_args__ = (
        Index("ix_address_blockchain", "blockchain"),
        Index("ix_address_exchange", "exchange_name"),
    )


class TrackedTransaction(Base):
    """Transactions involving designated addresses."""
    
    __tablename__ = "tracked_transactions"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    tx_hash = Column(String(128), unique=True, nullable=False, index=True)
    blockchain = Column(SQLEnum(BlockchainType), nullable=False)
    
    # Transaction details
    from_address = Column(String(128), index=True)
    to_address = Column(String(128), index=True)
    value = Column(Numeric(36, 18))
    value_usd = Column(Numeric(18, 2))
    
    # Block info
    block_number = Column(Integer)
    block_timestamp = Column(DateTime)
    
    # Designation link
    designated_address_id = Column(Integer, ForeignKey("designated_addresses.id"))
    address_record = relationship("DesignatedAddress", back_populates="transactions")
    
    # Analysis
    direction = Column(String(16))  # "incoming", "outgoing"
    risk_score = Column(Numeric(5, 2))  # 0-100
    
    # Evasion pattern classification
    evasion_pattern = Column(String(64))  # "layering", "mixing", "p2p", "direct"
    
    # A7A5 specific
    is_a7a5_tx = Column(Boolean, default=False)
    
    # Metadata
    raw_data = Column(JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow)
    
    __table_args__ = (
        Index("ix_tx_timestamp", "block_timestamp"),
        Index("ix_tx_value_usd", "value_usd"),
        Index("ix_tx_evasion", "evasion_pattern"),
    )


class Alert(Base):
    """Alerts generated from monitoring."""
    
    __tablename__ = "alerts"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    alert_type = Column(String(64), nullable=False)
    severity = Column(SQLEnum(AlertSeverity), default=AlertSeverity.MEDIUM)
    
    title = Column(String(256), nullable=False)
    description = Column(Text)
    
    # Related records
    entity_id = Column(Integer, ForeignKey("sanctioned_entities.id"))
    designated_address_id = Column(Integer, ForeignKey("designated_addresses.id"))
    transaction_id = Column(Integer, ForeignKey("tracked_transactions.id"))
    
    # Status
    is_acknowledged = Column(Boolean, default=False)
    acknowledged_at = Column(DateTime)
    acknowledged_by = Column(String(64))
    
    metadata = Column(JSONB, default={})
    created_at = Column(DateTime, default=datetime.utcnow)


class MonitoringStats(Base):
    """Daily monitoring statistics."""
    
    __tablename__ = "monitoring_stats"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(DateTime, nullable=False, index=True)
    
    # Counts
    total_entities_monitored = Column(Integer, default=0)
    total_addresses_monitored = Column(Integer, default=0)
    active_addresses = Column(Integer, default=0)
    new_transactions = Column(Integer, default=0)
    
    # Values
    total_volume_usd = Column(Numeric(18, 2), default=0)
    largest_tx_usd = Column(Numeric(18, 2), default=0)
    
    # By exchange
    garantex_volume = Column(Numeric(18, 2), default=0)
    cryptex_volume = Column(Numeric(18, 2), default=0)
    a7a5_volume = Column(Numeric(18, 2), default=0)
    
    # Evasion patterns detected
    layering_detected = Column(Integer, default=0)
    mixing_detected = Column(Integer, default=0)
    
    alerts_generated = Column(Integer, default=0)
    critical_alerts = Column(Integer, default=0)
    
    created_at = Column(DateTime, default=datetime.utcnow)


class SanctionsListUpdate(Base):
    """Track sanctions list updates from each source."""
    
    __tablename__ = "sanctions_list_updates"
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(SQLEnum(SanctionsSource), nullable=False)
    
    # Update info
    update_timestamp = Column(DateTime, nullable=False)
    entries_added = Column(Integer, default=0)
    entries_removed = Column(Integer, default=0)
    entries_modified = Column(Integer, default=0)
    
    # File info
    source_url = Column(String(512))
    file_hash = Column(String(128))
    
    # Status
    success = Column(Boolean, default=True)
    error_message = Column(Text)
    
    created_at = Column(DateTime, default=datetime.utcnow)
