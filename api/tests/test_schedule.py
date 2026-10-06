from datetime import date
from decimal import Decimal as D

from app.backends.base import normalise_phone
from app.domain.schedule import add_months, monthly_schedule


def test_add_months_never_drifts():
    start = date(2026, 1, 31)
    assert [add_months(start, i) for i in range(4)] == [
        date(2026, 1, 31),
        date(2026, 2, 28),
        date(2026, 3, 31),
        date(2026, 4, 30),
    ]
    assert add_months(date(2026, 11, 15), 3) == date(2027, 2, 15)
    assert add_months(date(2026, 3, 10), -4) == date(2025, 11, 10)


def test_declining_schedule_clears_exactly():
    rows = monthly_schedule(D("15000"), D("10"), 12, date(2026, 11, 1))
    assert rows[0].total == D("1318.74") and rows[0].interest == D("125.00")
    assert rows[-1].balance_after == 0
    assert sum(r.principal for r in rows) == D("15000")


def test_flat_schedule():
    rows = monthly_schedule(D("1200"), D("30"), 2, date(2026, 11, 1), "FLAT")
    assert [r.total for r in rows] == [D("630.00"), D("630.00")]
    assert rows[-1].balance_after == 0


def test_png_phone_numbers():
    assert normalise_phone("+675 7123 4567") == "71234567"
    assert normalise_phone("675-71234567") == "71234567"
    assert normalise_phone("7123 4567") == "71234567"


def test_port_moresby_time_without_tz_database(monkeypatch):
    import app.deps as deps

    def missing(name):
        raise deps.ZoneInfoNotFoundError(name)

    monkeypatch.setattr(deps, "ZoneInfo", missing)
    tz = deps.local_zone("Pacific/Port_Moresby")
    from datetime import datetime, timedelta

    assert tz.utcoffset(datetime(2026, 1, 1)) == timedelta(hours=10)
