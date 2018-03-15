from enum import IntEnum

from spfy import Spotify
from astral import Astral, GoogleGeocoder

from .import config


class Weekday(IntEnum):
    MONDAY = 0
    TUESDAY = 1
    WEDNESDAY = 2
    THURSDAY = 3
    FRIDAY = 4
    SATURDAY = 5
    SUNDAY = 6


ASTRAL = Astral()
ASTRAL.geocoder = GoogleGeocoder(cache=True)
DAY_MOMENTS = {
    'blue_hour',
    'blue_hour_middle',
    'blue_hour_end',
    'dawn',
    'dusk',
    'golden_hour',
    'golden_hour_middle',
    'golden_hour_end',
    'solar_noon',
    'sunrise',
    'sunset',
    'twilight',
    'twilight_middle',
    'twilight_end',
}
SPOTIFY = Spotify(** config.spotify.player)
SPOTIFY.authenticate(** config.spotify.auth)
