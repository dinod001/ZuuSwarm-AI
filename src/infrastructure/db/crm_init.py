"""
IT Operations database initialization.

Creates IT Ops tables via Supabase PostgreSQL schema.
Tables are created by supabase_schema.py (applied via ``make init-supabase``).
This module provides helpers to verify the schema is present.
"""

from loguru import logger
from sqlalchemy import text
from .sql_client import get_sql_engine


_REQUIRED_TABLES = [
    "divisions",
    "employees",
    "services",
    "assets_inventory",
    "live_tickets",
    "incident_history",
]


def init_crm_schema():
    """
    Verify IT Ops schema exists in Supabase PostgreSQL.

    IT Ops tables are created as part of the full Supabase schema
    (``supabase_schema.py``).  This function is kept for backward
    compatibility and simply logs a confirmation.
    """
    if check_crm_schema():
        logger.info("✓ IT Ops schema already exists in Supabase")
    else:
        logger.warning(
            "⚠️  IT Ops tables missing — run 'make init-supabase' to create them"
        )


def check_crm_schema() -> bool:
    """
    Check if all required IT Ops tables exist in PostgreSQL.

    Returns:
        True if all required tables exist
    """
    engine = get_sql_engine()

    placeholders = ", ".join(f":t{i}" for i in range(len(_REQUIRED_TABLES)))
    params = {f"t{i}": t for i, t in enumerate(_REQUIRED_TABLES)}

    with engine.connect() as conn:
        result = conn.execute(
            text(f"""
                SELECT tablename FROM pg_tables 
                WHERE schemaname = 'public'
                  AND tablename IN ({placeholders})
            """),
            params,
        )
        existing = {row[0] for row in result}

    missing = set(_REQUIRED_TABLES) - existing

    if missing:
        logger.warning(f"Missing IT Ops tables: {missing}")
        return False

    logger.info(f"✓ All IT Ops tables exist: {existing}")
    return True


if __name__ == "__main__":
    if check_crm_schema():
        logger.success("✓ IT Ops schema already exists")
    else:
        logger.warning("⚠️  IT Ops tables missing — run 'make init-supabase'")
