from app.services.agent_matching import _phone, build_agent_matching_context


def test_phone_normalization_keeps_digits_only():
    assert _phone("+351 912-345-678") == "351912345678"


def test_agent_matching_requires_exactly_one_record_id():
    try:
        build_agent_matching_context(None, None)
    except ValueError as exc:
        assert "contact_id ou lead_id" in str(exc)
    else:
        raise AssertionError("Expected a selector validation error")


def test_agent_matching_rejects_non_positive_record_ids():
    try:
        build_agent_matching_context(None, None, contact_id=0)
    except ValueError:
        pass
    else:
        raise AssertionError("Expected a positive-ID validation error")
