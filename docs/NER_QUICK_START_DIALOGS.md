# NER Agent - Quick Start Dialogs

Real conversation snippets showing how to use the NER Extraction agent. Copy these patterns for your own projects.

---

## Dialog 1: First Time User

**Scenario**: User has completed stages 1-3 and wants to start NER extraction

```
👤 User:
Start NER extraction

🤖 NER Agent:
I've analyzed 2 approved markdown files (247 lines total):
- product_reviews.md: 5 sections (complaints, defects, assembly issues)
- warranty_claims.md: 3 sections (claim details, resolutions)

Well-known types from your schema: Product, Supplier, Assembly

Found in text:
• Product - heavily mentioned (KALLAX, BILLY, MALM throughout)
• Assembly - mentioned in context of missing parts
• Supplier - NOT in markdown (only in CSVs, skip for NER)

Discovered types:
• Issue - product problems (broken legs, scratches, 14 mentions)
• Customer - people filing claims (names like Sarah, Mike)

Excluded:
• Rating (quantity, not entity)
• Delivery (only 2 mentions, not a pattern)

Proposing 4 types: Product, Assembly, Issue, Customer. Changes needed?

👤 User:
Looks good, approve

🤖 NER Agent:
✓ Approved! 4 entity types finalized.
Ready for Stage 5 (Fact Extraction).
```

---

## Dialog 2: Checking Before Proposing

**Scenario**: User wants to verify a concept exists before including it

```
👤 User:
Does "warranty" appear in the files?

🤖 NER Agent:
Searching for 'warranty'...

Found 12 matches in 2 files:

warranty_claims.md (10 matches):
> 23: warranty period expired after 2 years
> 45: warranty coverage unclear for Assembly defects
> 67: extended warranty purchased by 3 customers
[7 more matches...]

product_reviews.md (2 matches):
> 103: warranty terms were confusing
> 156: called warranty hotline, no response

Yes, warranty is a recurring theme. Should I add it as a discovered type?

👤 User:
Yes

🤖 NER Agent:
Added 'Warranty' (discovered). Now proposing 5 types. Want to see the full list?

👤 User:
approve

🤖 NER Agent:
✓ Approved! 5 entity types finalized.
```

---

## Dialog 3: Reading a Section

**Scenario**: User wants to inspect a specific section before deciding

```
👤 User:
Read lines 80-100 of product_reviews.md

🤖 NER Agent:
=== product_reviews.md, lines 80-100 ===

## Customer Service Interactions

Sarah Johnson contacted support about a broken shelf. The representative
offered a replacement but shipping took 3 weeks. Mike Chen had a similar
experience with a scratched table surface.

The support team response time averaged 48 hours. Some customers praised
the service quality, while others complained about long wait times.
Representatives were knowledgeable but overwhelmed during peak season.

===

I see mentions of:
- Customer names (Sarah Johnson, Mike Chen) → supports Customer type
- Support/representative → could be ServiceAgent type
- Response times, wait times → quantities, not entities

Should I add 'ServiceAgent' as a discovered type?

👤 User:
No, keep it simple. Just use Customer for now.

🤖 NER Agent:
Understood. Proposing Customer only (no ServiceAgent).
```

---

## Dialog 4: Removing a Type

**Scenario**: User realizes a proposed type isn't needed

```
👤 User:
Start NER extraction

🤖 NER Agent:
[Reviews files]

Proposing 6 types:
- Product (well_known)
- Assembly (well_known)
- Issue (discovered)
- Customer (discovered)
- Location (discovered) - warehouses, cities
- Material (discovered) - wood, metal, plastic

Ready to approve?

👤 User:
Remove Location and Material - too peripheral

🤖 NER Agent:
Removed Location and Material. Now proposing 4 types:
- Product (well_known)
- Assembly (well_known)
- Issue (discovered)
- Customer (discovered)

Better?

👤 User:
Perfect, approve

🤖 NER Agent:
✓ Approved! 4 entity types finalized.
```

---

## Dialog 5: Using the Critic

**Scenario**: User wants validation before approving

```
👤 User:
Propose entity types

🤖 NER Agent:
Proposing 5 types:
- Product (well_known)
- Issue (discovered)
- Customer (discovered)
- Rating (discovered)
- Age (discovered)

👤 User:
Run the critic first

[User calls kg_critic(scope="unstructured")]

🤖 Critic Agent:
VERDICT: retry

PROBLEMS:
1. 'Rating' is a quantity (property, not entity)
2. 'Age' is a quantity (property on Customer, not standalone entity)
3. 'Age' has no grounding evidence - ungrounded

👤 User:
Remove Rating and Age

🤖 NER Agent:
Removed Rating and Age. Now proposing 3 types:
- Product (well_known)
- Issue (discovered)
- Customer (discovered)

All problems fixed.

👤 User:
approve

🤖 NER Agent:
✓ Approved! 3 entity types finalized.
```

---

## Dialog 6: Search in Specific File

**Scenario**: User wants to check a specific file only

```
👤 User:
Search for "defect" in product_reviews.md only

🤖 NER Agent:
Searching 'defect' in product_reviews.md...

Found 8 matches:

> 34: The defect was obvious upon opening the box
  35: I immediately contacted customer service

> 67: Manufacturing defect caused the leg to crack
  68: This defect should have been caught in QC

> 89: Multiple defects in a single order (scratches, dents)
  90: Asked for full refund due to defects

[5 more matches...]

'Defect' is well-grounded in reviews. Should I include it as discovered type?

👤 User:
Yes, add Defect

🤖 NER Agent:
Added 'Defect' (discovered). Currently proposing 4 types.
```

---

## Dialog 7: Disambiguation

**Scenario**: A word has multiple meanings

```
👤 User:
Propose entity types

🤖 NER Agent:
I see 'Assembly' used two different ways:

1. Assembly (component) - physical parts like shelf legs, panels
   "The Assembly arrived damaged" (from your schema)

2. Assembly (process) - the act of putting furniture together
   "Assembly took 3 hours and was frustrating"

These are different concepts. Should I:
a) Only include Assembly (well_known) for components
b) Also add AssemblyProcess (discovered) for the activity
c) Something else

👤 User:
Option A - just the component

🤖 NER Agent:
Using Assembly (well_known) for components only. The process is just
an activity, not an entity we'll extract.

Proposing 3 types total. Approve?

👤 User:
yes

🤖 NER Agent:
✓ Approved!
```

---

## Dialog 8: Well-Known Coverage

**Scenario**: User wants to ensure schema types are included

```
👤 User:
What well-known types exist in the schema?

🤖 NER Agent:
From your construction plan:
- Product
- Supplier
- Assembly
- Component
- Warehouse

Checking which appear in markdown files...

Text grounding:
✓ Product - 47 mentions across both files
✓ Assembly - 12 mentions in reviews
✓ Component - 8 mentions in warranty claims
✗ Supplier - 0 mentions (only in CSVs, not markdown)
✗ Warehouse - 0 mentions (only in CSVs, not markdown)

Recommend including Product, Assembly, Component from schema.

👤 User:
Agreed. What discovered types should we add?

🤖 NER Agent:
Based on text patterns:
• Issue - product problems (18 mentions)
• Customer - people submitting reviews/claims (6 names found)

Proposing 5 types: Product, Assembly, Component, Issue, Customer.

👤 User:
approve

🤖 NER Agent:
✓ Approved!
```

---

## Dialog 9: Adding Multiple Types

**Scenario**: User wants to add several types iteratively

```
👤 User:
Start with just well-known types

🤖 NER Agent:
From schema + grounded in text:
- Product (well_known) - 47 mentions
- Assembly (well_known) - 12 mentions

Proposing these 2. Add discovered types?

👤 User:
Add Issue

🤖 NER Agent:
Added Issue (discovered) - product problems like defects, damages.
Now 3 types.

👤 User:
Add Customer and Warranty

🤖 NER Agent:
Added:
- Customer (discovered) - people in reviews/claims
- Warranty (discovered) - warranty coverage, claims

Now 5 types: Product, Assembly, Issue, Customer, Warranty.

👤 User:
approve

🤖 NER Agent:
✓ Approved! 5 entity types finalized.
```

---

## Dialog 10: Avoiding Quantities

**Scenario**: Agent catches quantities being proposed

```
👤 User:
What about Rating, Price, and Count?

🤖 NER Agent:
Those are quantities (properties), not entities:

❌ Rating → property on Product or Review (rating: 4.5)
❌ Price → property on Product (price: 129.99)
❌ Count → property (count: 3)

Entity types should be categories of things (Product, Issue), not
measurements describing those things.

Entity example: Product "KALLAX shelf"
Property example: product.rating = 4.5

I won't include these as entity types. They'll be properties during
graph construction instead.

👤 User:
Thanks for catching that. Proceed without them.

🤖 NER Agent:
Proposing 4 types (no quantities):
- Product (well_known)
- Issue (discovered)
- Customer (discovered)
- Warranty (discovered)
```

---

## Dialog 11: Quick Approve

**Scenario**: User trusts the agent's analysis

```
👤 User:
Analyze files and propose entity types for root cause analysis

🤖 NER Agent:
Analyzed 2 markdown files focused on product issues.

For root cause analysis goal, proposing:
- Product (well_known) - what failed
- Assembly (well_known) - which component
- Issue (discovered) - problem categories
- Defect (discovered) - specific defects

Excluded Customer (not relevant to root cause).

4 types focused on your goal. Approve?

👤 User:
approve

🤖 NER Agent:
✓ Approved! 4 entity types finalized.
```

---

## Dialog 12: Reconsidering After Critic

**Scenario**: Critic finds problems, user refines

```
👤 User:
Propose entity types

🤖 NER Agent:
Proposing 6 types including Issue, Problem, Defect...

👤 User:
Run critic

[kg_critic called]

🤖 Critic:
PROBLEMS:
1. 'Issue', 'Problem', 'Defect' overlap - consolidate to one type
2. 'Manager' has no grounding evidence - ungrounded

👤 User:
Keep only Defect, remove Issue and Problem. Remove Manager.

🤖 NER Agent:
Updated:
- Removed Issue, Problem (consolidated into Defect)
- Removed Manager (ungrounded)

Now proposing 4 types:
- Product (well_known)
- Assembly (well_known)
- Defect (discovered)
- Customer (discovered)

No overlaps. All grounded.

👤 User:
approve

🤖 NER Agent:
✓ Approved! 4 entity types finalized.
```

---

## Quick Command Reference

### Starting
- `"Start NER extraction"`
- `"Analyze files and propose entity types"`
- `"Begin stage 4"`

### Searching
- `"Search for 'X' in all files"`
- `"Does 'X' appear in the text?"`
- `"Search for 'X' in file.md only"`

### Reading Sections
- `"Read lines 50-80 of file.md"`
- `"Show me the 'Issues' section"`
- `"Read the beginning of reviews.md"`

### Modifying Proposals
- `"Add X as discovered type"`
- `"Remove Y"`
- `"Change X to Y"`
- `"Show current proposal"`

### Validation
- `"Run the critic"` (then call kg_critic)
- `"What well-known types exist?"`
- `"Which types are grounded?"`

### Approving
- `"approve"`
- `"looks good"`
- `"finalize these types"`

---

## Tips from Real Usage

1. **Start simple**: Let agent propose, then refine
2. **Use search**: Verify before adding new types
3. **Run critic**: Catch problems before approving
4. **3-6 types**: Quality over quantity
5. **No quantities**: Age, Rating, Price are properties
6. **Check overlap**: Issue vs Problem vs Defect - pick one
7. **Goal-focused**: Only include types that support your goal

---

## What Happens Next

After entity types are approved:
1. Move to Stage 5: Fact Extraction (relationships between entity types)
2. Or run `kg_critic(scope="unstructured")` for final validation
3. Entity types become the vocabulary for fact extraction
