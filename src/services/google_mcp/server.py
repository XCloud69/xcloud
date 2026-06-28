import os.path
import base64
from email.message import EmailMessage
from datetime import datetime, timedelta
from typing import Optional

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

SCOPES = [
    'https://www.googleapis.com/auth/gmail.modify',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/tasks'
]

def get_credentials():
    creds = None
    token_path = os.path.join(os.path.dirname(__file__), 'token.json')
    creds_path = os.path.join(os.path.dirname(__file__), 'credentials.json')
    if os.path.exists(token_path):
        creds = Credentials.from_authorized_user_file(token_path, SCOPES)
    if not creds or not creds.valid:
        if creds and creds.expired and creds.refresh_token:
            creds.refresh(Request())
        else:
            if not os.path.exists(creds_path):
                raise FileNotFoundError(f"{creds_path} not found. Please download OAuth client ID credentials from Google Cloud Console and save it as credentials.json here.")
            flow = InstalledAppFlow.from_client_secrets_file(creds_path, SCOPES)
            creds = flow.run_local_server(port=0)
        with open(token_path, 'w') as token:
            token.write(creds.to_json())
    return creds

mcp = FastMCP("GoogleWorkspace")

# ────────────────────────────── GMAIL TOOLS ──────────────────────────────

@mcp.tool()
def read_emails(max_results: int = 5, query: str = "is:inbox") -> str:
    """Read emails from Gmail based on a search query.

    Args:
        max_results: Maximum number of emails to return (default 5).
        query: Gmail search query (e.g. 'is:unread', 'from:boss@example.com').
    """
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    try:
        results = service.users().messages().list(userId='me', maxResults=max_results, q=query).execute()
        messages = results.get('messages', [])
        if not messages:
            return "No messages found."
        output = []
        for message in messages:
            msg = service.users().messages().get(userId='me', id=message['id']).execute()
            headers = msg['payload'].get('headers', [])
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown Sender')
            snippet = msg.get('snippet', '')
            output.append(f"From: {sender}\nSubject: {subject}\nSnippet: {snippet}\n---")
        return "\n".join(output)
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def send_email(to: str, subject: str, body: str) -> str:
    """Send an email from your Gmail account.

    Args:
        to: Email address of the recipient.
        subject: Subject of the email.
        body: Body content of the email.
    """
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    try:
        message = EmailMessage()
        message.set_content(body)
        message['To'] = to
        message['From'] = 'me'
        message['Subject'] = subject
        encoded_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        create_message = {'raw': encoded_message}
        send_message = (service.users().messages().send(userId="me", body=create_message).execute())
        return f"Email sent successfully! Message Id: {send_message['id']}"
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def search_emails(query: str, max_results: int = 10) -> str:
    """Search emails using Gmail's advanced search syntax.

    Args:
        query: Gmail search query (e.g. 'has:attachment from:example@.com', 'subject:"meeting" after:2026/01/01').
        max_results: Maximum number of results to return (default 10).
    """
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    try:
        results = service.users().messages().list(userId='me', maxResults=max_results, q=query).execute()
        messages = results.get('messages', [])
        if not messages:
            return "No messages found."
        output = []
        for msg_data in messages:
            msg = service.users().messages().get(userId='me', id=msg_data['id']).execute()
            headers = msg['payload'].get('headers', [])
            subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
            sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
            date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown')
            output.append(f"[{msg['id']}] {date} | From: {sender} | Subject: {subject}")
        return "\n".join(output)
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def get_email(message_id: str) -> str:
    """Get the full content of a specific email by its ID.

    Args:
        message_id: The Gmail message ID.
    """
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    try:
        msg = service.users().messages().get(userId='me', id=message_id, format='full').execute()
        headers = msg['payload'].get('headers', [])
        subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), 'No Subject')
        sender = next((h['value'] for h in headers if h['name'].lower() == 'from'), 'Unknown')
        to = next((h['value'] for h in headers if h['name'].lower() == 'to'), 'Unknown')
        date = next((h['value'] for h in headers if h['name'].lower() == 'date'), 'Unknown')
        body = ""
        if 'parts' in msg['payload']:
            for part in msg['payload']['parts']:
                if part['mimeType'] == 'text/plain' and 'data' in part.get('body', {}):
                    body = base64.urlsafe_b64decode(part['body']['data']).decode('utf-8', errors='replace')
                    break
        elif 'body' in msg['payload'] and 'data' in msg['payload']['body']:
            body = base64.urlsafe_b64decode(msg['payload']['body']['data']).decode('utf-8', errors='replace')
        return f"From: {sender}\nTo: {to}\nDate: {date}\nSubject: {subject}\n\n{body[:5000]}"
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def reply_to_email(message_id: str, body: str) -> str:
    """Reply to an existing email thread.

    Args:
        message_id: The Gmail message ID to reply to.
        body: The reply body content.
    """
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    try:
        original = service.users().messages().get(userId='me', id=message_id, format='metadata').execute()
        headers = original['payload'].get('headers', [])
        subject = next((h['value'] for h in headers if h['name'].lower() == 'subject'), '')
        if not subject.lower().startswith('re:'):
            subject = f"Re: {subject}"
        reply_to = next((h['value'] for h in headers if h['name'].lower() == 'from'), '')
        message = EmailMessage()
        message.set_content(body)
        message['To'] = reply_to
        message['Subject'] = subject
        message['In-Reply-To'] = message_id
        message['References'] = message_id
        encoded = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_result = service.users().messages().send(userId='me', body={'raw': encoded, 'threadId': original['threadId']}).execute()
        return f"Reply sent! Message Id: {send_result['id']}"
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def trash_email(message_id: str) -> str:
    """Move an email to trash.

    Args:
        message_id: The Gmail message ID to trash.
    """
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    try:
        service.users().messages().trash(userId='me', id=message_id).execute()
        return f"Message {message_id} moved to trash."
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def delete_email(message_id: str) -> str:
    """Permanently delete an email (use with caution).

    Args:
        message_id: The Gmail message ID to permanently delete.
    """
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    try:
        service.users().messages().delete(userId='me', id=message_id).execute()
        return f"Message {message_id} permanently deleted."
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def mark_as_read(message_id: str) -> str:
    """Mark an email as read.

    Args:
        message_id: The Gmail message ID to mark as read.
    """
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    try:
        service.users().messages().modify(userId='me', id=message_id, body={'removeLabelIds': ['UNREAD']}).execute()
        return f"Message {message_id} marked as read."
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def mark_as_unread(message_id: str) -> str:
    """Mark an email as unread.

    Args:
        message_id: The Gmail message ID to mark as unread.
    """
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    try:
        service.users().messages().modify(userId='me', id=message_id, body={'addLabelIds': ['UNREAD']}).execute()
        return f"Message {message_id} marked as unread."
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def list_labels() -> str:
    """List all Gmail labels/folders."""
    creds = get_credentials()
    service = build('gmail', 'v1', credentials=creds)
    try:
        results = service.users().labels().list(userId='me').execute()
        labels = results.get('labels', [])
        if not labels:
            return "No labels found."
        output = []
        for label in labels:
            output.append(f"{label['name']} (ID: {label['id']})")
        return "\n".join(output)
    except Exception as e:
        return f"An error occurred: {e}"

# ──────────────────────────── CALENDAR TOOLS ────────────────────────────

@mcp.tool()
def list_calendar_events(max_results: int = 10, days_ahead: int = 7) -> str:
    """List upcoming events from your primary Google Calendar.

    Args:
        max_results: Maximum number of events to return.
        days_ahead: Look for events up to this many days ahead.
    """
    creds = get_credentials()
    service = build('calendar', 'v3', credentials=creds)
    try:
        now = datetime.utcnow().isoformat() + 'Z'
        time_max = (datetime.utcnow() + timedelta(days=days_ahead)).isoformat() + 'Z'
        events_result = service.events().list(
            calendarId='primary', timeMin=now, timeMax=time_max,
            maxResults=max_results, singleEvents=True,
            orderBy='startTime'
        ).execute()
        events = events_result.get('items', [])
        if not events:
            return "No upcoming events found."
        output = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            output.append(f"ID: {event['id']} | Start: {start} | Summary: {event['summary']}")
        return "\n".join(output)
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def get_calendar_event(event_id: str) -> str:
    """Get details of a specific calendar event.

    Args:
        event_id: The Google Calendar event ID.
    """
    creds = get_credentials()
    service = build('calendar', 'v3', credentials=creds)
    try:
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        start = event['start'].get('dateTime', event['start'].get('date'))
        end = event['end'].get('dateTime', event['end'].get('date'))
        desc = event.get('description', 'No description')
        location = event.get('location', 'No location')
        return f"Summary: {event['summary']}\nStart: {start}\nEnd: {end}\nLocation: {location}\nDescription: {desc}"
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def create_calendar_event(summary: str, start_time_iso: str, end_time_iso: str, description: str = "", location: str = "") -> str:
    """Create a new event in your primary Google Calendar.

    Args:
        summary: Title of the event.
        start_time_iso: Start time in ISO format (e.g. '2026-05-10T09:00:00-07:00').
        end_time_iso: End time in ISO format (e.g. '2026-05-10T10:00:00-07:00').
        description: Optional description of the event.
        location: Optional location of the event.
    """
    creds = get_credentials()
    service = build('calendar', 'v3', credentials=creds)
    try:
        event_body = {
            'summary': summary,
            'description': description,
            'start': {'dateTime': start_time_iso},
            'end': {'dateTime': end_time_iso},
        }
        if location:
            event_body['location'] = location
        event = service.events().insert(calendarId='primary', body=event_body).execute()
        return f"Event created: {event.get('htmlLink')} (ID: {event['id']})"
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def update_calendar_event(event_id: str, summary: str = None, start_time_iso: str = None, end_time_iso: str = None, description: str = None) -> str:
    """Update an existing calendar event.

    Args:
        event_id: The Google Calendar event ID to update.
        summary: Optional new title.
        start_time_iso: Optional new start time in ISO format.
        end_time_iso: Optional new end time in ISO format.
        description: Optional new description.
    """
    creds = get_credentials()
    service = build('calendar', 'v3', credentials=creds)
    try:
        event = service.events().get(calendarId='primary', eventId=event_id).execute()
        if summary is not None:
            event['summary'] = summary
        if description is not None:
            event['description'] = description
        if start_time_iso is not None:
            event['start'] = {'dateTime': start_time_iso}
        if end_time_iso is not None:
            event['end'] = {'dateTime': end_time_iso}
        updated = service.events().update(calendarId='primary', eventId=event_id, body=event).execute()
        return f"Event updated: {updated.get('htmlLink')}"
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def delete_calendar_event(event_id: str) -> str:
    """Delete a calendar event.

    Args:
        event_id: The Google Calendar event ID to delete.
    """
    creds = get_credentials()
    service = build('calendar', 'v3', credentials=creds)
    try:
        service.events().delete(calendarId='primary', eventId=event_id).execute()
        return f"Event {event_id} deleted."
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def search_calendar_events(query: str, max_results: int = 10) -> str:
    """Search calendar events by keyword.

    Args:
        query: Free text to search for in event titles and descriptions.
        max_results: Maximum number of results to return.
    """
    creds = get_credentials()
    service = build('calendar', 'v3', credentials=creds)
    try:
        now = datetime.utcnow().isoformat() + 'Z'
        events_result = service.events().list(
            calendarId='primary', timeMin=now,
            maxResults=max_results, singleEvents=True,
            orderBy='startTime', q=query
        ).execute()
        events = events_result.get('items', [])
        if not events:
            return "No matching events found."
        output = []
        for event in events:
            start = event['start'].get('dateTime', event['start'].get('date'))
            output.append(f"ID: {event['id']} | {start} | {event['summary']}")
        return "\n".join(output)
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def quick_add_calendar_event(text: str) -> str:
    """Create a calendar event using natural language (e.g. 'Meeting with John at 3pm tomorrow').

    Args:
        text: Natural language event description.
    """
    creds = get_credentials()
    service = build('calendar', 'v3', credentials=creds)
    try:
        event = service.events().quickAdd(calendarId='primary', text=text).execute()
        return f"Event created: {event.get('htmlLink')} (ID: {event['id']})"
    except Exception as e:
        return f"An error occurred: {e}"

# ──────────────────────────── TASKS TOOLS ────────────────────────────

@mcp.tool()
def list_task_lists() -> str:
    """List all Google Tasks task lists."""
    creds = get_credentials()
    service = build('tasks', 'v1', credentials=creds)
    try:
        results = service.tasklists().list().execute()
        items = results.get('items', [])
        if not items:
            return "No task lists found."
        output = []
        for item in items:
            output.append(f"{item['title']} (ID: {item['id']})")
        return "\n".join(output)
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def create_task_list(title: str) -> str:
    """Create a new task list.

    Args:
        title: The title for the new task list.
    """
    creds = get_credentials()
    service = build('tasks', 'v1', credentials=creds)
    try:
        result = service.tasklists().insert(body={'title': title}).execute()
        return f"Task list created: {result['title']} (ID: {result['id']})"
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def delete_task_list(tasklist_id: str) -> str:
    """Delete a task list.

    Args:
        tasklist_id: The ID of the task list to delete.
    """
    creds = get_credentials()
    service = build('tasks', 'v1', credentials=creds)
    try:
        service.tasklists().delete(tasklist=tasklist_id).execute()
        return f"Task list {tasklist_id} deleted."
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def list_tasks(tasklist_id: str = '@default', max_results: int = 10, show_completed: bool = False) -> str:
    """List tasks from a task list.

    Args:
        tasklist_id: Task list ID (defaults to '@default' which is the default list).
        max_results: Maximum number of tasks to return (default 10).
        show_completed: Whether to include completed tasks (default False).
    """
    creds = get_credentials()
    service = build('tasks', 'v1', credentials=creds)
    try:
        results = service.tasks().list(
            tasklist=tasklist_id, maxResults=max_results,
            showCompleted=show_completed
        ).execute()
        items = results.get('items', [])
        if not items:
            return "No tasks found."
        output = []
        for item in items:
            status = item.get('status', 'needsAction')
            due = item.get('due', 'No due date')
            output.append(f"ID: {item['id']} | Title: {item['title']} | Status: {status} | Due: {due}")
        return "\n".join(output)
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def create_task(title: str, tasklist_id: str = '@default', notes: str = "", due_date_rfc3339: str = None) -> str:
    """Create a new task in a task list.

    Args:
        title: The title of the task.
        tasklist_id: Task list ID (defaults to '@default').
        notes: Optional notes/description for the task.
        due_date_rfc3339: Optional due date in RFC 3339 format (e.g., '2026-05-10T00:00:00.000Z').
    """
    creds = get_credentials()
    service = build('tasks', 'v1', credentials=creds)
    try:
        task = {'title': title, 'notes': notes}
        if due_date_rfc3339:
            task['due'] = due_date_rfc3339
        result = service.tasks().insert(tasklist=tasklist_id, body=task).execute()
        return f"Task created: {result['title']} (ID: {result['id']})"
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def update_task(task_id: str, tasklist_id: str = '@default', title: str = None, notes: str = None, due_date_rfc3339: str = None) -> str:
    """Update an existing task.

    Args:
        task_id: The task ID to update.
        tasklist_id: The task list ID containing the task (defaults to '@default').
        title: Optional new title.
        notes: Optional new notes.
        due_date_rfc3339: Optional new due date in RFC 3339 format.
    """
    creds = get_credentials()
    service = build('tasks', 'v1', credentials=creds)
    try:
        task = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
        if title is not None:
            task['title'] = title
        if notes is not None:
            task['notes'] = notes
        if due_date_rfc3339 is not None:
            task['due'] = due_date_rfc3339
        result = service.tasks().update(tasklist=tasklist_id, task=task_id, body=task).execute()
        return f"Task updated: {result['title']} (ID: {result['id']})"
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def complete_task(task_id: str, tasklist_id: str = '@default') -> str:
    """Mark a task as completed.

    Args:
        task_id: The task ID to mark complete.
        tasklist_id: The task list ID containing the task (defaults to '@default').
    """
    creds = get_credentials()
    service = build('tasks', 'v1', credentials=creds)
    try:
        task = service.tasks().get(tasklist=tasklist_id, task=task_id).execute()
        task['status'] = 'completed'
        task['completed'] = datetime.utcnow().isoformat() + 'Z'
        result = service.tasks().update(tasklist=tasklist_id, task=task_id, body=task).execute()
        return f"Task completed: {result['title']}"
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def delete_task(task_id: str, tasklist_id: str = '@default') -> str:
    """Delete a task.

    Args:
        task_id: The task ID to delete.
        tasklist_id: The task list ID containing the task (defaults to '@default').
    """
    creds = get_credentials()
    service = build('tasks', 'v1', credentials=creds)
    try:
        service.tasks().delete(tasklist=tasklist_id, task=task_id).execute()
        return f"Task {task_id} deleted."
    except Exception as e:
        return f"An error occurred: {e}"

if __name__ == "__main__":
    mcp.run(transport='stdio')
