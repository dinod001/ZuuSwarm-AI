"""
CRM MCP Server — exposes the existing CRMTool over the Model Context Protocol.

This is a thin wrapper around `src/agents/tools/crm_tool.py`. The business
logic stays exactly where it was — this file only adds the MCP transport layer.

Transport: stdio (default for local servers)

Run standalone:
    python -m mcp_servers.crm_server

Inspect interactively:
    npx @modelcontextprotocol/inspector python -m mcp_servers.crm_server

IMPORTANT — stdio gotcha:
    MCP over stdio uses stdout for the JSON-RPC protocol. NEVER `print()`
    to stdout from inside this process. All logging must go to stderr
    (loguru's default sink is stderr, so we're safe).
"""

import os
import sys

# Ensure src/ is importable when run as a script
_SRC = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
if _SRC not in sys.path:
    sys.path.insert(0, _SRC)

from dotenv import load_dotenv
# Subprocess CWD is src/, but .env lives at project root
_PROJECT_ROOT = os.path.dirname(_SRC)
load_dotenv(os.path.join(_PROJECT_ROOT, ".env"))

from loguru import logger
from mcp.server.fastmcp import FastMCP

from agents.tools.crm_tool import CRMTool


# ── Server + tool instance ──────────────────────────────────────

mcp = FastMCP("machina-crm")

# Lazy-init so that --help / import-only uses don't hit the DB
_crm: CRMTool | None = None


def _get_crm() -> CRMTool:
    global _crm
    if _crm is None:
        logger.info("Initialising CRMTool inside MCP server...")
        _crm = CRMTool()
    return _crm


# ── MCP Tools ───────────────────────────────────────────────────

@mcp.tool()
def create_ticket(
    issue_description: str,
    ticket_type: str,
    severity: str,
    reported_by: str,
    ticket_id: str | None = None,
    assigned_to: str = "AI-Agent",
) -> str:
    """Create a new IT support ticket."""
    return _get_crm().dispatch(
        "create_ticket",
        {
            "issue_description": issue_description,
            "ticket_type": ticket_type,
            "severity": severity,
            "reported_by": reported_by,
            "ticket_id": ticket_id,
            "assigned_to": assigned_to,
        },
    )

@mcp.tool()
def get_ticket_status(ticket_id: str) -> str:
    """Check a ticket's current status and details."""
    return _get_crm().dispatch("get_ticket_status", {"ticket_id": ticket_id})

@mcp.tool()
def update_ticket(
    ticket_id: str,
    status: str,
    assigned_to: str | None = None,
    resolution_notes: str | None = None,
) -> str:
    """Update a ticket's status, assignment, or resolution notes."""
    return _get_crm().dispatch(
        "update_ticket",
        {
            "ticket_id": ticket_id,
            "status": status,
            "assigned_to": assigned_to,
            "resolution_notes": resolution_notes,
        },
    )

@mcp.tool()
def get_asset_health(asset_name: str) -> str:
    """Check an asset's health status, CPU, and memory usage."""
    return _get_crm().dispatch("get_asset_health", {"asset_name": asset_name})

@mcp.tool()
def check_service_status(service_name: str) -> str:
    """Check a service's current operational status."""
    return _get_crm().dispatch("check_service_status", {"service_name": service_name})

@mcp.tool()
def check_incident_history(affected_service: str, limit: int = 3) -> str:
    """Look up past incident resolutions for a given service."""
    return _get_crm().dispatch(
        "check_incident_history",
        {"affected_service": affected_service, "limit": limit},
    )

@mcp.tool()
def perform_system_action(
    ticket_id: str,
    action_type: str,
    resolution_notes: str,
) -> str:
    """Execute a system action and resolve the ticket."""
    return _get_crm().dispatch(
        "perform_system_action",
        {
            "ticket_id": ticket_id,
            "action_type": action_type,
            "resolution_notes": resolution_notes,
        },
    )

@mcp.tool()
def check_user_clearance(email: str) -> str:
    """Check an employee's SQL clearance level by their email."""
    return _get_crm().dispatch("check_user_clearance", {"email": email})

@mcp.tool()
def get_all_asset_names() -> str:
    """Get a list of all valid asset names in the system."""
    return _get_crm().dispatch("get_all_asset_names", {})

@mcp.tool()
def get_all_service_names() -> str:
    """Get a list of all valid service names in the system."""
    return _get_crm().dispatch("get_all_service_names", {})


# ── Entry point ────────────────────────────────────────────────

if __name__ == "__main__":
    logger.info("Starting machina-crm MCP server on stdio...")
    mcp.run()
