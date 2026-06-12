"""
IT Operations MCP Tools — Ticketing, Observability, and Action tools.

Three tool classes matching the L1/L2/L3 agent architecture:
  - TicketingTool  (L1) — create tickets, check status
  - ObservabilityTool (L2) — check asset health, service status
  - ActionTool     (L3) — check incident history, perform system actions
"""

from typing import Optional
from loguru import logger

from services.crm_service.crm_db_client import (
    save_live_ticket,
    get_ticket_status,
    check_asset_status,
    check_service_health,
    check_incident_history,
    perform_system_action,
    update_ticket_status,
    check_user_clearance,
)


# ---------------------------------------------------------------------------
# 1. Ticketing MCP — used primarily by L1 Agent
# ---------------------------------------------------------------------------


class TicketingTool:
    """
    Ticket management tool for the L1 (Triage) Agent.

    Actions:
        create_ticket   — Create a new IT support ticket
        get_ticket_status — Check a ticket's current status
        update_ticket   — Update ticket status/assignment
    """

    def create_ticket(
        self,
        issue_description: str,
        ticket_type: str,
        severity: str,
        reported_by: str,
        ticket_id: Optional[str] = None,
        assigned_to: str = "AI-Agent",
    ) -> str:
        """Create a new ticket. Returns the ticket ID."""
        tid = save_live_ticket(
            issue_description=issue_description,
            ticket_type=ticket_type,
            severity=severity,
            reported_by=reported_by,
            ticket_id=ticket_id,
            assigned_to=assigned_to,
        )
        return f"Ticket {tid} created successfully (status: open, assigned: {assigned_to})"

    def get_ticket_status(self, ticket_id: str) -> str:
        """Check a ticket's current status and details."""
        ticket = get_ticket_status(ticket_id)
        if ticket is None:
            return f"Ticket {ticket_id} not found."

        return (
            f"Ticket: {ticket.id}\n"
            f"Description: {ticket.issue_description}\n"
            f"Type: {ticket.ticket_type}\n"
            f"Severity: {ticket.severity}\n"
            f"Status: {ticket.status}\n"
            f"Assigned to: {ticket.assigned_to or 'Unassigned'}\n"
            f"Reported by: {ticket.reported_by}\n"
            f"Resolution: {ticket.resolution_notes or 'N/A'}"
        )

    def update_ticket(
        self,
        ticket_id: str,
        status: str,
        assigned_to: Optional[str] = None,
        resolution_notes: Optional[str] = None,
    ) -> str:
        """Update a ticket's status, assignment, or resolution notes."""
        success = update_ticket_status(
            ticket_id=ticket_id,
            status=status,
            assigned_to=assigned_to,
            resolution_notes=resolution_notes,
        )
        if success:
            return f"Ticket {ticket_id} updated → status: {status}"
        return f"Ticket {ticket_id} not found."




# ---------------------------------------------------------------------------
# 2. Observability MCP — used primarily by L2 Agent
# ---------------------------------------------------------------------------


class ObservabilityTool:
    """
    System observability tool for the L2 (Diagnostic) Agent.

    Actions:
        get_asset_health     — Check asset (server/laptop/etc.) health
        check_service_status — Check service health status
    """

    def get_asset_health(self, asset_name: str) -> str:
        """Check an asset's health status, CPU, and memory usage."""
        asset = check_asset_status(asset_name)
        if asset is None:
            return f"Asset '{asset_name}' not found in inventory."

        cpu = f"{asset.cpu_usage_percent}%" if asset.cpu_usage_percent is not None else "N/A"
        mem = f"{asset.memory_usage_percent}%" if asset.memory_usage_percent is not None else "N/A"

        return (
            f"Asset: {asset.name} ({asset.asset_type})\n"
            f"Status: {asset.status}\n"
            f"CPU: {cpu}\n"
            f"Memory: {mem}\n"
            f"Location: {asset.location or 'N/A'}"
        )

    def check_service_status(self, service_name: str) -> str:
        """Check a service's current operational status."""
        service = check_service_health(service_name)
        if service is None:
            return f"Service '{service_name}' not found."

        return (
            f"Service: {service.name} (ID: {service.id})\n"
            f"Status: {service.status}\n"
            f"Division: {service.owner_division or 'N/A'}\n"
            f"Version: {service.version or 'N/A'}"
        )




# ---------------------------------------------------------------------------
# 3. Action MCP — used primarily by L3 Agent
# ---------------------------------------------------------------------------


class ActionTool:
    """
    System action tool for the L3 (Resolution) Agent.

    Actions:
        check_incident_history — Look up past incidents for a service
        perform_system_action  — Execute a fix and resolve the ticket
    """

    def check_incident_history(
        self,
        affected_service: str,
        limit: int = 3,
    ) -> str:
        """Look up past incident resolutions for a given service."""
        incidents = check_incident_history(
            affected_service=affected_service,
            limit=limit,
        )

        if not incidents:
            return f"No past incidents found for service '{affected_service}'."

        lines = [f"Past incidents for '{affected_service}' ({len(incidents)} found):"]
        for i, inc in enumerate(incidents, 1):
            lines.append(
                f"\n--- Incident {i}: {inc.title} ---\n"
                f"Root cause: {inc.root_cause or 'Unknown'}\n"
                f"Resolution: {inc.resolution_notes or 'N/A'}\n"
                f"Time to resolve: {inc.resolution_time_minutes or 'N/A'} minutes"
            )
        return "\n".join(lines)

    def perform_system_action(
        self,
        ticket_id: str,
        action_type: str,
        resolution_notes: str,
    ) -> str:
        """Execute a system action and resolve the ticket."""
        success = perform_system_action(
            ticket_id=ticket_id,
            action_type=action_type,
            resolution_notes=resolution_notes,
        )

        if success:
            return (
                f"✅ Action '{action_type}' executed successfully.\n"
                f"Ticket {ticket_id} has been resolved.\n"
                f"Notes: {resolution_notes}"
            )
        return f"⚠️ Ticket {ticket_id} not found. Action was not applied."


# ---------------------------------------------------------------------------
# 4. Unified CRM Tool
# ---------------------------------------------------------------------------


class CRMTool:
    """
    Unified IT Operations CRM Tool that provides a dispatch interface
    for Ticketing, Observability, and Action tools.
    """

    def __init__(self):
        self.ticketing = TicketingTool()
        self.observability = ObservabilityTool()
        self.action = ActionTool()

    def dispatch(self, action: str, params: dict) -> str:
        """Dispatch the given action to the appropriate underlying tool."""
        if action == "create_ticket":
            return self.ticketing.create_ticket(**params)
        elif action == "get_ticket_status":
            return self.ticketing.get_ticket_status(**params)
        elif action == "update_ticket":
            return self.ticketing.update_ticket(**params)
        elif action == "get_asset_health":
            return self.observability.get_asset_health(**params)
        elif action == "check_service_status":
            return self.observability.check_service_status(**params)
        elif action == "check_incident_history":
            return self.action.check_incident_history(**params)
        elif action == "perform_system_action":
            return self.action.perform_system_action(**params)
        elif action == "check_user_clearance":
            clearance = check_user_clearance(**params)
            return str(clearance) if clearance is not None else "Unknown"
        return f"Unknown action: {action}"


