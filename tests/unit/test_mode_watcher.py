import sys
from pathlib import Path
from unittest.mock import patch, MagicMock

import pytest

# Add mode-watcher package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "mode-watcher"))

# The module starts MQTT loop on import; mock it heavily

@pytest.fixture
def watcher():
    """Return the mode-watcher module with MQTT and requests mocked."""
    with patch('mode_watcher.mqtt.Client') as mock_mqtt_client, \
         patch('mode_watcher.requests') as mock_requests, \
         patch('mode_watcher.yaml.safe_load') as mock_yaml:
        # Provide minimal config
        mock_yaml.return_value = {
            "mqtt": {"broker": "localhost", "port": 1883},
            "mode_watcher": {
                "default_mode": "desktop",
                "rules": [
                    {"module_type": "HackRF", "mode": "pentest", "priority": 10},
                    {"module_type": "Zigbee", "mode": "smarthome", "priority": 20},
                ]
            }
        }
        # Mock MQTT client instance
        mock_mqtt_instance = MagicMock()
        mock_mqtt_client.return_value = mock_mqtt_instance

        import mode_watcher
        mode_watcher.mqtt_client = mock_mqtt_instance
        mode_watcher.requests = mock_requests
        # Reset rules to known state
        mode_watcher.RULES = [
            {"module_type": "HackRF", "mode": "pentest", "priority": 10},
            {"module_type": "Zigbee", "mode": "smarthome", "priority": 20},
        ]
        mode_watcher.RULES.sort(key=lambda r: r.get("priority", 100))
        mode_watcher.DEFAULT_MODE = "desktop"
        mode_watcher.active_modules = {}
        mode_watcher.current_mode = "desktop"
        yield mode_watcher

class TestModeWatcherInitialization:
    def test_default_mode(self, watcher):
        assert watcher.DEFAULT_MODE == "desktop"
        assert watcher.current_mode == "desktop"
        assert len(watcher.RULES) == 2

class TestOnMessageAttach:
    def test_attach_matching_highest_priority_rule(self, watcher):
        payload = '{"type":"HackRF","addr":"0x10"}'
        msg = MagicMock()
        msg.topic = "penta/module/attach"
        msg.payload = payload.encode()
        watcher.on_message(None, None, msg)
        # Should have switched to pentest
        watcher.requests.post.assert_called_with(
            f"{watcher.RESOLVER_URL}/api/v1/mode/switch?mode=pentest"
        )
        assert watcher.current_mode == "pentest"
        assert watcher.active_modules == {"0x10": "HackRF"}

    def test_attach_lower_priority_does_not_override(self, watcher):
        # Attach Zigbee first (priority 20), then HackRF (priority 10)
        watcher.on_message(None, None, MagicMock(topic="penta/module/attach", payload=b'{"type":"Zigbee","addr":"0x20"}'))
        watcher.on_message(None, None, MagicMock(topic="penta/module/attach", payload=b'{"type":"HackRF","addr":"0x10"}'))
        # Should still be pentest because HackRF has higher priority
        # The last call should be for pentest
        watcher.requests.post.assert_any_call(
            f"{watcher.RESOLVER_URL}/api/v1/mode/switch?mode=smarthome"
        )
        watcher.requests.post.assert_any_call(
            f"{watcher.RESOLVER_URL}/api/v1/mode/switch?mode=pentest"
        )
        assert watcher.current_mode == "pentest"

    def test_attach_no_matching_rule(self, watcher):
        watcher.on_message(None, None, MagicMock(topic="penta/module/attach", payload=b'{"type":"Keyboard","addr":"0x30"}'))
        # No mode switch
        watcher.requests.post.assert_not_called()
        assert watcher.current_mode == "desktop"

class TestOnMessageDetach:
    def test_detach_last_module_reverts_to_default(self, watcher):
        # Attach HackRF, then detach
        watcher.on_message(None, None, MagicMock(topic="penta/module/attach", payload=b'{"type":"HackRF","addr":"0x10"}'))
        watcher.on_message(None, None, MagicMock(topic="penta/module/detach", payload=b'{"addr":"0x10"}'))
        # Should revert to desktop
        watcher.requests.post.assert_called_with(
            f"{watcher.RESOLVER_URL}/api/v1/mode/switch?mode=desktop"
        )
        assert watcher.current_mode == "desktop"
        assert watcher.active_modules == {}

    def test_detach_one_of_multiple_keeps_mode(self, watcher):
        # Attach HackRF + Zigbee, then detach HackRF -> mode should fall back to next priority (Zigbee)
        watcher.on_message(None, None, MagicMock(topic="penta/module/attach", payload=b'{"type":"HackRF","addr":"0x10"}'))
        watcher.on_message(None, None, MagicMock(topic="penta/module/attach", payload=b'{"type":"Zigbee","addr":"0x20"}'))
        # Now current_mode = pentest
        watcher.on_message(None, None, MagicMock(topic="penta/module/detach", payload=b'{"addr":"0x10"}'))
        # Should switch to smarthome
        watcher.requests.post.assert_called_with(
            f"{watcher.RESOLVER_URL}/api/v1/mode/switch?mode=smarthome"
        )
        assert watcher.current_mode == "smarthome"
        assert watcher.active_modules == {"0x20": "Zigbee"}

class TestRecomputeMode:
    def test_recompute_empty_modules(self, watcher):
        watcher.active_modules = {}
        watcher.recompute_mode()
        watcher.requests.post.assert_called_with(
            f"{watcher.RESOLVER_URL}/api/v1/mode/switch?mode=desktop"
        )

    def test_recompute_with_matching_rule(self, watcher):
        watcher.active_modules = {"0x20": "Zigbee"}
        watcher.recompute_mode()
        watcher.requests.post.assert_called_with(
            f"{watcher.RESOLVER_URL}/api/v1/mode/switch?mode=smarthome"
        )
