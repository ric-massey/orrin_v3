def test_social_presence_emits_one_shot_departure_event(monkeypatch):
    from brain.runtime_coupling import social_presence as sp

    now = [0.0]
    monkeypatch.setattr(sp.time, "time", lambda: now[0])
    model = sp.SocialPresenceModel()

    assert model.get_state()["door_event"] is None

    now[0] = 700.0
    state = model.get_state()
    event = state["door_event"]
    assert state["pattern"] == "absent"
    assert event["from_pattern"] == "present"
    assert event["to_pattern"] == "absent"
    assert event["direction"] == "departure"
    assert "door" in event["tags"]
    assert "threshold_crossing" in event["tags"]

    assert model.get_state()["door_event"] is None


def test_social_presence_emits_arrival_event_on_user_contact(monkeypatch):
    from brain.runtime_coupling import social_presence as sp

    now = [0.0]
    monkeypatch.setattr(sp.time, "time", lambda: now[0])
    model = sp.SocialPresenceModel()

    now[0] = 700.0
    model.get_state()  # consume departure event
    model.mark_user_spoke()

    state = model.get_state()
    event = state["door_event"]
    assert state["pattern"] == "present"
    assert event["from_pattern"] == "absent"
    assert event["to_pattern"] == "present"
    assert event["direction"] == "arrival"
    assert "arrival" in event["tags"]
