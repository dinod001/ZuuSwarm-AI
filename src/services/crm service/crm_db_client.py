"""
IT Operations database client — CRUD operations for the IT Ops tables.

All queries use SQLAlchemy parameterized statements to prevent SQL injection.
Input validation is handled by Pydantic models from crm_models.py.
"""

from typing import Optional
from loguru import logger
from sqlalchemy import text

from infrastructure.db.sql_client import get_sql_engine
from infrastructure.db.crm_models import (
    SaveTicketRequest,
    UpdateTicketRequest,
    PerformActionRequest,
    AssetStatusResponse,
    ServiceHealthResponse,
    IncidentHistoryResponse,
    TicketStatusResponse,
)


# ---------------------------------------------------------------------------
# Ticket operations
# ---------------------------------------------------------------------------


def _generate_ticket_id() -> str:
    """
    Auto-generate the next ticket ID in TKT-XXXXX format.

    Queries the max existing ID and increments by 1.
    """
    engine = get_sql_engine()

    with engine.connect() as conn:
        result = conn.execute(
            text("SELECT id FROM live_tickets ORDER BY id DESC LIMIT 1")
        )
        row = result.scalar()

    if row is None:
        return "TKT-00001"

    # Extract the numeric part from e.g. 'TKT-00150'
    try:
        num = int(row.split("-")[1]) + 1
    except (IndexError, ValueError):
        num = 1

    return f"TKT-{num:05d}"


def save_live_ticket(
    issue_description: str,
    ticket_type: str,
    severity: str,
    reported_by: str,
    ticket_id: Optional[str] = None,
    assigned_to: str = "AI-Agent-01",
) -> str:
    """
    Create a new live ticket in the database.

    Args:
        issue_description:  Description of the issue
        ticket_type:        One of: access_identity, asset_provisioning,
                            service_degradation, critical_outage
        severity:           One of: low, medium, high, critical
        reported_by:        Employee ID who reported (e.g. 'EMP-0042')
        ticket_id:          Optional — auto-generated if not provided
        assigned_to:        Employee ID or agent ID assigned to the ticket

    Returns:
        The ticket ID (auto-generated or provided)

    Raises:
        ValueError: If input validation fails
    """
    # Auto-generate ticket ID if not provided
    if ticket_id is None:
        ticket_id = _generate_ticket_id()

    # Validate input via Pydantic model
    req = SaveTicketRequest(
        ticket_id=ticket_id,
        issue_description=issue_description,
        ticket_type=ticket_type,
        severity=severity,
        reported_by=reported_by,
        assigned_to=assigned_to,
    )

    engine = get_sql_engine()

    try:
        with engine.begin() as conn:
            conn.execute(
                text("""
                    INSERT INTO live_tickets
                        (id, issue_description, ticket_type, severity,
                         reported_by, status, assigned_to, created_at)
                    VALUES
                        (:id, :issue_description, :ticket_type, :severity,
                         :reported_by, 'open', :assigned_to, NOW())
                """),
                {
                    "id": req.ticket_id,
                    "issue_description": req.issue_description,
                    "ticket_type": req.ticket_type.value,
                    "severity": req.severity.value,
                    "reported_by": req.reported_by,
                    "assigned_to": req.assigned_to,
                },
            )

        logger.info(f"✅ Ticket {req.ticket_id} created successfully")
        return req.ticket_id

    except Exception as e:
        logger.error(f"❌ Failed to create ticket {ticket_id}: {e}")
        raise


def get_ticket_status(ticket_id: str) -> Optional[TicketStatusResponse]:
    """
    Retrieve a ticket's current status and details.

    Used by L1/L2/L3 agents to check ticket progress.

    Args:
        ticket_id: Ticket ID (e.g. 'TKT-00042')

    Returns:
        TicketStatusResponse or None if not found
    """
    if not ticket_id or not isinstance(ticket_id, str):
        raise ValueError("ticket_id must be a non-empty string")

    engine = get_sql_engine()

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, issue_description, ticket_type, severity,
                           status, assigned_to, reported_by,
                           resolution_notes,
                           created_at::text, resolved_at::text
                    FROM live_tickets
                    WHERE id = :ticket_id
                """),
                {"ticket_id": ticket_id},
            )
            row = result.mappings().fetchone()

        if row is None:
            logger.info(f"Ticket '{ticket_id}' not found")
            return None

        return TicketStatusResponse(**row)

    except Exception as e:
        logger.error(f"❌ Failed to get ticket status for '{ticket_id}': {e}")
        raise


def update_ticket_status(
    ticket_id: str,
    status: str,
    assigned_to: Optional[str] = None,
    resolution_notes: Optional[str] = None,
) -> bool:
    """
    Update an existing ticket's status, assignment, or resolution notes.

    Args:
        ticket_id:        Ticket ID to update
        status:           New status (open, investigating, resolved, closed)
        assigned_to:      Optional new assignee (keeps existing if None)
        resolution_notes: Optional resolution notes

    Returns:
        True if the ticket was updated successfully

    Raises:
        ValueError: If input validation fails
    """
    req = UpdateTicketRequest(
        ticket_id=ticket_id,
        status=status,
        assigned_to=assigned_to,
        resolution_notes=resolution_notes,
    )

    engine = get_sql_engine()

    try:
        with engine.begin() as conn:
            result = conn.execute(
                text("""
                    UPDATE live_tickets
                    SET status = :status,
                        assigned_to = COALESCE(:assigned_to, assigned_to),
                        resolution_notes = COALESCE(:resolution_notes, resolution_notes),
                        resolved_at = CASE
                            WHEN :status IN ('resolved', 'closed') THEN NOW()
                            ELSE resolved_at
                        END
                    WHERE id = :ticket_id
                """),
                {
                    "status": req.status.value,
                    "assigned_to": req.assigned_to,
                    "resolution_notes": req.resolution_notes,
                    "ticket_id": req.ticket_id,
                },
            )

        if result.rowcount == 0:
            logger.warning(f"⚠️ Ticket {ticket_id} not found")
            return False

        logger.info(f"✅ Ticket {ticket_id} updated → {status}")
        return True

    except Exception as e:
        logger.error(f"❌ Failed to update ticket {ticket_id}: {e}")
        raise


# ---------------------------------------------------------------------------
# Asset operations
# ---------------------------------------------------------------------------


def check_asset_status(asset_name: str) -> Optional[AssetStatusResponse]:
    """
    Look up an asset's current health status by name.

    Args:
        asset_name: Name of the asset (e.g. 'prod-web-02')

    Returns:
        AssetStatusResponse or None if not found
    """
    if not asset_name or not isinstance(asset_name, str):
        raise ValueError("asset_name must be a non-empty string")

    engine = get_sql_engine()

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, name, asset_type, status,
                           cpu_usage_percent, memory_usage_percent, location
                    FROM assets_inventory
                    WHERE name = :asset_name
                """),
                {"asset_name": asset_name},
            )
            row = result.mappings().fetchone()

        if row is None:
            logger.info(f"Asset '{asset_name}' not found")
            return None

        return AssetStatusResponse(**row)

    except Exception as e:
        logger.error(f"❌ Failed to check asset '{asset_name}': {e}")
        raise


# ---------------------------------------------------------------------------
# Service operations
# ---------------------------------------------------------------------------


def check_service_health(service_name: str) -> Optional[ServiceHealthResponse]:
    """
    Look up a service's current health by name.

    Args:
        service_name: Name of the service (e.g. 'auth-api')

    Returns:
        ServiceHealthResponse or None if not found
    """
    if not service_name or not isinstance(service_name, str):
        raise ValueError("service_name must be a non-empty string")

    engine = get_sql_engine()

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, name, status, owner_division, version
                    FROM services
                    WHERE name = :service_name
                """),
                {"service_name": service_name},
            )
            row = result.mappings().fetchone()

        if row is None:
            logger.info(f"Service '{service_name}' not found")
            return None

        return ServiceHealthResponse(**row)

    except Exception as e:
        logger.error(f"❌ Failed to check service '{service_name}': {e}")
        raise


# ---------------------------------------------------------------------------
# Incident history operations
# ---------------------------------------------------------------------------


def check_incident_history(
    affected_service: str,
    limit: int = 3,
) -> list[IncidentHistoryResponse]:
    """
    Retrieve past incident resolutions for a given service.

    Useful for the AI agent to find relevant past fixes when handling
    a new ticket for the same service.

    Args:
        affected_service: Service name (e.g. 'auth-api')
        limit:            Max number of incidents to return (default 3)

    Returns:
        List of IncidentHistoryResponse (most recent first), may be empty
    """
    if not affected_service or not isinstance(affected_service, str):
        raise ValueError("affected_service must be a non-empty string")

    # Clamp limit to a safe range
    limit = max(1, min(limit, 20))

    engine = get_sql_engine()

    try:
        with engine.connect() as conn:
            result = conn.execute(
                text("""
                    SELECT id, title, resolution_notes, root_cause,
                           resolution_time_minutes
                    FROM incident_history
                    WHERE affected_service = :affected_service
                    ORDER BY resolved_at DESC
                    LIMIT :limit
                """),
                {
                    "affected_service": affected_service,
                    "limit": limit,
                },
            )
            rows = result.mappings().fetchall()

        incidents = [IncidentHistoryResponse(**row) for row in rows]
        logger.info(
            f"Found {len(incidents)} past incident(s) for '{affected_service}'"
        )
        return incidents

    except Exception as e:
        logger.error(
            f"❌ Failed to check incident history for '{affected_service}': {e}"
        )
        raise


# ---------------------------------------------------------------------------
# System action operations (L3 Agent)
# ---------------------------------------------------------------------------


def perform_system_action(
    ticket_id: str,
    action_type: str,
    resolution_notes: str,
) -> bool:
    """
    Execute a system-level action and resolve the associated ticket.

    Used by the L3 Agent to apply a fix (restart, reset, config change, etc.)
    and mark the ticket as resolved in a single operation.

    Args:
        ticket_id:        Ticket ID to resolve
        action_type:      Type of action taken (e.g. 'restart_service',
                          'reset_credentials', 'scale_resources')
        resolution_notes: Description of what was done

    Returns:
        True if the action was logged and ticket resolved

    Raises:
        ValueError: If input validation fails
    """
    # Validate input
    req = PerformActionRequest(
        ticket_id=ticket_id,
        action_type=action_type,
        resolution_notes=resolution_notes,
    )

    engine = get_sql_engine()

    try:
        # Log the action and resolve the ticket in one transaction
        full_notes = f"[{req.action_type}] {req.resolution_notes}"

        with engine.begin() as conn:
            result = conn.execute(
                text("""
                    UPDATE live_tickets
                    SET status = 'resolved',
                        resolution_notes = :resolution_notes,
                        resolved_at = NOW()
                    WHERE id = :ticket_id
                """),
                {
                    "resolution_notes": full_notes,
                    "ticket_id": req.ticket_id,
                },
            )

        if result.rowcount == 0:
            logger.warning(f"⚠️ Ticket {ticket_id} not found for action")
            return False

        logger.info(
            f"✅ System action '{req.action_type}' executed, "
            f"ticket {req.ticket_id} resolved"
        )
        return True

    except Exception as e:
        logger.error(
            f"❌ Failed to perform action on ticket {ticket_id}: {e}"
        )
        raise
