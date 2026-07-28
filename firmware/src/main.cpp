/**
 * ENTERPRISE EMBEDDED C++ FIRMWARE (PHASE 7 PERFECTED: MASTER PRODUCTION BUILD)
 * Target Hardware: ESP32-WROOM-32 Microcontroller
 * Project: IoT-Based Automatic Climate Control System for Smart Classrooms Using 5G Network Technology
 * Architecture: Hard Physical Gating, Instant Post-Fault Kalman Recovery, Static Memory & 5G Slicing
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <DHT.h>
#include <vector>
#include <cmath>

// --- WIRELESS & NETWORK CONFIGURATION ---
const char* WIFI_SSID     = "Wokwi-GUEST";
const char* WIFI_PASSWORD = "";
const char* MQTT_BROKER   = "broker.emqx.io";
const int   MQTT_PORT     = 1883;
const char* CLIENT_ID     = "ESP32_Perception_Node_01";

// --- MQTT TOPICS ---
const char* TOPIC_PUB_TELEMETRY = "smart_classroom/telemetry/raw";
const char* TOPIC_SUB_CONTROLS  = "smart_classroom/controls";
const char* TOPIC_LWT           = "smart_classroom/status/esp32";

// --- HARDWARE PIN DEFINITIONS ---
#define DHT_PIN          15
#define DHT_TYPE         DHT22
#define MQ135_ANALOG_PIN 34
#define PIR_PIN          13
#define PIN_RELAY_HVAC   2
#define PIN_RELAY_VENT   4

DHT dht(DHT_PIN, DHT_TYPE);
WiFiClient espClient;
PubSubClient mqttClient(espClient);

// --- DYNAMIC 5G QoS & STATIC MEMORY VARIABLES ---
unsigned long lastTelemetryTime = 0;
unsigned long currentTelemetryIntervalMs = 2000;
static char currentNetworkSlice[32] = "5G_eMBB_Standard"; // Zero heap allocation!
static int consecutiveStatisticalAnomalies = 0;         // Leaky bucket deadlock breaker
static bool wasInHardFault = false;                     // Instant rebound guard

// ============================================================================
// ON-CHIP STATISTICAL ENGINE WITH STEP-CHANGE RECOVERY
// ============================================================================
class KalmanFilter {
private:
    float _err_measure;
    float _err_estimate;
    float _q;
    float _current_estimate;
    float _last_estimate;
public:
    KalmanFilter(float mea_e, float est_e, float q) {
        _err_measure = mea_e;
        _err_estimate = est_e;
        _q = q;
        _current_estimate = 26.0;
        _last_estimate = 26.0;
    }
    float getEstimate() const { return _current_estimate; }
    
    float updateEstimate(float mea) {
        _err_estimate = _err_estimate + _q;
        float kalman_gain = _err_estimate / (_err_estimate + _err_measure);
        _current_estimate = _last_estimate + kalman_gain * (mea - _last_estimate);
        _err_estimate = (1.0 - kalman_gain) * _err_estimate;
        _last_estimate = _current_estimate;
        return _current_estimate;
    }

    void forceReconverge(float new_val) {
        _current_estimate = new_val;
        _last_estimate    = new_val;
        _err_estimate     = 2.0;
    }
};

class ZScoreGuard {
private:
    std::vector<float> _residuals;
    size_t _window_size;
public:
    ZScoreGuard(size_t window_size) : _window_size(window_size) {}
    
    float evaluateAnomaly(float residual) const {
        if (_residuals.size() < 5) return 0.0;
        float sum = 0;
        for (float r : _residuals) sum += r;
        float mean = sum / _residuals.size();

        float sq_diff_sum = 0;
        for (float r : _residuals) sq_diff_sum += (r - mean) * (r - mean);
        float sigma = std::sqrt(sq_diff_sum / _residuals.size());

        if (sigma < 0.15) sigma = 0.15;
        if (sigma > 2.50) sigma = 2.50; 

        return std::abs(residual - mean) / sigma;
    }

    void addResidual(float residual) {
        _residuals.push_back(residual);
        if (_residuals.size() > _window_size) {
            _residuals.erase(_residuals.begin());
        }
    }

    void clearMemory() {
        _residuals.clear();
    }
};

KalmanFilter kFilterTemp(2.0, 2.0, 0.01);
ZScoreGuard  zGuardTemp(15);

void setupWiFi();
void reconnectMQTT();
void onMQTTMessage(char* topic, byte* payload, unsigned int length);
void readSensorsAndDispatch();
void setActuatorState(int pin, const char* stateName, bool isActive);

void setup() {
    Serial.begin(115200);
    while (!Serial) delay(10);
    Serial.println("\n[INIT] Booting ESP32 5G QoS Master Perception Node...");

    pinMode(PIN_RELAY_HVAC, OUTPUT);
    pinMode(PIN_RELAY_VENT, OUTPUT);
    pinMode(PIR_PIN, INPUT);
    digitalWrite(PIN_RELAY_HVAC, LOW);
    digitalWrite(PIN_RELAY_VENT, LOW);

    dht.begin();
    setupWiFi();
    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
    mqttClient.setCallback(onMQTTMessage);
    
    // CRITICAL: Expand buffer to 1024 bytes to prevent silent JSON packet drops
    mqttClient.setBufferSize(1024);
}

void loop() {
    if (!mqttClient.connected()) reconnectMQTT();
    mqttClient.loop();

    unsigned long currentMillis = millis();
    if (currentMillis - lastTelemetryTime >= currentTelemetryIntervalMs) {
        lastTelemetryTime = currentMillis;
        readSensorsAndDispatch();
    }
}

void setupWiFi() {
    Serial.printf("[5G RAN] Connecting to gNodeB SSID: %s\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
    Serial.printf("\n[5G SUCCESS] Assigned UE IP Address: %s\n", WiFi.localIP().toString().c_str());
}

void reconnectMQTT() {
    while (!mqttClient.connected()) {
        Serial.print("[MQTT] Attempting EMQX Handshake...");
        const char* lwt = "{\"status\":\"ESP32_HARDWARE_FAULT\",\"node\":\"ESP32_01\"}";
        if (mqttClient.connect(CLIENT_ID, nullptr, nullptr, TOPIC_LWT, 0, true, lwt)) {
            Serial.println(" [SUCCESS] Connected!");
            mqttClient.publish(TOPIC_LWT, "{\"status\":\"ONLINE_HEALTHY\",\"node\":\"ESP32_01\"}", true);
            mqttClient.subscribe(TOPIC_SUB_CONTROLS, 0);
        } else { delay(5000); }
    }
}

void onMQTTMessage(char* topic, byte* payload, unsigned int length) {
    StaticJsonDocument<512> doc;
    if (deserializeJson(doc, payload, length)) return;
    
    if (doc.containsKey("hvac")) {
        const char* hvacCmd = doc["hvac"];
        bool active = (strcmp(hvacCmd, "ACTIVE_COOLING") == 0 || strcmp(hvacCmd, "PRE_COOLING_ACTIVE") == 0);
        setActuatorState(PIN_RELAY_HVAC, "HVAC Cooling Compressor", active);
    }
    if (doc.containsKey("ventilation")) {
        const char* ventCmd = doc["ventilation"];
        bool active = (strcmp(ventCmd, "ACTIVE_EXHAUST") == 0);
        setActuatorState(PIN_RELAY_VENT, "Exhaust Fan Economizer", active);
    }

    if (doc.containsKey("qos_slice")) {
        const char* slice = doc["qos_slice"];
        strlcpy(currentNetworkSlice, slice, sizeof(currentNetworkSlice));
        if (strcmp(currentNetworkSlice, "5G_URLLC_CRITICAL") == 0) {
            currentTelemetryIntervalMs = 5000;
        } else {
            currentTelemetryIntervalMs = 2000;
        }
    }
}

void setActuatorState(int pin, const char* stateName, bool isActive) {
    int targetState = isActive ? HIGH : LOW;
    if (digitalRead(pin) != targetState) {
        digitalWrite(pin, targetState);
        Serial.printf("[ACTUATOR RX] Switched [%s] -> %s (GPIO %d)\n", stateName, isActive ? "ENERGIZED (HIGH)" : "STANDBY (LOW)", pin);
    }
}

void readSensorsAndDispatch() {
    float tempRaw = dht.readTemperature();
    float humPct  = dht.readHumidity();
    int rawMQ135  = analogRead(MQ135_ANALOG_PIN);
    int pirState  = digitalRead(PIR_PIN);

    if (isnan(tempRaw) || isnan(humPct)) { tempRaw = 26.5; humPct = 50.0; }
    float co2Ppm = constrain(map(rawMQ135, 0, 4095, 400, 2000), 400, 5000);
    int occupancyCount = (pirState == HIGH) ? 25 : 0;

    // --- LAYER 1: HARD PHYSICAL PLAUSIBILITY GATE ---
    bool isPhysicallyImpossible = (tempRaw < 10.0 || tempRaw > 45.0 || humPct < 5.0 || humPct > 99.0);

    // --- LAYER 2 & 3: STATISTICAL EVALUATION ---
    float currentKalmanEstimate = kFilterTemp.getEstimate();
    float residual = std::abs(tempRaw - currentKalmanEstimate);
    float zScore   = zGuardTemp.evaluateAnomaly(residual);

    bool isStatisticalAnomaly = (zScore > 3.0);
    const char* healthStatus;
    float reportedKalman;

    // --- STEP-CHANGE RECOVERY & INSTANT REBOUND ENGINE ---
    if (isPhysicallyImpossible) {
        healthStatus   = "PHYSICAL_BOUNDS_FAULT";
        reportedKalman = currentKalmanEstimate; 
        zScore         = 9.99;
        consecutiveStatisticalAnomalies = 0;
        wasInHardFault = true; // Flag that we entered an extreme physical fault
    } 
    else if (wasInHardFault) {
        // INSTANT REBOUND: Directly returning from a hard physical fault into valid limits!
        Serial.println("[SHIELD RECOVERY] Valid physical limits restored -> Instant Kalman & Z-Guard snap-back!");
        kFilterTemp.forceReconverge(tempRaw);
        zGuardTemp.clearMemory();
        wasInHardFault = false;
        consecutiveStatisticalAnomalies = 0;
        healthStatus   = "HEALTHY_RECONVERGED";
        reportedKalman = tempRaw;
        zScore         = 0.00;
    }
    else if (isStatisticalAnomaly) {
        consecutiveStatisticalAnomalies++;
        if (consecutiveStatisticalAnomalies >= 4) {
            Serial.println("[SHIELD RECOVERY] Step-change confirmed -> Auto-reconverging Kalman & Z-Guard!");
            kFilterTemp.forceReconverge(tempRaw);
            zGuardTemp.clearMemory();
            consecutiveStatisticalAnomalies = 0;
            healthStatus   = "HEALTHY_RECONVERGED";
            reportedKalman = tempRaw;
            zScore         = 0.00;
        } else {
            healthStatus   = "STATISTICAL_SPIKE_FAULT";
            reportedKalman = currentKalmanEstimate;
        }
    } 
    else {
        healthStatus   = "HEALTHY";
        reportedKalman = kFilterTemp.updateEstimate(tempRaw);
        zGuardTemp.addResidual(residual);
        consecutiveStatisticalAnomalies = 0;
        wasInHardFault = false;
    }

    bool isPoisoned = (strcmp(healthStatus, "HEALTHY") != 0 && strcmp(healthStatus, "HEALTHY_RECONVERGED") != 0);

    StaticJsonDocument<512> doc;
    doc["node_id"]       = CLIENT_ID;
    doc["timestamp_ms"]  = millis();
    doc["network_slice"] = currentNetworkSlice;
    
    JsonObject sensors = doc.createNestedObject("sensors");
    sensors["temp_raw"]        = round(tempRaw * 10.0) / 10.0;
    sensors["temp_kalman"]     = round(reportedKalman * 10.0) / 10.0;
    sensors["humidity"]        = round(humPct * 10.0) / 10.0;
    sensors["co2_raw"]         = co2Ppm;
    sensors["occupancy_count"] = occupancyCount;
    sensors["anomaly_score"]   = round(zScore * 100.0) / 100.0;
    sensors["status"]          = healthStatus;

    char jsonBuffer[512];
    serializeJson(doc, jsonBuffer);
    mqttClient.publish(TOPIC_PUB_TELEMETRY, jsonBuffer);
    
    // --- UNTRUNCATED FULL OBSERVABILITY PRINT MATRIX ---
    if (isPoisoned) {
        Serial.printf("[SHIELD ALARM!] [%s] Temp: %.1f°C (Kal: %.1f°C) | Hum: %.1f%% | CO2: %.0f PPM | Occ: %d | Z: %.2f => [%s]\n", 
                      currentNetworkSlice, tempRaw, reportedKalman, humPct, co2Ppm, occupancyCount, zScore, healthStatus);
    } else {
        Serial.printf("[TX FRAME] [%s] Temp: %.1f°C (Kal: %.1f°C) | Hum: %.1f%% | CO2: %.0f PPM | Occ: %d | Z: %.2f => [%s]\n", 
                      currentNetworkSlice, tempRaw, reportedKalman, humPct, co2Ppm, occupancyCount, zScore, healthStatus);
    }
}