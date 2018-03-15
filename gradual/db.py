import os
import logging
from uuid import UUID, uuid4
from datetime import date, datetime, timedelta

import astral
import backoff
import requests
import psycopg2.extras
from first import first
from dateutil import tz
from pony.orm import (
    Json,
    Database,
    Optional,
    Required,
    PrimaryKey,
    ObjectNotFound,
    ormtypes,
    sql_debug,
    db_session,
)
from spfy.constants import ItemType
from psycopg2.extensions import register_adapter

from .import config, logger
from .constants import ASTRAL, SPOTIFY

register_adapter(ormtypes.TrackedDict, psycopg2.extras.Json)
register_adapter(ormtypes.TrackedList, psycopg2.extras.Json)
logging.getLogger('backoff').addHandler(logging.StreamHandler())
if os.getenv('DEBUG'):
    sql_debug(True)
    logging.getLogger('pony.orm.sql').setLevel(logging.DEBUG)
db = Database()


def last(_list, **kwargs):
    return first(reversed(_list), **kwargs)


class Location(db.Entity):
    URL = 'https://freegeoip.net/json/'
    FIELDS = ('name', 'region', 'latitude', 'longitude', 'timezone', 'elevation')
    name = PrimaryKey(str)
    region = Required(str)
    latitude = Required(float)
    longitude = Required(float)
    timezone = Required(str)
    elevation = Required(int)

    @classmethod
    def from_astral(cls, location):
        return cls(** {f: getattr(location, f) for f in cls.FIELDS})

    @classmethod
    def from_json(cls, resp):
        location = astral.Location(
            [
                resp['city'],
                resp['region_name'],
                resp['latitude'],
                resp['longitude'],
                resp['time_zone'],
                0,
            ]
        )
        ASTRAL.geocoder._get_elevation(location)
        fields = {f: getattr(location, f) for f in cls.FIELDS}
        try:
            existing_location = cls[location.name]
            existing_location.set(**fields)
            return existing_location

        except:
            return cls(**fields)

    def to_astral(self):
        return astral.Location([getattr(self, f) for f in self.FIELDS])

    @classmethod
    @backoff.on_exception(backoff.expo, Exception, max_value=180)
    def astral_location(cls, name):
        try:
            location = cls[name].to_astral()
        except ObjectNotFound:
            try:
                location = ASTRAL.geocoder[name]
                cls.from_astral(location)
            except:
                resp = requests.get(cls.URL).json()
                location = Location.from_json(resp).to_astral()
        location.sunrise()
        return location


class Alarm(db.Entity):
    id = PrimaryKey(UUID, default=uuid4)
    hour = Required(int, min=0, max=23)
    minute = Required(int, min=0, max=59)
    days = Required(Json)
    moment = Optional(str, index=True)
    recurrent = Required(bool, default=False, index=True)
    enabled = Required(bool, default=True, index=True)
    temporary = Required(bool, default=False, index=True)
    skip = Required(bool, default=False, index=True)
    fade_args = Required(Json, volatile=True)
    recommendation_args = Required(Json, volatile=True)
    created_at = Required(datetime, default=datetime.now)
    offset_minutes = Required(int, default=0)
    snooze_minutes = Required(int, default=0)
    last_offset_minutes = Required(int, default=0)
    last_snooze_minutes = Required(int, default=0)

    # pylint: disable=arguments-differ
    def to_dict(self, *args, **kwargs):
        d = super().to_dict(*args, **kwargs)
        if 'id' in d:
            d['id'] = str(d['id'])
            d['next_time'] = str(self.next_time)
        return d

    def should_play(self):
        now = datetime.now(tz=tz.tzlocal())
        next_time = self.next_time
        conditions = (
            self.enabled and
            next_time.hour == now.hour and
            next_time.minute == now.minute and
            now.weekday() in self.days
        )
        if conditions:
            playback = SPOTIFY.current_playback()
            if playback:
                return not playback.is_playing

            return True

        return False

    @staticmethod
    def get_moment_time(moment, day=None):
        when = None
        if moment.endswith('_middle') or moment.endswith('_end'):
            moment, when = moment.rsplit('_', maxsplit=1)
        result = getattr(Location.astral_location(config.location.name), moment)(
            date=day
        )
        if isinstance(result, datetime):
            return result

        if when == 'middle':
            return ((result[1] - result[0]) / 2) + result[0]

        if when == 'end':
            return result[1]

        return result[0]

    def is_today(self):
        now = datetime.now(tz=tz.tzlocal())
        if self.moment:
            moment_time = self.get_moment_time(self.moment)
            if self.snooze_minutes:
                moment_time += timedelta(minutes=self.snooze_minutes)
            today = now.hour < moment_time.hour or (
                now.hour == moment_time.hour and now.minute <= moment_time.minute
            )
        else:
            alarm_time = datetime.now(tz=tz.tzlocal()).replace(
                hour=self.hour, minute=self.minute
            )
            if self.snooze_minutes:
                alarm_time += timedelta(minutes=self.snooze_minutes)
            today = now.hour < alarm_time.hour or (
                now.hour == alarm_time.hour and now.minute <= alarm_time.minute
            )
        return today

    @property
    def next_day(self):
        now = datetime.now(tz=tz.tzlocal())
        weekday = now.weekday()
        if self.is_today():
            next_day = first(
                self.days, key= lambda day: day >= weekday, default=self.days[0]
            )
        else:
            next_day = first(
                self.days, key= lambda day: day > weekday, default=self.days[0]
            )
        return next_day

    @property
    def previous_day(self):
        now = datetime.now(tz=tz.tzlocal())
        weekday = now.weekday()
        if self.is_today():
            previous_day = last(
                self.days, key= lambda day: day < weekday, default=self.days[-1]
            )
        else:
            previous_day = last(
                self.days, key= lambda day: day <= weekday, default=self.days[-1]
            )
        return previous_day

    @property
    def next_time(self):
        now = datetime.now(tz=tz.tzlocal())
        weekday = now.weekday()
        if now - self.previous_time > timedelta(hours=6):
            self.last_snooze_minutes = 0
            self.last_offset_minutes = 0
        if self.moment:
            next_time = self.get_moment_time(
                self.moment, day=date.today() + timedelta(days=self.next_day - weekday)
            )
        else:
            next_time = datetime(
                now.year,
                now.month,
                now.day,
                self.hour,
                self.minute,
                tzinfo=tz.tzlocal(),
            ) + timedelta(
                days=self.next_day - weekday
            )
        if self.snooze_minutes:
            next_time += timedelta(minutes=self.snooze_minutes)
        if next_time < now.replace(second=0, microsecond=0):
            next_time += timedelta(days=7)
        if self.offset_minutes:
            next_time += timedelta(minutes=self.offset_minutes)
        return next_time

    @property
    def previous_time(self):
        now = datetime.now(tz=tz.tzlocal())
        weekday = now.weekday()
        if self.moment:
            previous_time = self.get_moment_time(
                self.moment,
                day=date.today() - timedelta(days=weekday - self.previous_day),
            )
        else:
            previous_time = datetime(
                now.year,
                now.month,
                now.day,
                self.hour,
                self.minute,
                tzinfo=tz.tzlocal(),
            ) - timedelta(
                days=weekday - self.previous_day
            )
        if previous_time > now.replace(second=0, microsecond=0):
            previous_time -= timedelta(days=7)
        if self.last_snooze_minutes:
            previous_time += timedelta(minutes=self.last_snooze_minutes)
        if self.last_offset_minutes:
            previous_time += timedelta(minutes=self.last_offset_minutes)
        return previous_time

    @db_session
    def play(self):
        if self.temporary:
            logger.info('Alarm is temporary, deleting it')
            self.delete()  # pylint: disable=no-member
        else:
            if not self.recurrent:
                logger.info(
                    'Alarm is not recurrent, we\'re gonna disable it after it\'s played'
                )
                self.enabled = False
            if self.offset_minutes:
                logger.info('Alarm has an offset, resetting it')
                self.last_offset_minutes = self.offset_minutes
                self.offset_minutes = 0
            if self.snooze_minutes:
                logger.info('Alarm was snoozed, resetting it')
                self.last_snooze_minutes = self.snooze_minutes
                self.snooze_minutes = 0
        if self.skip:
            self.skip = False
            return

        SPOTIFY.play(
            item_type=ItemType.TRACKS,
            device=config.spotify.player.device,
            fade_args={** config.fade, ** self.fade_args},
            recommendation_args={
                ** config.recommendations, ** self.recommendation_args
            },
        )


if config.database.filename:
    config.database.filename = os.path.expandvars(config.database.filename)
    os.makedirs(os.path.dirname(config.database.filename), exist_ok=True)
db.bind(** config.database)
db.generate_mapping(create_tables=True)
