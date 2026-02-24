"""KG-Factory pipelines for multi-agent workflows."""

from .domain_builder import (
    build_domain_graph,
    validate_csv_uniqueness,
    create_unique_constraint,
    import_nodes,
    import_relationships,
    verify_import,
)
from .entity_resolution import (
    resolve_entities,
    find_candidate_matches,
    create_correspondences_for_candidates,
)
from .text_builder import (
    build_entity_schema,
    build_text_graph,
    detect_splitting_strategy,
    MarkdownSectionSplitter,
    ParagraphSplitter,
    RegexTextSplitter,
)

__all__ = [
    "build_domain_graph",
    "validate_csv_uniqueness",
    "create_unique_constraint",
    "import_nodes",
    "import_relationships",
    "verify_import",
    "build_text_graph",
    "build_entity_schema",
    "detect_splitting_strategy",
    "MarkdownSectionSplitter",
    "ParagraphSplitter",
    "RegexTextSplitter",
    "resolve_entities",
    "find_candidate_matches",
    "create_correspondences_for_candidates",
]
