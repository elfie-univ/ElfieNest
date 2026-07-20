from elfie.nervous_system import SensoryDamSignalFilter


def test_distinct_message_ids_allow_repeated_text():
    signal_filter = SensoryDamSignalFilter()
    first = {
        "message_id": "turn-1",
        "has_new_message": True,
        "user_message": "你好",
        "temperature": 24.0,
    }
    second = {**first, "message_id": "turn-2"}

    assert signal_filter.filter_noise(first) is True
    assert signal_filter.filter_noise(second) is True
