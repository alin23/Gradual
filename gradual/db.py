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
from pony.orm import *
from psycopg2.extensions import register_adapter

from . import config
from .constants import ASTRAL, SPOTIFY
from spfy.constants import ItemType

register_adapter(ormtypes.TrackedDict, psycopg2.extras.Json)
logging.getLogger('backoff').addHandler(logging.StreamHandler())

if os.getenv('DEBUG'):
    sql_debug(True)
    logging.getLogger('pony.orm.sql').setLevel(logging.DEBUG)

db = Database()


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
        return cls(**{f: getattr(location, f) for f in cls.FIELDS})

    @classmethod
    def from_json(cls, resp):
        location = astral.Location([
            resp['city'],
            resp['region_name'],
            resp['latitude'],
            resp['longitude'],
            resp['time_zone'],
            0
        ])
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
    fade_args = Required(Json, volatile=True)
    recommendation_args = Required(Json, volatile=True)
    created_at = Required(datetime, default=datetime.now)

    def to_dict(self, *args, **kwargs):
        d = super().to_dict(*args, **kwargs)
        if 'id' in d:
            d['id'] = str(d['id'])
            d['next_time'] = str(self.next_time)
        return d

    def should_play(self):
        now = datetime.now(tz=tz.tzlocal())
        conditions = (
            self.enabled and
            self.hour == now.hour and
            self.minute == now.minute and
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

        result = getattr(Location.astral_location(config.location.name), moment)(date=day)

        if isinstance(result, datetime):
            return result

        if when == 'middle':
            return ((result[1] - result[0]) / 2) + result[0]
        if when == 'end':
            return result[1]

        return result[0]

    @property
    def next_day(self):
        now = datetime.now(tz=tz.tzlocal())
        weekday = now.weekday()

        if self.moment:
            moment_time = self.get_moment_time(self.moment)
            not_today = now.hour > moment_time.hour or (now.hour == moment_time.hour and now.minute > moment_time.minute)
        else:
            not_today = now.hour > self.hour or (now.hour == self.hour and now.minute > self.minute)

        if not_today:
            next_day = first(self.days, key=lambda day: day > weekday, default=self.days[0])
        else:
            next_day = first(self.days, key=lambda day: day >= weekday, default=self.days[0])

        return next_day

    @property
    def next_time(self):
        now = datetime.now(tz=tz.tzlocal())
        weekday = now.weekday()

        if self.moment:
            next_time = self.get_moment_time(self.moment, day=date.today() + timedelta(days=self.next_day - weekday))
        else:
            next_time = datetime(now.year, now.month, now.day, self.hour, self.minute, tzinfo=tz.tzlocal()) + timedelta(days=self.next_day - weekday)

        if next_time < now.replace(second=0, microsecond=0):
            next_time += timedelta(days=7)

        return next_time

    @db_session
    def play(self):
        SPOTIFY.play(
            item_type=ItemType.TRACKS,
            device=config.spotify.player.device,
            fade_args={**config.fade, **self.fade_args},
            recommendation_args={**config.recommendations, **self.recommendation_args})


if config.database.filename:
    config.database.filename = os.path.expandvars(config.database.filename)
    os.makedirs(os.path.dirname(config.database.filename), exist_ok=True)

db.bind(**config.database)
db.generate_mapping(create_tables=True)
