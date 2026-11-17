"""Pure helpers for planned-maintenance exemption intervals and daily deductions."""
from datetime import date, datetime, time, timedelta

MAX_MINUTES = 60 * 24 * 31


def parse_moment(value, label="时刻"):
    """Parse a naive local start/end moment. Accepts ISO date, date+time or space separated."""
    text = str(value or "").strip()
    if not text:
        raise ValueError(f"{label}不能为空")
    normalized = text.replace("Z", "").replace("z", "")
    try:
        parsed = datetime.fromisoformat(normalized)
    except ValueError:
        raise ValueError(f"{label}须为 YYYY-MM-DD 或 YYYY-MM-DDTHH:MM 格式") from None
    if parsed.tzinfo is not None:
        parsed = parsed.replace(tzinfo=None)
    return parsed


def format_moment(value):
    return value.isoformat(sep=" ", timespec="minutes")


def split_interval(start, end):
    """Return {ISO day: minutes} for a [start, end) interval, splitting at local midnight."""
    if not isinstance(start, datetime) or not isinstance(end, datetime):
        raise ValueError("检修起止时刻须为日期时间")
    if end <= start:
        raise ValueError("检修结束时刻必须晚于开始时刻")
    if (end - start).total_seconds() / 60 > MAX_MINUTES:
        raise ValueError("单次检修区间不能超过31天")
    result = {}
    cursor = start
    while cursor < end:
        midnight = datetime.combine(cursor.date() + timedelta(days=1), time.min)
        segment_end = min(end, midnight)
        minutes = (segment_end - cursor).total_seconds() / 60
        if minutes > 0:
            key = cursor.date().isoformat()
            result[key] = result.get(key, 0.0) + minutes
        cursor = segment_end
    return {day: round(minutes, 4) for day, minutes in result.items()}


def merge_intervals(intervals):
    """Union of (start, end) datetime pairs; touching intervals merge and overlap is counted once."""
    ordered = sorted(intervals)
    merged = []
    for start, end in ordered:
        if end <= start:
            continue
        if merged and start <= merged[-1][1]:
            if end > merged[-1][1]:
                merged[-1] = (merged[-1][0], end)
        else:
            merged.append((start, end))
    return merged


def minutes_by_day(exemptions, channel):
    """Union all exemption intervals for one channel and return {ISO day: deducted minutes}."""
    intervals = []
    for item in exemptions or []:
        if str(item.get("channel")) != str(channel):
            continue
        try:
            start = parse_moment(item.get("start_at"), "检修开始时刻")
            end = parse_moment(item.get("end_at"), "检修结束时刻")
        except ValueError:
            continue
        if end > start:
            intervals.append((start, end))
    result = {}
    for start, end in merge_intervals(intervals):
        for day, minutes in split_interval(start, end).items():
            result[day] = result.get(day, 0.0) + minutes
    return {day: round(minutes, 4) for day, minutes in result.items()}


def total_minutes(daily):
    return round(sum((daily or {}).values()), 4)


def day_list(daily):
    return [{"day": day, "minutes": round(minutes, 4)} for day, minutes in sorted((daily or {}).items())]


def overlap_seconds(first, second):
    start = max(first[0], second[0])
    end = min(first[1], second[1])
    return max(0.0, (end - start).total_seconds())


def covers(day, start, end):
    """Whether a day-only record falls inside an interval (used for impact scoping)."""
    try:
        pointer = datetime.combine(date.fromisoformat(str(day)), time.min)
    except (TypeError, ValueError):
        return False
    return start <= pointer < end or start < pointer + timedelta(days=1) <= end
