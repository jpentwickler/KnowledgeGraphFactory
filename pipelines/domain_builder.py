"""Domain Graph Builder - CSV → Neo4j import pipeline.

Implements three-layer validation approach:
1. CSV validation (pre-import)
2. Database constraints (NODE KEY)
3. MERGE queries (idempotent imports)

Based on patterns from neo4j-contrib/mcp-neo4j-data-modeling.
"""

import os
from pathlib import Path
from typing import Optional

import pandas as pd
from neo4j import Driver

from tools.file_tools import _get_data_dir


def validate_csv_uniqueness(csv_path: str, unique_column: str) -> dict:
    """Validate CSV has no duplicate values in unique column.

    Layer 1 validation - catches issues before Neo4j operations.

    Checks:
    - File exists and is readable
    - Unique column exists in headers
    - No null/empty values in unique column
    - No duplicate values in unique column
    - No leading/trailing whitespace in values

    Args:
        csv_path: Absolute path to CSV file
        unique_column: Name of column that should be unique

    Returns:
        {
            "valid": True/False,
            "message": "...",
            "duplicates": [...] (if any),
            "row_count": N
        }
    """
    # Check file exists
    if not os.path.isfile(csv_path):
        return {
            "valid": False,
            "message": f"File not found: {csv_path}",
            "duplicates": [],
            "row_count": 0,
        }

    try:
        # Read CSV
        df = pd.read_csv(csv_path)
        row_count = len(df)

        # Check column exists
        if unique_column not in df.columns:
            return {
                "valid": False,
                "message": f"Column '{unique_column}' not found in CSV. Available columns: {list(df.columns)}",
                "duplicates": [],
                "row_count": row_count,
            }

        # Check for null/empty values
        null_count = df[unique_column].isnull().sum()
        if null_count > 0:
            return {
                "valid": False,
                "message": f"Found {null_count} null/empty values in '{unique_column}' column",
                "duplicates": [],
                "row_count": row_count,
            }

        # Check for whitespace issues
        col_values = df[unique_column].astype(str)
        has_whitespace = (col_values.str.strip() != col_values).any()
        if has_whitespace:
            return {
                "valid": False,
                "message": f"Found leading/trailing whitespace in '{unique_column}' column. Please clean data first.",
                "duplicates": [],
                "row_count": row_count,
            }

        # Check for duplicates
        duplicates_df = df[df.duplicated(subset=[unique_column], keep=False)]
        if len(duplicates_df) > 0:
            duplicate_values = duplicates_df[unique_column].unique().tolist()
            return {
                "valid": False,
                "message": f"Found {len(duplicate_values)} duplicate values in '{unique_column}' column",
                "duplicates": duplicate_values,
                "row_count": row_count,
            }

        # All checks passed
        return {
            "valid": True,
            "message": f"CSV validation passed: {row_count} rows, all unique in '{unique_column}'",
            "duplicates": [],
            "row_count": row_count,
        }

    except Exception as exc:
        return {
            "valid": False,
            "message": f"Error reading CSV: {exc}",
            "duplicates": [],
            "row_count": 0,
        }


def create_unique_constraint(driver: Driver, label: str, unique_col: str) -> None:
    """Create NODE KEY constraint for uniqueness + existence + index.

    Layer 2 validation - database-level enforcement.

    Pattern from neo4j-contrib/mcp-neo4j-data-modeling:
    CREATE CONSTRAINT {label}_{col}_key IF NOT EXISTS
    FOR (n:{label})
    REQUIRE (n.{col}) IS NODE KEY

    NODE KEY provides:
    - Uniqueness enforcement (no duplicate values)
    - Existence enforcement (no null values)
    - Automatic range index (fast MERGE lookups)

    Args:
        driver: Neo4j driver
        label: Node label (e.g., "Product")
        unique_col: Property name (e.g., "product_id")
    """
    constraint_name = f"{label}_{unique_col}_key".lower()

    query = f"""
    CREATE CONSTRAINT {constraint_name} IF NOT EXISTS
    FOR (n:{label})
    REQUIRE (n.{unique_col}) IS NODE KEY
    """

    with driver.session() as session:
        session.run(query)


def import_nodes(driver: Driver, spec: dict, data_dir: str) -> dict:
    """Import nodes from CSV using LOAD CSV + MERGE pattern.

    Layer 3 - idempotent import using MERGE.

    Args:
        driver: Neo4j driver
        spec: Node construction spec from approved_construction_plan
        data_dir: Base directory for CSV files

    Returns:
        {
            "label": "Product",
            "count": 50,
            "errors": []
        }
    """
    label = spec["label"]
    source_file = spec["source_file"]
    unique_col = spec["unique_column_name"]

    # Build file URI for LOAD CSV
    # Neo4j requires file:/// protocol for local files
    csv_path = os.path.join(data_dir, source_file)
    file_uri = Path(csv_path).as_uri()

    # MERGE query pattern
    query = f"""
    LOAD CSV WITH HEADERS FROM '{file_uri}' AS row
    MERGE (n:{label} {{{unique_col}: trim(row.{unique_col})}})
    SET n += row
    RETURN count(n) as created
    """

    try:
        with driver.session() as session:
            result = session.run(query)
            record = result.single()
            count = record["created"] if record else 0

            return {
                "label": label,
                "count": count,
                "errors": [],
            }

    except Exception as exc:
        return {
            "label": label,
            "count": 0,
            "errors": [str(exc)],
        }


def import_relationships(driver: Driver, spec: dict, data_dir: str) -> dict:
    """Import relationships from CSV using LOAD CSV + MERGE pattern.

    CRITICAL: Must run SERIALLY (not parallel) to avoid deadlocks.

    Args:
        driver: Neo4j driver
        spec: Relationship construction spec from approved_construction_plan
        data_dir: Base directory for CSV files

    Returns:
        {
            "type": "SUPPLIED_BY",
            "count": 30,
            "orphans": 2,
            "errors": []
        }
    """
    rel_type = spec["relationship_type"]
    source_file = spec["source_file"]
    from_label = spec["from_node_label"]
    from_col = spec["from_node_column"]
    to_label = spec["to_node_label"]
    to_col = spec["to_node_column"]

    # Build file URI
    csv_path = os.path.join(data_dir, source_file)
    file_uri = Path(csv_path).as_uri()

    # MERGE query pattern
    query = f"""
    LOAD CSV WITH HEADERS FROM '{file_uri}' AS row
    MATCH (from:{from_label} {{{from_col}: trim(row.{from_col})}})
    MATCH (to:{to_label} {{{to_col}: trim(row.{to_col})}})
    MERGE (from)-[r:{rel_type}]->(to)
    SET r += row
    RETURN count(r) as created
    """

    try:
        # Import relationships
        with driver.session() as session:
            result = session.run(query)
            record = result.single()
            created_count = record["created"] if record else 0

        # Count expected relationships (CSV rows)
        df = pd.read_csv(csv_path)
        expected_count = len(df)
        orphan_count = expected_count - created_count

        return {
            "type": rel_type,
            "count": created_count,
            "orphans": orphan_count,
            "errors": [],
        }

    except Exception as exc:
        return {
            "type": rel_type,
            "count": 0,
            "orphans": 0,
            "errors": [str(exc)],
        }


def verify_import(driver: Driver) -> dict:
    """Verify graph was built correctly.

    Returns:
        {
            "node_counts": {"Product": 50, "Supplier": 20, ...},
            "relationship_counts": {"SUPPLIED_BY": 30, ...},
            "orphan_nodes": 0,
            "total_nodes": 70,
            "total_relationships": 30
        }
    """
    with driver.session() as session:
        # Count nodes by label
        node_result = session.run(
            """
            MATCH (n)
            RETURN labels(n) as labels, count(*) as count
            """
        )
        node_counts = {}
        total_nodes = 0
        for record in node_result:
            labels = record["labels"]
            count = record["count"]
            # Use first label if multiple
            label = labels[0] if labels else "Unknown"
            node_counts[label] = count
            total_nodes += count

        # Count relationships by type
        rel_result = session.run(
            """
            MATCH ()-[r]->()
            RETURN type(r) as type, count(*) as count
            """
        )
        relationship_counts = {}
        total_relationships = 0
        for record in rel_result:
            rel_type = record["type"]
            count = record["count"]
            relationship_counts[rel_type] = count
            total_relationships += count

        # Count orphan nodes (no relationships)
        orphan_result = session.run(
            """
            MATCH (n)
            WHERE NOT (n)--()
            RETURN count(n) as orphans
            """
        )
        orphan_record = orphan_result.single()
        orphan_nodes = orphan_record["orphans"] if orphan_record else 0

        return {
            "node_counts": node_counts,
            "relationship_counts": relationship_counts,
            "orphan_nodes": orphan_nodes,
            "total_nodes": total_nodes,
            "total_relationships": total_relationships,
        }


def build_domain_graph(state: dict, driver: Driver) -> dict:
    """Build the Domain Graph layer from structured CSV data.

    Implements the three-step process:
    1. Validate all CSV files (pre-import layer)
    2. Create NODE KEY constraints (database layer)
    3. Import nodes via LOAD CSV + MERGE
    4. Import relationships via LOAD CSV + MERGE (serial)
    5. Verify import

    Args:
        state: Pipeline state with approved_construction_plan
        driver: Neo4j driver connection

    Returns:
        Verification results dict with counts and errors

    Raises:
        ValueError: If construction plan missing or CSV validation fails
        FileNotFoundError: If CSV files don't exist
    """
    # Get construction plan
    if "approved_construction_plan" not in state:
        raise ValueError(
            "No approved_construction_plan in state. "
            "Stage 3 (Schema Proposal) must be completed first."
        )

    plan = state["approved_construction_plan"]
    data_dir = _get_data_dir()

    results = {
        "nodes": [],
        "relationships": [],
        "errors": [],
        "verification": {},
    }

    print(f"\nData directory: {data_dir}")
    print(f"Construction plan items: {len(plan)}")

    # Step 1: Validate all CSV files FIRST
    print("\n[1/5] Validating CSV files...")
    for name, spec in plan.items():
        csv_path = os.path.join(data_dir, spec["source_file"])
        print(f"  Validating {spec['source_file']}...", end=" ")

        if spec["construction_type"] == "node":
            validation = validate_csv_uniqueness(csv_path, spec["unique_column_name"])
        else:
            # For relationships, just check file exists
            if not os.path.isfile(csv_path):
                validation = {
                    "valid": False,
                    "message": f"File not found: {csv_path}",
                }
            else:
                validation = {"valid": True, "message": "File exists"}

        if not validation["valid"]:
            print(f"[FAIL]")
            error_msg = f"CSV validation failed for {name}: {validation['message']}"
            results["errors"].append(error_msg)
            raise ValueError(error_msg)

        print(f"[OK]")

    # Step 2: Create all constraints
    print("\n[2/5] Creating NODE KEY constraints...")
    for name, spec in plan.items():
        if spec["construction_type"] == "node":
            label = spec["label"]
            unique_col = spec["unique_column_name"]
            print(f"  Creating constraint for {label}.{unique_col}...", end=" ")

            try:
                create_unique_constraint(driver, label, unique_col)
                print(f"[OK]")
            except Exception as exc:
                print(f"[FAIL]")
                error_msg = f"Constraint creation failed for {label}: {exc}"
                results["errors"].append(error_msg)
                raise ValueError(error_msg)

    # Step 3: Import all nodes
    print("\n[3/5] Importing nodes from CSV files...")
    for name, spec in plan.items():
        if spec["construction_type"] == "node":
            label = spec["label"]
            print(f"  Importing {label} nodes...", end=" ")

            result = import_nodes(driver, spec, data_dir)
            results["nodes"].append(result)

            if result["errors"]:
                print(f"[FAIL]")
                for error in result["errors"]:
                    print(f"    Error: {error}")
                results["errors"].extend(result["errors"])
            else:
                print(f"[OK] - {result['count']} nodes")

    # Step 4: Import relationships SERIALLY
    print("\n[4/5] Importing relationships from CSV files...")
    for name, spec in plan.items():
        if spec["construction_type"] == "relationship":
            rel_type = spec["relationship_type"]
            print(f"  Importing {rel_type} relationships...", end=" ")

            result = import_relationships(driver, spec, data_dir)
            results["relationships"].append(result)

            if result["errors"]:
                print(f"[FAIL]")
                for error in result["errors"]:
                    print(f"    Error: {error}")
                results["errors"].extend(result["errors"])
            else:
                print(f"[OK] - {result['count']} relationships", end="")
                if result["orphans"] > 0:
                    print(f" (WARNING: {result['orphans']} orphans)")
                else:
                    print()

    # Step 5: Verify
    print("\n[5/5] Verifying graph construction...")
    verification = verify_import(driver)
    results["verification"] = verification
    print(f"  Total nodes: {verification['total_nodes']}")
    print(f"  Total relationships: {verification['total_relationships']}")
    print(f"  Orphan nodes: {verification['orphan_nodes']}")

    return results
