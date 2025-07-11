import re
import datetime
from typing import Optional


def str_to_timedelta(string: str) -> Optional[datetime.timedelta]:
    string = re.sub(r'\s', r'', string)

    parts = re.match(
        r"""
        (?:(?P<weeks>\d+?)\s*(weeks?|wks?|w))?
        (?:(?P<days>\d+?)\s*(days?|d))?
        (?:(?P<hours>\d+?)\s*(hours?|hrs?|h))?
        (?:(?P<minutes>\d+?)\s*(minutes?|mins?|m))?
        (?:(?P<seconds>\d+?)\s*(seconds?|secs?|s))?
        """,
        string,
        flags=re.VERBOSE | re.IGNORECASE
    )

    if not parts:
        return None

    parts = parts.groupdict()
    parameters = {time: int(amount) for time, amount in parts.items() if amount}

    if not parameters:
        return None

    return datetime.timedelta(**parameters)


def seconds_to_human(seconds: float) -> str:
    units = {
        "year": 31536000,
        "month": 2592000,
        "week": 604800,
        "day": 86400,
        "hour": 3600,
        "minute": 60,
        "second": 1,
    }
    seconds = int(seconds)

    human_parts: list[str] = []
    for unit_name, unit_seconds in units.items():
        if seconds >= unit_seconds:
            count, seconds = divmod(seconds, unit_seconds)
            human_parts.append(f"{count} {unit_name}{'s' if count != 1 else ''}")
            
    if not human_parts:
        human_parts.append("0 seconds")

    return " and ".join(", ".join(human_parts).rsplit(", ", 1))
