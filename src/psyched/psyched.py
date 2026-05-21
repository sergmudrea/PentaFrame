#!/usr/bin/env python3
"""
psyched - Psycho‑emotional Monitor Daemon (v0.2)
=================================================
Subscribes to biometric sensor data over MQTT, computes stress and fatigue
indices, publishes results, and can trigger UI warnings or command restrictions.

New in v0.2:
  - Configurable sensor source: 'emulate' (default) or a real MQTT topic.
  - Multiple sensor inputs can be configured (heart_rate, gsr, temperature).
  - Emulation parameters adjustable via config file.

Usage:
    python3 src/psyched/psyched.py
"""

import json
import logging
import os
import random
import time
from pathlib import Path
from typing import Optional, Dict, Any

import paho.mqtt.client as mqtt
import yaml

# ---------- Configuration ----------
CONFIG_PATH = Path(os.environ.get("PENTA_CONFIG", "/etc/penta/config.yaml"))
if not CONFIG_PATH.exists():
    CONFIG_PATH = Path("config/penta.conf.example")

with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

PSYCHED_CONFIG = config.get("psyched", {})
MQTT_CONFIG = config.get("mqtt", {})

MQTT_BROKER = MQTT_CONFIG.get("broker", "localhost")
MQTT_PORT = MQTT_CONFIG.get("port", 1883)
MQTT_CLIENT_ID = "psyched"

# Topics
TOPIC_BIOMETRICS = PSYCHED_CONFIG.get("topic_biometrics", "penta/biometrics")
TOPIC_PSYCHE = "penta/psyche"
TOPIC_COMMAND_FILTER = "penta/command/filter"

# Thresholds
STRESS_THRESHOLD = PSYCHED_CONFIG.get("stress_threshold", 70)
FATIGUE_THRESHOLD = PSYCHED_CONFIG.get("fatigue_threshold", 80)

# Sensor configuration
SENSOR_MODE = PSYCHED_CONFIG.get("sensor_mode", "emulate")  # 'emulate' or 'real'
REAL_SENSOR_TOPICS = PSYCHED_CONFIG.get("real_sensor_topics", {})  # e.g. {"heart_rate": "penta/sensors/hr"}

# Emulation settings
EMULATE_INTERVAL = PSYCHED_CONFIG.get("emulate_interval", 5)

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] psyched: %(message)s")
logger = logging.getLogger("psyched")

# ---------- MQTT Client ----------
mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)

# In-memory biometric state (updated by sensor messages)
current_biometrics: Dict[str, float] = {
    "heart_rate": 70.0,
    "gsr": 1500.0,
    "temperature": 36.6,
}

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT broker")
        if SENSOR_MODE == "real":
            # Subscribe to individual sensor topics
            for sensor, topic in REAL_SENSOR_TOPICS.items():
                client.subscribe(topic, qos=1)
                logger.info(f"Subscribed to {topic} for {sensor}")
        else:
            # In emulate mode, we still subscribe to the main biometrics topic for external injection
            client.subscribe(TOPIC_BIOMETRICS, qos=1)
    else:
        logger.error(f"MQTT connection failed, rc={rc}")

def on_message(client, userdata, msg):
    """Process incoming biometric data."""
    try:
        payload = json.loads(msg.payload.decode())
        # Update internal state
        for key in current_biometrics.keys():
            if key in payload:
                current_biometrics[key] = payload[key]
        # Compute and publish
        stress, fatigue = compute_state(current_biometrics)
        state = {
            "stress": stress,
            "fatigue": fatigue,
            "timestamp": time.time()
        }
        mqtt_client.publish(TOPIC_PSYCHE, json.dumps(state), qos=1)
        # Check thresholds
        if stress > STRESS_THRESHOLD or fatigue > FATIGUE_THRESHOLD:
            mqtt_client.publish(TOPIC_COMMAND_FILTER, json.dumps({"block_dangerous": True, "reason": "stress/fatigue"}))
            logger.warning(f"High stress ({stress}) or fatigue ({fatigue}) – dangerous commands blocked.")
        else:
            mqtt_client.publish(TOPIC_COMMAND_FILTER, json.dumps({"block_dangerous": False}))
    except Exception as e:
        logger.error(f"Error processing message: {e}")

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# ---------- State Computation (unchanged) ----------
def compute_state(biometrics: Dict[str, float]) -> tuple[float, float]:
    hr = biometrics.get("heart_rate", 70)
    gsr = biometrics.get("gsr", 1500)
    temp = biometrics.get("temperature", 36.6)
    stress = max(0.0, min(100.0, (hr - 60) * 2.0 + (2000 - gsr) * 0.02))
    fatigue = max(0.0, min(100.0, (temp - 36.0) * 50.0 + random.uniform(0, 5)))
    return stress, fatigue

def emulate_biometrics():
    """Generate realistic fake data."""
    return {
        "heart_rate": random.randint(60, 100),
        "gsr": random.randint(800, 2500),
        "temperature": round(random.uniform(36.0, 37.5), 1),
    }

# ---------- Main Loop ----------
def main():
    logger.info(f"Starting psyched (mode: {SENSOR_MODE})...")
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_start()
    except Exception as e:
        logger.warning(f"Could not connect to MQTT: {e}. Running in offline mode.")
        mqtt_client.loop_start()

    if SENSOR_MODE == "emulate":
        logger.info("Emulation mode active.")
        while True:
            data = emulate_biometrics()
            mqtt_client.publish(TOPIC_BIOMETRICS, json.dumps(data))
            time.sleep(EMULATE_INTERVAL)
    else:
        # Real mode – just process incoming messages forever
        while True:
            time.sleep(1)

if __name__ == "__main__":
    main()
