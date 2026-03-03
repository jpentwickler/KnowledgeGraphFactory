# Risk Score and Criticality for Vacuum Assets

## Question
What does the risk score mean and when is it critical?

## Summarized Answer
Risk scores are composite metrics combining likelihood and impact analysis to guide maintenance decisions. They classify assets into five categories: Very Low (Green), Low (Light Green), Moderate (Yellow), High (Orange), and Critical (Red). Risk becomes critical when Health Index exceeds 0.9 with high impact classification, or when likelihood is "very likely" with significant consequences. Critical conditions trigger immediate CIP team evaluation, enhanced monitoring, and potential asset removal. The framework uses Health Index ranges where 0-0.75 indicates good condition, 0.75-0.9 shows warning condition, and above 0.9 represents critical condition requiring immediate attention.

## Overview
Risk assessment in vacuum pump systems combines likelihood and impact analysis to determine appropriate service strategies and maintenance actions. The risk score is a composite metric that guides operational decisions and resource allocation.

## Risk Matrix Framework

### Risk Score Components
The risk score is calculated using two primary dimensions:

1. **Likelihood**: Probability that a failure event will occur
2. **Impact**: Severity of consequences if the failure occurs

### Risk Categories and Thresholds
Based on the risk matrix analysis, assets are classified into the following categories:

| Risk Level | Color Code | Recommended Service Strategy | Action Required when an alarm occurs |
|------------|------------|------------------------------|--------------------------------------|
| **Very Low** | Green | RTF (Run to Failure) | Minimal monitoring |
| **Low** | Light Green | RTF (Run to Failure) | Basic monitoring |
| **Moderate** | Yellow | PdM (Predictive Maintenance) | Scheduled inspections |
| **High** | Orange | PdM (Predictive Maintenance) | Increased monitoring frequency |
| **Critical** | Red | PdM (Predictive Maintenance) | Immediate attention required |

## Critical Risk Conditions

### When Risk is Considered Critical
Risk becomes critical when:

1. **Health Index > 0.9** and **High Impact** classification
2. **Likelihood = "Very likely to happen"** and **Impact ≥ "Significant consequences"**
3. **Multiple failure indicators** converging simultaneously
4. **Process harshness** combined with **statistical performance degradation**

### Critical Risk Response Actions
- **Immediate Assessment**: CIP team evaluates next best action and schedule removal ASAP if necessary
- **Monitoring Enhancement**: Increase data verification frequency

## Likelihood Assessment Factors

### Data Sources for Likelihood Calculation
1. **Pump Telemetries**
   - Health Index
   - Temperature readings
   - Pressure measurements
   - Power consumption data

2. **Vibration Metrics**
   - Bearing condition indicators
   - Clogging detection signatures
   - Seizure warning signals
   - Processed by edge devices from raw vibration data

### Likelihood Determination Process
- Real-time data ingestion from pump telemetries
- Vibration signature analysis correlation
- Historical performance pattern recognition
- Business impact quantification
- Service level target alignment

### Health Index Definition
The Health Index is a decimal value between 0 and 1 that reflects the current wear condition of a vacuum pump:

- **0**: Nominal behavior with minimal wear
- **1**: Failure expected in short time

| HI Range | Condition Status | Risk Implication |
|----------|------------------|------------------|
| 0 ≤ HI ≤ 0.75 | Good Condition | Low risk of failure |
| 0.75 < HI ≤ 0.9 | Warning Condition | Moderate to high risk |
| 0.9 < HI ≤ 1.0 | Critical Condition | High to critical risk |

## Impact Assessment Categories

### Primary Impact Types
1. **Wafer Scrap Risk**: Financial loss due to product damage
2. **Downtime Impact**: Production interruption costs
3. **Service Cost**: Maintenance and repair expenses

### Consequence Severity Levels
| Impact Level | Description | Business Effect |
|--------------|-------------|-----------------|
| **Negligible** | Minimal operational disruption | Routine maintenance window |
| **Low** | Minor production delays | Scheduled downtime acceptable |
| **Moderate** | Significant operational impact | Production planning affected |
| **Significant** | Major production disruption | Critical path operations affected |
| **Catastrophic** | Severe business impact | Emergency response required |

## Knowledge Graph Entity Relationships

### Key Entities and Relationships
1. **Asset** → HAS → **Health Index**
2. **Health Index** → DETERMINES → **Risk Category**
3. **Risk Category** → DEFINES → **Service Strategy**
4. **Telemetry Data** → INFLUENCES → **Likelihood Assessment**
5. **Vibration Metrics** → CONTRIBUTES_TO → **Failure Prediction**
6. **Impact Assessment** → CONSIDERS → **Business Consequences**
7. **Risk Matrix** → GUIDES → **Maintenance Decisions**

## Conclusion
Risk scores provide a quantitative framework for maintenance decision-making by combining likelihood and impact assessments. Critical conditions are identified through Health Index thresholds, telemetry analysis, and business impact evaluation, enabling proactive maintenance strategies that optimize equipment availability and minimize operational risks.