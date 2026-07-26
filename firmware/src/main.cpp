/**
 * ENTERPRISE EMBEDDED C++ FIRMWARE (PHASE 6.3: FULL OBSERVABILITY MATRIX)
 * Target Hardware: ESP32-WROOM-32 Microcontroller
 * Project: IoT-Based Automatic Climate Control System for Smart Classrooms Using 5G Network Technology
 * Architecture: Hard Physical Gating, Quarantined Kalman Filtering & Full Telemetry Logging
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

unsigned long lastTelemetryTime = 0;
const unsigned long TELEMETRY_INTERVAL_MS = 2000;

// ============================================================================
// LAYER 2 & 3: QUARANTINED KALMAN FILTER & CLAMPED Z-SCORE GUARD
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
    Serial.println("\n[INIT] Booting ESP32 Full Observability Matrix...");

    pinMode(PIN_RELAY_HVAC, OUTPUT);
    pinMode(PIN_RELAY_VENT, OUTPUT);
    pinMode(PIR_PIN, INPUT);
    digitalWrite(PIN_RELAY_HVAC, LOW);
    digitalWrite(PIN_RELAY_VENT, LOW);

    dht.begin();
    setupWiFi();
    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
    mqttClient.setCallback(onMQTTMessage);
}

void loop() {
    if (!mqttClient.connected()) reconnectMQTT();
    mqttClient.loop();

    unsigned long currentMillis = millis();
    if (currentMillis - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
        lastTelemetryTime = currentMillis;
        readSensorsAndDispatch();
    }
}

void setupWiFi() {
    Serial.printf("[WIFI] Connecting to SSID: %s\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
    while (WiFi.status() != WL_CONNECTED) { delay(500); Serial.print("."); }
    Serial.printf("\n[WIFI SUCCESS] Assigned IP Address: %s\n", WiFi.localIP().toString().c_str());
}

void reconnectMQTT() {
    while (!mqttClient.connected()) {
        Serial.print("[MQTT] Attempting EMQX Handshake...");
        const char* lwt = "{\"status\":\"ESP32_HARDWARE_FAULT\",\"node\":\"ESP32_01\"}";
        if (mqttClient.connect(CLIENT_ID, nullptr, nullptr, TOPIC_LWT, 1, true, lwt)) {
            Serial.println(" [SUCCESS] Connected!");
            mqttClient.publish(TOPIC_LWT, "{\"status\":\"ONLINE_HEALTHY\",\"node\":\"ESP32_01\"}", true);
            mqttClient.subscribe(TOPIC_SUB_CONTROLS, 1);
        } else { delay(5000); }
    }
}

void onMQTTMessage(char* topic, byte* payload, unsigned int length) {
    StaticJsonDocument<256> doc;
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
}

void setActuatorState(int pin, const char* stateName, bool isActive) {
    digitalWrite(pin, isActive ? HIGH : LOW);
    Serial.printf("[ACTUATOR RX] Switched [%s] -> %s (GPIO %d)\n", stateName, isActive ? "ENERGIZED (HIGH)" : "STANDBY (LOW)", pin);
}

void readSensorsAndDispatch() {
    float tempRaw = dht.readTemperature();
    float humPct  = dht.readHumidity();
    int rawMQ135  = analogRead(MQ135_ANALOG_PIN);
    int pirState  = digitalRead(PIR_PIN);

    if (isnan(tempRaw) || isnan(humPct)) { tempRaw = 26.5; humPct = 50.0; }
    float co2Ppm = map(rawMQ135, 0, 4095, 400, 2000);
    int occupancyCount = (pirState == HIGH) ? 25 : 0;

    // --- LAYER 1: HARD PHYSICAL PLAUSIBILITY GATE ---
    bool isPhysicallyImpossible = (tempRaw < 10.0 || tempRaw > 45.0 || humPct < 5.0 || humPct > 99.0);

    // --- LAYER 2 & 3: STATISTICAL EVALUATION ---
    float currentKalmanEstimate = kFilterTemp.getEstimate();
    float residual = std::abs(tempRaw - currentKalmanEstimate);
    float zScore   = zGuardTemp.evaluateAnomaly(residual);

    bool isStatisticalAnomaly = (zScore > 3.0);
    bool isPoisoned = (isPhysicallyImpossible || isStatisticalAnomaly);

    const char* healthStatus;
    float reportedKalman;

    if (isPoisoned) {
        healthStatus   = isPhysicallyImpossible ? "PHYSICAL_BOUNDS_FAULT" : "STATISTICAL_SPIKE_FAULT";
        reportedKalman = currentKalmanEstimate; 
        if (isPhysicallyImpossible) zScore = 9.99; 
    } else {
        healthStatus   = "HEALTHY";
        reportedKalman = kFilterTemp.updateEstimate(tempRaw);
        zGuardTemp.addResidual(residual);
    }

    StaticJsonDocument<512> doc;
    doc["node_id"] = CLIENT_ID;
    doc["timestamp_ms"] = millis();
    
    JsonObject sensors = doc.createNestedObject("sensors");
    sensors["temp_raw"]    = round(tempRaw * 10.0) / 10.0;
    sensors["temp_kalman"] = round(reportedKalman * 10.0) / 10.0;
    sensors["humidity"]    = round(humPct * 10.0) / 10.0;
    sensors["co2_raw"]     = co2Ppm;
    sensors["occupancy_count"] = occupancyCount;
    sensors["anomaly_score"]   = round(zScore * 100.0) / 100.0;
    sensors["status"]          = healthStatus;

    char jsonBuffer[512];
    serializeJson(doc, jsonBuffer);
    mqttClient.publish(TOPIC_PUB_TELEMETRY, jsonBuffer);
    
    // --- FULL MATRIX VISUAL OBSERVABILITY PRINT ---
    if (isPoisoned) {
        Serial.printf("[SHIELD ALARM!] Temp: %.1f°C (Kal: %.1f°C) | Hum: %.1f%% | CO2: %.0f PPM | Occ: %d | Z: %.2f => [%s]\n", 
                      tempRaw, reportedKalman, humPct, co2Ppm, occupancyCount, zScore, healthStatus);
    } else {
        Serial.printf("[TX FRAME] Temp: %.1f°C (Kal: %.1f°C) | Hum: %.1f%% | CO2: %.0f PPM | Occ: %d | Z: %.2f => [%s]\n", 
                      tempRaw, reportedKalman, humPct, co2Ppm, occupancyCount, zScore, healthStatus);
    }
}