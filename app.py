# app.py
# 2019-06-15

from googleapiclient.discovery import build
from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request

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

# Parse all the command line arguments.
def parse_args(*args):
  parser = argparse.ArgumentParser(description='Calendar Status Light')

  parser.add_argument('--check_interval', type=int,
                      default=CHECK_INTERVAL_MINUTES,
                      help='How often to poll the calendar (in minutes)')

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


def status(cal, check_interval):
  # Query event list for today.
  today = datetime.datetime.combine(datetime.date.today(), datetime.time())
  delta = datetime.timedelta(days=1)

  body = {
      'calendarId': 'primary',
      'timeMin': today.isoformat() + 'Z',
      'timeMax': (today + delta).isoformat() + 'Z',
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

  # Query Free / Busy for the next 5m.
  now = datetime.datetime.utcnow()
  delta = datetime.timedelta(minutes=check_interval)

  # See if the primary calendar is busy right now.
  body = {
      'timeMin': now.isoformat() + 'Z',
      'timeMax': (now + delta).isoformat() + 'Z',
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

  # Authenticate and create an API client.
  creds = auth()
  cal = build('calendar', 'v3', credentials=creds)

  # Calculate the status
  print (status(cal, args.check_interval))


if __name__ == '__main__':
  import sys
  main(*sys.argv[1:])
