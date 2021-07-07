# app.py
# 2019-06-15

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import dateutil.parser
import gpiozero
import pytz

import argparse
import datetime
import enum
import os.path
import pickle
import re
import signal

# Directory where the script is.
DIR = os.path.dirname(os.path.realpath(__file__))

# Token storage.
TOKEN = os.path.join(DIR, 'secret/token.pkl')

# Required Google Calendar authentication constants.
CREDS = os.path.join(DIR, 'secret/credentials.json')
SCOPES = [
    'https://www.googleapis.com/auth/calendar.readonly',
    'https://www.googleapis.com/auth/calendar.settings.readonly',
]

# Runtime defaults.
# How often to check (in seconds).
CHECK_INTERVAL_SECONDS = 5


# Deduced option for what the calendar status is.
class CalendarStatus(enum.IntEnum):
  FREE = 1
  BUSY = 2
  AWAY = 3


# Terms that indicate away.
IGNORE_TERMS = ('oncall',)
AWAY_TERMS = ('wfh', 'ooo')
OVERRIDE_REGEX = re.compile(r'#calendar-status-light: ?(FREE|BUSY|AWAY)')
DAY_START = datetime.timedelta(hours=10, minutes=30)
DAY_END = datetime.timedelta(hours=18, minutes=30)
DAY_START = datetime.timedelta()
DAY_END = datetime.timedelta(hours=23, minutes=59)

# Declare which pins to use.
AWAY_PIN = "WPI0"
BUSY_PIN = "WPI1"
FREE_PIN = "WPI2"
BUZZ_PIN = "WPI3"

# Constant controlling initialization beep.
BEEP_TIME = 0.2


# Parse the format for a simple time during the day.
# This converts '12:34' -> timedelta(hours = 12, minutes = 34)
class ParseTimeAction(argparse.Action):

  def __call__(self, parser, namespace, string, option_string=None):
    # Check there are only two components.
    parts = [part.strip() for part in string.split(':')]
    if (len(parts) != 2):
      raise ValueError("Time is in a bad format: %s" % string)

    # Check each component is a number.
    if (not all([part.isdigit() for part in parts])):
      raise ValueError("Time is in a bad format: %s" % string)

    # Check both values are within time bounds (24h, 60m).
    (hours, minutes) = tuple([int(part) for part in parts])
    if (not 0 <= hours < 24 or not 0 <= minutes < 60):
      raise ValueError("Time encodes incorrect offset: %s" % string)

    # Store the value in a useable format.
    value = datetime.timedelta(hours=hours, minutes=minutes)
    setattr(namespace, self.dest, value)


# Parse all the command line arguments.
def parse_args(*args):
  parser = argparse.ArgumentParser(description='Calendar Status Light')

  parser.add_argument('--check_interval',
                      type=int,
                      default=CHECK_INTERVAL_SECONDS,
                      help='How often to poll the calendar (in seconds)')

  parser.add_argument('--day_start',
                      type=str,
                      default=DAY_START,
                      action=ParseTimeAction,
                      help='When the day starts, in "hh:mm" format')
  parser.add_argument('--day_end',
                      type=str,
                      default=DAY_END,
                      action=ParseTimeAction,
                      help='When the day ends, in "hh:mm" format')

  parser.add_argument('--auth_only',
                      action='store_true',
                      help='Only perform authentication with Google?')

  return parser.parse_args()


# Decorator to wrap a function in object storage (at a given file path).
def pickled(file_path):

  def decorator(func):

    def wrapped(*args, **kwargs):
      # Load the object from the file.
      obj = None
      if os.path.exists(file_path):
        with open(file_path, 'rb') as f:
          obj = pickle.load(f)

      # Update the object.
      obj = func(obj, *args, **kwargs)

      # Store the object back into the file.
      with open(file_path, 'wb') as f:
        pickle.dump(obj, f)

      # Return the object as well.
      return obj

    return wrapped

  return decorator


# Generate or update the OAuth2 creds.
@pickled(TOKEN)
def auth(creds):
  if not creds or not creds.valid:
    # Refresh the creds if possible
    if creds and creds.expired and creds.refresh_token:
      creds.refresh(Request())
    else:
      # Otherwise generate a creds.
      flow = InstalledAppFlow.from_client_secrets_file(CREDS, SCOPES)
      creds = flow.run_console(
          # Enable offline access so that you can refresh an access token
          # without re-prompting the user for permission. Recommended for web
          # server apps.
          access_type='offline',
          # Enable incremental authorization. Recommended as a best practice.
          include_granted_scopes='true')

  return creds


def parse_event_time(event_time, tzinfo):
  event_str = (event_time['date'] if
               ('date' in event_time) else event_time['dateTime'])
  return dateutil.parser.parse(event_str).replace(tzinfo=tzinfo)


def check_keywords(string, keywords):
  for keyword in keywords:
    if (keyword in string):
      return True
  return False


def check_event_override(event):
  # Find the override text in the description.
  m = OVERRIDE_REGEX.search(event['description'])
  if m is None:
    return None

  # Match the name to the enum name.
  for status in CalendarStatus:
    if status.name == m.group(0):
      return status

  # Otherwise give up.
  return None


def process_event(event, now, tz):
  # Respect overrides above all else.
  if (status := check_event_override(event)) is not None:
    return status

  # Default status to FREE, let the below modify it.
  cal_status = CalendarStatus.FREE

  # Skip cancelled events.
  if (event['status'] == 'cancelled'):
    return cal_status

  # Skip unconfirmed events.
  if (event['status'] != 'confirmed'):
    return cal_status

  # Parse event times.
  start = parse_event_time(event['start'], tz)
  end = parse_event_time(event['end'], tz)

  # Skip events out of scope.
  if (not start <= now < end):
    return cal_status

  # Ignore events that have been declined or have not been responded to.
  for attendee in event.get('attendees', []):
    if (attendee.get('self', False) and
        attendee['responseStatus'] in ('declined', 'needsAction')):
      return cal_status

  # Check against away keywords.
  title = event['summary'].lower()
  if (check_keywords(title, AWAY_TERMS)):
    cal_status = max(cal_status, CalendarStatus.AWAY)

  # Skip events with certain keywords.
  if (not check_keywords(title, IGNORE_TERMS)):
    cal_status = max(cal_status, CalendarStatus.BUSY)
  return cal_status


def status(cal, check_delta, day_start, day_end):
  # Get the user's timezone.
  tzinfo = cal.settings().get(setting='timezone').execute()
  tz = pytz.timezone(tzinfo.get('value', 'UTC'))

  # Determine when it is based on the timezone.
  now = datetime.datetime.now(tz=tz)
  today = now.replace(hour=0, minute=0, second=0, microsecond=0)

  # Check that the current time is between the given bounds.
  if (now < today + day_start or today + day_end < now):
    return CalendarStatus.AWAY

  # Query event list for today.
  cal_status = CalendarStatus.FREE
  delta = datetime.timedelta(days=1)
  body = {
      'calendarId': 'primary',
      'timeMin': today.isoformat(),
      'timeMax': (today + delta).isoformat(),
      'timeZone': tz.zone,
  }
  resp = cal.events().list(**body).execute()
  for event in resp['items']:
    status = process_event(event, now, tz)
    if cal_status < status:
      print(f'{event["summary"]} -> {status}')
      cal_status = status

  return cal_status


def stream(fn, *args, **kwargs):
  while True:
    val = fn(*args, **kwargs)
    print('stream (%s): %s' % (fn.__name__, val))
    yield fn(*args, **kwargs)


def main(*args):
  # Parse the arguments.
  args = parse_args(args)

  # Authenticate and bail early if requested.
  creds = auth()
  if (args.auth_only):
    return

  # Create an API client.
  cal = build('calendar', 'v3', credentials=creds)

  # Configure the stack.
  buzz = gpiozero.Buzzer(BUZZ_PIN)
  stack = gpiozero.LEDBoard(AWAY_PIN, BUSY_PIN, FREE_PIN)

  # Define a mapping between board LEDs and CalendarStatuses.
  led_mapping = dict([(CalendarStatus.AWAY, (1, 0, 0)),
                      (CalendarStatus.BUSY, (0, 1, 0)),
                      (CalendarStatus.FREE, (0, 0, 1))])

  # Configure the stack to update periodically.
  check_delta = datetime.timedelta(seconds=args.check_interval)
  stack.source_delay = check_delta.total_seconds()
  stack.source = (led_mapping[cal_status] for cal_status in stream(
      status, cal, check_delta, args.day_start, args.day_end))

  # Beep the buzzer once to indicate boot.
  buzz.beep(on_time=BEEP_TIME, n=1)

  # Wait for a signal, then quit.
  print('Waiting for signal...')
  signal.pause()


if __name__ == '__main__':
  import sys
  main(*sys.argv[1:])
