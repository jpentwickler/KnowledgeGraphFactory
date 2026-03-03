# Systematic Failure Investigation Framework for Vacuum Pump Assets

## Question
What systematic approach should I follow for failure investigation?

## Summarized Answer
DMAIC methodology provides structured investigation framework for complex failures. Define phase establishes problem statements, team formation, and success criteria. Measure phase collects comprehensive data including historical performance, failure events, and physical evidence with quality assurance protocols. Analyze phase employs techniques like 5 Why analysis, fishbone diagrams, and fault tree analysis to identify root causes through hypothesis development and validation. Improve phase develops solutions with pilot testing, cost-benefit analysis, and implementation planning. Control phase implements monitoring systems, documentation updates, and continuous improvement measures. Success requires appropriate team composition, systematic execution, and commitment to long-term control and monitoring.

## Overview
Systematic failure investigation ensures comprehensive root cause analysis, prevents recurrence, and drives continuous improvement in vacuum pump reliability. This framework provides structured methodologies for different failure types and contexts, with DMAIC as the primary systematic approach.

## Failure Report Context and Classification

### Failure Report Types
DMAIC analysis are needed for:

#### Type 1: Critical System Failures
**Characteristics**:
- Complete system shutdown or inability to restart
- Safety implications or environmental risks
- High business impact or production losses
- Examples: Motor breaker overcurrent, catastrophic mechanical failure

#### Type 2: Component-Level Failures
**Characteristics**:
- Individual component failure within larger system
- Limited immediate impact on overall performance
- Opportunity for predictive maintenance improvement
- Examples: Bearing failure, sensor malfunction, seal degradation

#### Type 4: Intermittent or Unusual Failures
**Characteristics**:
- Unusual parameter combinations or symptoms
- Limited historical precedent
- Examples: Transient electrical issues, environmental interactions

## DMAIC Methodology for Failure Investigation

### DMAIC Framework Overview
**DMAIC** is a data-driven improvement cycle used for improving, optimizing and stabilizing business processes and designs. The acronym stands for Define, Measure, Analyze, Improve, and Control.

**Application to Failure Investigation**: DMAIC provides systematic structure for complex failure investigations, ensuring comprehensive analysis and sustainable solutions while preventing recurrence through control measures.

### Phase 1: DEFINE

#### Purpose and Objectives
**Primary Goals**:
- Clearly articulate the failure problem and its impact
- Establish investigation scope and boundaries
- Assemble appropriate investigation team
- Define success criteria for resolution

#### Define Phase Activities

**Problem Statement Development**:
- **Failure description**: Specific symptoms and manifestations
- **Timeline establishment**: When failure occurred and was detected
- **Impact quantification**: Business, safety, and operational consequences
- **Scope definition**: Systems, components, and processes included

**Team Formation**:
- **Project leader**: Overall investigation coordination and accountability
- **Technical experts**: Domain knowledge in pumps, processes, and systems
- **Operations personnel**: Hands-on experience and operational context
- **Quality/reliability engineers**: Statistical analysis and methodology expertise

**Success Criteria Definition**:
- **Root cause identification**: Validated technical cause of failure
- **Solution implementation**: Effective corrective actions deployed
- **Recurrence prevention**: Control measures preventing similar failures
- **Documentation completion**: Knowledge capture and sharing

#### Define Phase Example: DS 1000 E Motor Failure
**Problem Statement**: "Busch DS 1000 E vacuum pump failed after 110 days of operation in ASM A400 furnace process at Infineon Villach, presenting as 'MB motor breaker overcurrent' with loud noise after restart attempt."

**Impact Assessment**:
- **Operational**: Complete furnace process shutdown
- **Production**: Lost wafer processing capability
- **Safety**: Electrical overcurrent condition
- **Timeline**: Immediate investigation required

### Phase 2: MEASURE

#### Purpose and Objectives
**Primary Goals**:
- Collect comprehensive data related to the failure
- Establish baseline performance metrics
- Document current state conditions
- Validate measurement systems and data quality

#### Measure Phase Activities

**Data Collection Strategy**:
- **Historical performance data**: Pre-failure trending and patterns
- **Failure event data**: Alarm logs, sensor readings, and system status
- **Environmental conditions**: Operating parameters and external factors
- **Maintenance records**: Service history and component replacement data

**Physical Evidence Gathering**:
- **Failed component inspection**: Visual examination and documentation
- **Photographic documentation**: Detailed images of failure modes and conditions
- **Sample collection**: Materials for laboratory analysis if required
- **Measurement verification**: Calibration and accuracy confirmation

**Data Quality Assurance**:
- **Measurement system analysis**: Accuracy, precision, and repeatability
- **Data integrity verification**: Completeness, consistency, and validity
- **Bias elimination**: Objective measurement and recording practices
- **Documentation standards**: Systematic recording and storage protocols

#### Measure Phase Example: DS 1000 E Investigation
**Data Collected**:
- **Failure symptoms**: Motor breaker overcurrent, loud noise after restart
- **Operating duration**: 110 days before failure
- **Physical inspection**: Process deposition present but rotors not stuck
- **Cable examination**: Brownish discoloration indicating thermal damage
- **Electrical measurements**: Current load analysis showing 21A operation

### Phase 3: ANALYZE

#### Purpose and Objectives
**Primary Goals**:
- Identify root cause(s) of the failure through systematic analysis
- Validate hypotheses with data and evidence
- Understand failure mechanisms and contributing factors
- Prioritize causes based on impact and likelihood

#### Root Cause Analysis Techniques

**5 Why Analysis**:
- **Systematic questioning**: Progressive drilling down to fundamental causes
- **Cause-effect relationships**: Logical connections between symptoms and causes
- **Evidence validation**: Supporting each "why" with factual data
- **Multiple pathway exploration**: Considering parallel and contributing causes

**Fishbone Diagram (Ishikawa)**:
- **Category organization**: People, Process, Equipment, Materials, Environment, Methods
- **Brainstorming facilitation**: Structured team input and idea generation
- **Cause categorization**: Systematic organization of potential factors
- **Priority identification**: Focus on most likely and impactful causes

**Fault Tree Analysis**:
- **Top-down approach**: Starting from failure event and working backwards
- **Boolean logic application**: AND/OR gate relationships between causes
- **Quantitative assessment**: Probability calculations when data available
- **Critical path identification**: Most likely failure sequences

#### Analyze Phase Example: DS 1000 E Root Cause
**5 Why Analysis Chain**:
1. **Why did pump fail?** → MB motor breaker overcurrent
2. **Why overcurrent?** → DP (Drive Part) failed
3. **Why did DP fail?** → Cable connection damaged/overloaded
4. **Why cable damaged?** → Load on cable too high
5. **Why load too high?** → Operating at 85 Hz with 21A load close to nominal current + 14-year-old cable degradation

**Validation Results**:
- **Motor analysis**: Compatible with 21A continuous load (No issue)
- **Cable analysis**: 4mm² copper wire at 60°C rated only 17.0A vs. 21A actual load
- **Visual evidence**: Brownish cable discoloration confirming thermal damage
- **Operational context**: High-frequency operation increasing current demand

### Phase 4: IMPROVE

#### Purpose and Objectives
**Primary Goals**:
- Develop and implement effective solutions to address root causes
- Pilot test solutions to validate effectiveness
- Plan full-scale implementation with risk mitigation
- Establish metrics to measure improvement success

#### Solution Development

**Immediate Corrective Actions**:
- **Emergency fixes**: Rapid response to prevent immediate recurrence
- **Safety measures**: Risk elimination or mitigation
- **System restoration**: Return to operational status
- **Temporary monitoring**: Enhanced surveillance during solution implementation

**Long-term Preventive Actions**:
- **Design improvements**: Engineering changes to eliminate failure modes
- **Process modifications**: Operational changes to reduce failure risk
- **Maintenance enhancements**: Improved inspection, service, and replacement protocols
- **Training and procedures**: Knowledge transfer and standardization

#### Improve Phase Example: DS 1000 E Solutions
**Short-term Actions**:
- **Cable replacement**: Immediate replacement of degraded brownish cable
- **Fleet inspection**: Check similar pump configurations (DS 1000/2000 E/F A-type screws)
- **Case documentation**: Reference numbers C0910000015 and C1038000500

**Long-term Improvements**:
- **Overhaul procedure update**: Include cable color inspection at every overhaul
- **Replacement criteria**: Change cables when brownish discoloration observed
- **Wire sizing verification**: Ensure adequate ampacity for operating conditions
- **Operating parameter optimization**: Review frequency settings and current demands

### Phase 5: CONTROL

#### Purpose and Objectives
**Primary Goals**:
- Sustain improvements and prevent failure recurrence
- Monitor solution effectiveness through ongoing measurement
- Establish control systems for early detection of similar issues
- Document lessons learned and update procedures

#### Control Phase Activities

**Control System Implementation**:
- **Monitoring protocols**: Regular inspection and measurement procedures
- **Alarm systems**: Early warning indicators for similar failure modes
- **Performance tracking**: Key metrics for solution effectiveness
- **Response procedures**: Defined actions when control limits are exceeded

**Documentation and Standardization**:
- **Procedure updates**: Maintenance and inspection protocol revisions
- **Training materials**: Knowledge transfer to relevant personnel
- **Failure database updates**: Historical record enhancement for future reference
- **Best practice sharing**: Cross-facility and industry knowledge dissemination

#### Control Phase Example: DS 1000 E Monitoring
**Control Measures**:
- **MTBF tracking**: Monitor if pumps exceed 150 days operation post-implementation
- **Cable inspection protocol**: Visual check at every overhaul with color assessment
- **Replacement trigger**: Immediate cable change when brownish discoloration observed
- **Performance monitoring**: Current draw and temperature trending

## Knowledge Graph Entity Relationships

### DMAIC Framework Relationships
1. **Failure_Event** → REQUIRES → **Investigation_Approach** (DMAIC/Simplified/Focused)
2. **Investigation_Type** → DETERMINES → **DMAIC_Phase_Emphasis**
3. **Define_Phase** → ESTABLISHES → **Problem_Statement** + **Investigation_Scope**
4. **Measure_Phase** → COLLECTS → **Failure_Data** + **Historical_Performance**
5. **Analyze_Phase** → IDENTIFIES → **Root_Cause** + **Contributing_Factors**
6. **Improve_Phase** → DEVELOPS → **Corrective_Actions** + **Preventive_Measures**
7. **Control_Phase** → IMPLEMENTS → **Monitoring_Systems** + **Documentation_Updates**

### Analysis Technique Relationships
8. **5_Why_Analysis** → REVEALS → **Causal_Chain** → LEADS_TO → **Root_Cause**
9. **Fishbone_Diagram** → ORGANIZES → **Potential_Causes** → GUIDES → **Investigation_Focus**
10. **Fault_Tree_Analysis** → MODELS → **Failure_Logic** → CALCULATES → **Failure_Probability**
11. **Statistical_Analysis** → VALIDATES → **Hypotheses** → CONFIRMS → **Root_Cause**
12. **Physical_Evidence** → SUPPORTS → **Analytical_Findings**

### Solution Implementation Relationships
13. **Root_Cause_Analysis** → GUIDES → **Solution_Selection**
14. **Corrective_Actions** → ADDRESS → **Immediate_Failure_Mode**
15. **Preventive_Actions** → ELIMINATE → **Future_Failure_Risk**
16. **Pilot_Testing** → VALIDATES → **Solution_Effectiveness**
17. **Control_Systems** → MONITOR → **Solution_Sustainability**

### Learning and Improvement Relationships
18. **Investigation_Results** → UPDATE → **Failure_Database** + **Knowledge_Base**
19. **Lessons_Learned** → IMPROVE → **Future_Investigation_Capability**
20. **Best_Practices** → STANDARDIZE → **Investigation_Procedures**
21. **Case_Studies** → TRAIN → **Investigation_Teams**
22. **Success_Metrics** → MEASURE → **Investigation_Effectiveness**

### Query-Enabling Relationships
These relationships enable the knowledge graph to answer:
- "What systematic approach should I follow for this motor overcurrent failure?"
- "Which DMAIC phases are most critical for electrical failures?"
- "What team composition is needed for a comprehensive pump failure investigation?"
- "How do I validate root causes identified through 5 Why analysis?"
- "What control measures should I implement to prevent cable overheating recurrence?"

## Conclusion
Systematic failure investigation using DMAIC methodology provides comprehensive frameworks for root cause analysis and sustainable solution implementation. The structured approach ensures:

- **Complete problem understanding** through systematic definition and measurement
- **Data-driven root cause identification** through rigorous analysis techniques
- **Effective solution development** with pilot testing and validation
- **Sustainable improvement** through control systems and monitoring
- **Knowledge preservation** for continuous organizational learning

Success depends on appropriate methodology selection based on failure context, skilled team composition, systematic execution of investigation phases, and commitment to long-term control and monitoring.