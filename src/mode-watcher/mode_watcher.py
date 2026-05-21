#!/usr/bin/env python3
"""
Penta Mode Watcher
==================
Subscribes to MQTT module attach/detach events and automatically
switches the system mode via the Resolver API.

Configuration (in /etc/penta/config.yaml):
  mode_watcher:
    rules:
      - module_type: "HackRF"
        mode: "pentest"
      - module_type: "Zigbee"
        mode: "smarthome"
      - module_type: "GPU"
        mode: "desktop"

Usage:
    python3 src/mode-watcher/mode_watcher.py
"""

import json
import logging
import time
from pathlib import Path
from typing import Optional, Dict, List

import paho.mqtt.client as mqtt
import requests
import yaml

# ---------- Configuration ----------
CONFIG_PATH = Path(os.environ.get("PENTA_CONFIG", "/etc/penta/config.yaml"))
if not CONFIG_PATH.exists():
    CONFIG_PATH = Path("config/penta.conf.example")

with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

MQTT_CONFIG = config.get("mqtt", {})
WATCHER_CONFIG = config.get("mode_watcher", {})

MQTT_BROKER = MQTT_CONFIG.get("broker", "localhost")
MQTT_PORT = MQTT_CONFIG.get("port", 1883)
MQTT_CLIENT_ID = "mode-watcher"

RESOLVER_URL = "http://localhost:8500"  # or unix socket path

# Rules: list of {"module_type": "...", "mode": "..."}
RULES: List[Dict[str, str]] = WATCHER_CONFIG.get("rules", [])

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] mode-watcher: %(message)s")
logger = logging.getLogger("mode-watcher")

# ---------- MQTT ----------
mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT broker")
        client.subscribe("penta/module/attach", qos=1)
        client.subscribe("penta/module/detach", qos=1)
    else:
        logger.error(f"MQTT connection failed, rc={rc}")

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        module_type = payload.get("type", "")
        if not module_type:
            return
        # Find matching rule
        for rule in RULES:
            if rule.get("module_type") == module_type:
                new_mode = rule["mode"]
                # Switch mode
                resp = requests.post(f"{RESOLVER_URL}/api/v1/mode/switch?mode={new_mode}")
                if resp.status_code == 200:
                    logger.info(f"Switched to mode '{new_mode}' due to {module_type} {msg.topic}")
                else:
                    logger.warning(f"Failed to switch mode: {resp.text}")
                break
    except Exception as e:
        logger.error(f"Error processing message: {e}")

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# ---------- Main ----------
def main():
    logger.info("Starting mode-watcher...")
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")

if __name__ == "__main__":
    import os
    main()
