"""Entity Resolution - Link Subject graph entities to Domain graph nodes.

Follows the Neo4j GraphRAG course patterns (Lesson 8):
1. Find unique entity labels in the subject graph
2. Find matching labels in the domain graph
3. Correlate property keys using fuzzy matching (rapidfuzz)
4. Create CORRESPONDS_TO relationships using Jaro-Winkler distance in Neo4j

Requires APOC plugin installed in Neo4j for apoc.text.jaroWinklerDistance.
"""

import re

from core.tracing import traceable
from neo4j import Driver
from rapidfuzz import fuzz


def find_unique_entity_labels(driver: Driver) -> list[str]:
    """Find all entity labels in the subject graph, excluding __ prefixed ones.

    Args:
        driver: Neo4j driver instance.

    Returns:
        List of entity label strings (e.g., ["Product", "Issue", "Feature"]).
    """
    with driver.session() as session:
        result = session.run(
            """
            MATCH (n)
            WHERE n:`__Entity__`
            WITH DISTINCT labels(n) AS entity_labels
            UNWIND entity_labels AS entity_label
            WITH entity_label
            WHERE NOT entity_label STARTS WITH "__"
            RETURN collect(entity_label) as unique_entity_labels
            """
        )
        record = result.single()
        if record:
            return record["unique_entity_labels"]
        return []


def find_unique_entity_keys(driver: Driver, label: str) -> list[str]:
    """Find property keys for entities of a given label in the subject graph.

    Args:
        driver: Neo4j driver instance.
        label: Entity label (e.g., "Product").

    Returns:
        List of property key strings.
    """
    with driver.session() as session:
        result = session.run(
            f"""
            MATCH (n:{label})
            WHERE n:`__Entity__`
            WITH DISTINCT keys(n) as entityKeys
            UNWIND entityKeys as entityKey
            RETURN collect(distinct(entityKey)) as unique_entity_keys
            """
        )
        record = result.single()
        if record:
            return record["unique_entity_keys"]
        return []


def find_unique_domain_keys(driver: Driver, label: str) -> list[str]:
    """Find property keys for domain nodes (NOT __Entity__) of a given label.

    Args:
        driver: Neo4j driver instance.
        label: Domain node label (e.g., "Product").

    Returns:
        List of property key strings.
    """
    with driver.session() as session:
        result = session.run(
            f"""
            MATCH (n:{label})
            WHERE NOT n:`__Entity__`
            WITH DISTINCT keys(n) as domainKeys
            UNWIND domainKeys as domainKey
            RETURN collect(distinct(domainKey)) as unique_domain_keys
            """
        )
        record = result.single()
        if record:
            return record["unique_domain_keys"]
        return []


def normalize_key(label: str, key: str) -> str:
    """Normalize a property key for a given label.

    Keys are normalized by:
    - lowercase the key
    - remove any leading/trailing whitespace
    - remove label prefix from key
    - replace internal whitespace with "_"

    Examples:
        normalize_key("Product", "Product_name") -> "name"
        normalize_key("Product", "product name") -> "name"
        normalize_key("Product", "price") -> "price"

    Args:
        label: The label context for normalization.
        key: The property key to normalize.

    Returns:
        Normalized key string.
    """
    lowercase_key = key.lower().strip()
    unprefixed_key = re.sub(f"^{label.lower()}[_ ]*", "", lowercase_key)
    normalized_key = re.sub(" ", "_", unprefixed_key)
    return normalized_key


def correlate_entity_and_domain_keys(
    label: str,
    entity_keys: list[str],
    domain_keys: list[str],
    similarity: float = 0.9,
) -> list[tuple[str, str, float]]:
    """Fuzzy match entity keys to domain keys using rapidfuzz.

    For each pair of (entity_key, domain_key), normalizes both keys
    and computes fuzzy similarity. Returns pairs above the threshold,
    sorted by similarity (highest first).

    Args:
        label: Label context for key normalization.
        entity_keys: Property keys from subject graph entities.
        domain_keys: Property keys from domain graph nodes.
        similarity: Minimum similarity threshold (0.0 to 1.0).

    Returns:
        List of (entity_key, domain_key, score) tuples sorted by score desc.
    """
    correlated_keys = []
    for entity_key in entity_keys:
        for domain_key in domain_keys:
            normalized_entity = normalize_key(label, entity_key)
            normalized_domain = normalize_key(label, domain_key)
            # rapidfuzz returns 0.0 -> 100.0, normalize to 0.0 -> 1.0
            fuzzy_score = fuzz.ratio(normalized_entity, normalized_domain) / 100
            if fuzzy_score > similarity:
                correlated_keys.append((entity_key, domain_key, fuzzy_score))
    correlated_keys.sort(key=lambda x: x[2], reverse=True)
    return correlated_keys


def correlate_subject_and_domain_nodes(
    driver: Driver,
    label: str,
    entity_key: str,
    domain_key: str,
    similarity: float = 0.9,
) -> dict:
    """Create CORRESPONDS_TO relationships using Jaro-Winkler distance.

    Uses MERGE for idempotent relationship creation. Requires APOC plugin
    for apoc.text.jaroWinklerDistance.

    Args:
        driver: Neo4j driver instance.
        label: Shared label between entity and domain nodes.
        entity_key: Property key on entity nodes.
        domain_key: Property key on domain nodes.
        similarity: Similarity threshold (0.0 to 1.0). Jaro-Winkler distance
                     must be below (1.0 - similarity).

    Returns:
        Dict with label and relationships_created count.
    """
    distance_threshold = 1.0 - similarity

    with driver.session() as session:
        result = session.run(
            f"""
            MATCH (entity:{label}:`__Entity__`), (domain:{label})
            WHERE NOT domain:`__Entity__`
              AND apoc.text.jaroWinklerDistance(entity[$entityKey], domain[$domainKey]) < $distance
            MERGE (entity)-[r:CORRESPONDS_TO]->(domain)
            ON CREATE SET r.created_at = datetime()
            ON MATCH SET r.updated_at = datetime()
            RETURN count(r) as relationshipCount
            """,
            {
                "entityKey": entity_key,
                "domainKey": domain_key,
                "distance": distance_threshold,
            },
        )
        record = result.single()
        count = record["relationshipCount"] if record else 0

    return {
        "label": label,
        "relationships_created": count,
    }


@traceable(name="pipeline.resolve_entities")
def resolve_entities(state: dict, driver: Driver) -> dict:
    """Full entity resolution pipeline.

    For each entity label found in the subject graph:
    1. Check if the same label exists in the domain graph
    2. If so, correlate property keys using fuzzy matching
    3. Use the best key pair to create CORRESPONDS_TO relationships

    Args:
        state: Pipeline state (used for progress tracking).
        driver: Neo4j driver instance.

    Returns:
        Dict with labels_checked, labels_resolved, per_label_results,
        and total_correspondences.
    """
    results = {
        "labels_checked": [],
        "labels_resolved": [],
        "per_label_results": [],
        "total_correspondences": 0,
    }

    print("\n[Entity Resolution] Finding entity labels in subject graph...")
    entity_labels = find_unique_entity_labels(driver)

    if not entity_labels:
        print("  No entity labels found. Has the text graph been built?")
        return results

    print(f"  Found entity labels: {entity_labels}")

    for label in entity_labels:
        print(f"\n  Checking label: {label}")
        results["labels_checked"].append(label)

        # Check if this label also exists in the domain graph
        domain_keys = find_unique_domain_keys(driver, label)
        if not domain_keys:
            print(f"    No domain nodes with label '{label}' found. Skipping.")
            results["per_label_results"].append(
                {
                    "label": label,
                    "status": "no_domain_match",
                    "message": f"No domain nodes with label '{label}'",
                }
            )
            continue

        entity_keys = find_unique_entity_keys(driver, label)
        if not entity_keys:
            print(f"    No entity keys found for '{label}'. Skipping.")
            results["per_label_results"].append(
                {
                    "label": label,
                    "status": "no_entity_keys",
                    "message": f"No entity property keys for '{label}'",
                }
            )
            continue

        # Correlate keys
        correlated = correlate_entity_and_domain_keys(
            label, entity_keys, domain_keys, similarity=0.5
        )

        if not correlated:
            print(f"    No correlating keys found for '{label}'. Skipping.")
            results["per_label_results"].append(
                {
                    "label": label,
                    "status": "no_key_correlation",
                    "entity_keys": entity_keys,
                    "domain_keys": domain_keys,
                    "message": "No property keys correlate above threshold",
                }
            )
            continue

        # Use the best key pair
        best_entity_key, best_domain_key, best_score = correlated[0]
        print(
            f"    Best key pair: {best_entity_key} <-> {best_domain_key} "
            f"(score: {best_score:.2f})"
        )

        # Create CORRESPONDS_TO relationships
        try:
            resolution = correlate_subject_and_domain_nodes(
                driver, label, best_entity_key, best_domain_key
            )
            count = resolution["relationships_created"]
            print(f"    Created {count} CORRESPONDS_TO relationships")

            results["labels_resolved"].append(label)
            results["total_correspondences"] += count
            results["per_label_results"].append(
                {
                    "label": label,
                    "status": "resolved",
                    "entity_key": best_entity_key,
                    "domain_key": best_domain_key,
                    "key_similarity": best_score,
                    "relationships_created": count,
                }
            )
        except Exception as exc:
            error_msg = str(exc)
            print(f"    [FAIL] {error_msg}")
            if "apoc" in error_msg.lower() or "unknown function" in error_msg.lower():
                print(
                    "    HINT: APOC plugin may not be installed. "
                    "Entity resolution requires apoc.text.jaroWinklerDistance."
                )
            results["per_label_results"].append(
                {
                    "label": label,
                    "status": "error",
                    "error": error_msg,
                }
            )

    # Update progress in state
    if "text_graph_progress" not in state:
        state["text_graph_progress"] = {}

    state["text_graph_progress"]["entity_resolution"] = {
        "status": "completed",
        "labels_resolved": results["labels_resolved"],
        "total_correspondences": results["total_correspondences"],
    }

    return results
