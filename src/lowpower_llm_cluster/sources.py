# src/lowpower_llm_cluster/sources.py
from __future__ import annotations

import base64
import json
import os
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin

import httpx

from .apple_resolution import resolve_apple_configuration
from .identity_extraction import enrich_hardware_identity, extract_marketplace_condition_evidence, extract_seller_firmware_evidence
from .market import DiscoveryAdapter, Listing, _now
from .quota import ProviderQuotaHistory
from .structured_identity import extract_structured_identity, structured_property_pairs

DEFAULT_TIMEOUT = httpx.Timeout(20.0, connect=10.0)
USER_AGENT = "LowPowerLLMCluster/0.6 (+https://github.com/hasnocool/LowPowerLLMCluster)"
_PROVIDER_QUOTAS = ProviderQuotaHistory()


async def _capture_quota(provider: str, response: httpx.Response) -> None:
    """Persist quota headers only when a provider actually exposes recognizable quota metadata."""
    await _PROVIDER_QUOTAS.observe(provider, response.headers)


def _float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _first_price_break(items: list[dict[str, Any]] | None) -> float | None:
    values: list[float] = []
    for item in items or []:
        price = _float(item.get("Price") or item.get("UnitPrice") or item.get("price"))
        if price is not None:
            values.append(price)
    return min(values) if values else None


def _manufacturer_name(value: Any) -> str | None:
    if isinstance(value, dict):
        value = value.get("Name") or value.get("name") or value.get("Value") or value.get("value")
    text = str(value or "").strip()
    return text or None


class JsonLdCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__()
        self._capture = False
        self._chunks: list[str] = []
        self.documents: list[Any] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        values = {k.casefold(): (v or "") for k, v in attrs}
        if tag.casefold() == "script" and values.get("type", "").casefold() == "application/ld+json":
            self._capture = True
            self._chunks = []

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._chunks.append(data)

    def handle_endtag(self, tag: str) -> None:
        if tag.casefold() != "script" or not self._capture:
            return
        self._capture = False
        raw = "".join(self._chunks).strip()
        if raw:
            try:
                self.documents.append(json.loads(raw))
            except json.JSONDecodeError:
                pass


def _jsonld_nodes(document: Any) -> list[dict[str, Any]]:
    if isinstance(document, list):
        nodes: list[dict[str, Any]] = []
        for item in document:
            nodes.extend(_jsonld_nodes(item))
        return nodes
    if not isinstance(document, dict):
        return []
    nodes = [document]
    graph = document.get("@graph")
    if isinstance(graph, list):
        nodes.extend(item for item in graph if isinstance(item, dict))
    return nodes


class ManufacturerJsonLdAdapter(DiscoveryAdapter):
    """Public manufacturer product pages exposing schema.org Product/Offer JSON-LD."""

    def __init__(self, urls: list[str], *, name: str = "manufacturer-jsonld") -> None:
        self.urls = urls
        self.name = name

    async def discover(self, queries: list[str]) -> list[Listing]:
        listings: list[Listing] = []
        needles = [query.casefold() for query in queries if query.strip()]
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, follow_redirects=True, headers={"User-Agent": USER_AGENT}) as client:
            for url in self.urls:
                response = await client.get(url)
                await _capture_quota(self.name, response)
                response.raise_for_status()
                collector = JsonLdCollector()
                collector.feed(response.text)
                for document in collector.documents:
                    for node in _jsonld_nodes(document):
                        types = node.get("@type")
                        type_set = {types} if isinstance(types, str) else set(types or [])
                        if "Product" not in type_set:
                            continue
                        title = str(node.get("name") or "").strip()
                        if needles and not any(needle in title.casefold() for needle in needles):
                            continue
                        offers = node.get("offers")
                        offer_list = offers if isinstance(offers, list) else [offers] if isinstance(offers, dict) else []
                        for index, offer in enumerate(offer_list):
                            price = _float(offer.get("price") or offer.get("lowPrice"))
                            currency = str(offer.get("priceCurrency") or "").upper()
                            if price is None or not currency:
                                continue
                            product_url = str(offer.get("url") or node.get("url") or response.url)
                            availability = str(offer.get("availability") or "").rsplit("/", 1)[-1] or None
                            sku = node.get("sku") or node.get("mpn")
                            brand = _manufacturer_name(node.get("brand") or node.get("manufacturer"))
                            configuration = {"manufacturer": brand, "mpn": str(node.get("mpn") or sku or "") or None}
                            configuration = extract_structured_identity(structured_property_pairs(node), existing=configuration)
                            configuration = resolve_apple_configuration(title, existing=configuration)
                            listings.append(
                                Listing(
                                    source=self.name,
                                    source_id=f"{url}#{sku or index}",
                                    url=urljoin(str(response.url), product_url),
                                    title=title,
                                    price=price,
                                    currency=currency,
                                    observed_at=_now(),
                                    seller=str(brand or response.url.host),
                                    sku=str(sku) if sku else None,
                                    configuration=configuration,
                                    availability=availability,
                                    source_kind="manufacturer",
                                    seller_metrics={"verified_source": True},
                                )
                            )
        return listings


class MouserAdapter(DiscoveryAdapter):
    name = "mouser"

    def __init__(self, api_key: str | None = None, *, results: int = 25) -> None:
        self.api_key = api_key or os.getenv("MOUSER_API_KEY")
        self.results = min(max(results, 1), 50)

    @property
    def enabled(self) -> bool:
        return bool(self.api_key)

    async def discover(self, queries: list[str]) -> list[Listing]:
        if not self.enabled:
            return []
        output: list[Listing] = []
        endpoint = "https://api.mouser.com/api/v1/search/keyword"
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
            for query in queries:
                response = await client.post(
                    endpoint,
                    params={"apiKey": self.api_key},
                    json={"SearchByKeywordRequest": {"keyword": query, "records": self.results, "startingRecord": 0, "searchOptions": "", "searchWithYourSignUpLanguage": ""}},
                )
                await _capture_quota(self.name, response)
                response.raise_for_status()
                payload = response.json()
                parts = ((payload.get("SearchResults") or {}).get("Parts") or [])
                for part in parts:
                    price = _first_price_break(part.get("PriceBreaks"))
                    if price is None:
                        continue
                    currency = str(part.get("Currency") or "USD").upper()
                    part_number = str(part.get("ManufacturerPartNumber") or part.get("MouserPartNumber") or "")
                    manufacturer = _manufacturer_name(part.get("Manufacturer"))
                    configuration = {"manufacturer": manufacturer, "mpn": part_number or None, "distributor_part_number": part.get("MouserPartNumber")}
                    configuration = extract_structured_identity(
                        structured_property_pairs(part.get("ProductAttributes"), part.get("Specifications"), part),
                        existing=configuration,
                    )
                    output.append(
                        Listing(
                            source=self.name,
                            source_id=str(part.get("MouserPartNumber") or part_number),
                            url=str(part.get("ProductDetailUrl") or "https://www.mouser.ca/"),
                            title=str(part.get("Description") or part_number),
                            price=price,
                            currency=currency,
                            observed_at=_now(),
                            seller="Mouser Electronics",
                            sku=part_number or None,
                            configuration=configuration,
                            availability=str(part.get("Availability") or "") or None,
                            source_kind="authorized_distributor",
                            seller_metrics={"verified_source": True, "lifecycle": part.get("LifecycleStatus")},
                        )
                    )
        return output


class DigiKeyAdapter(DiscoveryAdapter):
    """DigiKey Product Information V4 using an externally obtained OAuth token."""

    name = "digikey"

    def __init__(self, client_id: str | None = None, access_token: str | None = None, *, site: str = "CA", currency: str = "CAD", limit: int = 25) -> None:
        self.client_id = client_id or os.getenv("DIGIKEY_CLIENT_ID")
        self.access_token = access_token or os.getenv("DIGIKEY_ACCESS_TOKEN")
        self.site = site
        self.currency = currency
        self.limit = limit

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.access_token)

    async def discover(self, queries: list[str]) -> list[Listing]:
        if not self.enabled:
            return []
        endpoint = "https://api.digikey.com/products/v4/search/keyword"
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-DIGIKEY-Client-Id": str(self.client_id),
            "X-DIGIKEY-Locale-Site": self.site,
            "X-DIGIKEY-Locale-Language": "en",
            "X-DIGIKEY-Locale-Currency": self.currency,
            "User-Agent": USER_AGENT,
        }
        output: list[Listing] = []
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers=headers) as client:
            for query in queries:
                response = await client.post(endpoint, json={"Keywords": query, "Limit": self.limit, "Offset": 0})
                await _capture_quota(self.name, response)
                response.raise_for_status()
                payload = response.json()
                products = payload.get("Products") or payload.get("products") or []
                for product in products:
                    variations = product.get("ProductVariations") or product.get("productVariations") or []
                    price = None
                    for variation in variations:
                        price = price or _first_price_break(variation.get("StandardPricing") or variation.get("standardPricing"))
                    if price is None:
                        continue
                    product_number = str(product.get("ManufacturerProductNumber") or product.get("manufacturerProductNumber") or product.get("DigiKeyProductNumber") or "")
                    manufacturer = _manufacturer_name(product.get("Manufacturer") or product.get("manufacturer"))
                    description = product.get("Description") or product.get("description") or {}
                    if isinstance(description, dict):
                        description = description.get("ProductDescription") or description.get("productDescription")
                    url = str(product.get("ProductUrl") or product.get("productUrl") or "https://www.digikey.ca/")
                    configuration = {"manufacturer": manufacturer, "mpn": product_number or None, "distributor_part_number": product.get("DigiKeyProductNumber") or product.get("digiKeyProductNumber")}
                    configuration = extract_structured_identity(
                        structured_property_pairs(product.get("Parameters"), product.get("parameters"), product),
                        existing=configuration,
                    )
                    output.append(
                        Listing(
                            source=self.name,
                            source_id=str(product.get("DigiKeyProductNumber") or product.get("digiKeyProductNumber") or product_number),
                            url=url,
                            title=str(description or product_number),
                            price=price,
                            currency=self.currency,
                            observed_at=_now(),
                            seller="DigiKey",
                            sku=product_number or None,
                            configuration=configuration,
                            availability=str(product.get("QuantityAvailable") or product.get("quantityAvailable") or "") or None,
                            source_kind="authorized_distributor",
                            seller_metrics={"verified_source": True},
                        )
                    )
        return output


class EbayBrowseAdapter(DiscoveryAdapter):
    name = "ebay-ca"

    def __init__(self, client_id: str | None = None, client_secret: str | None = None, *, marketplace: str = "EBAY_CA", limit: int = 50) -> None:
        self.client_id = client_id or os.getenv("EBAY_CLIENT_ID")
        self.client_secret = client_secret or os.getenv("EBAY_CLIENT_SECRET")
        self.marketplace = marketplace
        self.limit = min(max(limit, 1), 200)

    @property
    def enabled(self) -> bool:
        return bool(self.client_id and self.client_secret)

    async def _token(self, client: httpx.AsyncClient) -> str:
        credentials = base64.b64encode(f"{self.client_id}:{self.client_secret}".encode()).decode()
        response = await client.post(
            "https://api.ebay.com/identity/v1/oauth2/token",
            headers={"Authorization": f"Basic {credentials}", "Content-Type": "application/x-www-form-urlencoded"},
            data={"grant_type": "client_credentials", "scope": "https://api.ebay.com/oauth/api_scope"},
        )
        await _capture_quota("ebay-oauth", response)
        response.raise_for_status()
        return str(response.json()["access_token"])

    async def discover(self, queries: list[str]) -> list[Listing]:
        if not self.enabled:
            return []
        output: list[Listing] = []
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT, headers={"User-Agent": USER_AGENT}) as client:
            token = await self._token(client)
            headers = {
                "Authorization": f"Bearer {token}",
                "X-EBAY-C-MARKETPLACE-ID": self.marketplace,
                "X-EBAY-C-ENDUSERCTX": "contextualLocation=country%3DCA",
            }
            for query in queries:
                response = await client.get(
                    "https://api.ebay.com/buy/browse/v1/item_summary/search",
                    params={"q": query, "limit": self.limit, "fieldgroups": "EXTENDED"},
                    headers=headers,
                )
                await _capture_quota(self.name, response)
                response.raise_for_status()
                payload = response.json()
                for item in payload.get("itemSummaries", []):
                    price_data = item.get("price") or {}
                    price = _float(price_data.get("value"))
                    if price is None:
                        continue
                    seller = item.get("seller") or {}
                    shipping_options = item.get("shippingOptions") or []
                    shipping = None
                    shipping_currency = None
                    for option in shipping_options:
                        cost = option.get("shippingCost") or {}
                        parsed = _float(cost.get("value"))
                        if parsed is not None and (shipping is None or parsed < shipping):
                            shipping = parsed
                            shipping_currency = cost.get("currency")
                    source_id = str(item.get("itemId") or item.get("legacyItemId") or item.get("itemWebUrl"))
                    title = str(item.get("title") or "")
                    description = str(item.get("shortDescription") or "")
                    configuration = resolve_apple_configuration(title, description=description, existing={})
                    configuration = extract_structured_identity(
                        structured_property_pairs(item.get("localizedAspects"), item.get("aspects")),
                        existing=configuration,
                    )
                    combined_text = f"{title} {description}".strip()
                    configuration = enrich_hardware_identity(combined_text, existing=configuration)
                    seller_fw = extract_seller_firmware_evidence(combined_text)
                    if seller_fw.get("board_revision") or seller_fw.get("installed_bios_version"):
                        configuration.setdefault("seller_firmware_evidence", seller_fw)
                        if seller_fw.get("board_revision"):
                            configuration.setdefault("board_revision", seller_fw["board_revision"])
                        if seller_fw.get("installed_bios_version"):
                            configuration.setdefault("installed_bios_version", seller_fw["installed_bios_version"])
                    condition_evidence = extract_marketplace_condition_evidence(combined_text)
                    if condition_evidence.get("confidence") != "unknown":
                        configuration.setdefault("seller_condition_evidence", condition_evidence)
                    structured_condition = {
                        "condition": item.get("condition"),
                        "condition_id": item.get("conditionId"),
                        "return_terms": item.get("returnTerms"),
                        "source_type": "structured_marketplace",
                    }
                    if any(structured_condition.get(key) not in (None, "", {}, []) for key in ("condition", "condition_id", "return_terms")):
                        configuration.setdefault("marketplace_condition", structured_condition)
                    output.append(
                        Listing(
                            source=self.name,
                            source_id=source_id,
                            url=str(item.get("itemWebUrl") or item.get("itemHref") or ""),
                            title=title,
                            price=price,
                            currency=str(price_data.get("currency") or "CAD").upper(),
                            observed_at=_now(),
                            seller=str(seller.get("username") or seller.get("userId") or "") or None,
                            sku=configuration.get("apple_part_number") or configuration.get("model_identifier") or configuration.get("apple_a_number") or configuration.get("device_sku"),
                            configuration=configuration,
                            shipping=shipping,
                            shipping_currency=str(shipping_currency or price_data.get("currency") or "CAD").upper(),
                            destination_country="CA",
                            availability=str(item.get("itemEndDate") or "active"),
                            source_kind="structured_marketplace",
                            seller_metrics={
                                "feedback_percentage": _float(seller.get("feedbackPercentage")),
                                "feedback_score": _float(seller.get("feedbackScore")),
                                "top_rated": bool(item.get("topRatedBuyingExperience")),
                                "seller_account_type": seller.get("sellerAccountType"),
                            },
                        )
                    )
        return output
