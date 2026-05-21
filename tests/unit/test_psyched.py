import sys
import json
import time
from pathlib import Path
from unittest.mock import patch, MagicMock, call

import pytest

# Add psyched package to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent / "src" / "psyched"))

# The psyched module creates MQTT client at import time, we must mock it.

@pytest.fixture
def psyched_module():
    """Import psyched with MQTT mocked."""
    with patch('psyched.mqtt.Client') as mock_mqtt_client:
        mock_instance = MagicMock()
        mock_mqtt_client.return_value = mock_instance

        import psyched
        psyched.mqtt_client = mock_instance
        yield psyched, mock_instance

class TestStateComputation:
    def test_normal_biometrics(self, psyched_module):
        psych, _ = psyched_module
        stress, fatigue = psych.compute_state({"heart_rate": 70, "gsr": 1500, "temperature": 36.6})
        assert 0 <= stress <= 100
        assert 0 <= fatigue <= 100
        # Normal rest should give low stress
        assert stress < 50

    def test_high_stress(self, psyched_module):
        psych, _ = psyched_module
        stress, _ = psych.compute_state({"heart_rate": 120, "gsr": 500, "temperature": 37.0})
        assert stress > 70

class TestOnMessage:
    def test_publishes_psyche_state(self, psyched_module):
        psych, mock_client = psyched_module
        payload = json.dumps({"heart_rate": 90, "gsr": 1000, "temperature": 36.8})
        msg = MagicMock()
        msg.payload = payload.encode()

        psych.on_message(mock_client, None, msg)

        # Check that psyche state was published
        publish_calls = mock_client.publish.call_args_list
        topics = [call_args[0][0] for call_args in publish_calls]
        assert psych.TOPIC_PSYCHE in topics

    def test_blocks_commands_when_stress_high(self, psyched_module):
        psych, mock_client = psyched_module
        payload = json.dumps({"heart_rate": 130, "gsr": 400, "temperature": 37.2})
        msg = MagicMock()
        msg.payload = payload.encode()

        psych.on_message(mock_client, None, msg)

        publish_calls = mock_client.publish.call_args_list
        # One of the calls should be a block command
        block_calls = [c for c in publish_calls if c[0][0] == psych.TOPIC_COMMAND_FILTER]
        assert len(block_calls) == 1
        block_data = json.loads(block_calls[0][0][1])
        assert block_data["block_dangerous"] == True

    def test_unblocks_when_normal(self, psyched_module):
        psych, mock_client = psyched_module
        payload = json.dumps({"heart_rate": 65, "gsr": 1600, "temperature": 36.5})
        msg = MagicMock()
        msg.payload = payload.encode()

        psych.on_message(mock_client, None, msg)

        block_calls = [c for c in mock_client.publish.call_args_list if c[0][0] == psych.TOPIC_COMMAND_FILTER]
        assert len(block_calls) == 1
        block_data = json.loads(block_calls[0][0][1])
        assert block_data["block_dangerous"] == False
