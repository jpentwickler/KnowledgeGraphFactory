# Risk Percentage Calculation Framework for Vacuum Pump Assets

## Question
How do you calculate the risk percentage for an asset?

## Summarized Answer
Risk percentage represents the 30-day failure probability using a hazard-based model. The process starts with Health Index smoothing through resampling, gap-filling, and noise reduction. Remaining Useful Lifetime (RUL) is calculated using exponential degradation modeling. Total hazard combines three components: condition hazard (1/RUL), shock hazard (random failures), and age hazard (Weibull-based aging). The 30-day failure probability is calculated as P_30d = 1 - exp(-h_total × H_effective), where effective exposure accounts for actual operational time. Risk levels range from A (≥80% - almost certain) to E (<10% - rare), with automated hourly calculations and CMMS work order generation for high-risk assets.

## Overview
Risk percentage represents the probability that an asset will fail within a 30-day forecast period, calculated using a comprehensive hazard-based model that combines condition monitoring, aging effects, and operational factors.

## Input Data Requirements

### Health Index Smoothing (HI_s)
The foundation of risk calculation begins with processing raw Health Index data:

**Processing Steps**:
1. **Resample** raw HI to 10-minute mean values
2. **Gap-fill** using linear interpolation (up to 30 minutes)
3. **Apply median filter** (3-point centered) to remove spikes
4. **Clip jumps** where ΔHI > ±0.5 (set to NaN)
5. **Bounds check** to clamp values between 0-1
6. **Apply causal EWMA** with α ≈ 0.15 for noise dampening

```python
hi = (raw.resample("10T").mean()
           .interpolate(limit=3)
           .rolling(3, center=True).median())
hi = hi.mask(hi.diff().abs() > 0.5).clip(0, 1)
HI_s = hi.ewm(alpha=0.15, adjust=False).mean()
```

### Remaining Useful Lifetime (RUL) Calculation
RUL estimation uses complementary exponential degradation modeling:

**Mathematical Model**:
```
HI_s(t) = 1 - A · e^(-b(t - t₀))
```

**Processing Steps**:
1. **Detect onset** when 24h rolling HI_s ≥ 0.15
2. **Transform** to linear: y = ln[1 - HI_s]
3. **Apply window** of last 300 hours after onset
4. **Robust fit** using Huber regression
5. **Extract parameters** slope b and intercept ln A
6. **Calculate RUL** = ln(A/(1 - 0.99)) / b
7. **Quality control** clamping between 1-40,000 hours

## Risk Calculation Framework

### Hazard Composition
Total hazard combines three independent failure mechanisms:

```
h_total = h_condition + h_shock + h_age
```

Where:
- **h_condition** = 1/RUL (wear-based hazard)
- **h_shock** = max(1/MTBF, λ_app) (random failure hazard)
- **h_age** = (β/η)(R_cum/η)^(β-1) (age-based hazard using Weibull parameters)

### Effective Exposure Calculation
30-day forecast considers actual operational exposure:

```
H_effective = DF × 720 hours
```

Where DF = duty factor (fraction of time actually operating)

### 30-Day Failure Probability
Final risk percentage calculation:

```
P_30d = 1 - exp(-h_total × H_effective)
```

## Risk Level Classification

| Level | Probability Range | Risk Percentage | Action Required |
|-------|------------------|-----------------|-----------------|
| **A** | ≥ 0.80 | ≥ 80% | Almost certain - immediate dispatch |
| **B** | 0.60-0.79 | 60-79% | Likely - schedule corrective work order |
| **C** | 0.30-0.59 | 30-59% | Possible - monitor and prepare |
| **D** | 0.10-0.29 | 10-29% | Unlikely - routine checks |
| **E** | < 0.10 | < 10% | Rare - very low risk |

## Advanced Model: Cox Proportional Hazards

For fleets with sufficient failure data (≥15-30 events), the framework can be upgraded using Cox Proportional Hazards modeling:

```
h(t|X) = h₀(t) · exp(β_HI·HI_s + β_dHI·dHI/dt + β_DF·DF + β_R·R_cum)
```

**Implementation Phases**:
- **15-30 failures**: Cox PH v1 using HI_s and dHI/dt
- **30-50 failures**: Cox PH v2 adding DF, R_cum, and model dummies
- **≥100 failures**: Parametric baseline with Bayesian confidence intervals

## Operational Implementation

### Automated Calculation Schedule
Risk percentages are calculated hourly following this sequence:

| Time | Process | Output |
|------|---------|--------|
| 00:05 | Pull raw HI + runtime data | raw_hi |
| 00:10 | Smooth HI using median + EWMA | HI_s |
| 00:15 | Fit RUL using exponential trend | RUL |
| 00:20 | Compute hazards (condition + shock + age) | hazard_table |
| 00:22 | Calculate P30d and risk level | P30d, level |
| 00:25 | Generate CMMS tickets for A/B levels | Work orders |

### Quality Control Parameters

**Smoothing Parameters**:
- Resampling interval: 10 minutes
- Gap-fill limit: 30 minutes
- Jump detection threshold: ±0.5 HI units
- EWMA alpha: 0.15

**RUL Parameters**:
- Onset threshold: HI_s ≥ 0.15
- Fitting window: 300 hours
- Failure threshold: HI_s = 0.99
- Valid range: 1-40,000 hours

## Knowledge Graph Entity Relationships

### Data Processing Relationships
1. **Raw_HI** → PROCESSED_INTO → **HI_s** → USED_FOR → **RUL_Calculation**
2. **HI_s_Trend** → INDICATES → **Degradation_Rate**
3. **RUL_Estimation** → DETERMINES → **Condition_Hazard**
4. **Operational_Data** → PROVIDES → **Duty_Factor** + **Runtime**
5. **Weibull_Parameters** → DEFINE → **Age_Hazard**

### Risk Calculation Relationships
6. **Condition_Hazard** + **Shock_Hazard** + **Age_Hazard** → COMBINE_INTO → **Total_Hazard**
7. **Total_Hazard** × **Effective_Exposure** → CALCULATES → **Failure_Probability**
8. **30_Day_Probability** → CLASSIFIED_AS → **Risk_Level** (A through E)
9. **Risk_Percentage** → TRIGGERS → **Maintenance_Actions**
10. **Historical_Failures** → VALIDATE → **Model_Accuracy**

### Operational Integration Relationships
11. **Hourly_Calculation** → GENERATES → **Current_Risk_Assessment**
12. **Risk_Level_A_B** → CREATES → **CMMS_Work_Orders**
13. **Service_Actions** → MODIFY → **Asset_Condition** → AFFECTS → **Future_Risk**
14. **Model_Performance** → DRIVES → **Parameter_Updates**

### Query-Enabling Relationships
These relationships enable the knowledge graph to answer:
- "What is the current 30-day failure probability for pump ID X?"
- "How does duty factor affect risk percentage calculation?"
- "What hazard components contribute most to total risk?"
- "When should the Cox proportional hazards model be implemented?"

## Conclusion
Risk percentage calculation integrates multiple data sources and analytical techniques to provide actionable failure probability estimates. The framework progresses from basic hazard composition to advanced Cox proportional hazards modeling based on available data maturity, ensuring appropriate model complexity while maintaining operational reliability.