import os.path
import base64
from email.message import EmailMessage
from datetime import datetime, timedelta

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from mcp.server.fastmcp import FastMCP

# If modifying these scopes, delete the file token.json.
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

# Initialize FastMCP
mcp = FastMCP("GoogleWorkspace")

# --- GMAIL TOOLS ---

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

# --- CALENDAR TOOLS ---

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
        now = datetime.utcnow().isoformat() + 'Z'  # 'Z' indicates UTC time
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
            output.append(f"Start: {start} | Summary: {event['summary']}")
            
        return "\n".join(output)
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def create_calendar_event(summary: str, start_time_iso: str, end_time_iso: str, description: str = "") -> str:
    """Create a new event in your primary Google Calendar.
    
    Args:
        summary: Title of the event.
        start_time_iso: Start time in ISO format (e.g. '2026-05-10T09:00:00-07:00').
        end_time_iso: End time in ISO format (e.g. '2026-05-10T10:00:00-07:00').
        description: Optional description of the event.
    """
    creds = get_credentials()
    service = build('calendar', 'v3', credentials=creds)
    
    try:
        event = {
            'summary': summary,
            'description': description,
            'start': {'dateTime': start_time_iso},
            'end': {'dateTime': end_time_iso},
        }
        
        event = service.events().insert(calendarId='primary', body=event).execute()
        return f"Event created: {event.get('htmlLink')}"
    except Exception as e:
        return f"An error occurred: {e}"

# --- TASKS TOOLS ---

@mcp.tool()
def list_tasks(max_results: int = 10) -> str:
    """List tasks from your primary Google Tasks list.
    
    Args:
        max_results: Maximum number of tasks to return.
    """
    creds = get_credentials()
    service = build('tasks', 'v1', credentials=creds)
    
    try:
        results = service.tasks().list(tasklist='@default', maxResults=max_results).execute()
        items = results.get('items', [])
        
        if not items:
            return "No tasks found."
            
        output = []
        for item in items:
            status = item.get('status', 'needsAction')
            due = item.get('due', 'No due date')
            output.append(f"Title: {item['title']} | Status: {status} | Due: {due}")
            
        return "\n".join(output)
    except Exception as e:
        return f"An error occurred: {e}"

@mcp.tool()
def create_task(title: str, notes: str = "", due_date_rfc3339: str = None) -> str:
    """Create a new task in your primary Google Tasks list.
    
    Args:
        title: The title of the task.
        notes: Optional notes/description for the task.
        due_date_rfc3339: Optional due date in RFC 3339 timestamp format (e.g., '2026-05-10T00:00:00.000Z').
    """
    creds = get_credentials()
    service = build('tasks', 'v1', credentials=creds)
    
    try:
        task = {
            'title': title,
            'notes': notes,
        }
        if due_date_rfc3339:
            task['due'] = due_date_rfc3339
            
        result = service.tasks().insert(tasklist='@default', body=task).execute()
        return f"Task created: {result['title']} (ID: {result['id']})"
    except Exception as e:
        return f"An error occurred: {e}"

if __name__ == "__main__":
    # Start the MCP server
    mcp.run(transport='stdio')
