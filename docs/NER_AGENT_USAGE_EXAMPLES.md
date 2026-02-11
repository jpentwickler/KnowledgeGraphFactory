# NER Extraction Agent - End User Examples

This guide shows how to use the NER Extraction Agent directly from Claude Code chat to analyze markdown files and identify entity types.

## Prerequisites

Before using the NER agent, you must complete stages 1-3:

1. **User Intent** (Stage 1) - Define your graph goal
2. **File Suggestion** (Stage 2) - Identify relevant markdown files
3. **Schema Proposal** (Stage 3) - Create the construction plan for structured data

The NER agent uses these approved artifacts to understand context.

## Basic Workflow

The NER agent is conversational. You interact with it through natural language:

```
User: "Analyze the approved markdown files and propose entity types"

Agent: [Reviews files, identifies well-known types from schema, discovers new types]
        [Proposes entity types with descriptions]

User: "Add 'Warranty' as a discovered type"

Agent: [Updates proposal]

User: "approve"

Agent: [Finalizes entity types]
```

## Example 1: Basic Analysis

**Goal**: Furniture supply chain — identify product issues from customer reviews

### Conversation

```
User → Claude Code:
"Start NER extraction - analyze the reviews to find entity types"

Claude Code → MCP → NER Agent:
kg_ner_extraction("analyze the reviews to find entity types")

NER Agent Response:
"I've reviewed 2 markdown files with 8 sections total:
- customer_reviews.md: 4 sections about products, assembly, defects
- warranty_claims.md: 4 sections about claims, resolutions

Well-known types from the schema:
- Product, Supplier, Assembly

I found these types mentioned in the text:

PROPOSED ENTITY TYPES:

1. Product (well_known)
   - Source: Existing graph schema
   - Why: Products like KALLAX, BILLY are mentioned throughout reviews
   - Example: 'The KALLAX shelf arrived damaged'

2. Assembly (well_known)
   - Source: Existing graph schema
   - Why: Assembly subcomponents and processes are discussed
   - Example: 'Missing screws prevented assembly completion'

3. Issue (discovered)
   - Source: Text analysis
   - Why: Supports root cause analysis goal - categorizes problems
   - Example: 'Broken leg', 'scratched surface', 'missing parts'

4. Customer (discovered)
   - Source: Text analysis
   - Why: Customers submit reviews and claims
   - Example: 'Sarah Johnson from Chicago'

I excluded 'Rating' (a quantity, not entity) and 'Warehouse' (only 1 mention, not pattern).

Should I propose these 4 types, or would you like changes?"
```

### Follow-up Examples

**Add a type:**
```
User: "Also include Defect as a discovered type - it's more specific than Issue"

Agent: "Updated. Should I keep Issue or replace it with Defect?"

User: "Replace Issue with Defect"

Agent: [Updates proposal, shows new list with Defect instead of Issue]
```

**Remove a type:**
```
User: "Remove Customer - we don't need that"

Agent: [Removes Customer, shows updated list with 3 types]
```

**Approve:**
```
User: "approve"

Agent: "Entity types approved! 3 types finalized:
- Product (well_known)
- Assembly (well_known)
- Defect (discovered)

Ready for Stage 5: Fact Extraction"
```

## Example 2: Using Search to Verify Types

**Goal**: Check whether "Warranty" appears in the text before proposing it

### Conversation

```
User: "Does 'warranty' appear in any of the markdown files?"

Agent: [Uses search_files tool]
"Searching for 'warranty'...

Found 7 matches across 2 files:
- warranty_claims.md (5 matches): 'warranty period', 'warranty coverage', etc.
- customer_reviews.md (2 matches): 'warranty unclear', 'warranty expired'

Yes, warranty is mentioned frequently. Would you like me to include 'Warranty'
as a discovered entity type?"

User: "Yes, add it"

Agent: [Updates proposal to include Warranty]
```

**Search with specific file:**
```
User: "Search for 'defect' in customer_reviews.md only"

Agent: [Uses search_files with file_path parameter]
"Found 4 mentions of 'defect' in customer_reviews.md:
- Line 23: 'The defect was obvious'
- Line 45: 'Manufacturing defect'
- Line 67: 'Hidden defects emerged'
- Line 89: 'Reported the defect immediately'

This confirms 'Defect' is well-grounded in the reviews."
```

## Example 3: Using Sample File for Deep Inspection

**Goal**: Read a specific section to understand entity mentions better

### Conversation

```
User: "Read lines 45-60 of customer_reviews.md - I want to see the
       'Assembly Issues' section in detail"

Agent: [Uses sample_file tool]
"Reading lines 45-60 of customer_reviews.md:

## Assembly Issues

Several customers reported problems during assembly. The BILLY bookcase
had missing screws in 3 cases. The KALLAX shelf instructions were unclear
about leg attachment. One customer, Mike Chen, said the pre-drilled holes
didn't align properly.

Assembly time averaged 2.5 hours, which customers found frustrating. The
tools included were low quality according to 5 reviewers.

Based on this section, I see:
- 'Tool' might be worth including (mentioned by multiple reviewers)
- 'Customer' names appear (Mike Chen)
- Specific products (BILLY, KALLAX) confirm Product type

Should I add 'Tool' as a discovered type?"

User: "No, tools are too peripheral. Focus on issues and products."

Agent: "Understood. Keeping focus on Problem/Defect/Issue types and Products."
```

## Example 4: Iterative Refinement with Critic

**Goal**: Propose types, run validation, refine based on feedback

### Conversation

```
User: "Propose entity types"

Agent: [Reviews files, proposes 6 types including Product, Issue, Warranty,
        Customer, Location, Rating]

User: "Run the critic on these"

[You call kg_critic with scope="unstructured"]

Critic: "PROBLEMS FOUND:
1. 'Rating' is a quantity (property on Review/Product), not an entity type
2. 'Location' has no grounding evidence - may be ungrounded
3. 'Customer' overlaps with 'Person' from well-known types - consolidate"

User: "Remove Rating and Location, change Customer to Person"

Agent: [Updates proposal]
"Updated to 4 types:
- Product (well_known)
- Person (well_known)
- Issue (discovered)
- Warranty (discovered)

Much cleaner. Ready to approve?"

User: "approve"
```

## Example 5: Checking Well-Known Type Coverage

**Goal**: Ensure all relevant graph schema types are included

### Conversation

```
User: "What well-known types are in the schema?"

Agent: "From the approved construction plan, these node labels exist:
- Product
- Supplier
- Assembly
- Component

Checking the markdown files for mentions..."

[Agent searches files]

Agent: "Text grounding results:
- Product: Heavily mentioned (50+ occurrences) ✓
- Supplier: Not mentioned in markdown files ✗
- Assembly: Mentioned 8 times ✓
- Component: Mentioned 15 times ✓

I recommend including Product, Assembly, Component as well-known types.
Supplier is in the schema but doesn't appear in the unstructured text,
so I'll exclude it from NER proposals (it's already handled by CSV import)."

User: "That makes sense. Proceed with those 3 well-known types plus any
       discovered types"

Agent: [Proposes well-known types + discovered types like Issue, Warranty]
```

## Example 6: Disambiguation

**Goal**: Handle ambiguous terms that mean different things

### Conversation

```
User: "Propose entity types including Assembly"

Agent: "I see 'Assembly' used in two different contexts:

1. Assembly (construction plan) - A physical subassembly component (leg, panel)
2. Assembly (reviews) - The process of assembling furniture ('assembly took 2 hours')

These are different concepts. The well-known 'Assembly' type from the schema
refers to components. Should I:
a) Only include Assembly (well_known) for components
b) Create a separate 'AssemblyProcess' (discovered) for the process
c) Something else?"

User: "Option A - just use Assembly for the component. The process is
       just an activity, not an entity."

Agent: "Agreed. Including Assembly (well_known) for components only."
```

## Example 7: Quantity vs Entity Check

**Goal**: Avoid proposing measurements as entity types

### Conversation

```
User: "What about 'Age', 'Price', and 'Rating'?"

Agent: "Those are quantities (measurements/properties), not entities:

- Age: Property on Person (e.g., customer.age = 35)
- Price: Property on Product (e.g., product.price = 49.99)
- Rating: Property on Review or Product (e.g., review.rating = 4.5)

Entity types should be categories of things (Product, Person, Issue),
not numbers describing those things. I won't propose these as entity types.

If you want to capture ratings, they'll be properties during graph construction,
not separate nodes."

User: "Perfect, thanks for catching that"
```

## Tool Usage Summary

The NER agent has 5 tools:

### 1. `sample_file`
**When to use**: Read specific sections by line number
```
"Read lines 100-150 of reviews.md"
"Show me the 'Defects' section starting at line 67"
```

### 2. `search_files`
**When to use**: Check if a term/pattern appears in text
```
"Search for 'warranty' across all files"
"Does 'defect' appear in reviews.md?"
"Find all mentions of 'customer complaint'"
```

### 3. `set_proposed_entities`
**When to use**: Agent uses this to save proposals (you don't call directly)

### 4. `get_proposed_entities`
**When to use**: See current proposal
```
"Show me what you've proposed so far"
"What entity types are in the current proposal?"
```

### 5. `approve_proposed_entities`
**When to use**: Finalize the entity types
```
"approve"
"looks good, approve it"
"finalize these entity types"
```

## Tips for Effective NER Conversations

1. **Start broad**: "Analyze files and propose entity types"
2. **Verify with search**: "Does X appear in the text?"
3. **Inspect sections**: "Read lines N-M to see context"
4. **Iterate**: Add/remove types until satisfied
5. **Use the critic**: Run `kg_critic(scope="unstructured")` before approving
6. **Quality over quantity**: 3-6 meaningful types beat 12 vague ones
7. **Check disambiguation**: Ask about terms that might be ambiguous
8. **Avoid quantities**: Exclude measurements, ratings, ages, prices, counts

## Common Patterns

### Pattern: Exploratory Analysis
```
1. "What files are approved for NER?"
2. "Search for [concept] across all files"
3. "If found, read that section in detail"
4. "Propose types based on findings"
```

### Pattern: Validation-First
```
1. "Propose entity types"
2. "Run critic" (via kg_critic)
3. "Fix problems based on critic feedback"
4. "Approve"
```

### Pattern: Focused Addition
```
1. "Show current proposal"
2. "Search for [new_concept]"
3. "Add [new_concept] as discovered type"
4. "Approve"
```

### Pattern: Well-Known Coverage
```
1. "What well-known types exist in the schema?"
2. "Which ones appear in the markdown files?"
3. "Include only the grounded well-known types"
4. "Add discovered types for new concepts"
```

## Next Steps After NER

Once entity types are approved:
1. **Run critic** (optional): `kg_critic(scope="unstructured")` for final validation
2. **Fact Extraction** (Stage 5): Define relationships between entity types
3. **Graph Build** (Stage 6): Extract instances and construct the Neo4j graph

## Troubleshooting

**Agent says "No approved files"**
- Complete Stage 2 (File Suggestion) first
- Ensure markdown files are in the approved list

**Agent says "No construction plan"**
- Complete Stage 3 (Schema Proposal) first
- The NER agent needs well-known types from the schema

**Agent proposes too many types**
- Ask to focus on 3-6 most important
- Use "quality over quantity" guidance
- Check for quantities masquerading as entities

**Unclear if type is grounded**
- Use search_files: "Search for [type] in all files"
- Run evidence validation via critic
- Read sections with sample_file

**Types overlap**
- Ask agent: "Do X and Y overlap?"
- Request consolidation: "Combine X and Y into single type"
- Critic will flag overlaps if you run validation
