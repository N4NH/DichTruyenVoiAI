import time
from src.core.key_rotator import KeyRotator

def test_key_rotation_round_robin():
    keys = ["key-1", "key-2", "key-3"]
    rotator = KeyRotator(api_keys=keys)

    assert rotator.get_key() == "key-1"
    assert rotator.get_key() == "key-2"
    assert rotator.get_key() == "key-3"
    assert rotator.get_key() == "key-1"

def test_key_cooldown():
    keys = ["key-1", "key-2"]
    rotator = KeyRotator(api_keys=keys, cooldown_seconds=1)

    rotator.mark_rate_limited("key-1")
    # key-1 is in cooldown, should get key-2
    assert rotator.get_key() == "key-2"
    assert rotator.get_key() == "key-2"

    status = rotator.get_status()
    assert status["total"] == 2
    assert status["in_cooldown"] == 1
    assert status["active"] == 1

def test_empty_keys():
    rotator = KeyRotator(api_keys=[])
    assert rotator.get_key() is None
    assert rotator.total_keys == 0

