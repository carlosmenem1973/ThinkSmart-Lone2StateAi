"""Extract real listing images and provide bounded Bedrock image analysis."""
from __future__ import annotations

import ipaddress
import json
import socket
import threading
import time
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from botocore.exceptions import BotoCoreError, ClientError

from app.core.config import settings
from app.services.ai import AIUnavailable, bedrock_runtime_client

TIMEOUT = httpx.Timeout(6.0, connect=3.0)
MAX_HTML = 1_500_000
MAX_IMAGE = 4_500_000
USER_AGENT = "ThinkSmartAI-PropertyPreview/1.0 (+https://thinksmart.pt)"
GEOCODER_USER_AGENT = "ThinkSmartAI/1.0 (https://thinksmart.pt; property-search)"
_geocode_lock = threading.Lock()
_geocode_last_request = 0.0
_geocode_cache: dict[str, tuple[float, float] | None] = {}
IMAGE_FORMATS = {"image/jpeg": "jpeg", "image/png": "png", "image/webp": "webp", "image/gif": "gif"}


def public_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname or parsed.username or parsed.password:
        raise ValueError("Only public HTTP(S) URLs are allowed.")
    host = parsed.hostname.rstrip(".").lower()
    if host in {"localhost", "localhost.localdomain"}:
        raise ValueError("Local hosts are not allowed.")
    addresses = {entry[4][0] for entry in socket.getaddrinfo(host, parsed.port or (443 if parsed.scheme == "https" else 80), type=socket.SOCK_STREAM)}
    if not addresses or any(not ipaddress.ip_address(ip.split("%", 1)[0]).is_global for ip in addresses):
        raise ValueError("Private or non-public network destinations are not allowed.")
    return value


def bounded_get(url: str, limit: int, prefix: str):
    current = url
    with httpx.Client(timeout=TIMEOUT, follow_redirects=False, trust_env=False, headers={"User-Agent": USER_AGENT, "Accept": "*/*"}) as client:
        for _ in range(4):
            current = public_url(current)
            with client.stream("GET", current) as response:
                if response.is_redirect:
                    location = response.headers.get("location")
                    if not location:
                        raise ValueError("Invalid redirect.")
                    current = urljoin(current, location)
                    continue
                response.raise_for_status()
                content_type = response.headers.get("content-type", "").split(";", 1)[0].lower().strip()
                if not content_type.startswith(prefix):
                    raise ValueError("Unexpected content type.")
                length = response.headers.get("content-length")
                if length and int(length) > limit:
                    raise ValueError("Resource exceeds size limit.")
                chunks = []
                size = 0
                for chunk in response.iter_bytes():
                    size += len(chunk)
                    if size > limit:
                        raise ValueError("Resource exceeds size limit.")
                    chunks.append(chunk)
                return b"".join(chunks), content_type, str(response.url)
    raise ValueError("Too many redirects.")


def walk_jsonld(value):
    if isinstance(value, dict):
        yield value
        for child in value.values():
            yield from walk_jsonld(child)
    elif isinstance(value, list):
        for child in value:
            yield from walk_jsonld(child)


def first_text(*values):
    for value in values:
        if isinstance(value, str) and value.strip():
            return value.strip()
        if isinstance(value, (int, float)):
            return str(value)
    return None



def geocode_verified_address(address: str | None) -> tuple[float, float] | None:
    """Resolve a published listing address only; never geocode a title or guess a location."""
    global _geocode_last_request
    if not address or len(address.strip()) < 8:
        return None
    query = address.strip()[:300]
    if query in _geocode_cache:
        return _geocode_cache[query]
    # Nominatim public service policy: keep requests serial and at most one per second.
    with _geocode_lock:
        if query in _geocode_cache:
            return _geocode_cache[query]
        wait = 1.05 - (time.monotonic() - _geocode_last_request)
        if wait > 0:
            time.sleep(wait)
        try:
            with httpx.Client(timeout=httpx.Timeout(5.0, connect=3.0), trust_env=False,
                              headers={"User-Agent": GEOCODER_USER_AGENT, "Accept": "application/json"}) as client:
                response = client.get("https://nominatim.openstreetmap.org/search",
                                      params={"q": query, "format": "jsonv2", "limit": 1, "addressdetails": 1})
                _geocode_last_request = time.monotonic()
                response.raise_for_status()
                results = response.json()
            if not results:
                _geocode_cache[query] = None
                return None
            latitude, longitude = float(results[0]["lat"]), float(results[0]["lon"])
            if not (-90 <= latitude <= 90 and -180 <= longitude <= 180):
                _geocode_cache[query] = None
                return None
            _geocode_cache[query] = (latitude, longitude)
            return latitude, longitude
        except (httpx.HTTPError, OSError, ValueError, KeyError, TypeError):
            _geocode_cache[query] = None
            return None


def extract_property_preview(url: str, title: str, snippet: str) -> dict:
    item = {
        "title": title[:300], "url": url, "description": snippet[:1200],
        "image_url": None, "image_urls": [], "price": None, "currency": None, "address": None,
        "latitude": None, "longitude": None, "property_type": None,
        "source_name": urlparse(url).hostname or "Fonte externa",
        "image_attribution_url": url, "location_precision": None, "map_location_source": None,
    }
    try:
        body, _, final_url = bounded_get(url, MAX_HTML, "text/")
        soup = BeautifulSoup(body, "html.parser")
        item["url"] = final_url
        og_title = soup.find("meta", property="og:title")
        og_description = soup.find("meta", property="og:description")
        og_image = soup.find("meta", property="og:image")
        twitter_image = soup.find("meta", attrs={"name": "twitter:image"})
        item["title"] = first_text(og_title.get("content") if og_title else None, soup.title.string if soup.title and soup.title.string else None, title)[:300]
        item["description"] = first_text(og_description.get("content") if og_description else None, snippet)[:1200]
        image_candidates = []
        for meta in soup.find_all("meta", property="og:image") + soup.find_all("meta", attrs={"name": "twitter:image"}):
            candidate = meta.get("content")
            if candidate:
                image_candidates.append(candidate)
        # Property portals frequently expose images through lazy-loaded img attributes.
        for image in soup.find_all("img"):
            for raw_image in (image.get("src"), image.get("data-src"), image.get("data-lazy-src"), image.get("data-original")):
                if raw_image:
                    image_candidates.append(raw_image)
            srcset = image.get("srcset") or image.get("data-srcset")
            if srcset:
                image_candidates.extend(part.strip().split(" ", 1)[0] for part in srcset.split(",") if part.strip())
        for raw_image in image_candidates:
            try:
                safe_image = public_url(urljoin(final_url, raw_image))
                if safe_image not in item["image_urls"] and len(item["image_urls"]) < 8:
                    item["image_urls"].append(safe_image)
            except (ValueError, TypeError):
                pass
        item["image_url"] = item["image_urls"][0] if item["image_urls"] else None
        for script in soup.find_all("script", attrs={"type": "application/ld+json"}):
            raw = script.string or script.get_text()
            if not raw or len(raw) > 500_000:
                continue
            try:
                data = json.loads(raw)
            except (TypeError, ValueError):
                continue
            for node in walk_jsonld(data):
                offers = node.get("offers") or {}
                if isinstance(offers, list):
                    offers = offers[0] if offers else {}
                address = node.get("address") or {}
                geo = node.get("geo") or {}
                if isinstance(address, dict):
                    address_text = ", ".join(filter(None, [
                        first_text(address.get("streetAddress")), first_text(address.get("postalCode")),
                        first_text(address.get("addressLocality")), first_text(address.get("addressRegion")),
                    ]))
                else:
                    address_text = address if isinstance(address, str) else None
                item["address"] = item["address"] or address_text
                if isinstance(offers, dict):
                    item["price"] = item["price"] or first_text(offers.get("price"))
                    item["currency"] = item["currency"] or first_text(offers.get("priceCurrency"))
                kind = node.get("@type")
                if isinstance(kind, list):
                    kind = " ".join(kind)
                item["property_type"] = item["property_type"] or first_text(node.get("name") if kind and any(t in str(kind) for t in ("Apartment", "House", "Residence")) else None)
                try:
                    item["latitude"] = item["latitude"] or (float(geo.get("latitude")) if geo.get("latitude") is not None else None)
                    item["longitude"] = item["longitude"] or (float(geo.get("longitude")) if geo.get("longitude") is not None else None)
                    if item["latitude"] is not None and item["longitude"] is not None:
                        item["location_precision"] = "listing_coordinates"
                        item["map_location_source"] = "listing"
                except (TypeError, ValueError):
                    pass
                images = node.get("image")
                if isinstance(images, (str, dict)):
                    images = [images]
                if isinstance(images, list):
                    for image in images:
                        raw = image.get("url") or image.get("contentUrl") if isinstance(image, dict) else image
                        if not isinstance(raw, str):
                            continue
                        try:
                            safe_image = public_url(urljoin(final_url, raw))
                            if safe_image not in item["image_urls"]:
                                item["image_urls"].append(safe_image)
                        except ValueError:
                            pass
                    item["image_url"] = item["image_urls"][0] if item["image_urls"] else None
    except (httpx.HTTPError, OSError, ValueError, TypeError):
        pass
    # Geocode only an address explicitly published by the listing. Do not infer from title or municipality.
    if item["latitude"] is None or item["longitude"] is None:
        coordinates = geocode_verified_address(item.get("address"))
        if coordinates:
            item["latitude"], item["longitude"] = coordinates
            item["location_precision"] = "address_geocoded"
            item["map_location_source"] = "nominatim"
    return item


def analyse_property_image(image_url: str, context: str = "") -> dict:
    if not settings.bedrock_vision_model_id.strip():
        raise AIUnavailable("BEDROCK_VISION_MODEL_ID não está configurado.")
    try:
        image_bytes, content_type, _ = bounded_get(image_url, MAX_IMAGE, "image/")
        image_format = IMAGE_FORMATS.get(content_type)
        if not image_format:
            raise ValueError("Only JPEG, PNG, WebP and GIF images can be analysed.")
        response = bedrock_runtime_client().converse(
            modelId=settings.bedrock_vision_model_id,
            system=[{"text": (
                "És um assistente de análise visual imobiliária em Portugal. Descreve apenas o que é "
                "visível. Não inventes área, medidas, localização, preço, estado estrutural, licenças "
                "ou características não observáveis. Não identifiques pessoas. Distingue observações "
                "de incertezas. Não faças avaliações financeiras ou inspeções técnicas. Responde em "
                "português europeu."
            )}],
            messages=[{"role": "user", "content": [
                {"text": ("Analisa esta fotografia de anúncio imobiliário. " + context[:1000]).strip()},
                {"image": {"format": image_format, "source": {"bytes": image_bytes}}},
            ]}],
            inferenceConfig={"maxTokens": 700, "temperature": 0.2},
        )
        blocks = response.get("output", {}).get("message", {}).get("content", [])
        analysis = "\n".join(block["text"] for block in blocks if isinstance(block, dict) and isinstance(block.get("text"), str)).strip()
        if not analysis:
            raise AIUnavailable("O modelo visual não devolveu uma análise.")
        return {"analysis": analysis, "model_id": settings.bedrock_vision_model_id, "image_source": image_url}
    except (ClientError, BotoCoreError) as exc:
        code = getattr(exc, "response", {}).get("Error", {}).get("Code", type(exc).__name__)
        raise AIUnavailable("Bedrock Vision não conseguiu analisar a fotografia (" + code + "). Confirme IAM para Nova 2 Lite.") from exc
    except (httpx.HTTPError, OSError, ValueError) as exc:
        raise AIUnavailable("Não foi possível obter uma fotografia pública válida (" + type(exc).__name__ + ").") from exc
