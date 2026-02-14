"""Text Graph Builder - Markdown -> Neo4j (Subject + Lexical graphs).

Wraps Neo4j's SimpleKGPipeline with custom components for:
- MarkdownDataLoader: reads markdown files, extracts title from H1
- RegexTextSplitter: chunks text on regex delimiters (e.g., "---")
- Contextualized extraction prompts per file
- Entity schema from approved_entity_types + approved_fact_types

Based on patterns from the Neo4j GraphRAG course (Lesson 8).
"""

import os
import re
from datetime import datetime, timezone
from pathlib import Path

from core.tracing import traceable

from neo4j import Driver
from neo4j_graphrag.embeddings import OpenAIEmbeddings
from neo4j_graphrag.experimental.components.pdf_loader import DataLoader
from neo4j_graphrag.experimental.components.text_splitters.base import TextSplitter
from neo4j_graphrag.experimental.components.types import (
    DocumentInfo,
    PdfDocument,
    TextChunk,
    TextChunks,
)
from neo4j_graphrag.experimental.pipeline.kg_builder import SimpleKGPipeline
from neo4j_graphrag.llm import OpenAILLM

from tools.file_tools import _get_data_dir


class MarkdownDataLoader(DataLoader):
    """Custom loader that reads markdown files for SimpleKGPipeline."""

    def extract_title(self, markdown_text: str) -> str:
        """Extract title from first H1 header, or 'Untitled'."""
        pattern = r"^# (.+)$"
        match = re.search(pattern, markdown_text, re.MULTILINE)
        return match.group(1) if match else "Untitled"

    async def run(self, filepath: Path, metadata=None) -> PdfDocument:
        """Read markdown file, return as PdfDocument with title metadata."""
        if metadata is None:
            metadata = {}
        with open(filepath, "r", encoding="utf-8") as f:
            markdown_text = f.read()
        doc_headline = self.extract_title(markdown_text)
        markdown_info = DocumentInfo(
            path=str(filepath),
            metadata={"title": doc_headline},
        )
        return PdfDocument(text=markdown_text, document_info=markdown_info)


class RegexTextSplitter(TextSplitter):
    """Split text using regex matched delimiters."""

    def __init__(self, pattern: str):
        self.re = pattern

    async def run(self, text: str) -> TextChunks:
        """Split text on regex pattern, return indexed chunks."""
        texts = re.split(self.re, text)
        chunks = [TextChunk(text=str(t), index=i) for i, t in enumerate(texts)]
        return TextChunks(chunks=chunks)


class MarkdownSectionSplitter(TextSplitter):
    """Split markdown on section headers (any heading level).

    Each chunk contains the heading line followed by its content,
    up to the next heading of equal or higher level.
    """

    async def run(self, text: str) -> TextChunks:
        """Split text on markdown headings, return indexed chunks."""
        # Split keeping heading lines as separate elements
        parts = re.split(r"(^#{1,6}\s+.+)$", text, flags=re.MULTILINE)

        # parts alternates: [pre-heading text, heading, content, heading, content, ...]
        sections = []

        # Anything before the first heading is a preamble
        preamble = parts[0].strip()
        if preamble:
            sections.append(preamble)

        # Reconstruct sections: heading + content
        for i in range(1, len(parts), 2):
            heading = parts[i]
            content = parts[i + 1] if i + 1 < len(parts) else ""
            section = (heading + "\n" + content).strip()
            if section:
                sections.append(section)

        chunks = [
            TextChunk(text=str(s), index=i) for i, s in enumerate(sections)
        ]
        return TextChunks(chunks=chunks)


class ParagraphSplitter(TextSplitter):
    """Split text on paragraph boundaries (double newlines)."""

    async def run(self, text: str) -> TextChunks:
        """Split text on double newlines, return indexed chunks."""
        paragraphs = re.split(r"\n\s*\n", text)
        chunks = [
            TextChunk(text=str(p.strip()), index=i)
            for i, p in enumerate(paragraphs)
            if p.strip()
        ]
        return TextChunks(chunks=chunks)


def detect_splitting_strategy(file_path: str) -> TextSplitter:
    """Auto-detect best splitting strategy for a markdown file.

    Inspects the file for structural markers and returns the appropriate
    splitter:
    - >=3 horizontal rules (``---``) -> RegexTextSplitter
    - >=3 markdown headings (``#``) -> MarkdownSectionSplitter
    - Otherwise -> ParagraphSplitter

    Args:
        file_path: Absolute path to markdown file.

    Returns:
        Configured TextSplitter instance.
    """
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            content = f.read()
    except OSError:
        # If we can't read the file, fall back to paragraph splitting
        return ParagraphSplitter()

    hr_count = len(re.findall(r"^---+\s*$", content, re.MULTILINE))
    heading_count = len(re.findall(r"^#{1,6}\s+", content, re.MULTILINE))

    if hr_count >= 3:
        return RegexTextSplitter("---")
    elif heading_count >= 3:
        return MarkdownSectionSplitter()
    else:
        return ParagraphSplitter()


def _create_splitter_from_config(config: dict) -> TextSplitter:
    """Create a TextSplitter from a state configuration dict.

    Args:
        config: Dict with ``strategy`` key (``"delimiter"``, ``"sections"``,
                ``"paragraphs"``) and optional ``pattern`` for delimiter strategy.

    Returns:
        Configured TextSplitter instance.
    """
    strategy = config.get("strategy", "delimiter")

    if strategy == "delimiter":
        pattern = config.get("pattern", "---")
        return RegexTextSplitter(pattern)
    elif strategy == "sections":
        return MarkdownSectionSplitter()
    elif strategy == "paragraphs":
        return ParagraphSplitter()
    else:
        # Unknown strategy, fall back to paragraph
        return ParagraphSplitter()


def build_entity_schema(state: dict) -> dict:
    """Build entity extraction schema from approved_entity_types and approved_fact_types.

    Args:
        state: Pipeline state with approved_entity_types and approved_fact_types.

    Returns:
        Schema dict with node_types, relationship_types, patterns,
        and additional_node_types=False.
    """
    entity_types = state.get("approved_entity_types", {})
    fact_types = state.get("approved_fact_types", {})

    node_types = sorted(entity_types.keys())
    relationship_types = [key.upper() for key in fact_types.keys()]
    patterns = [
        [fact["subject_label"], fact["predicate_label"].upper(), fact["object_label"]]
        for fact in fact_types.values()
    ]

    return {
        "node_types": node_types,
        "relationship_types": relationship_types,
        "patterns": patterns,
        "additional_node_types": False,
    }


def build_extraction_prompt(file_path: str, num_context_lines: int = 5) -> str:
    """Build contextualized entity extraction prompt with file header as context.

    Reads the first N lines of the file for document context, then returns
    a prompt template with {schema} and {text} placeholders.

    Args:
        file_path: Absolute path to the markdown file.
        num_context_lines: Number of lines to read for context.

    Returns:
        Prompt template string with {schema} and {text} placeholders.
    """
    # Read first N lines for context
    context_lines = []
    try:
        with open(file_path, "r", encoding="utf-8") as f:
            for _ in range(num_context_lines):
                line = f.readline()
                if not line:
                    break
                context_lines.append(line)
    except OSError:
        context_lines = ["(file context unavailable)"]

    context = "\n".join(context_lines)

    general_instructions = """
    You are a top-tier algorithm designed for extracting
    information in structured formats to build a knowledge graph.

    Extract the entities (nodes) and specify their type from the following text.
    Also extract the relationships between these nodes.

    Return result as JSON using the following format:
    {{"nodes": [ {{"id": "0", "label": "Person", "properties": {{"name": "John"}} }}],
    "relationships": [{{"type": "KNOWS", "start_node_id": "0", "end_node_id": "1", "properties": {{"since": "2024-08-01"}} }}] }}

    Use only the following node and relationship types (if provided):
    {schema}

    Assign a unique ID (string) to each node, and reuse it to define relationships.
    Do respect the source and target node types for relationship and
    the relationship direction.

    Make sure you adhere to the following rules to produce valid JSON objects:
    - Do not return any additional information other than the JSON in it.
    - Omit any backticks around the JSON - simply output the JSON on its own.
    - The JSON object must not wrapped into a list - it is its own JSON object.
    - Property names must be enclosed in double quotes
    """

    context_section = f"""
    Consider the following context to help identify entities and relationships:
    <context>
    {context}
    </context>"""

    input_section = """
    Input text:

    {text}
    """

    return general_instructions + "\n" + context_section + "\n" + input_section


def make_kg_pipeline(
    state: dict,
    neo4j_driver: Driver,
    file_path: str,
) -> tuple[SimpleKGPipeline, str]:
    """Build a SimpleKGPipeline configured for a specific file.

    Creates the pipeline with:
    - OpenAI GPT-4o for entity extraction
    - OpenAI text-embedding-3-large for chunk embeddings
    - Custom MarkdownDataLoader + adaptive TextSplitter
    - Entity schema from approved state artifacts
    - Contextualized extraction prompt from file header

    Splitting strategy is determined by:
    1. ``state["text_splitting"]`` override (if present)
    2. Auto-detection from file structure (default)

    Args:
        state: Pipeline state with approved_entity_types and approved_fact_types.
        neo4j_driver: Neo4j driver instance.
        file_path: Absolute path to the markdown file.

    Returns:
        Tuple of (configured SimpleKGPipeline, strategy name string).
    """
    llm = OpenAILLM(model_name="gpt-4o", model_params={"temperature": 0})
    embedder = OpenAIEmbeddings(model="text-embedding-3-large")
    schema = build_entity_schema(state)
    prompt = build_extraction_prompt(file_path)

    # Determine splitting strategy
    if "text_splitting" in state:
        splitter = _create_splitter_from_config(state["text_splitting"])
        strategy_name = state["text_splitting"].get("strategy", "delimiter")
    else:
        splitter = detect_splitting_strategy(file_path)
        # Derive strategy name from splitter type
        if isinstance(splitter, RegexTextSplitter):
            strategy_name = "delimiter"
        elif isinstance(splitter, MarkdownSectionSplitter):
            strategy_name = "sections"
        else:
            strategy_name = "paragraphs"

    pipeline = SimpleKGPipeline(
        llm=llm,
        driver=neo4j_driver,
        embedder=embedder,
        from_pdf=True,
        pdf_loader=MarkdownDataLoader(),
        text_splitter=splitter,
        schema=schema,
        prompt_template=prompt,
        perform_entity_resolution=True,
    )
    return pipeline, strategy_name


def _resolve_files_to_process(state: dict, message: str) -> list[str]:
    """Determine which markdown files to process based on message and progress.

    Logic:
    - If message contains a specific .md filename -> return just that file
    - If message contains "next" -> return next unprocessed file
    - Otherwise (empty, "all", "remaining") -> return all pending files

    Args:
        state: Pipeline state with approved_files and text_graph_progress.
        message: User message describing which files to process.

    Returns:
        List of relative file paths to process.
    """
    unstructured = state.get("approved_files", {}).get("unstructured", [])
    all_files = [f["path"] for f in unstructured]

    if not all_files:
        return []

    # Get already-processed files
    progress = state.get("text_graph_progress", {})
    processed = {entry["file"] for entry in progress.get("processed_files", [])}
    pending = [f for f in all_files if f not in processed]

    if not pending:
        return []

    msg_lower = message.lower().strip()

    # Check for specific filename
    for file_path in all_files:
        filename = os.path.basename(file_path).lower()
        # Match on basename without extension, or full basename
        name_no_ext = os.path.splitext(filename)[0]
        if filename in msg_lower or name_no_ext in msg_lower:
            if file_path in processed:
                return []  # Already done
            return [file_path]

    # Check for "next"
    if "next" in msg_lower:
        return [pending[0]]

    # Default: all pending
    return pending


def _count_neo4j_nodes(driver: Driver) -> dict:
    """Quick Neo4j node/relationship count for diagnostics."""
    try:
        records, _, _ = driver.execute_query(
            "MATCH (n) RETURN labels(n) AS labels, count(*) AS cnt"
        )
        counts = {str(r["labels"]): r["cnt"] for r in records}
        total = sum(counts.values())
        return {"total": total, "by_label": counts}
    except Exception as exc:
        return {"total": -1, "error": str(exc)}


async def _process_single_file(
    neo4j_driver: Driver,
    state: dict,
    file_path: str,
    data_dir: str,
) -> dict:
    """Process a single markdown file through the KG pipeline.

    Args:
        neo4j_driver: Neo4j driver instance.
        state: Pipeline state.
        file_path: Relative path to the markdown file.
        data_dir: Base data directory.

    Returns:
        Per-file result dict with file, status, result, error, and diagnostics fields.
    """
    full_path = os.path.join(data_dir, file_path)

    if not os.path.isfile(full_path):
        return {
            "file": file_path,
            "status": "error",
            "result": None,
            "error": f"File not found: {full_path}",
        }

    # Diagnostic: count nodes before processing
    before_counts = _count_neo4j_nodes(neo4j_driver)

    try:
        pipeline, strategy_name = make_kg_pipeline(state, neo4j_driver, full_path)
        result = await pipeline.run_async(file_path=str(full_path))

        # Diagnostic: count nodes after processing
        after_counts = _count_neo4j_nodes(neo4j_driver)
        nodes_added = after_counts["total"] - before_counts["total"]

        # Capture full result details for diagnostics
        result_repr = repr(result.result) if result else "None"

        # Check the writer result for silent failures.
        # Neo4jWriter catches ClientError and returns FAILURE status
        # without raising, so we must inspect the result explicitly.
        writer_error = None
        if result and result.result:
            r = result.result
            if hasattr(r, "status") and r.status == "FAILURE":
                writer_error = getattr(r, "metadata", {}).get("error", "unknown")
            elif isinstance(r, dict) and r.get("status") == "FAILURE":
                writer_error = r.get("metadata", {}).get("error", "unknown")

        if writer_error:
            return {
                "file": file_path,
                "status": "error",
                "result": result_repr,
                "error": f"Neo4j writer failed: {writer_error}",
                "split_strategy": strategy_name,
                "diagnostics": {
                    "nodes_before": before_counts["total"],
                    "nodes_after": after_counts["total"],
                    "nodes_added": nodes_added,
                },
            }

        return {
            "file": file_path,
            "status": "ok",
            "result": result_repr,
            "error": None,
            "split_strategy": strategy_name,
            "diagnostics": {
                "nodes_before": before_counts["total"],
                "nodes_after": after_counts["total"],
                "nodes_added": nodes_added,
            },
        }
    except Exception as exc:
        return {
            "file": file_path,
            "status": "error",
            "result": None,
            "error": str(exc),
        }


@traceable(name="pipeline.build_text_graph")
async def build_text_graph(state: dict, driver: Driver, message: str = "all") -> dict:
    """Build Subject + Lexical graphs from markdown files.

    Main entry point (async). Processes markdown files through
    SimpleKGPipeline for chunking, embedding, and entity extraction.

    Args:
        state: Pipeline state with approved_entity_types, approved_fact_types,
               and approved_files (with unstructured entries).
        driver: Neo4j driver instance.
        message: Controls which files to process ("all", "next", or filename).

    Returns:
        Dict with files_processed, files_skipped, errors, per_file_results,
        and progress info.

    Raises:
        ValueError: If prerequisites are missing.
    """
    # Validate prerequisites
    if "approved_entity_types" not in state:
        raise ValueError(
            "No approved_entity_types in state. "
            "Stage 4 (NER Extraction) must be completed first."
        )
    if "approved_fact_types" not in state:
        raise ValueError(
            "No approved_fact_types in state. "
            "Stage 5 (Fact Extraction) must be completed first."
        )

    unstructured = state.get("approved_files", {}).get("unstructured", [])
    if not unstructured:
        raise ValueError(
            "No unstructured files in approved_files. "
            "Stage 2 (File Suggestion) must include markdown files."
        )

    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError(
            "OPENAI_API_KEY environment variable is not set. "
            "Required for entity extraction (GPT-4o) and embeddings."
        )

    data_dir = _get_data_dir()

    # Resolve which files to process
    files_to_process = _resolve_files_to_process(state, message)

    if not files_to_process:
        progress = state.get("text_graph_progress", {})
        processed = progress.get("processed_files", [])
        return {
            "files_processed": [],
            "files_skipped": [],
            "errors": [],
            "per_file_results": [],
            "progress": {
                "total_processed": len(processed),
                "total_pending": 0,
                "message": "All files have already been processed.",
            },
        }

    # Initialize progress tracking
    if "text_graph_progress" not in state:
        all_files = [f["path"] for f in unstructured]
        state["text_graph_progress"] = {
            "processed_files": [],
            "pending_files": all_files,
        }

    results = {
        "files_processed": [],
        "files_skipped": [],
        "errors": [],
        "per_file_results": [],
    }

    print(f"\nData directory: {data_dir}")
    print(f"Files to process: {len(files_to_process)}")

    # Process each file sequentially (avoid Neo4j contention)
    for i, file_path in enumerate(files_to_process, 1):
        print(f"\n[{i}/{len(files_to_process)}] Processing {file_path}...", end=" ")

        file_result = await _process_single_file(driver, state, file_path, data_dir)
        results["per_file_results"].append(file_result)

        if file_result["status"] == "ok":
            print("[OK]")
            results["files_processed"].append(file_path)

            # Update progress
            state["text_graph_progress"]["processed_files"].append(
                {
                    "file": file_path,
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "split_strategy": file_result.get("split_strategy", "unknown"),
                }
            )
            if file_path in state["text_graph_progress"]["pending_files"]:
                state["text_graph_progress"]["pending_files"].remove(file_path)
        else:
            print(f"[FAIL] {file_result['error']}")
            results["errors"].append(f"{file_path}: {file_result['error']}")

    # Build progress summary
    progress = state["text_graph_progress"]
    results["progress"] = {
        "total_processed": len(progress["processed_files"]),
        "total_pending": len(progress["pending_files"]),
        "processed_files": [e["file"] for e in progress["processed_files"]],
        "pending_files": progress["pending_files"],
    }

    return results
