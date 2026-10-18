from datetime import datetime, timedelta, timezone

import pytest

from class_os.domain.temporal import Interval, instant, localize


def utc(day, hour=0):
    return datetime(2026, 10, day, hour, tzinfo=timezone.utc)


def test_utc_normalization_and_naive_rejection():
    assert instant(datetime(2026, 10, 8, 8, tzinfo=timezone(timedelta(hours=8)))) == utc(8)
    with pytest.raises(ValueError):
        instant(datetime(2026, 10, 8))


def test_interval_is_half_open_and_adjacent_periods_do_not_overlap():
    first, second = Interval(utc(8), utc(9)), Interval(utc(9), utc(10))
    assert first.contains(utc(8))
    assert not first.contains(utc(9))
    assert not first.overlaps(second) and not second.overlaps(first)
    assert first.overlaps(Interval(utc(8, 12), utc(10)))
    assert Interval(utc(8)).contains(utc(20))
    assert not Interval(utc(10)).overlaps(first)
    assert Interval(utc(8)).overlaps(second)


@pytest.mark.parametrize("end", [utc(7), utc(8)])
def test_empty_or_reverse_interval_is_rejected(end):
    with pytest.raises(ValueError):
        Interval(utc(8), end)


def test_dst_gap_and_ambiguous_time_are_not_guessed():
    with pytest.raises(ValueError):
        localize(datetime(2026, 3, 8, 2, 30), "America/New_York")
    ambiguous = datetime(2026, 11, 1, 1, 30)
    with pytest.raises(ValueError):
        localize(ambiguous, "America/New_York")
    early = localize(ambiguous, "America/New_York", fold=0)
    late = localize(ambiguous, "America/New_York", fold=1)
    assert late - early == timedelta(hours=1)
    assert early.tzinfo == timezone.utc and late.tzinfo == timezone.utc


def test_localization_requires_explicit_valid_zone_and_naive_wall_time():
    assert localize(datetime(2026, 10, 8, 8), "Asia/Shanghai") == utc(8)
    for zone in ["not/a-zone", "", "../UTC"]:
        with pytest.raises(ValueError):
            localize(datetime(2026, 10, 8), zone)
    with pytest.raises(ValueError):
        localize(utc(8), "UTC")
    with pytest.raises(ValueError):
        localize(datetime(2026, 10, 8), "UTC", fold=True)


def test_overlap_is_symmetric_for_all_boundaries():
    periods = [Interval(utc(start), utc(end)) for start in range(1, 8) for end in range(start + 1, 9)]
    for left in periods:
        for right in periods:
            assert left.overlaps(right) == right.overlaps(left)
