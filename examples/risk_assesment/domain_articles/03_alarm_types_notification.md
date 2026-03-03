# Alarm Types and Notification Framework for Vacuum Pump Assets

## Question
What is the difference between a warning alarm, a critical alarm, and an error alarm?

## Summarized answer
Warning alarms indicate early degradation when Health Index transitions from ≤0.75 to 0.75-0.9 range, requiring assessment scheduling within hours to days. Critical alarms signal imminent failure when HI exceeds 0.9, demanding immediate evaluation within minutes to hours. Error alarms address system-level issues including data integrity problems, infrastructure failures, and configuration errors, with response times varying from minutes to days depending on error type. Each alarm type serves distinct purposes: warnings for early detection, critical for failure prevention, and errors for system functionality. CIP engineers can manage notifications, reset training baselines, and configure system parameters based on alarm type and operational requirements.

## Overview
The vacuum pump monitoring system generates three distinct types of alarms based on Health Index (HI), Remaining Useful Lifetime (RUL), telemetries and Failure Likelihood (FL) assessments. Each alarm type serves different purposes in the predictive maintenance workflow and requires specific response protocols.

## Alarm Classification Framework

### Primary Alarm Types

| Alarm Type | Severity Level | Purpose | Response Timeline | CIP Engineer Action |
|------------|----------------|---------|------------------|-------------------|
| **Warning Alarm** | Low to Moderate | Early degradation detection | Hours to days | Schedule assessment |
| **Critical Alarm** | High | Imminent failure prevention | Minutes to hours | Immediate evaluation |
| **Error Alarm** | System-level | Data integrity and system issues | Minutes to days | System troubleshooting |

## Warning Alarm Specifications

### Trigger Conditions
Warning alarms are generated when:

**Health Index Threshold Crossing**:
1. HI transitions from Good (≤0.75) to Warning range (0.75 < HI ≤ 0.9)
2. Sustained HI elevation above 0.75 for configured duration

### Warning Alarm Example Scenarios
```
Warning: Pump ID P-001
HI: 0.78 (crossed 0.75 threshold)
RUL: 45 days (trending downward)
FL: Level 2 (Possible failure risk)
Action: Schedule inspection within 7 days
```

## Critical Alarm Specifications

### Trigger Conditions
Critical alarms are generated when:

**Critical Health Index Range**:
1. HI exceeds 0.9 (enters critical condition range)
2. HI approaching maximum value (>0.95)

### Critical Alarm Example Scenarios
```
Critical: Pump ID P-001
HI: 0.93 (critical range)
RUL: 3 days (imminent failure)
FL: Level 4 (Highly likely to fail)
Action: Emergency maintenance required
```

## Error Alarm Specifications

### Trigger Conditions
Error alarms are generated for system-level issues:

1. **Data Integrity Problems**:
   - Missing telemetry data for extended periods (>1 hour)
   - Sensor calibration errors or out-of-range readings
   - Communication failures with edge devices
   - Baseline reference data corruption

2. **Model Calculation Errors**:
   - HI calculation algorithm failures
   - RUL projection model errors
   - FL computation anomalies
   - Statistical model convergence issues

3. **System Infrastructure Issues**:
   - Network connectivity problems affecting data collection
   - Database synchronization errors
   - Monitoring system component failures
   - Integration pipeline disruptions

4. **Configuration Problems**:
   - Invalid threshold settings
   - Missing pump configuration parameters
   - Incorrect MTBF statistical data
   - Baseline reference period misalignment

### Error Alarm Categories

#### Data Quality Errors
```
Error: Data Quality Issue - Pump ID P-001
Issue: Telemetry data missing for 2 hours
Impact: HI calculation suspended
Action: Verify sensor connectivity and data pipeline
```

#### System Infrastructure Errors
```
Error: Network Communication Lost
Issue: Edge device P-001-VIB offline
Impact: Vibration metrics unavailable
Action: Network troubleshooting required
```

## Alarm Management and CIP Engineer Actions

### Data Analytics Feature Management
CIP engineers can perform the following actions through the system interface:

1. **Notification Management**:
   - Acknowledge alarms to stop repeated notifications
   - Set notification schedules and escalation 
   - Configure alarm recipients and communication channels

2. **Training and Baseline Control**:
   - Reset model training after maintenance events
   - Update baseline reference periods
   - Adjust statistical parameters based on operational changes

3. **Operational Overrides**:
   - Ignore specific time intervals (maintenance windows)
   - Temporarily disable alarms for planned maintenance

4. **System Optimization**:
   - Analyze false positive/negative rates
   - Optimize notification frequency and escalation timers

## Knowledge Graph Entity Relationships

### Alarm System Entities
1. **Pump_Asset** → GENERATES → **Alarm_Event**
2. **Health_Index** → TRIGGERS → **Warning_Alarm** | **Critical_Alarm**
3. **RUL_Value** → INFLUENCES → **Alarm_Severity**
4. **Failure_Likelihood** → DETERMINES → **Alarm_Priority**
5. **System_Error** → CREATES → **Error_Alarm**
6. **CIP_Engineer** → MANAGES → **Alarm_Response**
7. **Data_Analytics** → SUPPORTS → **Alarm_Configuration**

## Conclusion
The three-tier alarm system (Warning, Critical, Error) provides a comprehensive framework for vacuum pump condition monitoring and maintenance decision-making. Each alarm type serves specific purposes in the predictive maintenance strategy, with clear trigger conditions, response requirements, and CIP engineer actions that ensure optimal equipment reliability and operational efficiency.