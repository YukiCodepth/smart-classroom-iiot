/**
 * ENTERPRISE EMBEDDED C++ FIRMWARE
 * Target Hardware: ESP32-WROOM-32 Microcontroller
 * Project: IoT-Based Automatic Climate Control System for Smart Classrooms Using 5G Network Technology
 * Architecture: Hardware-in-the-Loop (HiTL) Perception Layer & Actuator Controller
 */

#include <Arduino.h>
#include <WiFi.h>
#include <PubSubClient.h>
#include <ArduinoJson.h>
#include <DHT.h>

// --- WIRELESS & NETWORK CONFIGURATION ---
const char* WIFI_SSID     = "Wokwi-GUEST";      // Wokwi Virtual 5G/Wi-Fi Access Point
const char* WIFI_PASSWORD = "";                 // Open network in simulation
const char* MQTT_BROKER   = "host.docker.internal"; // Points to our local EMQX Docker broker
const int   MQTT_PORT     = 1883;
const char* CLIENT_ID     = "ESP32_Perception_Node_01";

// --- MQTT TOPICS ---
const char* TOPIC_PUB_TELEMETRY = "smart_classroom/telemetry/raw";
const char* TOPIC_SUB_CONTROLS  = "smart_classroom/controls";
const char* TOPIC_LWT           = "smart_classroom/status/esp32";

// --- HARDWARE PIN DEFINITIONS ---
#define DHT_PIN         15  // Digital Pin for DHT22 Temp/Humidity Sensor
#define DHT_TYPE        DHT22
#define MQ135_ANALOG_PIN 34 // Analog ADC Pin for CO2 Gas Sensor
#define PIR_PIN         13  // Digital Pin for PIR Occupancy Sensor
#define PIN_RELAY_HVAC  2   // Digital Output: AC Cooling Motor / Compressor
#define PIN_RELAY_VENT  4   // Digital Output: Exhaust Fan / Economizer

// --- GLOBAL INSTANCES & TIMERS ---
DHT dht(DHT_PIN, DHT_TYPE);
WiFiClient espClient;
PubSubClient mqttClient(espClient);

unsigned long lastTelemetryTime = 0;
const unsigned long TELEMETRY_INTERVAL_MS = 2000; // 2Hz Telemetry Rate

// --- FUNCTION DECLARATIONS ---
void setupWiFi();
void reconnectMQTT();
void onMQTTMessage(char* topic, byte* payload, unsigned int length);
void readSensorsAndDispatch();
void setActuatorState(int pin, const char* stateName, bool isActive);

void setup() {
    Serial.begin(115200);
    while (!Serial) delay(10);
    Serial.println("\n[INIT] Booting ESP32 Smart Classroom Perception Node...");

    // Configure GPIO Actuator & Sensor Pins
    pinMode(PIN_RELAY_HVAC, OUTPUT);
    pinMode(PIN_RELAY_VENT, OUTPUT);
    pinMode(PIR_PIN, INPUT);
    
    // Default Actuators to SAFE OFF State
    digitalWrite(PIN_RELAY_HVAC, LOW);
    digitalWrite(PIN_RELAY_VENT, LOW);

    // Initialize DHT Sensor
    dht.begin();

    // Establish Network & Broker Links
    setupWiFi();
    mqttClient.setServer(MQTT_BROKER, MQTT_PORT);
    mqttClient.setCallback(onMQTTMessage);
}

void loop() {
    if (!mqttClient.connected()) {
        reconnectMQTT();
    }
    mqttClient.loop();

    // Non-Blocking Asynchronous Telemetry Dispatch
    unsigned long currentMillis = millis();
    if (currentMillis - lastTelemetryTime >= TELEMETRY_INTERVAL_MS) {
        lastTelemetryTime = currentMillis;
        readSensorsAndDispatch();
    }
}

// --- NETWORK CONNECTIVITY FUNCTIONS ---
void setupWiFi() {
    Serial.printf("[WIFI] Connecting to 5G RAN / Wi-Fi SSID: %s\n", WIFI_SSID);
    WiFi.mode(WIFI_STA);
    WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        Serial.print(".");
        attempts++;
    }
    
    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\n[WIFI SUCCESS] Assigned IP Address: %s\n", WiFi.localIP().toString().c_str());
    } else {
        Serial.println("\n[WIFI FAULT] Radio connection failed. Retrying in background...");
    }
}

void reconnectMQTT() {
    while (!mqttClient.connected()) {
        Serial.print("[MQTT] Attempting EMQX Broker Handshake...");
        
        // Define LWT Payload for Hardware Fault Monitoring
        const char* lwtPayload = "{\"status\":\"ESP32_HARDWARE_FAULT\",\"node\":\"ESP32_01\"}";
        
        if (mqttClient.connect(CLIENT_ID, nullptr, nullptr, TOPIC_LWT, 1, true, lwtPayload)) {
            Serial.println(" [SUCCESS] Connected to Broker!");
            // Publish Online Status Heartbeat
            mqttClient.publish(TOPIC_LWT, "{\"status\":\"ESP32_ONLINE_HEALTHY\",\"node\":\"ESP32_01\"}", true);
            // Subscribe to Actuator Command Topic
            mqttClient.subscribe(TOPIC_SUB_CONTROLS, 1);
        } else {
            Serial.printf(" [FAILED] rc=%d. Retrying in 5 seconds...\n", mqttClient.state());
            delay(5000); // Blocking delay acceptable only during initial network recovery
        }
    }
}

// --- CLOSED-LOOP ACTUATOR CONTROL RECEIVER ---
void onMQTTMessage(char* topic, byte* payload, unsigned int length) {
    Serial.printf("[MQTT RX] Command packet received on topic: %s\n", topic);
    
    StaticJsonDocument<256> doc;
    DeserializationError error = deserializeJson(doc, payload, length);
    
    if (error) {
        Serial.printf("[JSON FAULT] Malformed payload. Error: %s\n", error.c_str());
        return;
    }

    // Process HVAC Actuator Commands
    if (doc.containsKey("hvac")) {
        const char* hvacCmd = doc["hvac"];
        bool active = (strcmp(hvacCmd, "ACTIVE_COOLING") == 0 || strcmp(hvacCmd, "ON") == 0);
        setActuatorState(PIN_RELAY_HVAC, "HVAC Cooling Compressor", active);
    }

    // Process Exhaust Ventilation Actuator Commands
    if (doc.containsKey("ventilation")) {
        const char* ventCmd = doc["ventilation"];
        bool active = (strcmp(ventCmd, "ACTIVE_EXHAUST") == 0 || strcmp(ventCmd, "ON") == 0);
        setActuatorState(PIN_RELAY_VENT, "Exhaust Fan Economizer", active);
    }
}

void setActuatorState(int pin, const char* stateName, bool isActive) {
    digitalWrite(pin, isActive ? HIGH : LOW);
    Serial.printf("[ACTUATOR] Switched [%s] -> %s (GPIO %d)\n", stateName, isActive ? "ENERGIZED (HIGH)" : "STANDBY (LOW)", pin);
}

// --- PERCEPTION LAYER ACQUISITION & SERIALIZATION ---
void readSensorsAndDispatch() {
    // 1. Acquire Physical / Simulated Hardware Sensor Voltages
    float tempC = dht.readTemperature();
    float humPct = dht.readHumidity();
    int rawMQ135 = analogRead(MQ135_ANALOG_PIN);
    int pirState = digitalRead(PIR_PIN);

    // Fault Detection: Verify Sensor Integrity
    if (isnan(tempC) || isnan(humPct)) {
        Serial.println("[HARDWARE FAULT] DHT22 Sensor Read Failure. Check wiring pull-up resistors!");
        tempC = 26.5; // Fallback to fail-safe default during transient glitch
        humPct = 55.0;
    }

    // Convert ADC Voltage (0-4095 on ESP32) to CO2 PPM Approximation (400-2000 PPM Range)
    float co2Ppm = map(rawMQ135, 0, 4095, 400, 2000);
    
    // Simulate Occupancy Count from digital PIR motion triggers
    int occupancyCount = (pirState == HIGH) ? 25 : 0;

    // 2. Serialize Data into JSON Packet using ArduinoJson
    StaticJsonDocument<512> doc;
    doc["node_id"] = CLIENT_ID;
    doc["timestamp_ms"] = millis();
    
    JsonObject sensors = doc.createNestedObject("sensors");
    sensors["temp_raw"] = round(tempC * 10.0) / 10.0;
    sensors["humidity"] = round(humPct * 10.0) / 10.0;
    sensors["co2_raw"]  = co2Ppm;
    sensors["occupancy_count"] = occupancyCount;

    char jsonBuffer[512];
    serializeJson(doc, jsonBuffer);

    // 3. Dispatch over MQTT to Edge Processing Layer
    bool success = mqttClient.publish(TOPIC_PUB_TELEMETRY, jsonBuffer);
    
    if (success) {
        Serial.printf("[TX FRAME] Temp: %.1f°C | Hum: %.1f%% | CO2: %.0f PPM | Occ: %d => [PUBLISHED]\n", 
                      tempC, humPct, co2Ppm, occupancyCount);
    } else {
        Serial.println("[TX FAULT] MQTT Buffer Overflow or Radio Link Dropped!");
    }
}
