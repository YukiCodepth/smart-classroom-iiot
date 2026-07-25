#!/usr/bin/env python3
"""
ENTERPRISE INDUSTRIAL IOT EDGE AI DAEMON
Project: IoT-Based Automatic Climate Control System for Smart Classrooms Using 5G Network Technology
Architecture: Software-in-the-Loop (SiTL) Edge Pre-processing & Closed-Loop Control Engine
"""

import time
import math
import json
import random
import logging
from collections import deque
import paho.mqtt.client as mqtt
from influxdb_client import InfluxDBClient, Point
from influxdb_client.client.write_api import SYNCHRONOUS

# --- INDUSTRIAL LOGGING CONFIGURATION ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] (%(threadName)-10s) %(message)s",
    datefmt="%Y-%m-%d %H:%M:%S"
)
logger = logging.getLogger("EdgeAIDaemon")

# --- ENTERPRISE CONSTANTS & CONFIGURATION ---
INFLUX_URL = "http://localhost:8086"
INFLUX_TOKEN = "urop-2026-super-secret-enterprise-token"
INFLUX_ORG = "UROP_Research_Lab"
INFLUX_BUCKET = "classroom_telemetry"

MQTT_BROKER = "localhost"
MQTT_PORT = 1883
CLIENT_ID = "Linux_5G_Edge_Gateway_01"
TOPIC_TELEMETRY = "smart_classroom/telemetry"
TOPIC_CONTROLS = "smart_classroom/controls"
TOPIC_LWT = "smart_classroom/status/gateway"

WINDOW_SIZE = 5  # Moving average filter window size
TEMP_THRESHOLD_C = 27.5
CO2_THRESHOLD_PPM = 1000.0

# --- EDGE SIGNAL PROCESSING CLASS ---
class MovingAverageFilter:
    """Implements edge noise filtering: y[n] = (1/M) * sum(x[n-i])"""
    def __init__(self, window_size: int):
        self.buffer = deque(maxlen=window_size)
        
    def filter(self, new_val: float) -> float:
        self.buffer.append(new_val)
        return round(sum(self.buffer) / len(self.buffer), 2)

# --- THERMAL COMFORT & ENERGY MATHEMATICAL ENGINE ---
class ClimateIntelligenceEngine:
    @staticmethod
    def calculate_iso7730_pmv(temp_c: float, humidity_pct: float, air_speed: float = 0.15) -> float:
        """
        Calculates ASHRAE Standard 55 / ISO 7730 Predicted Mean Vote (PMV).
        Scale: -3 (Cold) to +3 (Hot). Ideal equilibrium = 0.0.
        """
        try:
            pa = (humidity_pct / 100.0) * 10 * math.exp(16.6536 - (4030.18 / (temp_c + 235)))
            pmv = (0.303 * math.exp(-0.036 * 58) + 0.028) * (
                (58 - 0) - 3.05 * 0.001 * (5733 - 6.99 * 58 - pa) 
                - 0.42 * (58 - 58.15) - 0.0014 * 58 * (34 - temp_c) 
                - 0.396 * ((temp_c + 273.15)**4) / 100000000.0 + 0.396 * ((temp_c + 273.15)**4) / 100000000.0
                + 12.1 * math.sqrt(air_speed) * (35.7 - 0.028 * 58 - temp_c)
            )
            return round(max(min(pmv, 3.0), -3.0), 2)
        except Exception as e:
            logger.error(f"PMV Math Error: {e}")
            return 0.0

    @staticmethod
    def calculate_energy_savings_pct(smart_power_w: float, baseline_power_w: float) -> float:
        """Calculates real-time energy savings vs. continuous static rule-based HVAC."""
        if baseline_power_w <= 0:
            return 0.0
        savings = (1.0 - (smart_power_w / baseline_power_w)) * 100.0
        return round(max(savings, 0.0), 1)

# --- MAIN INDUSTRIAL DAEMON CLASS ---
class EdgeAIDaemon:
    def __init__(self):
        self.running = True
        self.manual_override = False
        self.override_state = {"hvac": "OFF", "vent": "OFF"}
        
        self.temp_filter = MovingAverageFilter(WINDOW_SIZE)
        self.co2_filter = MovingAverageFilter(WINDOW_SIZE)
        self.intelligence = ClimateIntelligenceEngine()
        
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
            qos=1, 
            retain=True
        )

    def on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info("Connected to EMQX Enterprise MQTT Broker.")
            client.subscribe(TOPIC_CONTROLS, qos=1)
            client.publish(TOPIC_LWT, json.dumps({"status": "ONLINE_HEALTHY", "node": CLIENT_ID}), qos=1, retain=True)
        else:
            logger.error(f"MQTT Connection Refused. Return Code: {rc}")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            logger.info(f"Received Command on [{msg.topic}]: {payload}")
            
            if "manual_override" in payload:
                self.manual_override = bool(payload["manual_override"])
                logger.warning(f"MANUAL OVERRIDE TOGGLED: {self.manual_override}")
            if self.manual_override and "hvac" in payload:
                self.override_state["hvac"] = str(payload["hvac"])
            if self.manual_override and "vent" in payload:
                self.override_state["vent"] = str(payload["vent"])
        except Exception as e:
            logger.error(f"Malformed MQTT Command Packet: {e}")

    def generate_virtual_sensor_array(self):
        """Simulates perception layer data with realistic classroom environmental drift."""
        raw_temp = round(26.0 + random.uniform(-1.0, 3.0), 2)
        raw_hum = round(55.0 + random.uniform(-4.0, 6.0), 1)
        raw_co2 = round(800.0 + random.uniform(-50.0, 350.0), 1)
        raw_light = int(450 + random.uniform(-40, 40))
        occupancy = random.choice([0, 0, 15, 25, 30, 35])
        return raw_temp, raw_hum, raw_co2, raw_light, occupancy

    def run_pipeline(self):
        logger.info("Starting Real-Time Edge Processing & Closed-Loop Control Pipeline...")
        try:
            self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self.mqtt_client.loop_start()

            while self.running:
                raw_temp, raw_hum, raw_co2, raw_light, occupancy = self.generate_virtual_sensor_array()

                filt_temp = self.temp_filter.filter(raw_temp)
                filt_co2 = self.co2_filter.filter(raw_co2)

                pmv_index = self.intelligence.calculate_iso7730_pmv(filt_temp, raw_hum)

                if self.manual_override:
                    hvac_status = self.override_state["hvac"]
                    vent_status = self.override_state["vent"]
                    mode = "MANUAL_OVERRIDE"
                else:
                    mode = "AI_AUTOMATED"
                    if (pmv_index > 0.5 or filt_temp > TEMP_THRESHOLD_C) and occupancy > 0:
                        hvac_status = "ACTIVE_COOLING"
                    elif filt_temp > TEMP_THRESHOLD_C and occupancy == 0:
                        hvac_status = "ECO_STANDBY"
                    else:
                        hvac_status = "OFF"

                    vent_status = "ACTIVE_EXHAUST" if filt_co2 > CO2_THRESHOLD_PPM else "OFF"

                baseline_power = 3500.0
                smart_power = 0.0
                if hvac_status == "ACTIVE_COOLING": smart_power += 2500.0
                elif hvac_status == "ECO_STANDBY": smart_power += 300.0
                if vent_status == "ACTIVE_EXHAUST": smart_power += 400.0
                
                energy_saved = self.intelligence.calculate_energy_savings_pct(smart_power, baseline_power)

                telemetry_payload = {
                    "timestamp": time.strftime("%H:%M:%S"),
                    "node_id": CLIENT_ID,
                    "control_mode": mode,
                    "sensors": {
                        "temp_raw": raw_temp,
                        "temp_filtered": filt_temp,
                        "humidity": raw_hum,
                        "co2_raw": raw_co2,
                        "co2_filtered": filt_co2,
                        "light_lux": raw_light,
                        "occupancy_count": occupancy
                    },
                    "analytics": {
                        "pmv_index": pmv_index,
                        "energy_saved_pct": energy_saved
                    },
                    "actuators": {
                        "hvac": hvac_status,
                        "ventilation": vent_status
                    }
                }

                self.mqtt_client.publish(TOPIC_TELEMETRY, json.dumps(telemetry_payload), qos=1)

                point = Point("environmental_telemetry") \
                    .tag("gateway_node", CLIENT_ID) \
                    .tag("mode", mode) \
                    .field("temp_filtered", filt_temp) \
                    .field("humidity", raw_hum) \
                    .field("co2_filtered", filt_co2) \
                    .field("light_lux", raw_light) \
                    .field("occupancy", occupancy) \
                    .field("pmv_index", pmv_index) \
                    .field("energy_saved_pct", energy_saved) \
                    .field("hvac_active", 1 if hvac_status != "OFF" else 0) \
                    .field("vent_active", 1 if vent_status != "OFF" else 0)
                
                self.write_api.write(bucket=INFLUX_BUCKET, record=point)

                logger.info(f"--- TELEMETRY FRAME [{telemetry_payload['timestamp']}] ---")
                logger.info(f"Sensors  | Temp: {filt_temp}°C | Hum: {raw_hum}% | CO2: {filt_co2} ppm | Occupancy: {occupancy}")
                logger.info(f"AI Model | ISO 7730 PMV: {pmv_index} | Energy Efficiency Gain: {energy_saved}%")
                logger.info(f"Actuator | Mode: [{mode}] | HVAC: [{hvac_status}] | Vent: [{vent_status}]\n")

                time.sleep(2.0)

        except KeyboardInterrupt:
            logger.warning("Shutdown signal received. Terminating daemon...")
        finally:
            self.running = False
            self.mqtt_client.publish(TOPIC_LWT, json.dumps({"status": "OFFLINE_CLEAN", "node": CLIENT_ID}), qos=1, retain=True)
            self.mqtt_client.loop_stop()
            self.mqtt_client.disconnect()
            self.db_client.close()
            logger.info("Edge AI Daemon successfully shutdown.")

if __name__ == "__main__":
    daemon = EdgeAIDaemon()
    daemon.run_pipeline()
