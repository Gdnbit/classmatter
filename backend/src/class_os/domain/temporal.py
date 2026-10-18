"""UTC instants and [valid_from, valid_to), not a workflow/calendar engine."""
from dataclasses import dataclass
from datetime import datetime, timezone
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError


def instant(value: datetime) -> datetime:
    if not isinstance(value, datetime) or value.tzinfo is None or value.utcoffset() is None:
        raise ValueError("An explicit offset is required")
    return value.astimezone(timezone.utc)


def localize(wall_time: datetime, zone: str, *, fold: int | None = None) -> datetime:
    if (not isinstance(wall_time, datetime) or wall_time.tzinfo is not None
            or not isinstance(zone, str) or not zone
            or (fold is not None and (type(fold) is not int or fold not in (0, 1)))):
        raise ValueError("Invalid local time")
    try:
        timezone_info = ZoneInfo(zone)
    except (ValueError, ZoneInfoNotFoundError):
        raise ValueError("Unknown timezone") from None
    candidates = {}
    for choice in (0, 1):
        candidate = wall_time.replace(tzinfo=timezone_info, fold=choice).astimezone(timezone.utc)
        if candidate.astimezone(timezone_info).replace(tzinfo=None, fold=0) == wall_time.replace(fold=0):
            candidates[choice] = candidate
    if not candidates:
        raise ValueError("Nonexistent local time")
    if len(set(candidates.values())) > 1 and fold is None:
        raise ValueError("Ambiguous local time requires explicit fold")
    selected = 0 if fold is None else fold
    if selected not in candidates:
        raise ValueError("Invalid local time fold")
    return candidates[selected]


@dataclass(frozen=True)
class Interval:
    valid_from: datetime
    valid_to: datetime | None = None

    def __post_init__(self):
        object.__setattr__(self, "valid_from", instant(self.valid_from))
        if self.valid_to is not None:
            object.__setattr__(self, "valid_to", instant(self.valid_to))
            if self.valid_to <= self.valid_from:
                raise ValueError("Validity interval must be nonempty")

    def contains(self, value: datetime) -> bool:
        value = instant(value)
        return self.valid_from <= value and (self.valid_to is None or value < self.valid_to)

    def overlaps(self, other: "Interval") -> bool:
        return ((self.valid_to is None or other.valid_from < self.valid_to)
                and (other.valid_to is None or self.valid_from < other.valid_to))
