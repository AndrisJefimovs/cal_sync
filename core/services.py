import os
import pickle
import datetime
import uuid  # For generating UIDs for new events

from google_auth_oauthlib.flow import InstalledAppFlow
from google.auth.transport.requests import Request
from googleapiclient.discovery import build

import caldav
from ics import Calendar, Event


class GoogleSheetsService:
    SCOPES = ['https://www.googleapis.com/auth/spreadsheets.readonly']

    def __init__(self, credentials_file='credentials.json', token_file='token.pickle'):
        self.credentials_file = credentials_file
        self.token_file = token_file
        self.service = self._authenticate()

    def _authenticate(self):
        """
        Authenticates with Google API. Handles token storage/refresh.
        For production web apps, you'd integrate this with Django's OAuth flow
        and store tokens in your CalendarConfig model.
        """
        creds = None
        if os.path.exists(self.token_file):
            with open(self.token_file, 'rb') as token:
                creds = pickle.load(token)
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                # The following will open a browser window for authentication
                # This is suitable for development/initial setup but
                # for production you'd use a web-based OAuth flow.
                flow = InstalledAppFlow.from_client_secrets_file(
                    self.credentials_file, self.SCOPES)
                creds = flow.run_local_server(port=0)
            # Save the credentials for the next run
            with open(self.token_file, 'wb') as token:
                pickle.dump(creds, token)
        return build('sheets', 'v4', credentials=creds)

    def get_sheet_data(self, spreadsheet_id, range_name):
        """
        Fetches data from a specified Google Sheet.
        """
        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=spreadsheet_id, range=range_name).execute()
            values = result.get('values', [])
            return values
        except Exception as e:
            print(f"Error fetching Google Sheet data: {e}")
            raise


class CalDAVService:
    def __init__(self, caldav_url, username, password):
        self.caldav_url = caldav_url
        self.username = username
        self.password = password
        self._client = None
        self._principal = None
        self._calendar = None  # actual caldav.Calendar object

    def _get_client(self):
        if not self._client:
            self._client = caldav.DAVClient(
                url=self.caldav_url,
                username=self.username,
                password=self.password
            )
        return self._client

    def _get_principal(self):
        if not self._principal:
            client = self._get_client()
            # Test connection here
            try:
                self._principal = client.principal()
            except Exception as e:
                raise Exception(
                    f"Failed to get CalDAV principal (check URL/credentials): {e}")
        return self._principal

    def get_or_select_calendar(self):
        """
        Connects to CalDAV server and returns the primary calendar.
        In a real app, you might offer the user a choice if they have multiple.
        """
        if not self._calendar:
            principal = self._get_principal()
            calendars = principal.calendars()
            if not calendars:
                raise Exception(
                    "No CalDAV calendars found for this user with the provided URL and credentials.")
            # Assuming the first one for simplicity. Consider letting user choose.
            self._calendar = calendars[0]
        return self._calendar

    def find_event_by_uid(self, uid):
        """Finds an event by its UID within the selected calendar."""
        calendar = self.get_or_select_calendar()
        try:
            # CalDAV library's `event_by_uid` method is ideal for this
            return calendar.event_by_uid(uid)
        except caldav.lib.error.NotFoundError:
            return None  # Event not found, which is expected for new events
        except Exception as e:
            print(f"Error finding CalDAV event by UID {uid}: {e}")
            raise

    def create_event(self, sheet_event):
        """Creates a new event in the CalDAV calendar."""
        calendar = self.get_or_select_calendar()

        c = Calendar()
        e = Event()
        e.name = sheet_event.title
        e.description = sheet_event.description
        e.begin = sheet_event.start_time
        e.end = sheet_event.end_time
        # Generate a UID for the event. Using sheet_event's PK ensures uniqueness
        # and stability for updates. Appending a UUID makes it globally unique.
        e.uid = f"django-sheet-event-{sheet_event.pk}-{uuid.uuid4()}"

        c.events.add(e)

        try:
            # Add the event to the calendar
            caldav_event = calendar.add_event(str(c))
            # print(f"CalDAV event '{sheet_event.title}' created with UID: {e.uid}")
            return e.uid  # Return the UID we assigned for tracking
        except Exception as ex:
            print(f"Error creating CalDAV event '{sheet_event.title}': {ex}")
            raise

    def update_event(self, caldav_uid, sheet_event):
        """Updates an existing event in the CalDAV calendar."""
        calendar = self.get_or_select_calendar()
        existing_event_resource = self.find_event_by_uid(caldav_uid)

        if not existing_event_resource:
            print(
                f"Warning: CalDAV event with UID {caldav_uid} not found for update. Creating new event for '{sheet_event.title}'.")
            # Fallback to create if not found
            return self.create_event(sheet_event)

        # Parse the existing iCalendar data
        existing_cal = Calendar(existing_event_resource.data)
        if not existing_cal.events:
            raise Exception(
                f"No events found in existing CalDAV resource for UID {caldav_uid}. Cannot update.")

        # Get the first (and likely only) event
        cal_event = next(iter(existing_cal.events))

        # Update event properties
        cal_event.name = sheet_event.title
        cal_event.description = sheet_event.description
        cal_event.begin = sheet_event.start_time
        cal_event.end = sheet_event.end_time
        # UID should remain the same

        try:
            # Update the event
            existing_event_resource.data = str(existing_cal)
            existing_event_resource.save()
            # print(f"CalDAV event '{sheet_event.title}' (UID: {caldav_uid}) updated.")
            return caldav_uid  # Return the same UID
        except Exception as ex:
            print(
                f"Error updating CalDAV event '{sheet_event.title}' (UID: {caldav_uid}): {ex}")
            raise

    def delete_event(self, caldav_uid):
        """Deletes an event from the CalDAV calendar."""
        calendar = self.get_or_select_calendar()
        existing_event_resource = self.find_event_by_uid(caldav_uid)

        if existing_event_resource:
            try:
                existing_event_resource.delete()
                # print(f"CalDAV event with UID {caldav_uid} deleted.")
                return True
            except Exception as ex:
                print(
                    f"Error deleting CalDAV event with UID {caldav_uid}: {ex}")
                raise
        else:
            print(
                f"CalDAV event with UID {caldav_uid} not found for deletion (already gone?).")
            return False
