# tests/test_sources.py
from lowpower_llm_cluster.sources import JsonLdCollector, _first_price_break, _jsonld_nodes


def test_jsonld_collector_extracts_product_offer():
    html = '''<html><script type="application/ld+json">{"@type":"Product","name":"Example Board","sku":"ABC-1","offers":{"@type":"Offer","price":"199.99","priceCurrency":"USD"}}</script></html>'''
    collector = JsonLdCollector(); collector.feed(html)
    assert collector.documents
    nodes = _jsonld_nodes(collector.documents[0])
    product = next(node for node in nodes if node.get("@type") == "Product")
    assert product["sku"] == "ABC-1"
    assert product["offers"]["price"] == "199.99"


def test_price_break_parser_uses_lowest_numeric_price():
    assert _first_price_break([{"Price": "2.50"}, {"UnitPrice": 1.75}]) == 1.75
