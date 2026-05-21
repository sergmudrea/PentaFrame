import sys
import json
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add pentad package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "pentad"))

# The pentad module creates Flask app and MQTT client at import time.
# We must mock dependencies before importing.

@pytest.fixture
def client():
    """Create a Flask test client with mocked I²C and MQTT."""
    with patch('pentad.mqtt.Client') as mock_mqtt_client, \
         patch('pentad.i2c_scan', return_value=[0x10, 0x20]), \
         patch('pentad.read_eeprom') as mock_eeprom, \
         patch('pentad.psutil', None):  # psutil may not be installed; skip
        # Mock EEPROM reads
        def eeprom_side_effect(addr, bus=1):
            if addr == 0x10:
                return {"type": "HackRF", "serial": "12345", "addr": "0x10"}
            elif addr == 0x20:
                return {"type": "NVMe", "serial": "67890", "addr": "0x20"}
            return None
        mock_eeprom.side_effect = eeprom_side_effect

        # Mock MQTT client methods
        mock_mqtt_instance = MagicMock()
        mock_mqtt_client.return_value = mock_mqtt_instance

        import pentad
        pentad.mqtt_client = mock_mqtt_instance  # ensure the module uses our mock

        # Create test client
        with pentad.app.test_client() as c:
            # Force initial scan to populate connected_modules
            pentad.detect_modules()
            yield c

class TestStatus:
    def test_status_returns_modules(self, client):
        resp = client.get('/api/v1/status')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert 'modules' in data
        modules = data['modules']
        assert len(modules) == 2
        types = [m['type'] for m in modules]
        assert 'HackRF' in types
        assert 'NVMe' in types

    def test_status_includes_count(self, client):
        resp = client.get('/api/v1/status')
        data = json.loads(resp.data)
        assert data['count'] == 2

class TestScan:
    def test_scan_returns_modules(self, client):
        resp = client.get('/api/v1/scan')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert len(data['modules']) == 2

class TestPower:
    def test_power_on_off_valid_module(self, client):
        resp = client.post('/api/v1/module/0x10/power',
                           data=json.dumps({'state': 'off'}),
                           content_type='application/json')
        assert resp.status_code == 200
        data = json.loads(resp.data)
        assert data['result'] == 'ok'
        assert data['state'] == 'off'

    def test_power_invalid_state(self, client):
        resp = client.post('/api/v1/module/0x10/power',
                           data=json.dumps({'state': 'invalid'}),
                           content_type='application/json')
        assert resp.status_code == 400

    def test_power_unknown_module(self, client):
        resp = client.post('/api/v1/module/0x99/power',
                           data=json.dumps({'state': 'on'}),
                           content_type='application/json')
        assert resp.status_code == 404

class TestResources:
    def test_resources_without_psutil(self, client):
        resp = client.get('/api/v1/resources')
        assert resp.status_code == 501  # not implemented without psutil
