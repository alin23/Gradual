__version__ = '0.3.0'
APP_NAME = 'Alarm'

import os  # isort:skip

ENV = os.getenv(f'{APP_NAME.upper()}_ENV', 'config')  # isort:skip

import kick  # isort:skip

kick.start(f'{APP_NAME.lower()}', config_variant=ENV)  # isort:skip

from kick import config, logger  # isort:skip
