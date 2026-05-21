#!/usr/bin/env python3
"""
pentad - Penta Module Daemon
=============================
Scans I²C bus for PMC-128 modules, reads EEPROM identifiers,
publishes attach/detach events over MQTT, and provides a REST API
for module power control and status.

Usage:
    python3 src/pentad/pentad.py
"""

import json
import logging
import os
import sys
import time
from pathlib import Path
from typing import Optional

import paho.mqtt.client as mqtt
import yaml
from flask import Flask, jsonify, request

# ---------- Configuration ----------
CONFIG_PATH = Path("/etc/penta/config.yaml")
if not CONFIG_PATH.exists():
    CONFIG_PATH = Path("config/penta.conf.example")

with open(CONFIG_PATH, "r") as f:
    config = yaml.safe_load(f)

PENTAD_CONFIG = config.get("pentad", {})
MQTT_CONFIG = config.get("mqtt", {})
SECURITY_CONFIG = config.get("security", {})

# Defaults
I2C_BUS = PENTAD_CONFIG.get("i2c_bus", 1)
SCAN_INTERVAL = PENTAD_CONFIG.get("scan_interval", 5)       # seconds
EEPROM_ADDR_PREFIX = 0x50                                   # typical 24C02 base
MODULE_GPIO_BASE = PENTAD_CONFIG.get("gpio_base", 0)
PWR_EN_GPIO = PENTAD_CONFIG.get("pwr_en_gpio", None)        # optional global kill

MQTT_BROKER = MQTT_CONFIG.get("broker", "localhost")
MQTT_PORT = MQTT_CONFIG.get("port", 1883)
MQTT_CLIENT_ID = MQTT_CONFIG.get("client_id", "pentad")
MQTT_TOPIC_ATTACH = "penta/module/attach"
MQTT_TOPIC_DETACH = "penta/module/detach"
MQTT_TOPIC_STATUS = "penta/module/status"

# ---------- Logging ----------
logging.basicConfig(level=logging.INFO, format="%(asctime)s [%(levelname)s] pentad: %(message)s")
logger = logging.getLogger("pentad")

# ---------- Flask REST API ----------
app = Flask(__name__)

# In-memory state of connected modules
connected_modules: dict[str, dict] = {}

# ---------- MQTT Client ----------
mqtt_client = mqtt.Client(client_id=MQTT_CLIENT_ID)

def on_connect(client, userdata, flags, rc):
    if rc == 0:
        logger.info("Connected to MQTT broker")
    else:
        logger.error(f"MQTT connection failed, rc={rc}")

mqtt_client.on_connect = on_connect

try:
    mqtt_client.connect(MQTT_BROKER, MQTT_PORT, 60)
    mqtt_client.loop_start()
except Exception as e:
    logger.warning(f"Could not connect to MQTT: {e}. Running without MQTT.")

# ---------- I²C / Module Helpers ----------
def i2c_scan(bus: int = I2C_BUS) -> list[int]:
    """
    Perform an I²C scan on the given bus and return a list of detected addresses.
    Falls back to i2cdetect shell command if smbus2 is not available.
    """
    try:
        import smbus2
        bus_obj = smbus2.SMBus(bus)
        detected = []
        for addr in range(0x03, 0x78):
            try:
                bus_obj.read_byte(addr)
                detected.append(addr)
            except OSError:
                pass
        bus_obj.close()
        return detected
    except ImportError:
        import subprocess
        try:
            out = subprocess.check_output(["i2cdetect", "-y", str(bus)], text=True)
            # Parse i2cdetect output (simple table parser)
            for line in out.splitlines()[1:]:
                parts = line.split()
                for p in parts[1:]:
                    if p != "--" and not p.startswith("UU"):
                        detected.append(int(p, 16))
            return detected
        except Exception:
            logger.error("I²C scan failed. Is i2c-tools installed?")
            return []

def read_eeprom(addr: int, bus: int = I2C_BUS) -> Optional[dict]:
    """
    Try to read a small EEPROM (AT24C02) to get module type and serial.
    Returns dict with keys: type, serial, addr.
    """
    try:
        import smbus2
        bus_obj = smbus2.SMBus(bus)
        # First 2 bytes: length of type string, then type, then serial
        raw = bus_obj.read_i2c_block_data(addr, 0, 64)
        bus_obj.close()
        # Very simple decoding: first byte is length of type name
        type_len = raw[0]
        if type_len == 0 or type_len > 32:
            return None
        mod_type = bytes(raw[1:1+type_len]).decode("ascii", errors="replace").strip("\x00")
        # Next byte is length of serial, or assume remaining
        serial_len = raw[1+type_len]
        serial = bytes(raw[2+type_len:2+type_len+serial_len]).decode("ascii", errors="replace").strip("\x00")
        return {"type": mod_type, "serial": serial, "addr": f"0x{addr:02X}"}
    except ImportError:
        # Fallback: try to read via i2cget (limited)
        return {"type": "unknown", "serial": "unknown", "addr": f"0x{addr:02X}"}
    except Exception as e:
        logger.debug(f"EEPROM read failed at {addr:#04x}: {e}")
        return None

def detect_modules():
    """Scan bus, read EEPROMs, compare with known state and publish events."""
    global connected_modules
    current_addrs = i2c_scan()
    current_keys = {f"0x{a:02X}" for a in current_addrs}

    # Detach modules that disappeared
    for addr_key in list(connected_modules.keys()):
        if addr_key not in current_keys:
            mod = connected_modules.pop(addr_key)
            logger.info(f"Module detached: {mod}")
            mqtt_client.publish(MQTT_TOPIC_DETACH, json.dumps(mod), qos=1)

    # Attach new modules
    for addr in current_addrs:
        addr_key = f"0x{addr:02X}"
        if addr_key not in connected_modules:
            info = read_eeprom(addr)
            if info is None:
                info = {"type": "unknown", "serial": "unknown", "addr": addr_key}
            connected_modules[addr_key] = info
            logger.info(f"Module attached: {info}")
            mqtt_client.publish(MQTT_TOPIC_ATTACH, json.dumps(info), qos=1)

# ---------- REST Endpoints ----------
@app.route("/api/v1/status", methods=["GET"])
def api_status():
    """Return connected modules and daemon uptime."""
    return jsonify({
        "modules": list(connected_modules.values()),
        "count": len(connected_modules),
        "uptime": time.monotonic()
    })

@app.route("/api/v1/scan", methods=["GET"])
def api_scan():
    """Force a scan and return current modules."""
    detect_modules()
    return jsonify({
        "modules": list(connected_modules.values()),
        "count": len(connected_modules)
    })

@app.route("/api/v1/module/<addr>/power", methods=["POST"])
def api_power(addr: str):
    """Control power of a specific module (via GPIO)."""
    data = request.get_json(force=True, silent=True) or {}
    state = data.get("state", "").lower()
    if state not in ("on", "off"):
        return jsonify({"error": "state must be 'on' or 'off'"}), 400

    if addr not in connected_modules:
        return jsonify({"error": "module not found"}), 404

    # In a real implementation we'd toggle a GPIO line via libgpiod.
    # Here we simulate and log.
    logger.info(f"Power {state} requested for module {addr}")
    # For global kill switch GPIO:
    if SECURITY_CONFIG.get("killswitch_gpio") and state == "off":
        logger.info("Kill switch activated via software (hardware kill also exists)")
    return jsonify({"addr": addr, "state": state, "result": "ok"})

@app.route("/api/v1/resources", methods=["GET"])
def api_resources():
    """Return basic system resources (CPU, memory)."""
    try:
        import psutil
        mem = psutil.virtual_memory()
        return jsonify({
            "cpu_percent": psutil.cpu_percent(interval=1),
            "memory_total_mb": mem.total // (1024*1024),
            "memory_used_mb": mem.used // (1024*1024),
        })
    except ImportError:
        return jsonify({"message": "psutil not installed, install for resource info"}), 501

# ---------- Main Loop ----------
def main():
    logger.info("Starting pentad...")
    # First scan
    detect_modules()

    # Start REST API in a separate thread
    import threading
    rest_port = PENTAD_CONFIG.get("rest_port", 8600)
    threading.Thread(target=lambda: app.run(host="0.0.0.0", port=rest_port, debug=False, use_reloader=False), daemon=True).start()

    # Periodic scan loop
    try:
        while True:
            time.sleep(SCAN_INTERVAL)
            detect_modules()
    except KeyboardInterrupt:
        logger.info("Shutting down pentad")
        mqtt_client.loop_stop()
        mqtt_client.disconnect()

if __name__ == "__main__":
    main()
