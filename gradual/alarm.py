#!/usr/bin/env python3
from time import sleep
from datetime import datetime, timedelta
from threading import Thread

import hug
import fire
import kick
from first import first
from dateutil import tz

from . import APP_NAME, logger
from .db import Alarm, select, db_session
from .types import (
    Day,
    AlarmTime,
    uuid,
    number,
    one_of,
    in_range,
    smart_boolean,
    comma_separated_days
)
from .constants import DAY_MOMENTS
from .middleware import LogMiddleware

enabled = True
cli = False


@hug.get()
def pause():
    global enabled
    enabled = False
    return {'running': enabled}


@hug.get()
def unpause():
    global enabled
    enabled = True
    return {'running': enabled}


@hug.get()
def state():
    return {'running': enabled}


@hug.get()
@db_session
def clear(disabled=True):
    if disabled:
        return select(a for a in Alarm if not a.enabled).delete(bulk=True)
    else:
        return select(a for a in Alarm).delete(bulk=True)


@hug.get()
@db_session
def enable(uid: uuid):
    if cli:
        uid = uuid(uid)

    Alarm[uid].enabled = True
    return Alarm[uid].to_dict()


@hug.get()
@db_session
def disable(uid: uuid):
    if cli:
        uid = uuid(uid)

    Alarm[uid].enabled = False
    return Alarm[uid].to_dict()


@hug.post('/alarm')
@db_session
def create(
        moment: AlarmTime=None, hour: number=0, minute: number=0,
        days: comma_separated_days=[], after_minutes: number=0, after_hours: number=0,
        recurrent: smart_boolean=None, enabled: smart_boolean=True,
        temporary: smart_boolean=False, **kwargs):

    if cli:
        moment = moment and AlarmTime(moment)
        days = comma_separated_days(days)

    now = datetime.now(tz=tz.tzlocal())
    fade_args = {k[5:]: v for k, v in kwargs.items() if k.startswith('fade_')}
    recommendation_args = {k[4:]: v for k, v in kwargs.items() if k.startswith('rec_')}

    if moment in DAY_MOMENTS:
        moment_time = Alarm.get_moment_time(moment)
        hour = moment_time.hour
        minute = moment_time.minute
        days = days or [now.weekday() + (moment_time < now)]
    elif moment or after_hours or after_minutes:
        if not moment:
            moment = now + timedelta(hours=after_hours, minutes=after_minutes)
        elif isinstance(moment, datetime) and moment < now:
            moment += timedelta(days=1)

        hour = moment.hour
        minute = moment.minute
        days = days or [moment.weekday()]
        moment = ''

    if recurrent is None:
        recurrent = len(days) > 1

    alarm = Alarm(
        hour=hour,
        minute=minute,
        days=days,
        moment=moment,
        recurrent=recurrent,
        enabled=enabled,
        temporary=temporary,
        fade_args=fade_args,
        recommendation_args=recommendation_args)

    return alarm.to_dict()


@hug.put('/alarm')
@db_session
def modify(
        uid: uuid, moment: one_of(DAY_MOMENTS)=None, hour: number=None, minute: number=None,
        days: comma_separated_days=None, recurrent: smart_boolean=None, enabled: smart_boolean=None,
        temporary: smart_boolean=None, erase_fade_args: smart_boolean=False, erase_recommendation_args: smart_boolean=False, **kwargs):

    if cli:
        uid = uuid(uid)
        days = days and comma_separated_days(days)

    alarm = Alarm[uid]
    if moment is not None:
        moment_time = Alarm.get_moment_time(moment)
        alarm.moment = moment
        alarm.hour = moment_time.hour
        alarm.minute = moment_time.minute
    else:
        if hour is not None:
            alarm.hour = hour
        if minute is not None:
            alarm.minute = minute

    if days is not None:
        alarm.days = days
    if recurrent is not None:
        alarm.recurrent = recurrent
    elif days is not None:
        alarm.recurrent = len(days) > 1
    if enabled is not None:
        alarm.enabled = enabled
    if temporary is not None:
        alarm.temporary = temporary

    if erase_fade_args:
        alarm.fade_args = {}
    alarm.fade_args.update({k[5:]: v for k, v in kwargs.items() if k.startswith('fade_')})

    if erase_recommendation_args:
        alarm.recommendation_args = {}
    alarm.recommendation_args.update({k[4:]: v for k, v in kwargs.items() if k.startswith('rec_')})

    return alarm.to_dict()


@hug.get('/alarm')
@db_session
def find(
        uid: uuid=None, day: Day=None, moment: one_of(DAY_MOMENTS)=None,
        hour: in_range(0, 23)=None, exact_time: smart_boolean=None,
        recurrent: smart_boolean=None, enabled: smart_boolean=None, temporary: smart_boolean=None):

    if cli:
        uid = uid and uuid(uid)
        day = day and Day(day)

    if uid is not None:
        return Alarm[uid].to_dict()

    results = select(a for a in Alarm)
    if day is not None:
        results = results.where(lambda a: day in a.days)
    elif moment is not None:
        results = results.where(lambda a: a.moment == moment)
    elif hour is not None:
        results = results.where(lambda a: a.hour == hour)
    elif exact_time is not None:
        if exact_time:
            results = results.where(lambda a: a.moment != '')
        else:
            results = results.where(lambda a: a.moment == '')
    elif enabled is not None:
        results = results.where(lambda a: a.enabled == enabled)
    elif recurrent is not None:
        results = results.where(lambda a: a.recurrent == recurrent)
    elif temporary is not None:
        results = results.where(lambda a: a.temporary == temporary)

    return [a.to_dict() for a in results]


@hug.delete('/alarm')
@db_session
def delete(uid: uuid):
    if cli:
        uid = uuid(uid)

    a = Alarm[uid]
    alarm_data = a.to_dict()
    a.delete()
    return alarm_data


def run():
    global enabled, cli
    cli = False
    Thread(target=api.http.serve, kwargs=dict(port=6035), daemon=True).start()

    while True:
        if enabled:
            with db_session:
                alarms = select(a for a in Alarm if a.enabled)
                next_alarm = first(sorted(alarms, key=lambda a: a.next_time))
                if next_alarm and next_alarm.should_play():
                    logger.info(f'Playing alarm: {next_alarm.to_dict()}')
                    if not next_alarm.recurrent:
                        logger.info('Alarm is not recurrent, we\'re gonna disable it after it\'s played')
                        next_alarm.enabled = False
                    next_alarm.play()
                    if next_alarm.temporary:
                        logger.info('Alarm is temporary, deleting it')
                        next_alarm.delete()
        else:
            logger.debug('Alarm manager is paused, sleeping 40 seconds')
        sleep(40)


def update_config(name='config'):
    kick.update_config(APP_NAME.lower(), variant=name)


api = hug.API(__name__)
api.http.add_middleware(LogMiddleware())


def main():
    """Main function."""

    global cli
    try:
        cli = True
        fire.Fire()
    except KeyboardInterrupt:
        logger.info('Quitting')


if __name__ == '__main__':
    main()
