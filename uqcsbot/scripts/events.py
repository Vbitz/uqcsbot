from typing import List
from uqcsbot import bot, Command
from icalendar import Calendar, vText
from requests import get
from datetime import datetime, timedelta
from pytz import timezone, utc
import re

CALENDAR_URL = "https://calendar.google.com/calendar/ical/q3n3pce86072n9knt3pt65fhio%40group.calendar.google.com" \
               "/public/basic.ics"
FILTER_REGEX = re.compile('(full|all|[0-9]+( weeks?)?)')
BRISBANE_TZ = timezone('Australia/Brisbane')
MONTHS = ["JAN", "FEB", "MAR", "APR", "MAY", "JUN", "JUL", "AUG", "SEP", "OCT", "NOV", "DEC"]


class EventFilter(object):
    def __init__(self, full=False, weeks=None, cap=None, is_valid=True):
        self.is_valid = is_valid
        self._full = full
        self._weeks = weeks
        self._cap = cap

    @staticmethod
    def from_command(command: Command):
        if not command.has_arg():
            return EventFilter(weeks=2)
        else:
            match = re.match(FILTER_REGEX, command.arg)
            if not match:
                return EventFilter(is_valid=False)
            filter_str = match.group(0)
            if filter_str in ['full', 'all']:
                return EventFilter(full=True)
            elif 'week' in filter_str:
                return EventFilter(weeks=int(filter_str.split()[0]))
            else:
                return EventFilter(cap=int(filter_str))

    def filter_events(self, events: List['Event'], start_time: datetime):
        if self._weeks is not None:
            end_time = start_time + timedelta(weeks=self._weeks)
            return [e for e in events if e.start < end_time]
        if self._cap is not None:
            return events[:self._cap]

    def get_header(self):
        if self._full:
            return "List of *all* upcoming events"
        elif self._weeks is not None:
            return f"Events in the *next _{self._weeks}_ weeks*"
        else:
            return f"The *next _{self._cap}_ events*"

    def get_no_result_msg(self):
        if self._weeks is not None:
            return f"There doesn't appear to be any events in the next *{self._weeks}* weeks"
        else:
            return "There doesn't appear to be any upcoming events..."


class Event(object):
    def __init__(self, start: datetime, end: datetime, location: vText, summary: vText):
        self.start = start
        self.end = end
        self.location = location
        self.summary = summary

    @staticmethod
    def from_cal_event(cal_event):
        start = cal_event.get('dtstart').dt
        end = cal_event.get('dtend').dt
        location = cal_event.get('location', 'TBA')
        summary = cal_event.get('summary')
        return Event(start, end, location, summary)

    def __str__(self):
        d1 = self.start.astimezone(BRISBANE_TZ)
        d2 = self.end.astimezone(BRISBANE_TZ)

        start_str = f"{MONTHS[d1.month-1]} {d1.day} {d1.hour}:{d1.minute:02}"
        if (d1.month, d1.day) != (d2.month, d2.day):
            end_str = f"{MONTHS[d2.month-1]} {d2.day} {d2.hour}:{d2.minute:02}"
        else:
            end_str = f"{d2.hour}:{d2.minute:02}"

        return f"*{start_str} - {end_str}* - _{self.location}_: `{self.summary}`"


@bot.on_command('events')
async def handle_events(command: Command):
    event_filter = EventFilter.from_command(command)
    if not event_filter.is_valid:
        bot.post_message(command.channel, "Invalid events filter.")
        return

    http_response = await bot.run_async(get, CALENDAR_URL)
    cal = Calendar.from_ical(http_response.content)

    current_time = datetime.now(tz=BRISBANE_TZ).astimezone(utc)

    # TODO: support recurring events
    # subcomponents are how icalendar returns the list of things in the calendar
    # we are only interested in ones with the name VEVENT as they are events
    # we also currently filter out recurring events
    events = [Event.from_cal_event(c) for c in cal.subcomponents if c.name == 'VEVENT' and c.get('RRULE') is None]
    # next we want to filter out any events that are not after the current time
    events = [e for e in events if e.start > current_time]
    # then we apply our event filter as generated earlier
    events = event_filter.filter_events(events, current_time)
    # then, we sort the events by date
    events = sorted(events, key=lambda e: e.start, reverse=True)

    # then print to the user the result
    if not events:
        message = f"_{event_filter.get_no_result_msg()}_\r\n" \
                  f"For a full list of events, visit: https://uqcs.org.au/calendar.html"
    else:
        message = f"{event_filter.get_header()}\r\n" + '\r\n'.join(str(e) for e in events)

    bot.post_message(command.channel, message)
