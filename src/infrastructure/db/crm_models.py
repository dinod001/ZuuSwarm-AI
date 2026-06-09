"""
IT Operations Pydantic models for input validation.

These models mirror the CHECK constraints defined in supabase_schema.py
so that invalid data is rejected at the Python layer before reaching
the database.
"""

from enum import Enum
from typing import Optional
from pydantic import BaseModel, Field


# ---------------------------------------------------------------------------
# Enums (match DB CHECK constraints exactly)
# ---------------------------------------------------------------------------

class TicketType(str, Enum):
    ACCESS_IDENTITY = "access_identity"
    ASSET_PROVISIONING = "asset_provisioning"
    SERVICE_DEGRADATION = "service_degradation"
    CRITICAL_OUTAGE = "critical_outage"


class Severity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class TicketStatus(str, Enum):
    OPEN = "open"
    INVESTIGATING = "investigating"
    RESOLVED = "resolved"
    CLOSED = "closed"


class AssetType(str, Enum):
    SERVER = "server"
    LAPTOP = "laptop"
    NETWORK_SWITCH = "network_switch"
    LOAD_BALANCER = "load_balancer"
    STORAGE_ARRAY = "storage_array"


class ResourceStatus(str, Enum):
    """Shared status enum for services and assets."""
    HEALTHY = "healthy"
    DEGRADED = "degraded"
    OFFLINE = "offline"
    MAINTENANCE = "maintenance"


class RootCause(str, Enum):
    CONFIGURATION_DRIFT = "configuration_drift"
    RESOURCE_EXHAUSTION = "resource_exhaustion"
    SOFTWARE_BUG = "software_bug"
    HUMAN_ERROR = "human_error"
    EXTERNAL_ATTACK = "external_attack"
    HARDWARE_FAILURE = "hardware_failure"


# ---------------------------------------------------------------------------
# Request models (input validation)
# ---------------------------------------------------------------------------

class SaveTicketRequest(BaseModel):
    """Validates input for creating a new live ticket."""
    ticket_id: str = Field(..., min_length=1, max_length=50)
    issue_description: str = Field(..., min_length=1, max_length=2000)
    ticket_type: TicketType
    severity: Severity
    reported_by: str = Field(..., min_length=1, max_length=50)
    assigned_to: str = Field(default="AI-Agent-01", max_length=50)


class UpdateTicketRequest(BaseModel):
    """Validates input for updating a ticket's status."""
    ticket_id: str = Field(..., min_length=1, max_length=50)
    status: TicketStatus
    assigned_to: Optional[str] = Field(default=None, max_length=50)
    resolution_notes: Optional[str] = Field(default=None, max_length=5000)


# ---------------------------------------------------------------------------
# Response models (structured return types)
# ---------------------------------------------------------------------------

class AssetStatusResponse(BaseModel):
    """Structured response for asset status checks."""
    id: str
    name: str
    asset_type: Optional[str] = None
    status: Optional[str] = None
    cpu_usage_percent: Optional[int] = None
    memory_usage_percent: Optional[int] = None
    location: Optional[str] = None


class ServiceHealthResponse(BaseModel):
    """Structured response for service health checks."""
    id: str
    name: str
    status: Optional[str] = None
    owner_division: Optional[str] = None
    version: Optional[str] = None


class IncidentHistoryResponse(BaseModel):
    """Structured response for past incident lookups."""
    id: str
    title: str
    resolution_notes: Optional[str] = None
    root_cause: Optional[str] = None
    resolution_time_minutes: Optional[int] = None
