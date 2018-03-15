import json
from functools import partial

from astral import Location


class LocationEncoder(json.JSONEncoder):

    def default(self, o):
        if isinstance(o, Location):
            return {
                'name': o.name,
                'region': o.region,
                'latitude': o.latitude,
                'longitude': o.longitude,
                'timezone': o.timezone,
                'elevation': o.elevation,
            }

        return super().default(o)


class LocationDecoder(json.JSONDecoder):
    LOCATION_FIELDS = {
        'name', 'region', 'latitude', 'longitude', 'timezone', 'elevation'
    }

    def __init__(self, *args, **kwargs):
        kwargs.pop('object_hook', None)
        super().__init__(object_hook=self.decode_location_object, *args, **kwargs)

    def decode_location_object(self, o):
        if o.keys() == self.LOCATION_FIELDS:
            return Location(
                [
                    o['name'],
                    o['region'],
                    o['latitude'],
                    o['longitude'],
                    o['timezone'],
                    o['elevation'],
                ]
            )

        return o


dumps = partial(json.dumps, cls=LocationEncoder)
loads = partial(json.loads, cls=LocationDecoder)
