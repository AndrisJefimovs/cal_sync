# Google Sheets - CalDAV - synchronisation tool

This tool is used to read events from a Google Sheet with assigned people. Every person registered and configured will receive all the events to their calendar automatically to never miss them.

The following command reads the Google Sheet and updates the local information about the events:

`python manage.py poll_sheet --spreadsheet_id <sheet_id> --range_name 'Sheet1!A:I'`.

