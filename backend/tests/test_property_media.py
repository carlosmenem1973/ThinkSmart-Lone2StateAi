from app.services import property_media


def test_geocode_only_uses_published_address(monkeypatch):
    called = []
    monkeypatch.setattr(property_media, "_geocode_cache", {})
    monkeypatch.setattr(property_media, "geocode_verified_address", lambda address: called.append(address))
    result = property_media.extract_property_preview(
        "https://example.com/listing/1", "Apartamento T2", "Anúncio de teste"
    )
    assert result["latitude"] is None
    assert result["longitude"] is None
    assert result["location_precision"] is None
    assert called == []


def test_extracts_lazy_loaded_images_and_structured_coordinates(monkeypatch):
    html = b"""
    <html><head><title>Imovel</title>
    <script type="application/ld+json">
    {"@type":"Apartment","name":"T2","address":{"streetAddress":"Rua Exemplo 10","addressLocality":"Alges"},"geo":{"latitude":38.7,"longitude":-9.2}}
    </script></head><body>
    <img data-src="/images/photo-1.jpg" alt="Sala">
    <img data-srcset="/images/photo-2.jpg 800w, /images/photo-small.jpg 300w">
    </body></html>
    """
    monkeypatch.setattr(property_media, "public_url", lambda url: url)
    monkeypatch.setattr(property_media, "bounded_get", lambda *args, **kwargs: (html, "text/html", "https://example.com/listing/1"))
    monkeypatch.setattr(property_media, "geocode_verified_address", lambda address: None)
    result = property_media.extract_property_preview(
        "https://example.com/listing/1", "Apartamento T2", "T2 em Algés"
    )
    assert result["image_url"] == "https://example.com/images/photo-1.jpg"
    assert "https://example.com/images/photo-2.jpg" in result["image_urls"]
    assert result["latitude"] == 38.7
    assert result["longitude"] == -9.2
    assert result["location_precision"] == "listing_coordinates"


def test_address_geocode_is_marked_as_approximate(monkeypatch):
    html = b'<html><head><meta property="og:title" content="T2"></head><body></body></html>'
    monkeypatch.setattr(property_media, "public_url", lambda url: url)
    monkeypatch.setattr(property_media, "bounded_get", lambda *args, **kwargs: (html, "text/html", "https://example.com/listing/1"))
    monkeypatch.setattr(property_media, "geocode_verified_address", lambda address: (38.7, -9.2) if address else None)
    # Inject the structured address through the HTML JSON-LD data.
    html_with_address = b'<script type="application/ld+json">{"@type":"Apartment","address":{"streetAddress":"Rua Exemplo 10","addressLocality":"Alges"}}</script>'
    monkeypatch.setattr(property_media, "bounded_get", lambda *args, **kwargs: (html_with_address, "text/html", "https://example.com/listing/1"))
    result = property_media.extract_property_preview("https://example.com/listing/1", "T2", "T2")
    assert result["latitude"] == 38.7
    assert result["longitude"] == -9.2
    assert result["location_precision"] == "address_geocoded"
    assert result["map_location_source"] == "nominatim"
