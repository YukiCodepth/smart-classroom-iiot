# ⚡ Industrial IoT Climate Control & Energy Economizer
### *Autonomous Smart Classroom Management Powered by 5G Network Slicing & Edge AI*

![Enterprise IIoT](https://img.shields.io/badge/Architecture-Industrial%20Edge%20AI-0052FF?style=for-the-badge&logo=arm&logoColor=white)
![Firmware](https://img.shields.io/badge/Firmware-Embedded%20C%2B%2B-00599C?style=for-the-badge&logo=c%2B%2B&logoColor=white)
![Gateway](https://img.shields.io/badge/Gateway-Python%203.10%2B-3776AB?style=for-the-badge&logo=python&logoColor=white)
![Database](https://img.shields.io/badge/Historian-InfluxDB%202.7-22ADF6?style=for-the-badge&logo=influxdb&logoColor=white)
![Visualization](https://img.shields.io/badge/Observability-Grafana-F46800?style=for-the-badge&logo=grafana&logoColor=white)
![5G RAN](https://img.shields.io/badge/Network-5G%20RAN%20Slicing-FF0055?style=for-the-badge)
![License](https://img.shields.io/badge/License-MIT-success?style=for-the-badge)

---

## 📌 Executive Summary

Modern educational facilities and industrial workspaces suffer from severe energy inefficiency and delayed environmental remediation due to legacy, rule-based HVAC systems. This project introduces a **closed-loop, edge-computed Industrial IoT (IIoT) architecture** that combines on-chip statistical anomaly rejection, real-time thermodynamic machine learning, and dynamic **5G Radio Access Network (RAN) Quality of Service (QoS) slicing**.

By decoupling physical sensor noise from automated control logic, the system maintains strict **ASHRAE / ISO 7730 thermal comfort standards** while achieving up to **91.4% energy savings** over baseline industrial consumption—all while actively defending against hardware short-circuits and cyber data-poisoning attacks in real time.

---

## 🏛️ System Architecture & The 3 Pillars

### I. Embedded Perception & 3-Layer Cybersecurity Shield
Microcontrollers deployed in physical environments are inherently vulnerable to electrical noise, sensor degradation, and malicious data injection. The ESP32 firmware implements an on-chip, defense-in-depth statistical filtering pipeline prior to network transmission:

```mermaid
graph TD
    A[Raw Sensor Input] --> B{Layer 1: Hard Physical Gate<br/>10°C to 45°C | 5% to 99% RH}
    B -- Out of Bounds --> C[🚨 HARD FAULT: Quarantine Kalman<br/>Hold Last Known Valid Estimate]
    B -- Plausible --> D[Layer 2: Quarantined Kalman Filter<br/>Recursive Error Estimation]
    D --> E{Layer 3: Rolling Z-Score Guard<br/>Evaluate Residual against σ}
    E -- Z > 3.0σ --> F[🚨 STATISTICAL SPIKE: Trap Attack<br/>Increment Leaky Bucket Counter]
    E -- Z ≤ 3.0σ --> G[✔️ HEALTHY: Update Variance Buffer<br/>Dispatch Telemetry Frame]
    F -- 4 Consecutive Anomalies --> H[🔄 STEP-CHANGE RECOVERY<br/>Auto-Reconverge Kalman & Reset Z-Guard]

```

* **Layer 1 (Hard Physical Plausibility Gating):** Immediately discards physically impossible readings (e.g., $80^\circ\text{C}$ hardware spikes or $-40^\circ\text{C}$ open circuits), preventing corrupted data from entering statistical buffers.
* **Layer 2 (Quarantined Kalman Filtering):** An adaptive recursive filter that smooths gaussian environmental noise. Upon detecting a Layer 1 or Layer 3 anomaly, the filter enters **quarantine mode**, freezing its state estimation to hold steady-state control logic.
* **Layer 3 (Clamped Z-Score Anomaly Guard):** A rolling standard deviation engine ($\sigma$) that tracks estimation residuals. Outliers exceeding $3.0\sigma$ are trapped as cyber injection attacks.
* **Step-Change Deadlock Breaker:** A leaky-bucket recovery algorithm that prevents latched alarms. If 4 consecutive valid-bound anomalies occur, the system identifies a legitimate environmental step-change (e.g., sudden window opening) and autonomously reconverges the Kalman filter and Z-score memory.

---

### II. Dynamic 5G RAN Slicing & Closed-Loop Telemetry

The system communicates over an asynchronous MQTT v1/v2 pipeline utilizing unacknowledged **QoS 0** packet delivery to eliminate handshake latency across public cloud brokers (`broker.emqx.io`).

```mermaid
sequenceDiagram
    autonumber
    participant MCU as ESP32 Perception Node
    participant Broker as EMQX Cloud Broker (QoS 0)
    participant Gateway as Linux Edge AI Daemon
    participant TSDB as InfluxDB & Grafana

    MCU->>Broker: Publish Telemetry (eMBB Slice | 2000ms rate)
    Broker->>Gateway: Ingest Packet (Calculate Hardware RTT Delta)
    
    alt RTT > 120ms OR Cyber Shield Alarm Active
        Gateway->>Gateway: Shift Slice -> 5G_URLLC_CRITICAL
        Gateway->>Broker: Publish Control Command (Throttle Rate -> 5000ms)
        Broker->>MCU: Switch Relays & Update Transmission Interval
    else Normal RAN & Healthy Sensors
        Gateway->>Gateway: Maintain 5G_eMBB_Standard
        Gateway->>Broker: Publish Control Command (Rate -> 2000ms)
        Broker->>MCU: Energize/Standby Actuator Relays (HVAC / Exhaust)
    end

    Gateway->>TSDB: Write Telemetry Matrix (Fields: Mode, Health, Slice)

```

* **True Hardware RTT Tracking:** The gateway computes network latency using MCU hardware timestamps (`timestamp_ms`), making latency calculations 100% immune to web sandbox or virtual machine clock throttling.
* **Active Rate Adaptation:** When network congestion ($>120\text{ms}$ RTT) or sensor attacks occur, the gateway dynamically commands the ESP32 to shift from **`5G_eMBB_Standard`** (Enhanced Mobile Broadband, 2000ms interval) to **`5G_URLLC_CRITICAL`** (Ultra-Reliable Low-Latency Communication, 5000ms interval), preserving critical radio bandwidth for emergency safety alarms.

---

### III. Edge AI & Predictive Thermodynamic Economizer

The Linux gateway hosts an online machine learning engine and international environmental comfort calculators that replace reactive thermostats with predictive climate modeling:

* **Thermodynamic Machine Learning (`SGDRegressor`):** Continuously trains on localized temperature, humidity, occupancy count, and human body heat gain ($100\text{W}$ per person) using regularized Stochastic Gradient Descent ($\alpha=0.0001$). It predicts room temperature **+15 minutes into the future**.
* **Model Poisoning Defense:** When the embedded Cyber Shield signals a sensor fault, the Linux gateway immediately freezes SGD weight updates (`🚨 [ML PROTECTED]`), ensuring outlier attacks cannot corrupt the neural regression weights.
* **ASHRAE / ISO 7730 Comfort Index:** Calculates the Predicted Mean Vote (PMV) thermal comfort index on a scale from $-3.0$ (Cold) to $+3.0$ (Hot), maintaining localized comfort between $-0.5$ and $+0.5$.
* **Actuator State-Gating:** GPIO relay commands are gated by physical hardware state checks (`if (digitalRead(pin) != targetState)`), eliminating electromagnetic relay chattering and serial log spam.

---

## 📐 Mathematical Formulations

### 1. Recursive Quarantined Kalman Filter

The on-chip state estimation predicts and updates thermal velocity while isolating measurement errors:

$$\hat{x}_k^- = \hat{x}_{k-1}$$

$$P_k^- = P_{k-1} + Q$$

$$K_k = \frac{P_k^-}{P_k^- + R}$$

$$\hat{x}_k = \hat{x}_k^- + K_k \left( z_k - \hat{x}_k^- \right)$$

$$P_k = \left( 1 - K_k \right) P_k^-$$

*Where $Q = 0.01$ (process noise covariance), $R = 2.0$ (measurement noise covariance), and $K_k$ is the adaptive Kalman gain. If $\vert{}z_k - \hat{x}_k^-\vert{} > 3.0\sigma$, $K_k$ is forced to $0$, holding $\hat{x}_k = \hat{x}_{k-1}$.*

---

### 2. Clamped Rolling Z-Score Anomaly Guard

Statistical variance is evaluated over a sliding window of $N=15$ residuals, with clamping applied to prevent division-by-zero during steady-state classroom periods:

$$\mu = \frac{1}{N} \sum_{i=1}^{N} r_i, \quad \text{where } r_i = \vert{}z_i - \hat{x}_i\vert{}$$

$$\sigma = \sqrt{ \frac{1}{N} \sum_{i=1}^{N} \left( r_i - \mu \right)^2 }, \quad \text{subject to } 0.15 \le \sigma \le 2.50$$

$$Z = \frac{\vert{}r_k - \mu\vert{}}{\sigma}$$

---

### 3. ISO 7730 PMV Comfort Index Approximation

Thermal comfort is derived from partial water vapor pressure ($p_a$) and heat transfer coefficients:

$$p_a = \left( \frac{\text{RH}}{100} \right) \cdot 10 \cdot \exp \left( 16.6536 - \frac{4030.18}{T + 235} \right)$$

$$\text{PMV} = \left( 0.303 \exp(-0.036 M) + 0.028 \right) \cdot \left[ (M - W) - H_{\text{evap}} - H_{\text{conv}} - H_{\text{rad}} \right]$$

*Where $T$ is filtered temperature ($^\circ\text{C}$), $\text{RH}$ is relative humidity ($\%$), $M=58\text{ W/m}^2$ (metabolic rate for seated students), and $W=0$ (external work).*

---

### 4. Real-Time Economizer Efficiency Gain

Energy savings are computed by comparing real-time AI actuator loads against a baseline industrial HVAC continuous draw ($P_{\text{base}} = 3500\text{W}$):

$$\text{Savings}(\%) = \max \left( 0.0, \left[ 1.0 - \frac{P_{\text{hvac}} + P_{\text{vent}}}{P_{\text{base}}} \right] \times 100 \right)$$

*Where $P_{\text{hvac}} \in \{0\text{W}, 300\text{W}, 1200\text{W}, 2500\text{W}\}$ based on ECO standby, pre-cooling, or active compressor states, and $P_{\text{vent}} = 400\text{W}$ during active economizer exhaust ventilation.*

---

## 🛠️ System Hardware & Pinout Matrix

The microcontroller perception node is engineered for the **ESP32-WROOM-32** development board. Analog industrial gas sensors are modeled via voltage dividers in simulation environments.

| Component | MCU Pin | I/O Type | Physical Function / Simulation Mapping | Actuator / Safe-State |
| --- | --- | --- | --- | --- |
| **DHT22 Sensor** | `GPIO 15` | Digital In | Captures ambient Temperature ($^\circ\text{C}$) and Humidity ($\% \text{RH}$) | Out-of-bounds trigger ($<10^\circ\text{C}$ or $>45^\circ\text{C}$) |
| **MQ135 Gas Sensor** | `GPIO 34` | Analog In | Measures air quality ($\text{CO}_2$). Simulated via $10\text{k}\Omega$ slide potentiometer ($0\text{V}$–$3.3\text{V} \rightarrow 400$–$2000\text{ PPM}$) | Exceeding $1000\text{ PPM}$ triggers active exhaust |
| **PIR Motion Sensor** | `GPIO 13` | Digital In | Detects classroom occupancy. Maps digital HIGH to student count ($0 \text{ or } 25$) | Zero occupancy shifts HVAC to ECO Standby |
| **HVAC Relay (Blue LED)** | `GPIO 2` | Digital Out | Controls primary cooling compressor. In series with $220\Omega$ current-limiting resistor | Gated transition: STANDBY (LOW) $\leftrightarrow$ ENERGIZED (HIGH) |
| **Exhaust Relay (Red LED)** | `GPIO 4` | Digital Out | Controls economizer exhaust ventilation fan. In series with $220\Omega$ resistor | Gated transition: STANDBY (LOW) $\leftrightarrow$ ENERGIZED (HIGH) |

---

## 🚀 Quick-Start Execution Guide

### Prerequisites

* **Linux Environment:** Ubuntu 20.04+, macOS (Apple Silicon M1/M2/M3 native or Linux VM), or Windows WSL2.
* **Python:** Version `3.10` or higher.
* **Time-Series Stack:** Local or Docker instance of **InfluxDB v2.7+** and **Grafana v9.0+**.
* **Digital Twin Simulator:** Web browser with access to [Wokwi ESP32 Simulator](https://wokwi.com).

---

### Step 1: Clone & Configure the Linux Edge Gateway

1. Clone the repository and navigate into the workspace:
```bash
git clone [https://github.com/your-username/smart-classroom-iiot.git](https://github.com/your-username/smart-classroom-iiot.git)
cd smart-classroom-iiot

```


2. Create and activate a isolated Python virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate

```


3. Install core enterprise dependencies:
```bash
pip install --upgrade pip
pip install paho-mqtt influxdb-client scikit-learn numpy

```


4. Launch the automated Edge AI Gateway Daemon:
```bash
python3 edge-daemon/edge_ai_daemon.py

```


*Verify in your terminal:* You should immediately see confirmation logs stating `Connected to 5G Cloud MQTT Broker (broker.emqx.io)` and `Subscribed to topic [smart_classroom/telemetry/raw] with QoS 0 successfully!`.

---

### Step 2: Deploy the Wokwi Digital-Twin Hardware

1. Open a blank ESP32 project in your browser: **[https://wokwi.com/projects/new/esp32](https://wokwi.com/projects/new/esp32)**.
2. In the **`sketch.ino`** tab, paste the complete C++ firmware code from `firmware/src/main.cpp`.
3. In the **`diagram.json`** tab, paste the exact hardware circuit layout from `firmware/diagram.json`.
4. Create a **`libraries.txt`** tab (click the `+` icon) and add:
```text
PubSubClient
ArduinoJson
DHT sensor library

```


5. **The Magic Reload:** Click inside the code editor, press **`F1`** on your keyboard, and select **"Reload Diagram"** (or click the Save/Share button). The visual engine will instantly wire your DHT22, slide potentiometer, PIR sensor, resistors, and LEDs onto the canvas.
6. Click the green **Play** button to boot the microcontroller.

---

### Step 3: Configure Grafana Time-Series Observability

1. Access your Grafana UI at `http://localhost:3000`.
2. Add InfluxDB as a data source pointing to your bucket (`classroom_telemetry`).
3. Import the pre-built dashboard JSON located in `dashboards/grafana-iiot-layout.json`.
4. **Clean Schema Verification:** Notice that state variables (`mode`, `sensor_health`, `network_slice`) are queried as InfluxDB **Fields**, not Tags. This guarantees exactly **one unbroken time-series curve** per sensor and zero visual widget fragmentation!

---

## ⚠️ Production Cautions & Architectural Edge-Cases

During enterprise deployment or hardware modification, adhere strictly to these engineering guardrails established during post-mortem audits:

> **1. The 256-Byte PubSubClient Memory Trap**
> By default, the Arduino `PubSubClient` library allocates a hardcoded memory limit of 256 bytes for outgoing frames. Because Phase 7 enterprise JSON telemetry (containing 5G slice strings, timestamps, and floating-point sensor matrices) reaches ~275 bytes, **failing to explicitly expand the buffer will cause silent 100% packet drops!** Always ensure `mqttClient.setBufferSize(1024);` is called inside `setup()`.

> **2. Stack Memory Corruption in JSON Callbacks**
> Never assign raw pointers (`const char*`) to global variables directly from temporary `StaticJsonDocument` stack allocations inside MQTT message callbacks. When the function returns, stack memory is deallocated, causing silent garbage character injection or fatal MCU crashes. Always use managed `String` objects or static stack arrays (`strlcpy(target, source, sizeof(target))`).

> **3. Web Simulator Wall-Clock Throttling vs. Hardware RTT**
> Sandbox environments like Wokwi throttle execution to ~30% real-time speed depending on browser CPU load. Never compute network round-trip time using host wall-clock deltas (`time.time() - last_arrival`), or browser lag will be misidentified as severe RAN network congestion. Always compute RTT latency against **microcontroller hardware clock timestamps (`payload["timestamp_ms"]`)**.

> **4. TSDB Tag Cardinality & UI Fragmentation**
> Never store highly mutable state strings (`mode`, `sensor_health`, `network_slice`) as InfluxDB **Tags (`.tag()`)**. In time-series database modeling, every unique tag combination spawns a new, isolated database table. If stored as tags, Grafana will split your dashboard into multiple repetitive UI widgets and broken line segments. Always store dynamic states as **Fields (`.field()`)**.

---

## 📜 License & Research Attribution

This engineering architecture is released under the **MIT License**. Engineered for industrial ECE research, advanced edge computing showcases, and autonomous smart building implementations.

```

```
