"""Deterministic, explainable matching between CRM clients and property leads.

Matching is computed from current PostgreSQL rows on demand. It never sends
communications and never treats a discovered lead as proof of ownership.
"""
from __future__ import annotations

import re
import unicodedata
from typing import Any

from app.models.contact import Contact
from app.models.entities import Lead


def _normalise(value: Any) -> str:
    if value is None:
        return ""
    text = unicodedata.normalize("NFKD", str(value))
    text = "".join(ch for ch in text if not unicodedata.combining(ch))
    return re.sub(r"\s+", " ", re.sub(r"[^a-z0-9]+", " ", text.lower())).strip()


def _number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    raw = re.sub(r"[^0-9,.]", "", str(value))
    if not raw:
        return None
    # Portuguese listings commonly use 350.000 or 350 000 for thousands.
    if "," in raw and "." in raw:
        if raw.rfind(",") > raw.rfind("."):
            raw = raw.replace(".", "").replace(",", ".")
        else:
            raw = raw.replace(",", "")
    elif "," in raw:
        tail = raw.rsplit(",", 1)[-1]
        raw = raw.replace(",", ".") if len(tail) <= 2 else raw.replace(",", "")
    elif "." in raw:
        tail = raw.rsplit(".", 1)[-1]
        if len(tail) != 2:
            raw = raw.replace(".", "")
    try:
        return float(raw)
    except ValueError:
        return None


def _data(lead: Lead) -> dict:
    return lead.property_data if isinstance(lead.property_data, dict) else {}


def _first(data: dict, *keys: str):
    for key in keys:
        value = data.get(key)
        if value not in (None, ""):
            return value
    return None


def _property_facts(lead: Lead) -> dict:
    data = _data(lead)
    title = lead.title or ""
    description = str(_first(data, "description", "summary", "features") or "")
    price = _number(_first(data, "price", "asking_price", "sale_price", "rent_price"))
    if price is None:
        price = _number(re.search(r"([0-9][0-9., ]{2,})\s*€", title + " " + description).group(1)) if re.search(r"([0-9][0-9., ]{2,})\s*€", title + " " + description, re.I) else None
    bedrooms = _number(_first(data, "bedrooms", "rooms", "room_count", "typology_rooms"))
    if bedrooms is None:
        found = re.search(r"\bt\s*([0-9])\b", _normalise(title + " " + description))
        if found:
            bedrooms = float(found.group(1))
    area = _number(_first(data, "area", "area_m2", "gross_area", "useful_area", "size"))
    kind = _normalise(lead.property_type or _first(data, "property_type", "type") or title)
    operation = _normalise(_first(data, "operation", "transaction_type", "listing_type") or title + " " + description)
    municipality = _normalise(lead.municipality or _first(data, "municipality", "city", "locality"))
    district = _normalise(lead.district or _first(data, "district", "region"))
    return {
        "price": price, "bedrooms": bedrooms, "area": area, "kind": kind,
        "operation": operation, "municipality": municipality, "district": district,
        "title": title, "description": description,
    }


def _client_facts(contact: Contact) -> dict:
    preferences = _normalise(contact.property_preferences or "")
    return {
        "preferences": preferences,
        "municipality": _normalise(contact.municipality),
        "district": _normalise(contact.district),
        "budget_min": _number(contact.budget_min),
        "budget_max": _number(contact.budget_max),
    }


def score_client_property(contact: Contact, lead: Lead) -> dict:
    """Return a 0..100 score and auditable reasons; unknown fields are not penalised."""
    client = _client_facts(contact)
    prop = _property_facts(lead)
    score = 0.0
    weight = 0.0
    matched: list[str] = []
    missing: list[str] = []

    # Location: municipality is strongest, district is a useful fallback.
    if client["municipality"]:
        weight += 30
        if prop["municipality"] and (
            client["municipality"] == prop["municipality"]
            or client["municipality"] in prop["municipality"]
            or prop["municipality"] in client["municipality"]
        ):
            score += 30
            matched.append("municipality")
        else:
            missing.append("municipality")
    elif client["district"]:
        weight += 20
        if prop["district"] and (client["district"] == prop["district"] or client["district"] in prop["district"]):
            score += 20
            matched.append("district")
        else:
            missing.append("district")

    # Budget: use the contact's stated range and the listing's structured/visible price.
    if client["budget_min"] is not None or client["budget_max"] is not None:
        weight += 30
        if prop["price"] is not None:
            low = client["budget_min"] if client["budget_min"] is not None else 0
            high = client["budget_max"] if client["budget_max"] is not None else float("inf")
            if low <= prop["price"] <= high:
                score += 30
                matched.append("budget")
            else:
                # A small, explainable partial score for listings up to 10% outside the range.
                boundary = low if prop["price"] < low else high
                distance = abs(prop["price"] - boundary) / max(boundary, 1)
                if distance <= 0.10:
                    score += 15
                    matched.append("budget_near")
                else:
                    missing.append("budget")
        else:
            missing.append("price")

    # Property type is matched by meaningful tokens, not by an LLM guess.
    type_terms = {"apartamento": {"apartamento", "apartments", "flat"}, "moradia": {"moradia", "casa", "house"}, "terreno": {"terreno", "lote", "land"}, "quarto": {"quarto", "room"}}
    requested_types = {term for term, variants in type_terms.items() if any(v in client["preferences"] for v in variants)}
    if requested_types:
        weight += 15
        if any(term in prop["kind"] for term in requested_types):
            score += 15
            matched.append("property_type")
        else:
            missing.append("property_type")

    requested_bedrooms = re.search(r"\bt\s*([1-9])\b|\b([1-9])\s*quartos?\b", client["preferences"])
    if requested_bedrooms:
        requested = float(requested_bedrooms.group(1) or requested_bedrooms.group(2))
        weight += 15
        if prop["bedrooms"] is not None and prop["bedrooms"] == requested:
            score += 15
            matched.append("bedrooms")
        elif prop["bedrooms"] is not None:
            missing.append("bedrooms")
        else:
            missing.append("bedrooms_unknown")

    area_range = re.search(r"\b(\d{2,4})\s*(?:a|ate|-)\s*(\d{2,4})\s*m2\b", client["preferences"])
    area_single = re.search(r"\b(\d{2,4})\s*m2\b", client["preferences"])
    if area_range or area_single:
        weight += 10
        if prop["area"] is not None:
            if area_range:
                low_area, high_area = sorted((float(area_range.group(1)), float(area_range.group(2))))
            else:
                low_area = float(area_single.group(1))
                high_area = float("inf")
            if low_area <= prop["area"] <= high_area:
                score += 10
                matched.append("area")
            else:
                missing.append("area")
        else:
            missing.append("area_unknown")

    # If a client explicitly states buy/rent, compare it with the listing operation.
    wants_rent = any(word in client["preferences"] for word in ("arrendar", "arrendamento", "alugar", "rent"))
    wants_buy = any(word in client["preferences"] for word in ("comprar", "compra", "buy"))
    if wants_rent or wants_buy:
        weight += 10
        operation_matches = ("rent" in prop["operation"] or "arrend" in prop["operation"] or "alug" in prop["operation"]) if wants_rent else ("sale" in prop["operation"] or "vend" in prop["operation"] or "compr" in prop["operation"])
        if operation_matches:
            score += 10
            matched.append("operation")
        else:
            missing.append("operation")

    # No criteria means no meaningful match, rather than an arbitrary high score.
    percentage = round((score / weight) * 100) if weight else 0
    return {
        "score": max(0, min(100, percentage)),
        "matched_on": matched,
        "missing_or_mismatched": missing,
        "explanation": _explain(matched, missing),
    }


def _explain(matched: list[str], missing: list[str]) -> str:
    labels = {
        "municipality": "localização", "district": "distrito", "budget": "orçamento",
        "budget_near": "orçamento próximo", "property_type": "tipo de imóvel",
        "bedrooms": "tipologia", "area": "área", "operation": "tipo de operação",
    }
    positives = [labels.get(item, item) for item in matched]
    gaps = [labels.get(item, item) for item in missing if not item.endswith("_unknown")]
    parts = []
    if positives:
        parts.append("Compatível em " + ", ".join(positives))
    if gaps:
        parts.append("a confirmar: " + ", ".join(gaps))
    return "; ".join(parts) if parts else "Dados insuficientes para uma correspondência fiável."


def property_payload(lead: Lead, match: dict) -> dict:
    data = _data(lead)
    return {
        "lead_id": lead.id, "title": lead.title, "property_type": lead.property_type,
        "address": lead.address, "municipality": lead.municipality, "district": lead.district,
        "source_url": lead.source_url, "price": _first(data, "price", "asking_price", "sale_price", "rent_price"),
        "area": _first(data, "area", "area_m2", "gross_area", "useful_area", "size"),
        "bedrooms": _first(data, "bedrooms", "rooms", "room_count", "typology_rooms"),
        **match,
    }
