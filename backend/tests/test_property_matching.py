from types import SimpleNamespace

from app.services.property_matching import score_client_property


def test_matches_client_by_location_and_budget():
    contact = SimpleNamespace(
        property_preferences="Apartamento T2 para comprar",
        municipality="Oeiras", district="Lisboa",
        budget_min=200000, budget_max=350000,
    )
    lead = SimpleNamespace(
        title="Apartamento T2 à venda",
        property_type="Apartamento",
        municipality="Oeiras", district="Lisboa",
        property_data={"price": "325.000", "bedrooms": 2, "operation": "sale"},
    )
    result = score_client_property(contact, lead)
    assert result["score"] == 100
    assert {"municipality", "budget", "property_type", "bedrooms", "operation"}.issubset(set(result["matched_on"]))


def test_does_not_invent_match_when_listing_price_unknown():
    contact = SimpleNamespace(
        property_preferences="Apartamento para comprar",
        municipality="Lisboa", district=None,
        budget_min=None, budget_max=300000,
    )
    lead = SimpleNamespace(
        title="Apartamento T2", property_type="Apartamento",
        municipality="Lisboa", district=None, property_data={},
    )
    result = score_client_property(contact, lead)
    assert "price" in result["missing_or_mismatched"]
    assert result["score"] < 100


def test_owner_and_client_matching_are_not_inferred_by_score():
    # The matching API links owner records only by exact email/phone; the scoring
    # function is intentionally only for client search criteria.
    contact = SimpleNamespace(
        property_preferences=None, municipality=None, district=None,
        budget_min=None, budget_max=None,
    )
    lead = SimpleNamespace(title="Moradia", property_type=None, municipality=None,
        district=None, property_data={})
    assert score_client_property(contact, lead)["score"] == 0
