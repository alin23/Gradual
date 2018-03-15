import hug
from dateutil import tz, parser
from hug.types import *

from .constants import DAY_MOMENTS, Weekday


@hug.type(extend=text)
def AlarmTime(value):
    """Parses text as datetime using dateutil.parser"""
    if value in DAY_MOMENTS:
        return value

    return parser.parse(value).replace(tzinfo=tz.tzlocal())


@hug.type(extend=number)
def Day(value):
    if isinstance(value, int):
        return value

    return Weekday[value.upper()].value




# pylint: disable=too-few-public-methods
class Days(DelimitedList):
    """Parses day strings as calendar days"""

    def __init__(self, using=','):
        super().__init__(using=using)

    def __call__(self, value):
        values = super().__call__(value)
        try:
            days = list(map(int, values))
        except:
            days = [Weekday[day.upper()].value for day in values]
        return sorted(set(days))


comma_separated_days = Days()
