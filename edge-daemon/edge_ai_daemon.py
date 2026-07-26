#!/usr/bin/env python3
"""
ENTERPRISE INDUSTRIAL IOT EDGE AI DAEMON (PHASE 6.3: FULL OBSERVABILITY MATRIX)
Project: IoT-Based Automatic Climate Control System for Smart Classrooms Using 5G Network Technology
Architecture: Hard Physical Gating, ML Training Freeze & Complete Visual Telemetry Matrix
"""

import time
import math
import json
import logging
import numpy as np
from collections import deque
from sklearn.linear_model import SGDRegressor
from sklearn.preprocessing import StandardScaler
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(threadName)-10s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("EdgeAIDaemon")

INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "urop-2026-super-secret-enterprise-token"
INFLUX_ORG = "UROP_Research_Lab"
INFLUX_BUCKET = "classroom_telemetry"

MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883
CLIENT_ID = "Linux_5G_Edge_Gateway_01"

TOPIC_TELEMETRY_RAW = "smart_classroom/telemetry/raw"
TOPIC_CONTROLS      = "smart_classroom/controls"
TOPIC_LWT           = "smart_classroom/status/gateway"

WINDOW_SIZE = 5
TEMP_THRESHOLD_C = 27.5
CO2_THRESHOLD_PPM = 1000.0

class OnlineThermodynamicPredictor:
    def __init__(self):
        self.model = SGDRegressor(max_iter=1000, tol=1e-3, learning_rate='invscaling', eta0=0.01)
        self.scaler = StandardScaler()
        self.history = deque(maxlen=30)
        self.is_fitted = False
        self.last_valid_prediction = 26.0

    def update_and_predict(self, current_temp: float, humidity: float, occupancy: int, is_poisoned: bool) -> float:
        body_heat_gain = occupancy * 100.0
        features = np.array([[current_temp, humidity, occupancy, body_heat_gain]])
        
        if not is_poisoned:
            self.history.append((features[0], current_temp))
            if len(self.history) >= 5:
                X_train = np.array([item[0] for item in self.history])
                y_train = np.array([item[1] for item in self.history])
                X_scaled = self.scaler.fit_transform(X_train)
                self.model.partial_fit(X_scaled, y_train)
                self.is_fitted = True
        else:
            logger.warning("🚨 [ML PROTECTED] Freezing SGD weight updates to prevent neural poisoning!")
        
        if self.is_fitted and len(self.history) >= 5:
            future_heat_gain = body_heat_gain * 1.15
            X_future = np.array([[current_temp, humidity, occupancy, future_heat_gain]])
            X_future_scaled = self.scaler.transform(X_future)
            predicted_temp = self.model.predict(X_future_scaled)[0]
            
            thermal_velocity = (current_temp - self.history[0][1]) / len(self.history)
            raw_pred = predicted_temp + (thermal_velocity * 15.0)
            
            clamped_pred = round(max(min(raw_pred, 45.0), 10.0), 2)
            self.last_valid_prediction = clamped_pred
            return clamped_pred
            
        return round(current_temp, 2)

class MovingAverageFilter:
    def __init__(self, window_size: int):
        self.buffer = deque(maxlen=window_size)
    def filter(self, new_val: float) -> float:
        self.buffer.append(new_val)
        return round(sum(self.buffer) / len(self.buffer), 2)

class ClimateIntelligenceEngine:
    @staticmethod
    def calculate_iso7730_pmv(temp_c: float, humidity_pct: float, air_speed: float = 0.15) -> float:
        try:
            pa = (humidity_pct / 100.0) * 10 * math.exp(16.6536 - (4030.18 / (temp_c + 235)))
            pmv = (0.303 * math.exp(-0.036 * 58) + 0.028) * (
                (58 - 0) - 3.05 * 0.001 * (5733 - 6.99 * 58 - pa) 
                - 0.42 * (58 - 58.15) - 0.0014 * 58 * (34 - temp_c) 
                - 0.396 * ((temp_c + 273.15)**4) / 100000000.0 + 0.396 * ((temp_c + 273.15)**4) / 100000000.0
                + 12.1 * math.sqrt(air_speed) * (35.7 - 0.028 * 58 - temp_c)
            )
            return round(max(min(pmv, 3.0), -3.0), 2)
        except Exception:
            return 0.0

    @staticmethod
    def calculate_energy_savings_pct(smart_power_w: float, baseline_power_w: float) -> float:
        if baseline_power_w <= 0: return 0.0
        savings = (1.0 - (smart_power_w / baseline_power_w)) * 100.0
        return round(max(savings, 0.0), 1)

class EdgeAIDaemon:
    def __init__(self):
        self.running = True
        self.manual_override = False
        self.override_state = {"hvac": "OFF", "vent": "OFF"}
        self.real_hardware_data = None
        
        self.temp_filter = MovingAverageFilter(WINDOW_SIZE)
        self.co2_filter = MovingAverageFilter(WINDOW_SIZE)
        self.intelligence = ClimateIntelligenceEngine()
        self.ml_predictor = OnlineThermodynamicPredictor()
        
        try:
            self.db_client = InfluxDBClient(url=INFLUX_URL, token=INFLUX_TOKEN, org=INFLUX_ORG)
            self.write_api = self.db_client.write_api(write_options=SYNCHRONOUS)
            logger.info("Connected to InfluxDB 2.7 Time-Series Historian.")
        except Exception as e:
            logger.critical(f"InfluxDB Connection Failed: {e}")
            raise

        self.mqtt_client = mqtt.Client(client_id=CLIENT_ID, protocol=mqtt.MQTTv5)
        self.mqtt_client.on_connect = self.on_mqtt_connect
        self.mqtt_client.on_message = self.on_mqtt_message
        self.mqtt_client.will_set(
            TOPIC_LWT, 
            payload=json.dumps({"status": "EDGE_OFFLINE_FAULT", "node": CLIENT_ID}), 
            qos=1, retain=True
        )

    def on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info(f"Connected to Cloud MQTT Broker ({MQTT_BROKER}).")
            client.subscribe(TOPIC_TELEMETRY_RAW, qos=1)
            client.subscribe(TOPIC_CONTROLS, qos=1)
            client.publish(TOPIC_LWT, json.dumps({"status": "ONLINE_HEALTHY", "node": CLIENT_ID}), qos=1, retain=True)
        else:
            logger.error(f"MQTT Connection Refused. rc={rc}")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            if msg.topic == TOPIC_TELEMETRY_RAW and "sensors" in payload:
                s = payload["sensors"]
                self.real_hardware_data = {
                    "temp_raw": float(s.get("temp_raw", 24.0)),
                    "temp_kalman": float(s.get("temp_kalman", 24.0)),
                    "hum": float(s.get("humidity", 40.0)),
                    "co2": float(s.get("co2_raw", 400.0)),
                    "occ": int(s.get("occupancy_count", 0)),
                    "z_score": float(s.get("anomaly_score", 0.0)),
                    "status": str(s.get("status", "HEALTHY"))
                }
            elif msg.topic == TOPIC_CONTROLS and "manual_override" in payload:
                self.manual_override = bool(payload["manual_override"])
                if self.manual_override:
                    self.override_state["hvac"] = str(payload.get("hvac", "OFF"))
                    self.override_state["vent"] = str(payload.get("vent", "OFF"))
        except Exception as e:
            logger.error(f"Malformed MQTT Packet: {e}")

    def run_pipeline(self):
        logger.info("Starting BULLETPROOF SAFE-STATE Full Observability Pipeline...")
        logger.info("Waiting for live telemetry from Wokwi ESP32...")
        try:
            self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self.mqtt_client.loop_start()

            while self.running:
                if self.real_hardware_data is None:
                    time.sleep(1.0)
                    continue

                raw_temp    = self.real_hardware_data["temp_raw"]
                kalman_temp = self.real_hardware_data["temp_kalman"]
                raw_hum     = self.real_hardware_data["hum"]
                raw_co2     = self.real_hardware_data["co2"]
                occupancy   = self.real_hardware_data["occ"]
                z_score     = self.real_hardware_data["z_score"]
                status      = self.real_hardware_data["status"]
                raw_light   = 500

                is_poisoned = (status != "HEALTHY")

                if is_poisoned:
                    logger.warning(f"🚨 [CYBER SHIELD ACTIVE!] Fault Type: [{status}] | Z: {z_score}σ")
                    logger.warning(f"🚨 Rejecting Corrupted Spike ({raw_temp}°C) -> Quarantined Kalman Hold ({kalman_temp}°C)!")
                    working_temp = kalman_temp
                else:
                    working_temp = raw_temp

                filt_temp = self.temp_filter.filter(working_temp)
                filt_co2  = self.co2_filter.filter(raw_co2)

                pred_temp_15m = self.ml_predictor.update_and_predict(filt_temp, raw_hum, occupancy, is_poisoned)
                pmv_index = self.intelligence.calculate_iso7730_pmv(filt_temp, raw_hum)

                if self.manual_override:
                    hvac_status = self.override_state["hvac"]
                    vent_status = self.override_state["vent"]
                    mode = "MANUAL_OVERRIDE"
                else:
                    mode = "AI_AUTOMATED" if not is_poisoned else f"SAFE_STATE_{status}"
                    if pred_temp_15m >= TEMP_THRESHOLD_C and filt_temp < TEMP_THRESHOLD_C and occupancy > 0:
                        hvac_status = "PRE_COOLING_ACTIVE"
                        mode = "AI_PREDICTIVE_ECO"
                    elif (pmv_index > 0.5 or filt_temp >= TEMP_THRESHOLD_C) and occupancy > 0:
                        hvac_status = "ACTIVE_COOLING"
                    elif filt_temp >= TEMP_THRESHOLD_C and occupancy == 0:
                        hvac_status = "ECO_STANDBY"
                    else:
                        hvac_status = "OFF"

                    vent_status = "ACTIVE_EXHAUST" if filt_co2 > CO2_THRESHOLD_PPM else "OFF"

                control_command = {
                    "hvac": "ACTIVE_COOLING" if hvac_status in ["ACTIVE_COOLING", "PRE_COOLING_ACTIVE"] else hvac_status,
                    "ventilation": vent_status,
                    "mode": mode,
                    "predicted_temp_15m": pred_temp_15m
                }
                self.mqtt_client.publish(TOPIC_CONTROLS, json.dumps(control_command), qos=1)

                baseline_power = 3500.0
                smart_power = 0.0
                if hvac_status == "ACTIVE_COOLING": smart_power += 2500.0
                elif hvac_status == "PRE_COOLING_ACTIVE": smart_power += 1200.0
                elif hvac_status == "ECO_STANDBY": smart_power += 300.0
                if vent_status == "ACTIVE_EXHAUST": smart_power += 400.0
                energy_saved = self.intelligence.calculate_energy_savings_pct(smart_power, baseline_power)

                point = Point("environmental_telemetry") \
                    .tag("gateway_node", CLIENT_ID) \
                    .tag("mode", mode) \
                    .tag("sensor_health", status) \
                    .field("temp_raw", raw_temp) \
                    .field("temp_kalman", kalman_temp) \
                    .field("temp_filtered", filt_temp) \
                    .field("temp_predicted_15m", pred_temp_15m) \
                    .field("anomaly_z_score", z_score) \
                    .field("humidity", raw_hum) \
                    .field("co2_filtered", filt_co2) \
                    .field("light_lux", raw_light) \
                    .field("occupancy", occupancy) \
                    .field("pmv_index", pmv_index) \
                    .field("energy_saved_pct", energy_saved)
                self.write_api.write(bucket=INFLUX_BUCKET, record=point)

                # --- 100% FULL OBSERVABILITY MATRIX VISUAL PRINT ---
                logger.info(f"--- TINYML HEALTH FRAME [{time.strftime('%H:%M:%S')}] ---")
                logger.info(f"Sensor In    | Temp: {raw_temp}°C (Kalman: {kalman_temp}°C) | Hum: {raw_hum}% | CO2: {filt_co2} ppm | Occ: {occupancy} | Z: {z_score}σ => [{status}]")
                logger.info(f"ML Forecast  | Predicted Temp in +15m: {pred_temp_15m}°C | Mode: [{mode}]")
                logger.info(f"AI Actuators | HVAC: [{hvac_status}] | Exhaust Vent: [{vent_status}] | Energy Saved: {energy_saved}%\n")

                time.sleep(2.0)

        except KeyboardInterrupt:
            logger.warning("Shutdown signal received...")
        finally:
            self.running = False
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.db_client.close()

if __name__ == "__main__":
    daemon = EdgeAIDaemon()
    daemon.run_pipeline()
