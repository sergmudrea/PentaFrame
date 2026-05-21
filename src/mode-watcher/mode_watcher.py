#!/usr/bin/env python3
"""
Penta Mode Watcher (v1.1)
==========================
Subscribes to MQTT module attach/detach events and automatically
switches the system mode via the Resolver API.

New in v1.1:
  - Handles 'detach' events: if no other module of a higher-priority rule
    is attached, reverts to the default mode.
  - Mode rules can specify a 'priority' (lower = more important).
  - Default mode is configurable (default: "desktop").

Configuration (in /etc/penta/config.yaml):
  mode_watcher:
    default_mode: "desktop"
    rules:
      - module_type: "HackRF"
        mode: "pentest"
        priority: 10
      - module_type: "Zigbee"
        mode: "smarthome"
        priority: 20
      - module_type: "GPU"
        mode: "desktop"
        priority: 30
"""

import json
import logging
import os
import time
from pathlib import Path
from typing import Dict, List, Optional

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

RESOLVER_URL = "http://localhost:8500"  # will be updated to Unix socket later

DEFAULT_MODE = WATCHER_CONFIG.get("default_mode", "desktop")
RULES: List[Dict[str, str]] = WATCHER_CONFIG.get("rules", [])

# Sort rules by priority (lowest first)
RULES.sort(key=lambda r: r.get("priority", 100))

# ---------- State ----------
active_modules: Dict[str, str] = {}  # module_type -> addr
current_mode: str = DEFAULT_MODE

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

def switch_mode(new_mode: str):
    """Call Resolver to switch mode."""
    global current_mode
    if new_mode != current_mode:
        resp = requests.post(f"{RESOLVER_URL}/api/v1/mode/switch?mode={new_mode}")
        if resp.status_code == 200:
            logger.info(f"Switched mode: {current_mode} → {new_mode}")
            current_mode = new_mode
        else:
            logger.warning(f"Failed to switch mode to '{new_mode}': {resp.text}")

def recompute_mode():
    """Determine the most appropriate mode based on currently attached modules."""
    if not active_modules:
        switch_mode(DEFAULT_MODE)
        return
    # Find the rule with the smallest priority whose module is attached
    for rule in RULES:
        if rule["module_type"] in active_modules.values():
            switch_mode(rule["mode"])
            return
    # No matching rule -> default
    switch_mode(DEFAULT_MODE)

def on_message(client, userdata, msg):
    try:
        payload = json.loads(msg.payload.decode())
        module_type = payload.get("type", "")
        addr = payload.get("addr", "")
        if not module_type:
            return

        if msg.topic == "penta/module/attach":
            active_modules[addr] = module_type
            logger.info(f"Module {module_type} ({addr}) attached.")
        elif msg.topic == "penta/module/detach":
            if addr in active_modules:
                removed = active_modules.pop(addr)
                logger.info(f"Module {removed} ({addr}) detached.")
            else:
                # If detach payload lacks addr, remove by type (best effort)
                for k, v in list(active_modules.items()):
                    if v == module_type:
                        active_modules.pop(k)
                        logger.info(f"Module {v} ({k}) detached (by type).")
                        break

        recompute_mode()
    except Exception as e:
        logger.error(f"Error processing message: {e}")

mqtt_client.on_connect = on_connect
mqtt_client.on_message = on_message

# ---------- Main ----------
def main():
    logger.info(f"Starting mode-watcher (default mode: {DEFAULT_MODE})...")
    try:
        mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
        mqtt_client.loop_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down.")
    except Exception as e:
        logger.error(f"Fatal error: {e}")

if __name__ == "__main__":
    main()
