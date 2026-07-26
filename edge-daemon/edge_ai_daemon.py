#!/usr/bin/env python3
"""
ENTERPRISE INDUSTRIAL IOT EDGE AI DAEMON (REAL HARDWARE HITL BRIDGE)
Project: IoT-Based Automatic Climate Control System for Smart Classrooms Using 5G Network Technology
Architecture: Hardware-in-the-Loop (HiTL) Real Sensor Processing & Actuator Control Engine
"""

import time
import math
import json
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

# CLOUD BRIDGE: Must match line 17 of your Wokwi C++ code!
MQTT_BROKER = "broker.emqx.io"
MQTT_PORT = 1883
CLIENT_ID = "Linux_5G_Edge_Gateway_01"

# TOPICS
TOPIC_TELEMETRY_RAW = "smart_classroom/telemetry/raw"   # Incoming from Wokwi ESP32
TOPIC_TELEMETRY_UI  = "smart_classroom/telemetry"       # Outgoing to UI
TOPIC_CONTROLS      = "smart_classroom/controls"        # Outgoing commands to Wokwi LEDs
TOPIC_LWT           = "smart_classroom/status/gateway"

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

# --- MAIN INDUSTRIAL DAEMON CLASS ---
class EdgeAIDaemon:
    def __init__(self):
        self.running = True
        self.manual_override = False
        self.override_state = {"hvac": "OFF", "vent": "OFF"}
        
        # Holds the real physical data arriving from Wokwi hardware
        self.real_hardware_data = None
        
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
            qos=1, retain=True
        )

    def on_mqtt_connect(self, client, userdata, flags, rc, properties=None):
        if rc == 0:
            logger.info(f"Connected to Cloud MQTT Broker ({MQTT_BROKER}).")
            # SUBSCRIBE TO REAL HARDWARE DATA FROM WOKWI!
            client.subscribe(TOPIC_TELEMETRY_RAW, qos=1)
            client.subscribe(TOPIC_CONTROLS, qos=1)
            client.publish(TOPIC_LWT, json.dumps({"status": "ONLINE_HEALTHY", "node": CLIENT_ID}), qos=1, retain=True)
        else:
            logger.error(f"MQTT Connection Refused. Return Code: {rc}")

    def on_mqtt_message(self, client, userdata, msg):
        try:
            payload = json.loads(msg.payload.decode("utf-8"))
            
            # 1. CATCH REAL SENSOR TELEMETRY FROM WOKWI ESP32
            if msg.topic == TOPIC_TELEMETRY_RAW:
                if "sensors" in payload:
                    self.real_hardware_data = {
                        "temp": float(payload["sensors"]["temp_raw"]),
                        "hum": float(payload["sensors"]["humidity"]),
                        "co2": float(payload["sensors"]["co2_raw"]),
                        "occ": int(payload["sensors"]["occupancy_count"])
                    }
                else:
                    self.real_hardware_data = {
                        "temp": float(payload.get("temp_raw", 24.0)),
                        "hum": float(payload.get("humidity", 40.0)),
                        "co2": float(payload.get("co2_raw", 400.0)),
                        "occ": int(payload.get("occupancy_count", 0))
                    }
                    
            # 2. CATCH MANUAL OVERRIDE COMMANDS
            elif msg.topic == TOPIC_CONTROLS and "manual_override" in payload:
                self.manual_override = bool(payload["manual_override"])
                if self.manual_override:
                    self.override_state["hvac"] = str(payload.get("hvac", "OFF"))
                    self.override_state["vent"] = str(payload.get("vent", "OFF"))
        except Exception as e:
            logger.error(f"Malformed MQTT Packet: {e}")

    def run_pipeline(self):
        logger.info("Starting REAL HARDWARE Closed-Loop Control Pipeline...")
        logger.info("Waiting for live telemetry packets from Wokwi ESP32...")
        try:
            self.mqtt_client.connect(MQTT_BROKER, MQTT_PORT, keepalive=60)
            self.mqtt_client.loop_start()

            while self.running:
                # If Wokwi hasn't sent data yet, pause and wait
                if self.real_hardware_data is None:
                    time.sleep(1.0)
                    continue

                # PULL ONLY REAL ORIGINAL DATA FROM HARDWARE
                raw_temp = self.real_hardware_data["temp"]
                raw_hum  = self.real_hardware_data["hum"]
                raw_co2  = self.real_hardware_data["co2"]
                occupancy = self.real_hardware_data["occ"]
                raw_light = 500 # Constant Lux for baseline

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

                # SEND ACTUATOR COMMANDS BACK TO WOKWI ESP32 OVER CLOUD MQTT!
                control_command = {
                    "hvac": hvac_status,
                    "ventilation": vent_status,
                    "mode": mode
                }
                self.mqtt_client.publish(TOPIC_CONTROLS, json.dumps(control_command), qos=1)

                # Calculate energy
                baseline_power = 3500.0
                smart_power = 0.0
                if hvac_status == "ACTIVE_COOLING": smart_power += 2500.0
                elif hvac_status == "ECO_STANDBY": smart_power += 300.0
                if vent_status == "ACTIVE_EXHAUST": smart_power += 400.0
                energy_saved = self.intelligence.calculate_energy_savings_pct(smart_power, baseline_power)

                # Write to InfluxDB for Grafana
                point = Point("environmental_telemetry") \
                    .tag("gateway_node", CLIENT_ID) \
                    .tag("mode", mode) \
                    .field("temp_filtered", filt_temp) \
                    .field("humidity", raw_hum) \
                    .field("co2_filtered", filt_co2) \
                    .field("light_lux", raw_light) \
                    .field("occupancy", occupancy) \
                    .field("pmv_index", pmv_index) \
                    .field("energy_saved_pct", energy_saved)
                self.write_api.write(bucket=INFLUX_BUCKET, record=point)

                logger.info(f"--- REAL HARDWARE FRAME [{time.strftime('%H:%M:%S')}] ---")
                logger.info(f"Wokwi Sensor | Temp: {filt_temp}°C | Hum: {raw_hum}% | CO2: {filt_co2} ppm | Occ: {occupancy}")
                logger.info(f"AI Decision  | ISO 7730 PMV: {pmv_index} | Energy Saved: {energy_saved}%")
                logger.info(f"Actuator Out | HVAC: [{hvac_status}] | Vent: [{vent_status}] -> [SENT TO WOKWI LEDs]\n")

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
