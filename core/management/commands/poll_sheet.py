from django.core.management.base import BaseCommand
from django.utils import timezone
from core.services import GoogleSheetsService, CalDAVService
from core.models import SheetEvent, UserProfile, UserEventBinding, CalendarConfig, UserCalDAVEvent
import datetime
import pytz


class Command(BaseCommand):
    help = 'Polls Google Sheet for events, updates the database, and syncs to CalDAV.'

    def add_arguments(self, parser):
        parser.add_argument('--spreadsheet_id', type=str, required=True,
                            help='The ID of the Google Spreadsheet.')
        parser.add_argument('--range_name', type=str, default='Sheet1!A:I',
                            help='The A1 notation of the range to retrieve (e.g., Sheet1!A:I).')

    def handle(self, *args, **options):
        spreadsheet_id = options['spreadsheet_id']
        range_name = options['range_name']
        # Get Django's default timezone from settings.py (USE_TZ=True recommended)
        local_timezone = pytz.timezone(timezone.get_current_timezone().key)

        self.stdout.write(self.style.SUCCESS(
            f'Polling Google Sheet: {spreadsheet_id} range: {range_name}'))

        # Initialize Google Sheets Service (this will perform the initial OAuth flow if token.pickle doesn't exist)
        try:
            gs_service = GoogleSheetsService()
            sheet_data = gs_service.get_sheet_data(spreadsheet_id, range_name)
        except Exception as e:
            self.stdout.write(self.style.ERROR(
                f'Failed to connect to Google Sheets API: {e}'))
            self.stdout.write(self.style.ERROR(
                'Please ensure `credentials.json` is in the project root and you have authenticated via the browser during the first run.'))
            return

        if not sheet_data:
            self.stdout.write(self.style.WARNING(
                'No data found in the sheet.'))
            return

        headers = sheet_data[0]  # Assuming first row is headers
        event_rows = sheet_data[1:]  # Actual data starts from the second row

        # IMPORTANT: Adjust column_map to match your Google Sheet's actual columns
        # Example mapping:
        # Col 0: Title, Col 1: Description, Col 2: Start_DateTime, Col 3: End_DateTime
        # Col 4: Person1, Col 5: Person2, Col 6: Person3, Col 7: Person4, Col 8: UniqueID
        column_map = {
            'event_id_in_sheet': 0,  # This must be a unique identifier from your sheet
            'title': 1,
            'description': 2,
            'start_time': 3,
            'end_time': 4,
            'person1': 5,
            'person2': 6,
            'person3': 7,
            'person4': 8,
        }

        required_columns = ['title', 'start_time',
                            'end_time', 'event_id_in_sheet']
        for col in required_columns:
            if col not in column_map or column_map[col] >= len(headers):
                self.stdout.write(self.style.ERROR(
                    f"Missing or incorrect column mapping for '{col}'. Check `column_map` and `range_name`."))
                return

        # To track event IDs present in the current sheet fetch
        processed_sheet_event_ids = set()

        for i, row in enumerate(event_rows):
            # Ensure row has enough columns for all mapped data
            if len(row) < max(column_map.values()) + 1:
                self.stdout.write(self.style.WARNING(
                    f'Skipping row {i+2} (0-indexed row {i+1}) due to insufficient columns: {row}'))
                continue

            try:
                start_time_str = row[column_map['start_time']]
                end_time_str = row[column_map['end_time']]

                start_time = datetime.datetime.strptime(
                    start_time_str, '%d/%m/%Y %H:%M:%S')
                end_time = datetime.datetime.strptime(
                    end_time_str, '%d/%m/%Y %H:%M:%S')

                # Make timezone aware using Django's configured timezone
                start_time = local_timezone.localize(start_time)
                end_time = local_timezone.localize(end_time)

                event_id_in_sheet = row[column_map['event_id_in_sheet']]
                if not event_id_in_sheet:
                    self.stdout.write(self.style.WARNING(
                        f'Skipping row {i+2}: No unique event ID found.'))
                    continue

                processed_sheet_event_ids.add(event_id_in_sheet)

                # Get person names, handling cases where they might be empty or missing
                person1_name = row[column_map['person1']
                                   ] if column_map['person1'] < len(row) else None
                person2_name = row[column_map['person2']
                                   ] if column_map['person2'] < len(row) else None
                person3_name = row[column_map['person3']
                                   ] if column_map['person3'] < len(row) else None
                person4_name = row[column_map['person4']
                                   ] if column_map['person4'] < len(row) else None

                sheet_event, created = SheetEvent.objects.update_or_create(
                    event_id_in_sheet=event_id_in_sheet,
                    defaults={
                        'title': row[column_map['title']],
                        'description': row[column_map['description']] if column_map['description'] < len(row) else '',
                        'start_time': start_time,
                        'end_time': end_time,
                        'person1_name': person1_name,
                        'person2_name': person2_name,
                        'person3_name': person3_name,
                        'person4_name': person4_name,
                    }
                )
                if created:
                    self.stdout.write(self.style.SUCCESS(
                        f'Created new SheetEvent: {sheet_event.title} (ID: {sheet_event.event_id_in_sheet})'))
                else:
                    self.stdout.write(self.style.SUCCESS(
                        f'Updated SheetEvent: {sheet_event.title} (ID: {sheet_event.event_id_in_sheet})'))

                # --- Trigger CalDAV Sync for this event ---
                self._sync_sheet_event_to_users_calendars(
                    sheet_event, self.stdout, self.style)

            except (ValueError, IndexError, KeyError) as e:
                self.stdout.write(self.style.ERROR(
                    f'Error processing row {i+2}: {row} - {e}'))
                continue

        # --- Handle deletions from Sheet ---
        # Find SheetEvents in our DB that are no longer present in the fetched sheet data
        events_to_delete_from_db = SheetEvent.objects.exclude(
            event_id_in_sheet__in=list(processed_sheet_event_ids))
        for sheet_event in events_to_delete_from_db:
            self.stdout.write(self.style.WARNING(
                f"SheetEvent '{sheet_event.title}' (ID: {sheet_event.event_id_in_sheet}) no longer in sheet. Deleting from DB and CalDAV."))
            self._delete_sheet_event_from_users_calendars(
                sheet_event, self.stdout, self.style)
            sheet_event.delete()  # Delete from your DB as well

        self.stdout.write(self.style.SUCCESS(
            'Finished polling Google Sheet and syncing events.'))

    def _sync_sheet_event_to_users_calendars(self, sheet_event, stdout, style):
        """
        Synchronizes a single SheetEvent to the calendars of all relevant users.
        """
        # Collect all person names from the sheet event that are not empty/None
        sheet_person_names = [
            sheet_event.person1_name,
            sheet_event.person2_name,
            sheet_event.person3_name,
            sheet_event.person4_name,
        ]
        # Filter out None and empty strings
        sheet_person_names = [
            name.strip() for name in sheet_person_names if name and name.strip()]

        # If no names are assigned to the event, there's no one to sync it to.
        if not sheet_person_names:
            return

        # Find all UserEventBindings where the sheet_name matches one of the person names
        users_to_sync_bindings = UserEventBinding.objects.filter(
            sheet_name__in=sheet_person_names)

        for binding in users_to_sync_bindings:
            user_profile = binding.user_profile
            stdout.write(style.HTTP_INFO(
                f"Attempting sync for user '{user_profile.user.username}' for event '{sheet_event.title}'..."))
            try:
                calendar_config = CalendarConfig.objects.get(
                    user_profile=user_profile)
                caldav_service = CalDAVService(
                    calendar_config.caldav_url,
                    calendar_config.caldav_username,
                    calendar_config.caldav_password
                )

                user_caldav_event, created = UserCalDAVEvent.objects.get_or_create(
                    user_profile=user_profile,
                    sheet_event=sheet_event,
                    # Temp empty, will be filled upon creation
                    defaults={'caldav_uid': ''}
                )

                if created or not user_caldav_event.caldav_uid:
                    # Event not yet synced for this user, or UID is missing
                    stdout.write(style.SUCCESS(
                        f"User {user_profile.user.username}: Creating new CalDAV event for '{sheet_event.title}'"))
                    try:
                        caldav_uid = caldav_service.create_event(sheet_event)
                        user_caldav_event.caldav_uid = caldav_uid
                        user_caldav_event.save()
                        stdout.write(style.SUCCESS(
                            f"User {user_profile.user.username}: Successfully created CalDAV event '{sheet_event.title}' (UID: {caldav_uid})"))
                    except Exception as e:
                        stdout.write(style.ERROR(
                            f"User {user_profile.user.username}: Failed to create CalDAV event for '{sheet_event.title}': {e}"))
                else:
                    # Event already exists, update it
                    stdout.write(style.SUCCESS(
                        f"User {user_profile.user.username}: Updating CalDAV event for '{sheet_event.title}' (UID: {user_caldav_event.caldav_uid})"))
                    try:
                        caldav_service.update_event(
                            user_caldav_event.caldav_uid, sheet_event)
                        stdout.write(style.SUCCESS(
                            f"User {user_profile.user.username}: Successfully updated CalDAV event '{sheet_event.title}'"))
                    except Exception as e:
                        stdout.write(style.ERROR(
                            f"User {user_profile.user.username}: Failed to update CalDAV event for '{sheet_event.title}' (UID: {user_caldav_event.caldav_uid}): {e}"))

            except CalendarConfig.DoesNotExist:
                stdout.write(style.WARNING(
                    f"User {user_profile.user.username}: No CalDAV config found. Skipping event '{sheet_event.title}'."))
            except Exception as e:
                stdout.write(style.ERROR(
                    f"User {user_profile.user.username}: General error during CalDAV sync for '{sheet_event.title}': {e}"))

    def _delete_sheet_event_from_users_calendars(self, sheet_event, stdout, style):
        """
        Deletes a SheetEvent from all relevant users' calendars.
        """
        # Find all UserCalDAVEvent entries related to this sheet_event
        user_caldav_events_to_delete = UserCalDAVEvent.objects.filter(
            sheet_event=sheet_event)

        if not user_caldav_events_to_delete.exists():
            stdout.write(style.WARNING(
                f"No CalDAV events tracked for sheet event '{sheet_event.title}' for deletion."))
            return

        for user_caldav_event in user_caldav_events_to_delete:
            user_profile = user_caldav_event.user_profile
            stdout.write(style.HTTP_INFO(
                f"Attempting deletion for user '{user_profile.user.username}' for event '{sheet_event.title}'..."))
            try:
                calendar_config = CalendarConfig.objects.get(
                    user_profile=user_profile)
                caldav_service = CalDAVService(
                    calendar_config.caldav_url,
                    calendar_config.caldav_username,
                    calendar_config.caldav_password
                )
                stdout.write(style.WARNING(
                    f"User {user_profile.user.username}: Deleting CalDAV event for '{sheet_event.title}' (UID: {user_caldav_event.caldav_uid})"))
                caldav_service.delete_event(user_caldav_event.caldav_uid)
                user_caldav_event.delete()  # Remove from our tracking table
                stdout.write(style.SUCCESS(
                    f"User {user_profile.user.username}: Successfully deleted CalDAV event '{sheet_event.title}'."))
            except CalendarConfig.DoesNotExist:
                stdout.write(style.WARNING(
                    f"User {user_profile.user.username}: No CalDAV config found for deleting event '{sheet_event.title}'."))
            except Exception as e:
                stdout.write(style.ERROR(
                    f"User {user_profile.user.username}: Error deleting CalDAV event for '{sheet_event.title}': {e}"))
