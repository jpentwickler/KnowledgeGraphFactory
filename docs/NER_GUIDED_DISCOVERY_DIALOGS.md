# NER Agent - Guided Discovery Dialogs

These dialogs show how users can **guide the agent** to explore specific parts of files or investigate concepts they've noticed. The user acts as a domain expert, directing the agent's attention to areas that might reveal important entity types.

---

## Dialog 1: User Spots a Pattern in Document

**Scenario**: User read a file and noticed a recurring concept the agent might miss

```
👤 User:
I read the customer_reviews.md file and noticed people keep mentioning
"delivery issues" - late deliveries, wrong addresses, damaged in transit.
Can you search for delivery-related mentions and see if this should be
an entity type?

🤖 NER Agent:
Searching for 'delivery'...

Found 14 matches across files:

product_reviews.md (12 matches):
> 45: delivery took 3 weeks instead of promised 5 days
> 67: delivery driver left package in rain
> 89: delivery address was wrong, had to reorder
> 103: delivery tracking number never worked
[8 more matches...]

warranty_claims.md (2 matches):
> 23: claimed delivery damage for broken shelf
> 56: delivery photo showed intact box

Pattern identified:
- Late delivery (4 mentions)
- Wrong delivery (3 mentions)
- Damaged during delivery (5 mentions)
- Delivery tracking issues (2 mentions)

This looks like a valid discovered type. Should I add 'DeliveryIssue'
as a distinct category from product defects?

👤 User:
Yes, add it. Delivery problems are different from product problems.

🤖 NER Agent:
Added 'DeliveryIssue' (discovered) - problems with shipping/logistics.
Now proposing 5 types including DeliveryIssue.
```

---

## Dialog 2: User Wants Specific Section Analyzed

**Scenario**: User knows a particular section contains important concepts

```
👤 User:
Look at the "Resolution Process" section in warranty_claims.md around
lines 120-160. I think there might be entity types related to how
claims are resolved.

🤖 NER Agent:
Reading lines 120-160 of warranty_claims.md...

## Resolution Process

Claims are handled by specialists who assess the damage. If approved,
customers receive either a replacement, refund, or repair kit. The
specialist assigns a resolution code (R-REPLACE, R-REFUND, R-REPAIR).

Some claims are escalated to senior specialists when the cost exceeds $200.
The escalation process involves manager approval and additional photo
documentation.

Resolution timeline:
- Standard claims: 3-5 business days
- Escalated claims: 7-10 business days
- Repair kit shipment: additional 5-7 days

===

I see several potential entity types:
1. Specialist - people who handle claims
2. ResolutionType - replacement, refund, repair (but these might be properties)
3. Escalation - special handling process (but this might be a status/property)

Question: Should 'Specialist' be a separate type from 'Customer',
or should we have a general 'Person' type with roles?

👤 User:
Add Specialist as separate from Customer. They're different actors
in the system. Skip ResolutionType and Escalation - those are statuses,
not entities.

🤖 NER Agent:
Added 'Specialist' (discovered) - people who process warranty claims.
Excluded ResolutionType and Escalation (statuses/properties).

Now proposing: Product, Customer, Specialist, Issue, Warranty.
```

---

## Dialog 3: User Directs Search for Domain Concept

**Scenario**: User has domain knowledge about a concept that should exist

```
👤 User:
In furniture quality control, there's usually a concept of "batch" or
"lot number" - products from the same manufacturing run. Search for
mentions of batch, lot, or manufacturing run to see if this appears
in the data.

🤖 NER Agent:
Searching for 'batch', 'lot', and 'manufacturing'...

'batch': 3 matches
> warranty_claims.md, line 78: entire batch from supplier S-1203 had defects
> warranty_claims.md, line 134: batch number B-2024-0315 recalled

'lot': 1 match
> product_reviews.md, line 201: lot code printed on bottom of shelf

'manufacturing': 7 matches
> product_reviews.md, line 45: manufacturing defect in leg assembly
> product_reviews.md, line 67: manufacturing date was 6 months ago
> warranty_claims.md, line 89: manufacturing facility in Poland
[4 more matches...]

Findings:
- Batch/lot numbers are mentioned (B-2024-0315)
- Associated with defects and recalls
- Links products to manufacturing runs

Should I add 'Batch' or 'ManufacturingLot' as a discovered entity type?

👤 User:
Yes, add Batch. This is important for tracking which products came from
the same production run when we find defects.

🤖 NER Agent:
Added 'Batch' (discovered) - manufacturing batch/lot for quality tracking.
This will help connect products to their production run.

Now proposing 6 types including Batch.
```

---

## Dialog 4: User Notices Missing Connection

**Scenario**: User realizes entity types need an intermediary concept

```
👤 User:
You proposed Product and Issue as entity types. But I'm looking at
the reviews and seeing that issues aren't directly on products - they're
on specific instances. Like "my KALLAX shelf had a broken leg" vs
"all KALLAX shelves have broken legs". Should we have something between
Product and Issue?

Can you look at how people describe problems in product_reviews.md?

🤖 NER Agent:
Reading product_reviews.md to analyze how issues are described...

Pattern analysis:
- "My KALLAX shelf arrived with..." (specific instance)
- "The product I received..." (specific instance)
- "Order #12345 had..." (specific instance)
- "This particular unit..." (specific instance)

vs rarely:
- "All KALLAX shelves..." (product type level)

You're right - issues are reported on specific product instances,
not the product type itself.

Should I add 'ProductInstance' or 'Order' as an entity type to capture
the specific item the customer received?

👤 User:
Add ProductInstance. That's the actual physical item delivered to
the customer.

🤖 NER Agent:
Added 'ProductInstance' (discovered) - specific product unit received.

Now the model is clearer:
- Product (type: "KALLAX shelf")
- ProductInstance (specific unit: "my KALLAX shelf, order #12345")
- Issue (problem: "broken leg")

Proposing 7 types now.
```

---

## Dialog 5: User Wants Different Granularity

**Scenario**: User guides agent to split or merge types based on analysis needs

```
👤 User:
You proposed "Issue" as a single entity type. But I need to distinguish
between different kinds of problems for root cause analysis. Can you
read the issues section and break down what categories exist?

🤖 NER Agent:
Reading issue descriptions across files...

Issue categorization found:
1. Physical damage (broken, cracked, scratched) - 23 mentions
2. Missing parts (screws, instructions, components) - 18 mentions
3. Design flaws (holes don't align, unstable) - 7 mentions
4. Quality defects (rough edges, color mismatch) - 12 mentions

Should I split "Issue" into:
a) Keep single "Issue" type with a category property
b) Create 4 types: Damage, MissingPart, DesignFlaw, QualityDefect
c) Create 2 types: PhysicalIssue (damage/defects) and AssemblyIssue (missing/design)

👤 User:
Option B - create separate types. I need to analyze each category
differently for root cause.

🤖 NER Agent:
Split into 4 specific types:
- Damage (discovered) - physical damage like broken, cracked, scratched
- MissingPart (discovered) - missing screws, components, instructions
- DesignFlaw (discovered) - design problems causing issues
- QualityDefect (discovered) - manufacturing quality problems

Removed general "Issue" type.
Now proposing 8 types total.
```

---

## Dialog 6: User Points to Temporal Concepts

**Scenario**: User wants to track time-based entities

```
👤 User:
I noticed people mention seasons and time periods in the reviews - like
"during the holiday rush" or "summer sale items". Search for mentions
of time periods, seasons, or dates to see if temporal context matters
for quality issues.

🤖 NER Agent:
Searching for temporal references...

Found patterns:
- "holiday season" (4 mentions) - increased delivery delays
- "summer sale" (3 mentions) - quality issues with discounted items
- "Black Friday order" (2 mentions) - shipping problems
- "Christmas delivery" (5 mentions) - time pressure issues
- "Q4 2024" (1 mention)

Temporal context appears in:
- Delivery issues (tied to busy seasons)
- Quality problems (sale items vs regular stock)

Question: Should these be entity types like 'SaleEvent' or 'Season',
or are these just properties/context on existing entities?

👤 User:
Skip it. These are context, not entities we need to extract. The
delivery issues and quality problems are what matter, not the season.

🤖 NER Agent:
Understood. Temporal references are contextual, not core entities
for your analysis. Keeping focus on Product, Issue, Customer, etc.

Current proposal: 5 types (no temporal entities).
```

---

## Dialog 7: User Directs Investigation of Stakeholders

**Scenario**: User wants to map out all actors/roles in the domain

```
👤 User:
I want to understand all the people and roles involved in this process.
Search for different types of people mentioned - customers, workers,
support staff, anyone who appears in the text.

🤖 NER Agent:
Searching for people/role references...

Found these human actors:

Customers (35 mentions):
- "I ordered...", "customer Sarah Johnson", "buyers reported..."

Support Representatives (12 mentions):
- "representative helped", "support agent", "customer service rep"

Specialists (8 mentions):
- "warranty specialist", "claim specialist assessed"

Delivery Drivers (6 mentions):
- "driver left package", "delivery person"

Quality Inspectors (2 mentions):
- "inspector noted", "QC team"

Suppliers (mentioned but as companies, not people):
- "supplier XYZ", "vendor ABC"

Should I create separate entity types for each role, or consolidate?

👤 User:
Create three: Customer, SupportAgent, WarrantySpecialist. Skip
delivery drivers and inspectors - not enough mentions to matter.

🤖 NER Agent:
Added:
- Customer (discovered) - people who purchase and review products
- SupportAgent (discovered) - customer service representatives
- WarrantySpecialist (discovered) - people who process warranty claims

Skipped DeliveryDriver and QualityInspector (peripheral, low frequency).

Now proposing 7 types with clear actor roles.
```

---

## Dialog 8: User Guides Hierarchical Discovery

**Scenario**: User wants to explore part-whole relationships

```
👤 User:
Products have components - shelves have legs, panels, screws. Can you
look through the files and identify what components are mentioned?
I want to understand the product structure.

🤖 NER Agent:
Searching for component mentions in both files...

Product components found:

Structural components:
- Legs (15 mentions) - "broken leg", "leg attachment"
- Panels (12 mentions) - "side panel cracked", "back panel missing"
- Shelves (8 mentions) - "shelf surface scratched"

Hardware:
- Screws (18 mentions) - "missing screws", "wrong screw size"
- Brackets (7 mentions) - "bracket bent", "mounting bracket"
- Dowels (4 mentions) - "wooden dowels broke"

Other:
- Instructions (9 mentions) - often listed as "missing"

The well-known type 'Assembly' from your schema might cover these.
Should I:
a) Use Assembly (well_known) for all components
b) Create specific types: Leg, Panel, Hardware, etc.
c) Create Component (discovered) as parent, with types as properties

👤 User:
Use Assembly for the physical parts (legs, panels, brackets).
Add "Instructions" as a separate discovered type - it's referenced
often and it's not a physical component.

🤖 NER Agent:
Using:
- Assembly (well_known) - physical components like legs, panels, screws
- Instructions (discovered) - assembly guides, manuals

Instructions is separate because it's documentation, not hardware.

Now proposing 6 types with clear structure.
```

---

## Dialog 9: User Requests Cross-File Pattern Check

**Scenario**: User suspects a concept appears differently in different files

```
👤 User:
I think "complaint" and "claim" might refer to the same thing but
are used differently in reviews vs warranty docs. Can you check both
files and see if these should be separate entity types or combined?

🤖 NER Agent:
Analyzing 'complaint' vs 'claim' usage across files...

product_reviews.md:
- "complaint" (7 times) - informal grievances in reviews
  > "my complaint is the shelf wobbles"
  > "filed a complaint about delivery"

warranty_claims.md:
- "claim" (23 times) - formal warranty requests
  > "submitted claim #W-2024-0156"
  > "claim was approved for replacement"
- "complaint" (0 times)

Pattern:
- Complaints: informal, in product reviews, no tracking number
- Claims: formal, in warranty system, has IDs (W-2024-XXXX)

These appear to be different concepts:
- Complaint = informal issue report
- Claim = formal warranty request

Should I create both as entity types, or just Claim (the formal one)?

👤 User:
Just create Claim. The informal complaints are just reviews, we don't
need to track them separately.

🤖 NER Agent:
Added 'Claim' (discovered) - formal warranty request with tracking ID.

Skipping informal complaints (just review content).
Now proposing 5 types.
```

---

## Dialog 10: User Directs Negative Discovery

**Scenario**: User tells agent what NOT to include based on their knowledge

```
👤 User:
Before you propose types, let me tell you what NOT to include:
- Don't include colors (they're properties)
- Don't include prices or measurements
- Don't include locations (warehouse, city) - we only care about
  the products and issues, not where things happen

Now analyze the files with those constraints.

🤖 NER Agent:
Understood. Analyzing with exclusions...

Scanning for entity types, excluding:
- Colors (property of Product)
- Prices/measurements (properties)
- Locations (contextual, not analysis focus)

Found:
- Product (well_known) - KALLAX, BILLY, MALM
- Assembly (well_known) - components
- Issue (discovered) - product problems
- Customer (discovered) - people in reviews/claims
- Warranty (discovered) - warranty coverage

Explicitly excluded from proposal:
- "Color" (mentioned 12 times, but it's a property)
- "Stockholm", "Chicago" (mentioned 8 times, but locations excluded per your guidance)
- "Price", "Cost" (mentioned 15 times, but measurements excluded)

Proposing 5 types as requested.

👤 User:
Perfect. That's exactly what I wanted.

🤖 NER Agent:
Great! Your constraints focused the analysis on core entities.
Ready to approve these 5 types?
```

---

## Dialog 11: User Guides Investigation of Edge Cases

**Scenario**: User asks agent to investigate unusual or rare mentions

```
👤 User:
I saw a few mentions of "refurbished" or "returned" products in the
reviews. Search for those terms and tell me if there's a pattern
worth capturing as an entity type.

🤖 NER Agent:
Searching for 'refurbished', 'returned', 'open box'...

'refurbished': 4 matches
> product_reviews.md, line 89: bought refurbished KALLAX, missing parts
> product_reviews.md, line 134: refurbished items don't include warranty
> warranty_claims.md, line 67: claim denied - refurbished item
> warranty_claims.md, line 98: refurbished product not eligible

'returned': 6 matches
> product_reviews.md, line 45: previous customer returned this unit
> product_reviews.md, line 78: received returned item as "new"

'open box': 2 matches
> product_reviews.md, line 156: open box deal had damage

Pattern found:
- Refurbished/returned items have different warranty rules
- Quality issues more common on these items
- Customers often don't realize they received returned/refurbished

This seems like a product status/condition. Should I:
a) Add 'ProductCondition' as entity type (new, refurbished, returned)
b) Skip it (it's a property on Product)
c) Add 'RefurbishedProduct' as separate entity type

👤 User:
Skip it. It's a status property on Product, not a separate entity.
Just note in the schema that Product should have a "condition" property.

🤖 NER Agent:
Noted: Product should have condition property (new/refurbished/returned).
Not creating separate entity type.

Keeping proposal at 5 types (no ProductCondition).
```

---

## Dialog 12: User Combines Domain Knowledge with Text

**Scenario**: User knows domain concepts and wants to verify they exist in text

```
👤 User:
In supply chain analysis, we typically track: suppliers, products,
defects, and root causes. I see Product and Defect in your proposal.
But I don't see "root cause" - can you search for mentions of why
defects happen? Terms like "cause", "reason", "because", "due to".

🤖 NER Agent:
Searching for causal language in defect descriptions...

Found causal mentions:

warranty_claims.md:
> 45: defect caused by improper packaging during shipping
> 67: crack due to manufacturing equipment malfunction
> 89: missing parts because supplier shipment was incomplete
> 103: damage from warehouse handling error

product_reviews.md:
> 34: broke because the wood quality was poor
> 56: failed due to design weakness in joint
> 78: issue caused by rushed assembly at factory

Causal categories found:
1. Packaging problems (3 mentions)
2. Manufacturing equipment (2 mentions)
3. Supplier issues (2 mentions)
4. Material quality (4 mentions)
5. Design problems (3 mentions)

Should I create 'RootCause' or 'CauseCategory' as an entity type to
capture these causal factors?

👤 User:
Yes! Add RootCause as a discovered type. This is exactly what I need
for root cause analysis - linking defects to their causes.

🤖 NER Agent:
Added 'RootCause' (discovered) - underlying reason for defects
(packaging, manufacturing, supplier, material, design).

This creates the chain: Product → Defect → RootCause

Now proposing 6 types with clear causality tracking.
```

---

## Key Patterns in Guided Discovery

### 1. **User Points to Document Section**
"Look at lines X-Y..." or "Check the [section name]..."

### 2. **User Requests Pattern Search**
"Search for [concept] and see if it's a pattern..."

### 3. **User Provides Domain Knowledge**
"In this industry, we usually track..." or "There should be..."

### 4. **User Questions Agent's Proposal**
"You said X, but shouldn't it be Y?" or "What about Z?"

### 5. **User Sets Constraints**
"Don't include..." or "Focus only on..." or "Exclude..."

### 6. **User Suggests Splits/Merges**
"Break down [type] into..." or "Combine [type1] and [type2]..."

### 7. **User Directs Cross-Reference**
"Compare how [concept] appears in file1 vs file2..."

---

## Why Guided Discovery Works

1. **User has domain expertise** - knows what matters for their analysis
2. **User read the actual files** - spotted patterns agent might miss
3. **User understands the goal** - can prioritize what supports their needs
4. **Agent has search tools** - can verify patterns and count mentions
5. **Agent has full context** - can read sections and cross-reference
6. **Collaboration** - combines human insight with AI pattern recognition

---

## Commands for Guiding the Agent

### Direct to Section
- `"Read lines X-Y of [file]"`
- `"Look at the [section name] section"`
- `"Check the beginning/middle/end of [file]"`

### Request Search
- `"Search for [term] and analyze the pattern"`
- `"Look for mentions of [concept]"`
- `"Compare usage of [term1] vs [term2]"`

### Share Knowledge
- `"In this domain, we track [concepts]"`
- `"I know [concept] exists - verify it in the text"`
- `"This industry typically has [entity types]"`

### Set Direction
- `"Focus on [aspect]"`
- `"Exclude [concept]"`
- `"Don't include [types]"`
- `"Split [type] into finer categories"`

### Challenge Proposals
- `"Why did you choose X over Y?"`
- `"Shouldn't [concept] be separate?"`
- `"What about [concept I noticed]?"`

### Verify Hunches
- `"I think [concept] might be important - check it"`
- `"Does [pattern] appear in the data?"`
- `"Are [concept1] and [concept2] the same thing?"`
