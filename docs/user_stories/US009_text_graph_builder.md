# US009: Text Graph Builder (Subject + Lexical + Entity Resolution)

## User Story

**As a** KG-Factory User
**I want** a text graph builder that processes markdown files into subject and lexical graphs, and links them to the domain graph via entity resolution
**So that** my knowledge graph integrates both structured (CSV) and unstructured (markdown) data into a single queryable graph

## Story Points: 8

## Status: Not Started

## Acceptance Criteria

### Scope Control (UX)

- [ ] `kg_build_graph` supports a `scope` parameter: `"structured"`, `"unstructured"`, `"resolve"`, `"all"`
- [ ] `scope="structured"` builds the domain graph from CSVs only (existing US008 behavior)
- [ ] `scope="unstructured"` builds the subject + lexical graphs from markdown files
- [ ] `scope="resolve"` runs entity resolution to link subject graph to domain graph
- [ ] `scope="all"` runs all three in sequence (structured -> unstructured -> resolve)
- [ ] Default scope remains `"structured"` for backward compatibility

### File-Level Control (UX)

- [ ] For `scope="unstructured"`, the `message` parameter controls which files to process
- [ ] User can process all files: "Process all markdown files"
- [ ] User can process a specific file: "Process gothenburg_table_reviews.md"
- [ ] User can process the next unprocessed file: "Process the next file"
- [ ] Progress is tracked in state: `_text_graph_progress` with processed/pending file lists
- [ ] Each file processing result is reported individually (chunks created, entities extracted, relationships created)

### Lexical Graph (per file)

- [ ] Custom `MarkdownDataLoader` reads markdown files and extracts document title from first H1
- [ ] Custom `RegexTextSplitter` chunks markdown on `---` delimiters (review boundaries)
- [ ] `(__Document__)` nodes created with metadata (title, path)
- [ ] `(__Chunk__)` nodes created with text content and embedding vectors
- [ ] `HAS_CHUNK` relationships link Document to Chunks
- [ ] `NEXT` relationships link sequential Chunks
- [ ] Embeddings generated via OpenAI `text-embedding-3-large`

### Subject Graph (per file)

- [ ] Entity schema built from `approved_entity_types` and `approved_fact_types`
- [ ] `additional_node_types` set to `False` (strict extraction)
- [ ] Per-file contextualized extraction prompt (first 5 lines as context)
- [ ] `(Label:__Entity__)` nodes created for extracted entities (e.g., `Product:__Entity__`)
- [ ] Fact relationships created between entities (e.g., `HAS_ISSUE`, `INCLUDES_FEATURE`)
- [ ] `MENTIONED_IN` relationships link entities to chunks where they appear
- [ ] Uses `SimpleKGPipeline` from `neo4j-graphrag` (following Neo4j best practices)

### Entity Resolution

- [ ] Finds unique entity labels in subject graph (excluding `__` prefixed internal labels)
- [ ] Finds matching labels in domain graph (non-`__Entity__` nodes)
- [ ] Correlates property keys between entity and domain nodes using fuzzy matching (`rapidfuzz`)
- [ ] Creates `CORRESPONDS_TO` relationships using `apoc.text.jaroWinklerDistance` in Neo4j
- [ ] Uses `MERGE` for idempotent resolution (safe to re-run)
- [ ] Reports correlation results per label (entity count, matches found, threshold used)

### Pipeline Integration

- [ ] `SimpleKGPipeline` handles chunking, embedding, extraction, and writing in one pass per file
- [ ] LLM for entity extraction uses OpenAI GPT-4o (via `neo4j-graphrag` `OpenAILLM`)
- [ ] Embeddings use OpenAI `text-embedding-3-large` (via `neo4j-graphrag` `OpenAIEmbeddings`)
- [ ] Neo4j driver reused from `utils/neo4j_utils.py`
- [ ] All operations are idempotent (MERGE-based, safe to re-run)

### Error Handling

- [ ] Missing `OPENAI_API_KEY` gives clear error message
- [ ] Missing APOC plugin gives clear error during entity resolution
- [ ] Individual file failures don't stop the batch (reported and skipped)
- [ ] Connection failures handled gracefully with actionable messages

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests for text builder utilities (schema builder, key normalization, progress tracking)
- [ ] Interactive test script works end-to-end (`test_07_text_builder.py`)
- [ ] Can complete full flow: build structured -> build unstructured (file by file or all) -> resolve entities
- [ ] Progress tracking works (processed files persist across calls)
- [ ] MCP tool `kg_build_graph` works with all scopes from Claude Code
- [ ] Code reviewed

## Technical Notes

### Architecture

The text graph builder extends the existing `kg_build_graph` MCP tool with a `scope` parameter (same pattern as `kg_critic`). It wraps Neo4j's `SimpleKGPipeline` with custom components.

```
kg_build_graph(message, scope)
  |
  +-> scope="structured"   --> build_domain_graph(state, driver)     [existing US008]
  |
  +-> scope="unstructured" --> build_text_graph(state, driver, ...)  [NEW]
  |     |
  |     +-> For each selected markdown file:
  |           +-> MarkdownDataLoader         (reads file, extracts title)
  |           +-> RegexTextSplitter          (chunks on "---")
  |           +-> OpenAIEmbeddings           (embeds chunks)
  |           +-> OpenAILLM + entity_schema  (extracts entities + relationships)
  |           +-> SimpleKGPipeline.run_async (writes everything to Neo4j)
  |           +-> Update _text_graph_progress
  |
  +-> scope="resolve"     --> resolve_entities(state, driver)        [NEW]
  |     |
  |     +-> find_unique_entity_labels()
  |     +-> For each label found in both subject and domain graphs:
  |           +-> correlate_entity_and_domain_keys()  (rapidfuzz)
  |           +-> correlate_subject_and_domain_nodes() (Jaro-Winkler in Cypher)
  |
  +-> scope="all"         --> structured + unstructured + resolve     [NEW]
```

### Files to Create

```
pipelines/
  text_builder.py                  # NEW: Markdown -> Neo4j (SimpleKGPipeline wrapper)
  entity_resolution.py             # NEW: Subject <-> Domain linking

tests/
  test_07_text_builder.py          # NEW: Interactive integration test
  unit/
    test_text_builder.py           # NEW: Unit tests for utilities
```

### Files to Update

```
pipelines/__init__.py              # UPDATE: Add text builder + entity resolution exports
mcp_server/server.py              # UPDATE: Add scope parameter to kg_build_graph
requirements.txt                  # UPDATE: Uncomment neo4j-graphrag, rapidfuzz, add openai
```

### Component Specifications

#### 1. MarkdownDataLoader (in `pipelines/text_builder.py`)

Extends `neo4j_graphrag.experimental.components.pdf_loader.DataLoader`.

```python
class MarkdownDataLoader(DataLoader):
    """Custom loader that reads markdown files for SimpleKGPipeline."""

    def extract_title(self, markdown_text: str) -> str:
        """Extract title from first H1 header, or 'Untitled'."""

    async def run(self, filepath: Path, metadata={}) -> PdfDocument:
        """Read markdown file, return as PdfDocument with title metadata."""
```

#### 2. RegexTextSplitter (in `pipelines/text_builder.py`)

Extends `neo4j_graphrag.experimental.components.text_splitters.base.TextSplitter`.

```python
class RegexTextSplitter(TextSplitter):
    """Split text using regex delimiters (e.g., '---' for review boundaries)."""

    def __init__(self, pattern: str):
        self.re = pattern

    async def run(self, text: str) -> TextChunks:
        """Split text on regex pattern, return indexed chunks."""
```

#### 3. Entity Schema Builder (in `pipelines/text_builder.py`)

Builds the schema dict from approved state artifacts.

```python
def build_entity_schema(state: dict) -> dict:
    """Build entity extraction schema from approved_entity_types and approved_fact_types.

    Returns:
        {
            "node_types": ["Product", "Issue", "Feature"],
            "relationship_types": ["HAS_ISSUE", "INCLUDES_FEATURE"],
            "patterns": [["Product", "HAS_ISSUE", "Issue"], ...],
            "additional_node_types": False
        }
    """
```

#### 4. Contextualized Extraction Prompt (in `pipelines/text_builder.py`)

Per-file prompt template that provides document context for entity extraction.

```python
def build_extraction_prompt(file_path: str, num_context_lines: int = 5) -> str:
    """Build contextualized entity extraction prompt with file header as context.

    Includes:
    - General extraction instructions (JSON output format)
    - Schema placeholder {schema}
    - File context (first N lines)
    - Input text placeholder {text}
    """
```

#### 5. build_text_graph (in `pipelines/text_builder.py`)

Main entry point for text processing.

```python
async def build_text_graph(
    state: dict,
    neo4j_driver,
    files_to_process: list[str] | None = None
) -> dict:
    """Process markdown files into subject + lexical graphs.

    Args:
        state: Pipeline state with approved_entity_types, approved_fact_types, approved_files
        neo4j_driver: Neo4j driver instance
        files_to_process: Specific files to process, or None for all pending

    Returns:
        {
            "files_processed": ["file1.md", "file2.md"],
            "total_chunks": 82,
            "total_entities": 47,
            "per_file_results": [{...}, ...],
            "errors": []
        }
    """
```

#### 6. Entity Resolution Functions (in `pipelines/entity_resolution.py`)

Following the Neo4j course patterns exactly:

```python
def find_unique_entity_labels(driver) -> list[str]:
    """Find all entity labels in subject graph (excluding __ prefixed)."""

def find_unique_entity_keys(driver, label: str) -> list[str]:
    """Find property keys for entities of a given label."""

def find_unique_domain_keys(driver, label: str) -> list[str]:
    """Find property keys for domain nodes of a given label."""

def normalize_key(label: str, key: str) -> str:
    """Normalize property key: lowercase, strip label prefix, replace spaces."""

def correlate_entity_and_domain_keys(
    label: str, entity_keys: list[str], domain_keys: list[str],
    similarity: float = 0.9
) -> list[tuple[str, str, float]]:
    """Fuzzy match entity keys to domain keys using rapidfuzz."""

def correlate_subject_and_domain_nodes(
    driver, label: str, entity_key: str, domain_key: str,
    similarity: float = 0.9
) -> dict:
    """Create CORRESPONDS_TO relationships using Jaro-Winkler distance."""

def resolve_entities(state: dict, driver) -> dict:
    """Full entity resolution pipeline.

    Returns:
        {
            "labels_checked": ["Product", "Issue", "Feature"],
            "labels_resolved": ["Product"],
            "relationships_created": 10,
            "per_label_results": [{...}, ...]
        }
    """
```

#### 7. Progress Tracking (in state)

```python
state["_text_graph_progress"] = {
    "processed_files": [
        {
            "file": "product_reviews/gothenburg_table_reviews.md",
            "chunks_created": 12,
            "entities_extracted": 8,
            "relationships_created": 5,
            "timestamp": "2026-02-12T10:30:00"
        }
    ],
    "pending_files": [
        "product_reviews/malmo_desk_reviews.md",
        "product_reviews/uppsala_sofa_reviews.md"
    ],
    "entity_resolution": {
        "status": "not_started",  # or "completed"
        "labels_resolved": [],
        "total_correspondences": 0
    }
}
```

### MCP Integration

**Updated kg_build_graph signature:**

```python
@mcp.tool
def kg_build_graph(message: str = "build", scope: str = "structured") -> dict:
    """Build the knowledge graph in Neo4j from approved artifacts.

    Args:
        message: Instructions for the build (e.g., file selection for unstructured scope).
        scope: What to build.
            - "structured": Domain graph from CSVs (default, existing behavior)
            - "unstructured": Subject + Lexical graphs from markdown files
            - "resolve": Entity resolution (link Subject <-> Domain)
            - "all": Everything in sequence

    Returns:
        dict with agent_response (summary) and status (details)
    """
```

**File selection logic for `scope="unstructured"`:**

The `message` parameter is parsed to determine which files to process:
- Contains a specific filename -> process that file only
- Contains "next" -> process next unprocessed file
- Contains "all" or "remaining" -> process all pending files
- Default (empty/generic) -> process all pending files

### Key Design Decisions

**SimpleKGPipeline (not custom)**: Following Neo4j's own best practices from the course.
The pipeline handles chunking, embedding, entity extraction, and graph writing in a single
pass. This is less code, more maintainable, and aligned with the Neo4j ecosystem.

**OpenAI for LLM + Embeddings**: The `neo4j-graphrag` library has native support for
`OpenAILLM` and `OpenAIEmbeddings`. Using Claude for extraction would require a custom
adapter. OpenAI GPT-4o is the proven path from the course. Embeddings require OpenAI
regardless (Anthropic doesn't offer embeddings).

**Scope parameter (not separate tools)**: Matches the existing `kg_critic(scope)` pattern.
Keeps the MCP tool count at 9 (not 11). User gets full control via scope + message.

**Progress tracking in state**: Allows file-by-file processing across multiple MCP calls.
The `_text_graph_progress` key uses the `_` prefix convention for ephemeral state, but
is persisted via `_should_persist()` for cross-call tracking.

**Entity resolution as separate scope**: Lets the user inspect the subject graph in
Neo4j Browser before connecting it to the domain graph. Also allows re-running
resolution with different parameters.

**RegexTextSplitter on "---"**: Markdown horizontal rules are natural review boundaries
in the furniture supply chain dataset. This produces semantically meaningful chunks
rather than arbitrary token windows.

**Contextualized extraction prompt**: The first 5 lines of each file provide document
context (title, product name) to the LLM when extracting entities from individual chunks.
This improves extraction accuracy, especially for chunks that don't repeat the product name.

### Example Conversation Flow

```
User: "Build the domain graph from CSVs"
Claude Code: kg_build_graph(message="build", scope="structured")
-> [1/5] Validate... [2/5] Constraints... [3/5] Nodes... [4/5] Rels... [5/5] Verify
-> "Domain graph built: 75 nodes, 111 relationships"

User: "Now process just the first markdown file"
Claude Code: kg_build_graph(message="process gothenburg_table_reviews.md", scope="unstructured")
-> Processing gothenburg_table_reviews.md...
-> "Processed 1/10 files: 12 chunks, 8 entities, 5 relationships. 9 files pending."

User: "Looks good in Neo4j Browser. Process the rest."
Claude Code: kg_build_graph(message="process remaining files", scope="unstructured")
-> Processing helsingborg_dresser_reviews.md... [OK]
-> Processing jonkoping_coffee_table_reviews.md... [OK]
-> ... (8 more)
-> "Processed 9/9 remaining files: 98 chunks, 67 entities, 42 relationships total."

User: "Connect the subject graph to the domain graph"
Claude Code: kg_build_graph(message="resolve", scope="resolve")
-> Checking entity labels: Product, Issue, Feature, Location
-> Product: correlated name <-> product_name (similarity 0.95)
->   Created 10 CORRESPONDS_TO relationships
-> Issue, Feature, Location: no matching domain labels
-> "Entity resolution complete: 10 correspondences for Product"

User: "Build everything from scratch"
Claude Code: kg_build_graph(message="build all", scope="all")
-> [Phase 1/3] Building domain graph... 75 nodes, 111 relationships
-> [Phase 2/3] Processing 10 markdown files... 110 chunks, 75 entities
-> [Phase 3/3] Resolving entities... 10 correspondences
-> "Complete knowledge graph built!"
```

### Environment Variables

**Existing (no change):**
- `NEO4J_URI` - Neo4j connection URI
- `NEO4J_USER` - Neo4j username
- `NEO4J_PASSWORD` - Neo4j password
- `NEO4J_IMPORT_DIR` - Path to data files

**New:**
- `OPENAI_API_KEY` - Required for entity extraction (GPT-4o) and embeddings (text-embedding-3-large)

### Graph Model After Build

```
DOMAIN GRAPH (from CSVs)
  (Product)--[Contains]--(Assembly)--[Is_Part_Of]--(Part)
      |                                              |
      |                                        [Supplied_By]
      |                                              |
      |                                         (Supplier)
      |
  [CORRESPONDS_TO]
      |
      v
SUBJECT GRAPH (from markdown, entities extracted by LLM)
  (Product:__Entity__)--[HAS_ISSUE]--(Issue:__Entity__)
      |
  [INCLUDES_FEATURE]
      |
  (Feature:__Entity__)
      |
  [MENTIONED_IN]
      |
      v
LEXICAL GRAPH (from markdown, chunks with embeddings)
  (__Document__)--[HAS_CHUNK]--(__Chunk__)--[NEXT]--(__Chunk__)
                                   |
                              [embedding]  (vector for similarity search)
```

## Dependencies

- US001 (Core Agent Framework) must be complete
- US008 (Domain Graph Builder) must be complete - provides `build_domain_graph` and `utils/neo4j_utils.py`
- US006 (NER Extraction Agent) must be complete - provides `approved_entity_types`
- US007 (Fact Extraction Agent) must be complete - provides `approved_fact_types`
- `approved_user_goal` must exist in state
- `approved_files` must exist in state (with both structured and unstructured files)
- `approved_construction_plan` must exist in state
- `approved_entity_types` must exist in state
- `approved_fact_types` must exist in state
- Neo4j instance with APOC plugin installed (for entity resolution)
- OpenAI API key (for LLM extraction and embeddings)

### Python Dependencies (new)

```
neo4j-graphrag>=1.0.0        # SimpleKGPipeline, OpenAILLM, OpenAIEmbeddings
rapidfuzz>=3.0.0             # Fuzzy string matching for entity resolution
openai>=1.0.0                # Required by neo4j-graphrag for LLM + embeddings
```

## Out of Scope

- Custom LLM adapter for Anthropic (using OpenAI via neo4j-graphrag)
- Vector similarity search indexes (can be added later for RAG queries)
- Composite chunking strategies (fixed token + semantic)
- Multi-language entity extraction
- Relationship property extraction (only type + direction)
- Custom embedding models (using OpenAI text-embedding-3-large)

## Validation Scenarios

### Scenario 1: Single file processing via MCP

1. Load state with all approved artifacts from Stages 1-5
2. Domain graph already built (scope="structured" completed)
3. User: "Process just the gothenburg table reviews"
4. `kg_build_graph(message="gothenburg_table_reviews.md", scope="unstructured")`
5. Pipeline processes the file: chunks on "---", embeds, extracts entities
6. Returns: chunks created, entities extracted, relationships created
7. User inspects graph in Neo4j Browser
8. `_text_graph_progress` shows 1 processed, 9 pending

### Scenario 2: Full pipeline via scope="all"

1. Load state with all approved artifacts from Stages 1-5
2. User: "Build the complete knowledge graph"
3. `kg_build_graph(message="build everything", scope="all")`
4. Phase 1: Domain graph from CSVs (75 nodes, 111 relationships)
5. Phase 2: Text graph from all markdown files (110 chunks, 75 entities)
6. Phase 3: Entity resolution (10 CORRESPONDS_TO for Product)
7. Returns comprehensive summary of all three phases

### Scenario 3: Entity resolution after inspection

1. Text graph already built
2. User inspects entity nodes in Neo4j Browser
3. User: "Connect the extracted entities to the domain graph"
4. `kg_build_graph(message="resolve", scope="resolve")`
5. Finds Product entities match domain Product nodes via name/product_name
6. Creates CORRESPONDS_TO relationships with Jaro-Winkler similarity
7. Reports per-label results and total correspondences
