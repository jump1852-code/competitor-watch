from dataclasses import replace

from competitor_watch.detect import diff_snapshots, index
from competitor_watch.models import ChangeType, Product


def p(pid: str, price: float | None = 10.0, **kw) -> Product:
    return Product(
        id=pid, target="t", name=f"Item {pid}", url=f"https://x/{pid}", price=price, currency="USD", **kw
    )


def types(changes):
    return sorted((c.type.value, c.product_id) for c in changes)


def test_no_changes():
    snap = index([p("a"), p("b")])
    assert diff_snapshots(snap, snap, "now") == []


def test_new_and_removed():
    old = index([p("a"), p("b")])
    new = index([p("b"), p("c")])
    assert types(diff_snapshots(old, new, "now")) == [("new", "c"), ("removed", "a")]


def test_price_up_and_down_with_pct():
    old = index([p("a", 100.0), p("b", 50.0)])
    new = index([p("a", 110.0), p("b", 40.0)])
    changes = {c.product_id: c for c in diff_snapshots(old, new, "now")}
    assert changes["a"].type is ChangeType.PRICE_UP and changes["a"].pct_change == 10.0
    assert changes["b"].type is ChangeType.PRICE_DOWN and changes["b"].pct_change == -20.0


def test_float_noise_ignored():
    assert diff_snapshots(index([p("a", 10.0)]), index([p("a", 10.0001)]), "now") == []


def test_attribute_change_reports_before_after():
    a = p("a", availability="In stock")
    changes = diff_snapshots(index([a]), index([replace(a, availability="Out of stock")]), "now")
    assert len(changes) == 1
    assert changes[0].type is ChangeType.CHANGED
    assert changes[0].fields == {"availability": ["In stock", "Out of stock"]}


def test_change_roundtrip():
    from competitor_watch.models import Change

    c = diff_snapshots(index([p("a", 10)]), index([p("a", 12)]), "now", sample=True)[0]
    again = Change.from_dict(c.to_dict())
    assert again == c and again.sample
