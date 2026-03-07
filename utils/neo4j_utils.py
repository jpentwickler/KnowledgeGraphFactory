"""Neo4j connection utilities for KG-Factory.

Provides centralized driver management, connection testing, and configuration.
"""

import os
from typing import Optional

import neo4j
from neo4j import GraphDatabase, Driver


def get_neo4j_driver(
    uri: Optional[str] = None,
    user: Optional[str] = None,
    password: Optional[str] = None,
) -> Driver:
    """Create and return a Neo4j driver instance.

    Reads from environment variables if parameters not provided:
    - NEO4J_URI (required): bolt://... or neo4j://... or neo4j+s://...
    - NEO4J_USER (required): username
    - NEO4J_PASSWORD (required): password

    Args:
        uri: Neo4j connection URI (optional, defaults to env var)
        user: Neo4j username (optional, defaults to env var)
        password: Neo4j password (optional, defaults to env var)

    Returns:
        Configured Neo4j driver with connection pooling

    Raises:
        ValueError: If required env vars or parameters missing
        neo4j.exceptions.ServiceUnavailable: If can't connect to Neo4j
    """
    # Get connection parameters
    uri = uri or os.environ.get("NEO4J_URI")
    user = user or os.environ.get("NEO4J_USER")
    password = password or os.environ.get("NEO4J_PASSWORD")

    # Validate required parameters
    if not uri:
        raise ValueError(
            "NEO4J_URI is required. Set environment variable or pass as parameter."
        )
    if not user:
        raise ValueError(
            "NEO4J_USER is required. Set environment variable or pass as parameter."
        )
    if not password:
        raise ValueError(
            "NEO4J_PASSWORD is required. Set environment variable or pass as parameter."
        )

    # Create driver with connection pooling
    # Note: Encryption is automatically enabled for neo4j+s:// and bolt+s:// URIs.
    # Do NOT pass encrypted= parameter with these URIs (it will cause an error).
    pool_size = int(os.environ.get("NEO4J_POOL_SIZE", "50"))
    connection_timeout = float(os.environ.get("NEO4J_CONNECTION_TIMEOUT", "30"))

    try:
        driver = GraphDatabase.driver(
            uri,
            auth=(user, password),
            max_connection_pool_size=pool_size,
            connection_timeout=connection_timeout,
        )

        # Verify connectivity
        driver.verify_connectivity()

        return driver

    except neo4j.exceptions.ServiceUnavailable as exc:
        raise neo4j.exceptions.ServiceUnavailable(
            f"Failed to connect to Neo4j at {uri}. "
            f"Check that Neo4j is running and credentials are correct. "
            f"Error: {exc}"
        ) from exc
    except Exception as exc:
        raise Exception(f"Unexpected error creating Neo4j driver: {exc}") from exc


def test_connection(driver: Driver) -> dict:
    """Test Neo4j connection and return server info.

    Args:
        driver: Neo4j driver instance

    Returns:
        Dictionary with connection info:
        {
            "connected": True,
            "neo4j_version": "5.x.x",
            "database": "neo4j"
        }

    Raises:
        Exception: If connection test fails
    """
    try:
        # Execute a simple query to test connectivity
        with driver.session() as session:
            result = session.run(
                """
                CALL dbms.components()
                YIELD name, versions, edition
                WHERE name = 'Neo4j Kernel'
                RETURN versions[0] as version, edition
                """
            )
            record = result.single()

            if record:
                version = record["version"]
                edition = record["edition"]
            else:
                version = "unknown"
                edition = "unknown"

            # Get current database name
            db_result = session.run("CALL db.info() YIELD name RETURN name")
            db_record = db_result.single()
            database = db_record["name"] if db_record else "neo4j"

            return {
                "connected": True,
                "neo4j_version": version,
                "edition": edition,
                "database": database,
            }

    except Exception as exc:
        raise Exception(f"Connection test failed: {exc}") from exc


def close_driver(driver: Driver) -> None:
    """Safely close the Neo4j driver connection.

    Args:
        driver: Neo4j driver instance to close
    """
    try:
        driver.close()
    except Exception as exc:
        # Log but don't raise - closing is best-effort
        print(f"Warning: Error closing Neo4j driver: {exc}")
