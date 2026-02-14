# US010: Adaptive Markdown Splitting

## User Story

**As a** KG-Factory User
**I want** the text graph builder to automatically detect the best chunking strategy for different markdown file structures
**So that** entity extraction works accurately regardless of whether my markdown files are reviews, documentation, articles, or unstructured prose

## Story Points: 3

## Status: Not Started

## Acceptance Criteria

- [ ] Text builder detects document structure before chunking (horizontal rules, section headers, paragraphs)
- [ ] Auto-detection chooses appropriate splitter based on structural markers:
  - Files with `---` horizontal rules (≥3 occurrences) → RegexTextSplitter("---")
  - Files with markdown headings (≥3 occurrences) → MarkdownSectionSplitter
  - Files with neither → ParagraphSplitter (double newline boundaries)
- [ ] User can override auto-detection via `state["text_splitting"]` configuration
- [ ] User can specify custom regex pattern for delimiter-based splitting
- [ ] Each file in a batch can use a different splitting strategy (per-file detection)
- [ ] Split strategy used is logged in `text_graph_progress` per file
- [ ] Unit tests verify auto-detection logic for different markdown formats
- [ ] Integration test processes multiple file types with different structures
- [ ] Documentation explains when each strategy is used and how to override

## Definition of Done

- [ ] Code implemented and working
- [ ] Unit tests for detection logic and all splitter types passing
- [ ] Integration test with mixed markdown formats (reviews + docs + articles)
- [ ] `text_builder.py` modified to support adaptive splitting
- [ ] State schema supports optional `text_splitting` configuration
- [ ] User can process diverse markdown files without manual configuration
- [ ] Code reviewed

## Technical Notes

### Architecture

The adaptive splitting feature extends `make_kg_pipeline()` in `text_builder.py` to detect document structure before creating the pipeline.

```
make_kg_pipeline(state, driver, file_path)
    |
    +-> Check for text_splitting config in state
    |     |
    |     +-> If configured: use specified strategy
    |     +-> If not: auto-detect from file structure
    |
    +-> detect_splitting_strategy(file_path)
    |     |
    |     +-> Read file content
    |     +-> Count structural markers:
    |           +-> horizontal_rules = count("^---$")
    |           +-> headings = count("^#{1,6}\s+")
    |     +-> Decision logic:
    |           +-> If horizontal_rules >= 3 → RegexTextSplitter("---")
    |           +-> Elif headings >= 3 → MarkdownSectionSplitter
    |           +-> Else → ParagraphSplitter
    |
    +-> Create SimpleKGPipeline with detected/configured splitter
```

### Four Splitter Implementations

**1. RegexTextSplitter** (existing)
- Splits on regex pattern (e.g., `"---"`, `"==="`, `r"\*\*\*"`)
- Use case: Structured content with explicit delimiters
- Example: Product reviews, FAQ entries, changelog entries

**2. MarkdownSectionSplitter** (new)
- Splits on markdown headings (`#`, `##`, `###`, etc.)
- Pattern: `r'^#{1,6}\s+'` with MULTILINE flag
- Use case: Documentation, wikis, technical articles
- Example:
  ```markdown
  # Introduction
  [content]

  ## Installation
  [content]

  ## Usage
  [content]
  ```

**3. ParagraphSplitter** (new)
- Splits on double newlines (`\n\n`)
- Use case: Essays, blog posts, narrative text
- Example: Prose without section markers

**4. FixedSizeSplitter** (future, optional)
- Splits into fixed token windows with overlap
- Use case: Fallback for completely unstructured text
- Uses neo4j-graphrag's built-in `FixedSizeSplitter(chunk_size=250, chunk_overlap=50)`

### Files to Create/Update

```
pipelines/
  text_builder.py              # UPDATE: Add adaptive splitting logic
                               #   - Add MarkdownSectionSplitter class
                               #   - Add ParagraphSplitter class
                               #   - Add detect_splitting_strategy()
                               #   - Update make_kg_pipeline()

tests/unit/
  test_text_builder.py         # UPDATE: Add splitter detection tests
                               #   - test_detect_horizontal_rule_format()
                               #   - test_detect_section_format()
                               #   - test_detect_paragraph_format()
                               #   - test_section_splitter_on_headings()
                               #   - test_paragraph_splitter_on_newlines()

tests/
  test_07_text_builder.py      # UPDATE: Add multi-format test scenario

docs/
  implementation/
    US010_adaptive_splitting.md # NEW: Implementation guide
```

### New Splitter Classes

**MarkdownSectionSplitter**
```python
class MarkdownSectionSplitter(TextSplitter):
    """Split markdown on section headers."""

    async def run(self, text: str) -> TextChunks:
        # Split on headings (any level: #, ##, ###, etc.)
        pattern = r'^(#{1,6}\s+.+)$'
        parts = re.split(pattern, text, flags=re.MULTILINE)

        # Reconstruct sections (heading + content)
        sections = []
        for i in range(1, len(parts), 2):
            if i+1 < len(parts):
                section = parts[i] + "\n" + parts[i+1]
                sections.append(section.strip())

        chunks = [
            TextChunk(text=str(s), index=i)
            for i, s in enumerate(sections)
            if s
        ]
        return TextChunks(chunks=chunks)
```

**ParagraphSplitter**
```python
class ParagraphSplitter(TextSplitter):
    """Split markdown on paragraph boundaries."""

    async def run(self, text: str) -> TextChunks:
        # Split on double newlines
        paragraphs = re.split(r'\n\s*\n', text)

        chunks = [
            TextChunk(text=str(p.strip()), index=i)
            for i, p in enumerate(paragraphs)
            if p.strip()
        ]
        return TextChunks(chunks=chunks)
```

### Detection Logic

```python
def detect_splitting_strategy(file_path: str) -> TextSplitter:
    """Auto-detect best splitting strategy for a markdown file.

    Args:
        file_path: Absolute path to markdown file.

    Returns:
        Configured TextSplitter instance.
    """
    with open(file_path, 'r', encoding='utf-8') as f:
        content = f.read()

    # Count structural markers
    hr_count = len(re.findall(r'^---$', content, re.MULTILINE))
    heading_count = len(re.findall(r'^#{1,6}\s+', content, re.MULTILINE))

    # Decision thresholds
    if hr_count >= 3:
        return RegexTextSplitter("---")
    elif heading_count >= 3:
        return MarkdownSectionSplitter()
    else:
        return ParagraphSplitter()
```

### State Configuration (Optional Override)

Users can configure splitting strategy in state:

```python
# Default: auto-detect (no config needed)
# state["text_splitting"] not set

# Override: use specific strategy
state["text_splitting"] = {
    "strategy": "delimiter",     # "delimiter", "sections", "paragraphs"
    "pattern": "---"              # only for delimiter strategy
}

# Example configurations:
state["text_splitting"] = {"strategy": "sections"}
state["text_splitting"] = {"strategy": "paragraphs"}
state["text_splitting"] = {"strategy": "delimiter", "pattern": r"\*\*\*"}
```

### Updated make_kg_pipeline() Logic

```python
def make_kg_pipeline(state, neo4j_driver, file_path):
    llm = OpenAILLM(model_name="gpt-4o", model_params={"temperature": 0})
    embedder = OpenAIEmbeddings(model="text-embedding-3-large")
    schema = build_entity_schema(state)
    prompt = build_extraction_prompt(file_path)

    # Determine splitting strategy
    if "text_splitting" in state:
        # User override
        config = state["text_splitting"]
        strategy = config.get("strategy", "delimiter")

        if strategy == "delimiter":
            pattern = config.get("pattern", "---")
            splitter = RegexTextSplitter(pattern)
        elif strategy == "sections":
            splitter = MarkdownSectionSplitter()
        elif strategy == "paragraphs":
            splitter = ParagraphSplitter()
        else:
            # Fallback to auto-detect
            splitter = detect_splitting_strategy(file_path)
    else:
        # Auto-detect (default)
        splitter = detect_splitting_strategy(file_path)

    return SimpleKGPipeline(
        llm=llm,
        driver=neo4j_driver,
        embedder=embedder,
        from_pdf=True,
        pdf_loader=MarkdownDataLoader(),
        text_splitter=splitter,
        schema=schema,
        prompt_template=prompt,
    )
```

### Progress Tracking Enhancement

Add split strategy info to `text_graph_progress`:

```python
state["text_graph_progress"]["processed_files"].append({
    "file": "reviews/stockholm_chair_reviews.md",
    "timestamp": "2026-02-14T10:30:00",
    "split_strategy": "delimiter",        # NEW
    "split_pattern": "---",               # NEW
    "chunks_created": 12
})
```

### Example Scenarios

**Scenario 1: Reviews with horizontal rules**
```markdown
# Product Reviews
## Rating: 5/5
Great product!
---
## Rating: 4/5
Good but pricey.
---
```
→ **Auto-detected**: RegexTextSplitter("---")
→ **Chunks**: 2 (one per review)

**Scenario 2: Documentation with sections**
```markdown
# User Guide
## Installation
Follow these steps...
## Configuration
Edit the config file...
## Usage
Run the command...
```
→ **Auto-detected**: MarkdownSectionSplitter
→ **Chunks**: 3 (Introduction, Installation, Configuration, Usage)

**Scenario 3: Article with paragraphs**
```markdown
# My Thoughts

This is the introduction paragraph.

This is the second paragraph with more details.

This is the conclusion.
```
→ **Auto-detected**: ParagraphSplitter
→ **Chunks**: 3 (one per paragraph)

**Scenario 4: User override**
```python
# User wants all files split by sections, regardless of structure
state["text_splitting"] = {"strategy": "sections"}
```
→ **Forced**: MarkdownSectionSplitter for all files

## Dependencies

- US009 (Text Graph Builder) must be complete
- Existing `RegexTextSplitter` class in `text_builder.py`
- Existing `TextSplitter` base class from `neo4j_graphrag`

## Out of Scope

- HTML chunking (only markdown)
- PDF chunking (separate feature)
- Semantic chunking based on content meaning (requires embeddings)
- Custom chunking logic beyond the four strategies
- GUI for configuring splitting strategy

## Validation Scenarios

### Scenario 1: Auto-detect across mixed file types

1. Create three markdown files:
   - `reviews.md` with `---` delimiters
   - `docs.md` with `##` section headers
   - `article.md` with plain paragraphs
2. Run `kg_build_graph(scope="unstructured", message="all")`
3. Verify in `text_graph_progress`:
   - `reviews.md` → strategy="delimiter"
   - `docs.md` → strategy="sections"
   - `article.md` → strategy="paragraphs"
4. Check Neo4j: each file has appropriate chunk boundaries

### Scenario 2: User override for consistent chunking

1. Set `state["text_splitting"] = {"strategy": "sections"}`
2. Process multiple files with different structures
3. Verify all files use MarkdownSectionSplitter
4. Verify chunks align with section headers regardless of file format

### Scenario 3: Custom delimiter pattern

1. Create file with `***` as delimiter instead of `---`
2. Set `state["text_splitting"] = {"strategy": "delimiter", "pattern": r"\*\*\*"}`
3. Process file
4. Verify chunks split on `***` boundaries

## Benefits

1. **Works out-of-the-box** for diverse markdown formats (no configuration needed)
2. **Semantic chunks** that match document structure (better entity extraction)
3. **User control** when needed (override via state configuration)
4. **Per-file adaptation** in mixed datasets (reviews + docs in same project)
5. **Transparent** (split strategy logged in progress tracking)

## Migration Path

Existing implementations using hardcoded `RegexTextSplitter("---")` continue to work:
- Auto-detection defaults to `"---"` for files with horizontal rules
- No breaking changes to API or state schema
- Optional enhancement via `text_splitting` state configuration
