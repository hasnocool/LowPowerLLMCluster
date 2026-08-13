from __future__ import annotations

import json
import re
from pathlib import Path
from urllib.parse import urlparse

CONFIG = Path(__file__).resolve().parents[1] / "config" / "discovery.example.json"
PUBLIC_TYPES = {"html_index", "sitemap", "feed", "announcement_index"}


def _config() -> dict:
    return json.loads(CONFIG.read_text(encoding="utf-8"))


def test_public_source_pool_is_broad_unique_and_bounded() -> None:
    sources = list(_config()["sources"])
    names = [str(source["name"]) for source in sources]
    assert len(names) == len(set(names))
    public = [source for source in sources if source.get("type") in PUBLIC_TYPES]
    assert len(public) >= 30
    for source in public:
        assert source.get("same_host") is True
        assert source.get("seeds")
        assert source.get("include_patterns")
        assert 1 <= int(source.get("max_index_pages", 0)) <= 8
        assert 1 <= int(source.get("max_candidate_pages", 0)) <= 200
        assert 1 <= int(source.get("subworkers", 0)) <= 4
        for seed in source["seeds"]:
            parsed = urlparse(seed)
            assert parsed.scheme == "https"
            assert parsed.netloc


def test_public_sources_do_not_require_credentials() -> None:
    forbidden = ("api_key", "apikey", "credential", "access_token", "client_secret", "password")
    for source in _config()["sources"]:
        if source.get("type") in PUBLIC_TYPES:
            serialized = json.dumps(source).lower()
            assert not any(fragment in serialized for fragment in forbidden)


def test_announcement_sources_are_explicitly_bounded() -> None:
    announcements = [source for source in _config()["sources"] if source.get("type") == "announcement_index"]
    assert {source["name"] for source in announcements} >= {
        "linuxgizmos-announcements",
        "cnx-software-announcements",
        "hackster-hardware-announcements",
        "servethehome-announcements",
        "phoronix-hardware-announcements",
    }
    for source in announcements:
        assert int(source["max_candidate_pages"]) <= 30
        assert float(source["source_trust"]) < 0.7


def test_representative_urls_match_configured_patterns() -> None:
    sources = {source["name"]: source for source in _config()["sources"]}
    examples = {
        "best-buy-ca-public": "https://www.bestbuy.ca/en-ca/product/pny-geforce-rtx-5070-oc-12gb-gddr7-video-card/18934175",
        "newegg-ca-public": "https://www.newegg.ca/asus-prime-rtx5060ti-16g-geforce-rtx-5060-ti-16gb-graphics-card-triple-fans/p/N82E16814126791?Item=N82E16814126791",
        "radxa-products-public": "https://radxa.com/products/rock5/5itxp/",
        "hardkernel-odroid-public": "https://www.hardkernel.com/shop/odroid-h5/",
        "pine64-sbc-public": "https://pine64.com/product/quartz64-model-a-4gb-single-board-computer/",
        "orange-pi-public": "https://www.orangepi.org/html/hardWare/computerAndMicrocontrollers/details/Orange-Pi-5-Max.html",
        "banana-pi-public": "https://www.banana-pi.org/en/banana-pi-sbcs/169.html",
        "asrock-industrial-public": "https://www.asrockind.com/en-gb/4X4-8840U",
        "linuxgizmos-announcements": "https://linuxgizmos.com/aicore-dx-m1m-module-provides-25-tops-edge-ai-acceleration-in-m-2-form-factor/",
        "cnx-software-announcements": "https://www.cnx-software.com/2026/07/28/example-edge-ai-board/",
    }
    for name, url in examples.items():
        patterns = [re.compile(value, re.I) for value in sources[name]["include_patterns"]]
        assert any(pattern.search(url) for pattern in patterns), (name, url)
