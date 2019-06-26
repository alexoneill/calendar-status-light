# app.py
# 2019-06-15

# Get GPIO (which may fail when not running on a RPi).
# If this fails, prefer to continue without it.
try:
  import RPi.GPIO as GPIO
except RuntimeError:
  GPIO = None

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
import pytz

import argparse
import datetime
import enum
import os.path
import pickle


# Token storage.
TOKEN = 'secret/token.pkl'

# Required Google Calendar authentication constants.
CREDS = 'secret/credentials.json'
SCOPES = [
  'https://www.googleapis.com/auth/calendar.readonly',
  'https://www.googleapis.com/auth/calendar.settings.readonly',
]

# Runtime constants.
# How often to check (in minutes).
CHECK_INTERVAL_MINUTES = 5

# Deduced option for what the calendar status is.
class CalendarStatus(enum.Enum):
  AWAY = 1
  BUSY = 2
  FREE = 3

# Terms that indicate away.
AWAY_TERMS = ('wfh', 'ooo')
DAY_START = datetime.timedelta(hours = 10, minutes = 30)
DAY_END = datetime.timedelta(hours = 18, minutes = 30)

# TODO(me): Fill this in!
# Map CalendarStatus to output pin.
OUTPUT_PINS = dict([
  (CalendarStatus.AWAY, 0),
  (CalendarStatus.BUSY, 0),
  (CalendarStatus.FREE, 0),
])


# Parse the format for a simple time during the day.
# This converts '12:34' -> timedelta(hours = 12, minutes = 34)
class ParseTimeAction(argparse.Action):
  def __call__(self, parser, namespace, string, option_string = None):
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
    value = datetime.timedelta(hours = hours, minutes = minutes)
    setattr(namespace, self.dest, value)


# Parse all the command line arguments.
def parse_args(*args):
  parser = argparse.ArgumentParser(description='Calendar Status Light')

  parser.add_argument('--check_interval', type=int,
                      default=CHECK_INTERVAL_MINUTES,
                      help='How often to poll the calendar (in minutes)')

  parser.add_argument('--day_start', type=str, required=True,
                      action=ParseTimeAction,
                      help='When the day starts, in "hh:mm" format')
  parser.add_argument('--day_end', type=str, required=True,
                      action=ParseTimeAction,
                      help='When the day ends, in "hh:mm" format')

  parser.add_argument('--auth_only', type=bool, action='store_true',
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
      creds = flow.run_console()

  return creds


def status(cal, check_interval, day_start, day_end):
  # Get the user's timezone.
  tzinfo = cal.settings().get(setting='timezone').execute()
  tz = pytz.timezone(tzinfo.get('value', 'UTC'))

  # Determine when it is based on the timezone.
  now = datetime.datetime.now(tz = tz)
  today = now.replace(hour = 0, minute = 0, second = 0, microsecond = 0)

  # Check that the current time is between the given bounds.
  if (now < today + day_start or today + day_end < now):
    return CalendarStatus.AWAY

  # Query event list for today.
  delta = datetime.timedelta(days=1)
  body = {
      'calendarId': 'primary',
      'timeMin': today.isoformat(),
      'timeMax': (today + delta).isoformat(),
      'timeZone': tz.zone,
    }
  resp = cal.events().list(**body).execute()
  for event in resp['items']:
    for term in AWAY_TERMS:
      if (term in event['summary'].lower()
          and 'date' in event['start']
          and 'dateTime' not in event['start']
          and 'date' in event['end']
          and 'dateTime' not in event['end']):
        return CalendarStatus.AWAY

  # Query Free / Busy for the next 5m on the primary calendar.
  delta = datetime.timedelta(minutes=check_interval)
  body = {
      'timeMin': now.isoformat(),
      'timeMax': (now + delta).isoformat(),
      'timeZone': tz.zone,
      'items': [{
        'id': 'primary',
      }]
    }
  resp = cal.freebusy().query(body = body).execute()

  # If the response contains any items, consider the status to be busy.
  if (resp.get('calendars', {}).get('primary', {}).get('busy', [])):
    return CalendarStatus.BUSY

  return CalendarStatus.FREE


def main(*args):
  # Parse the arguments.
  args = parse_args(args)

  # Authenticate and bail early if requested.
  creds = auth()
  if (args.auth_only):
    return

  # Create an API client.
  cal = build('calendar', 'v3', credentials=creds)

  # Calculate the status.
  cal_status = status(cal, args.check_interval, args.day_start, args.day_end)
  print(cal_status)

  if (GPIO is not None):
    # Configure GPIO.
    GPIO.setmode(GPIO.BOARD)
    for pin in OUTPUT_PINS.values():
      GPIO.setup(pin, GPIO.OUT)

    # Output the status to the light.
    for status_key, pin in OUTPUT_PINS.items():
      GPIO.output(pin, status_key == cal_status)

    GPIO.cleanup()


if __name__ == '__main__':
  import sys
  main(*sys.argv[1:])
