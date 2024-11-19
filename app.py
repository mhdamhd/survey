# app.py

import json
import os
import time
import dash
from dash import html, dcc, Input, Output, State, callback
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import uuid
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
# from io import BytesIO
# from PIL import Image
# import base64
# from googleapiclient.http import MediaIoBaseDownload

# Initialize the Dash app with Bootstraps
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    url_base_pathname='/',
    suppress_callback_exceptions=True
)

server = app.server  # For production deployment

# Google Sheets and Drive Configuration
SHEET_ID = '1dzWJ5vqYjIu5UuqwRTdxCf58aIAiQGNntMrXPNf5U2I'
DATABASE_SHEET_ID = '1VsNv9kAVl-JEA5m8jS2ZNSCrvi8m0GThBZ5b_N9dxII'
# DRIVE_FOLDER_ID = '1yRERxJiQ86CvkS7vp2qCwPUyg1HK95SW'
DRIVE_FOLDER_ID = '1AUmkb2SnbayhMGW_xa6NacNfDHY0MDgV'
# SERVICE_ACCOUNT_FILE = './service_account_key.json'
service_account_key = os.environ.get('SERVICE_ACCOUNT_KEY', '{}')
SERVICE_ACCOUNT_INFO = json.loads(service_account_key)

# Global configurations
CONFIG = {
    'BASE_URL': 'https://raw-camel-myownbusiness-b038f14b.koyeb.app',  # Change this in production
    'REVIEW_PATH': '/review'
}

# Initialize Google Sheets and Drive API
# creds = service_account.Credentials.from_service_account_info(
#     GOOGLE_CREDENTIALS,
#     scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
# )
creds = service_account.Credentials.from_service_account_info(
    SERVICE_ACCOUNT_INFO,
    scopes=['https://www.googleapis.com/auth/spreadsheets', 'https://www.googleapis.com/auth/drive']
)
sheets_service = build('sheets', 'v4', credentials=creds)

def get_column_letter(n):
        """Convert a number to a Google Sheets-style column letter."""
        result = ""
        while n > 0:
            n, remainder = divmod(n - 1, 26)
            result = chr(65 + remainder) + result  # Ensures letters are A-Z only
        return result

def get_folder_names_from_sheet(sheet_id):
    """Retrieve folder names from the 'Names' sheet in the Google Sheets file."""
    try:
        response = sheets_service.spreadsheets().values().get(
            spreadsheetId=sheet_id,
            range='Names!A2:A'  # Adjust the range if necessary
        ).execute()
        folder_names = [row[0] for row in response.get('values', []) if row]
        print(f"Retrieved {len(folder_names)} folder names from Google Sheets.")
        return folder_names
    except Exception as e:
        print(f"Error retrieving folder names from Google Sheets: {e}")
        return []


class UserManager:
    """Enhanced user management with secure tokens and folder distribution."""

    def __init__(self, sheets_service, sheet_id):
        self.users = {}
        self.access_tokens = {}
        self.sheets_service = sheets_service
        self.sheet_id = sheet_id
        self.load_users_from_sheet()
        self.initialize_distribution_sheet()
        self.pending_distributions = []  # Initialize the list for batch saving

    def initialize_distribution_sheet(self):
        """Initialize Distribution sheet with token and folder_name columns."""
        headers = [["token", "folder_name"]]
        try:
            result = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range='Distribution!A1:B1'
            ).execute()

            if 'values' not in result:
                # Sheet does not exist or is empty, set up headers
                self.sheets_service.spreadsheets().values().append(
                    spreadsheetId=self.sheet_id,
                    range='Distribution!A1',
                    valueInputOption='RAW',
                    insertDataOption='INSERT_ROWS',
                    body={'values': headers}
                ).execute()
                print("Initialized Distribution sheet.")
        except Exception as e:
            print(f"Error initializing Distribution sheet: {e}")


    def add_user(self, username, email):
        """Add a new user with a secure, unique token and save to Google Sheets."""
        user_id = str(uuid.uuid4())
        
        while True:
            access_token = str(uuid.uuid4())
            if access_token not in self.access_tokens:
                break
        
        user_data = {
            'username': username,
            'email': email,
            'access_token': access_token,
            'assigned_folders': set()  # Using set for efficient operations
        }
        self.users[user_id] = user_data
        self.access_tokens[access_token] = user_id
        
        review_url = f"{CONFIG['BASE_URL']}{CONFIG['REVIEW_PATH']}?token={access_token}"
        
        # Save the new user to Google Sheets
        self.save_user_to_sheet(user_id, user_data)
        
        return user_id, review_url

    def save_user_to_sheet(self, user_id, user_data):
        """Save a user's details to Google Sheets."""
        row = [
            user_id,
            user_data['username'],
            user_data['email'],
            user_data['access_token']
        ]
        
        try:
            self.sheets_service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range='Users!A2',  # Assuming the user data starts from A2
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()
        except Exception as e:
            print(f"Error saving user to Google Sheets: {e}")

    def get_user_by_token(self, token):
        """Get user information from access token, including assigned folders from Google Sheets."""
        user_id = self.access_tokens.get(token)
        if not user_id or user_id not in self.users:
            return None

        # Attempt to find the row for the user in Google Sheets by matching the user_id
        try:
            response = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range='Users!A2:Z'  # Adjust as needed to ensure you cover all user rows
            ).execute()

            # Locate the user row
            for idx, row in enumerate(response.get('values', []), start=2):  # start=2 to match Google Sheets row numbers
                if row[0] == user_id:  # Assume user_id is in column A
                    assigned_folders = row[4:]  # Columns E onwards hold folders
                    self.users[user_id]['assigned_folders'] = set(assigned_folders)
                    break
            else:
                self.users[user_id]['assigned_folders'] = set()  # Default to empty if not found

        except Exception as e:
            print(f"Error loading assigned folders for user {user_id}: {e}")
            self.users[user_id]['assigned_folders'] = set()

        return self.users[user_id]


    def load_users_from_sheet(self):
        """Load all users from Google Sheets."""
        try:
            response = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range='Users!A2:D'  # Adjust the range as necessary
            ).execute()
            
            if 'values' in response:
                self.users.clear()
                self.access_tokens.clear()
                for row in response['values']:
                    user_id, username, email, access_token = row
                    self.users[user_id] = {
                        'username': username,
                        'email': email,
                        'access_token': access_token,
                        'assigned_folders': set()
                    }
                    self.access_tokens[access_token] = user_id
            print("Users loaded from Google Sheets successfully.")

        except Exception as e:
            print(f"Error loading users from Google Sheets: {e}")


    def distribute_folders(self, folder_names, selected_user_ids):
        """
        Distribute folder names among selected users evenly and log each distribution in the Distribution sheet.
        """
        try:
            if not folder_names or not selected_user_ids:
                print("No folders or users to distribute")
                return False

            # Initialize distribution sheet if needed
            self.initialize_distribution_sheet()

            # Distribute folders evenly among users
            num_users = len(selected_user_ids)
            folders_per_user = len(folder_names) // num_users
            extra_folders = len(folder_names) % num_users
            folder_index = 0
            rows_to_append = []

            for i, user_id in enumerate(selected_user_ids):
                if user_id not in self.users:
                    continue

                # Calculate the number of folders for this user
                num_folders = folders_per_user + (1 if i < extra_folders else 0)
                user_folders = [folder_names[folder_index + j] for j in range(num_folders)]
                token = self.users[user_id]['access_token']
                folder_index += num_folders

                # Prepare data to append to "Distribution" sheet
                for folder_name in user_folders:
                    rows_to_append.append([token, folder_name])

            # Append rows to "Distribution" sheet
            self.sheets_service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range='Distribution!A2',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': rows_to_append}
            ).execute()

            print("Folders distributed and logged in Distribution sheet successfully.")
            return True

        except Exception as e:
            print(f"Error in distribute_folders: {e}")
            return False

    def get_user_row(self, user_id):
        """
        Retrieve the row number for a specific user by user_id in Google Sheets.
        Assumes that the user_id is located in column A of the 'Users' sheet.
        """
        try:
            response = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range='Users!A2:A'  # Adjust the range if necessary
            ).execute()

            # Google Sheets rows are 1-indexed, and our range starts from row 2
            for idx, row in enumerate(response.get('values', []), start=2):  # start=2 to match the row number
                if row[0] == user_id:
                    return idx

            print(f"User ID {user_id} not found in Google Sheets.")
            return None

        except Exception as e:
            print(f"Error retrieving user row: {e}")
            return None

    def save_batch_to_sheet(self):
        """Save the assigned folders as additional columns in each user's row."""
        if not self.pending_distributions:
            print("No pending distributions to save.")
            return

        try:
            # Retrieve existing data to find the row numbers for each user
            existing_data = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range='Users!A2:D'  # Adjust if needed
            ).execute().get('values', [])

            # Dictionary to map user_id to row index (Google Sheets rows are 1-indexed)
            user_row_map = {row[0]: idx + 2 for idx, row in enumerate(existing_data)}  # Start from A2

            # Prepare batch update for each user's row with folder names
            data_to_update = []
            for folder_name, _, username, _ in self.pending_distributions:
                user_id = next((user_id for user_id, info in self.users.items() if info['username'] == username), None)
                if user_id and user_id in user_row_map:
                    row_number = user_row_map[user_id]  # Ensure row_number is a valid integer
                    range_to_update = f'Users!E{row_number}'  # Format correctly as 'Users!E2', etc.
                    data_to_update.append({
                        'range': range_to_update,
                        'majorDimension': 'ROWS',
                        'values': [[folder_name]]
                    })

            # Execute batch update with the accumulated data for all users
            if data_to_update:
                try:
                    self.sheets_service.spreadsheets().values().batchUpdate(
                        spreadsheetId=self.sheet_id,
                        body={'data': data_to_update, 'valueInputOption': 'RAW'}
                    ).execute()
                    print("Folders successfully updated for each user.")
                except Exception as e:
                    print(f"Error saving folders to Google Sheets: {e}")

        except Exception as e:
            print(f"Error saving batch to Google Sheets: {e}")

    def get_user_assignments(self, token):
        """Retrieve folders assigned to a specific user from the Distribution sheet."""
        try:
            response = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range='Distribution!A2:B'
            ).execute()

            # Retrieve folders assigned to this token
            assigned_folders = [
                row[1] for row in response.get('values', []) if row[0] == token
            ]
            
            # Debugging statement
            print(f"Assigned folders for token {token}: {assigned_folders}")
            
            return assigned_folders

        except Exception as e:
            print(f"Error retrieving assignments for token {token}: {e}")
            return []

class GoogleSheetsManager:
    """Simplified Google Sheets integration with specific columns."""

    def __init__(self, sheet_id, service):
        self.sheet_id = sheet_id
        self.service = service
        self.initialize_sheet()

    def initialize_sheet(self):
        """Initialize sheet with specified columns."""
        headers = [[
            'Folder',
            'Review Date',
            'Reviewer',
            'Decision'
        ]]

        try:
            result = self.service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range='Sheet1!A1:D1'
            ).execute()

            if 'values' not in result:
                self.service.spreadsheets().values().append(
                    spreadsheetId=self.sheet_id,
                    range='Sheet1!A1',
                    valueInputOption='RAW',
                    insertDataOption='INSERT_ROWS',
                    body={'values': headers}
                ).execute()
        except Exception as e:
            print(f"Error initializing sheet: {e}")
            raise

    def log_review(self, folder_name, reviewer, decision):
        """Log review with essential fields only."""
        row = [
            folder_name,
            datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
            reviewer,
            decision
        ]

        try:
            self.service.spreadsheets().values().append(
                spreadsheetId=self.sheet_id,
                range='Sheet1!A2',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [row]}
            ).execute()
            return True
        except Exception as e:
            print(f"Error logging review: {e}")
            return False

class ImageReviewApp:
    """Application class that constructs image URLs based on folder names."""

    def __init__(self, sheets_manager, user_manager):
        self.folders = {}  # Mapping from folder name to image URLs
        self.sheets_manager = sheets_manager
        self.user_manager = user_manager
        # Fetch folder names from the Google Sheets 'Names' sheet
        self.folder_names = get_folder_names_from_sheet(DATABASE_SHEET_ID)
        self.construct_folder_image_urls()

    def construct_folder_image_urls(self):
        """Construct image URLs for each folder name."""
        for folder_name in self.folder_names:
            before_image_url = f"https://magic-rewards.com/maids/output_for_survey/{folder_name}/photo.jpeg"
            after_image_url = f"https://magic-rewards.com/maids/output_for_survey/{folder_name}/photo_enhanced.jpeg"
            self.folders[folder_name] = {
                'before_image_url': before_image_url,
                'after_image_url': after_image_url,
                'processed': True,
                'error': None
            }


# Initialize managers
user_manager = UserManager(sheets_service=sheets_service, sheet_id='1VsNv9kAVl-JEA5m8jS2ZNSCrvi8m0GThBZ5b_N9dxII')
sheets_manager = GoogleSheetsManager(SHEET_ID, sheets_service)
review_app = ImageReviewApp(sheets_manager, user_manager)

# Layout Components
def create_admin_layout():
    # Get the current users
    users = user_manager.users
    user_list = html.Div([
        dbc.ListGroup([dbc.ListGroupItem(f"{info['username']} ({info['email']})") for info in users.values()])
    ])
    options = [{'label': f"{info['username']} ({info['email']})", 'value': user_id} for user_id, info in users.items()]

    return dbc.Container([
        html.H1("Image Enhancement Review Dashboard", className='text-center mb-4'),

        dbc.Row([
            dbc.Col([
                dbc.Card([
                    dbc.CardHeader("User Management"),
                    dbc.CardBody([
                        dbc.Input(id='username-input', placeholder='Username', className='mb-2'),
                        dbc.Input(id='email-input', placeholder='Email', className='mb-2'),
                        dbc.Button("Add User", id='add-user-button', color='primary', className='mb-3'),
                        dbc.Button("Refresh Users", id='refresh-users-button', color='secondary', className='mb-3', style={'margin-left': '10px'}),
                        html.Div(id='user-action-status', className='mt-2'),  # For status messages
                        html.Div(id='user-list', children=user_list),
                        html.Hr(),
                        html.H6("Registered Users"),
                        dbc.Checklist(id='user-selection-checklist', options=options, value=[])
                    ])
                ], className='mb-3'),

                dbc.Card([
                    dbc.CardHeader("Folder Distribution"),
                    dbc.CardBody([
                        html.Div(id='distribution-status'),
                        html.Div(id='user-links', className='mt-3'),
                        dbc.Button("Distribute Folders", id='distribute-button', color='primary', className='mt-3')
                    ])
                ])
            ], width=12, lg=4)
        ])
    ], fluid=True)



def format_metrics(metrics):
    """Formats image metrics for display."""
    return html.Div([
        html.P(f"{key.replace('_', ' ').title()}: {value:.2f}" if isinstance(value, float) else f"{key.replace('_', ' ').title()}: {value}")
        for key, value in metrics.items()
    ])

def create_review_layout(token):
    user = user_manager.get_user_by_token(token)
    if not user:
        return html.Div("Invalid access token", className='text-center p-5')
    
    return dbc.Container([
        html.H2(f"Welcome, {user['username']}!", className='text-center mb-4'),
        dcc.Store(id='user-token-store', data={'token': token}),
        dcc.Store(id='review-session-store', data={}),  # Initialized empty; data will be set in callback

        dbc.Row([
            dbc.Col([
                html.H5("Before", className='text-center'),
                html.Img(
                    id='before-image',
                    src='',  # Initialize with an empty string or placeholder
                    className='img-fluid',
                    style={'height': '300px', 'width': 'auto', 'margin-left': '200px'}
                ),
            ], md=6),
            dbc.Col([
                html.H5("After", className='text-center'),
                html.Img(
                    id='after-image',
                    src='',  # Initialize with an empty string or placeholder
                    className='img-fluid',
                    style={'height': '300px', 'width': 'auto', 'margin-left': '200px'}
                ),
            ], md=6),
        ]),
        dbc.Row([
            dbc.Col([
                html.Div([
                    dbc.Button("Accept", id='accept-button', color='success', className='me-2'),
                    dbc.Button("Reject", id='reject-button', color='danger', className='ms-2'),
                ], id='review-buttons'),
            ], className='text-center mt-4')
        ]),
        dbc.Row([
            dbc.Col([
                dbc.Progress(id='review-progress', className='mt-4'),
                html.Div(id='review-status', className='text-center mt-2')
            ])
        ])
    ], fluid=True)


# URL Routing
app.layout = html.Div([
    dcc.Location(id='url', refresh=False),
    html.Div(id='page-content')
])

@callback(
    Output('page-content', 'children'),
    Input('url', 'pathname'),
    Input('url', 'search')
)
def display_page(pathname, search):
    if pathname == CONFIG['REVIEW_PATH']:
        token = search.split('=')[-1] if search else None
        return create_review_layout(token)
    return create_admin_layout()

@callback(
    [Output('user-list', 'children'),
     Output('user-selection-checklist', 'options'),
     Output('username-input', 'value'),
     Output('email-input', 'value'),
     Output('user-action-status', 'children')],
    [Input('add-user-button', 'n_clicks'),
     Input('refresh-users-button', 'n_clicks')],
    [State('username-input', 'value'),
     State('email-input', 'value')]
)
def update_user_list(add_user_clicks, refresh_users_clicks, username, email):
    ctx = dash.callback_context
    triggered_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

    # Initialize return variables
    user_list = html.Div()
    options = []
    username_value = username
    email_value = email
    status_message = ''

    if triggered_id == 'add-user-button':
        if username and email:
            user_manager.add_user(username, email)
            status_message = html.Div("User added successfully.", className='text-success')
            username_value = ''
            email_value = ''
        else:
            status_message = html.Div("Please enter both username and email.", className='text-danger')

    elif triggered_id == 'refresh-users-button':
        user_manager.load_users_from_sheet()
        status_message = html.Div("Users refreshed from Google Sheet.", className='text-info')

    # Update user list and options after any action
    users = user_manager.users
    user_list = html.Div([
        dbc.ListGroup([dbc.ListGroupItem(f"{info['username']} ({info['email']})") for info in users.values()])
    ])
    options = [{'label': f"{info['username']} ({info['email']})", 'value': user_id} for user_id, info in users.items()]

    return user_list, options, username_value, email_value, status_message

@callback(
    [Output('distribution-status', 'children'),
     Output('user-links', 'children')],
    Input('distribute-button', 'n_clicks'),
    [State('user-selection-checklist', 'value')]
)
def distribute_folders_callback(n_clicks, selected_users):
    if not n_clicks or not selected_users:
        raise PreventUpdate

    # Get folder names from the 'Names' sheet
    folder_names = get_folder_names_from_sheet(DATABASE_SHEET_ID)

    if not folder_names:
        return html.Div("No folders available.", className='text-warning'), None

    # Distribute folders among selected users
    success = user_manager.distribute_folders(folder_names, selected_users)
    if not success:
        return html.Div("Error distributing folders.", className='text-danger'), None

    links = [html.Div([
                html.H6(f"{user_manager.users[user_id]['username']}"),
                html.P(f"Review Link: {CONFIG['BASE_URL']}{CONFIG['REVIEW_PATH']}?token={user_manager.users[user_id]['access_token']}")
            ]) for user_id in selected_users]
    return html.Div("Folders distributed successfully!", className='text-success'), html.Div(links)


@callback(
    Output('review-session-store', 'data'),
    Input('url', 'pathname'),
    State('user-token-store', 'data')
)
def initialize_review_session(pathname, token_data):
    if pathname != CONFIG['REVIEW_PATH'] or not token_data:
        raise PreventUpdate

    user = user_manager.get_user_by_token(token_data['token'])
    if not user:
        raise PreventUpdate

    # Fetch assigned folders once
    assigned_folders = user_manager.get_user_assignments(user['access_token'])

    # Fetch reviewed folders
    reviewed_folders = get_reviewed_folders_from_sheet(user['username'])

    # Store both assigned and reviewed folders
    return {
        'assigned_folders': assigned_folders,
        'reviewed': list(reviewed_folders)
    }

@callback(
    Output('review-session-store', 'data', allow_duplicate=True),
    [Input('accept-button', 'n_clicks'), Input('reject-button', 'n_clicks')],
    [State('user-token-store', 'data'), State('review-session-store', 'data')],
    prevent_initial_call=True
)
def log_review_to_sheets_and_session(accept_clicks, reject_clicks, token_data, session_data):
    if not token_data or not session_data:
        raise PreventUpdate

    user = user_manager.get_user_by_token(token_data['token'])
    if not user:
        raise PreventUpdate

    assigned_folders = session_data['assigned_folders']
    reviewed_set = set(session_data['reviewed'])
    unreviewed = [folder for folder in assigned_folders if folder not in reviewed_set]

    if not unreviewed:
        return dash.no_update

    current_folder_name = unreviewed[0]

    ctx = dash.callback_context
    if ctx.triggered:
        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        decision = 'accept' if button_id == 'accept-button' else 'reject'
        review_date = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        reviewer = user['username']
        review_row = [current_folder_name, review_date, reviewer, decision]

        # Log to Google Sheets
        try:
            sheets_service.spreadsheets().values().append(
                spreadsheetId=SHEET_ID,
                range='Sheet1!A2',
                valueInputOption='RAW',
                insertDataOption='INSERT_ROWS',
                body={'values': [review_row]}
            ).execute()
        except Exception as e:
            print(f"Error logging review to Google Sheets: {e}")
            return dash.no_update

        # Update the reviewed data in session
        reviewed_set.add(current_folder_name)
        session_data['reviewed'] = list(reviewed_set)
        return session_data

    return dash.no_update



def get_reviewed_folders_from_sheet(reviewer_username, retries=3, delay=1):
    """Retrieve reviewed folders from the Google Sheet for a specific reviewer with retries."""
    for attempt in range(retries):
        try:
            response = sheets_service.spreadsheets().values().get(
                spreadsheetId=SHEET_ID,
                range='Sheet1!A2:D'  # Adjusted range to include the 'Reviewer' column
            ).execute()
            # Convert list of rows to a set of reviewed folder names by the reviewer
            reviewed_folders = {
                row[0] for row in response.get('values', [])
                if len(row) >= 3 and row[2] == reviewer_username  # Check if 'Reviewer' matches
            }
            return reviewed_folders
        except Exception as e:
            print(f"Attempt {attempt + 1}: Error retrieving reviewed folders from Google Sheet: {e}")
            if attempt < retries - 1:
                time.sleep(delay)  # Wait before retrying
            else:
                print("Max retries reached. Unable to retrieve updated data from Google Sheets.")
                return set()

@callback(
    [
        Output('before-image', 'src'),
        Output('after-image', 'src'),
        Output('review-progress', 'value'),
        Output('review-status', 'children'),
        Output('review-buttons', 'style')
    ],
    Input('review-session-store', 'data'),
    State('user-token-store', 'data')
)
def handle_review(session_data, token_data):
    if not token_data or not session_data:
        raise PreventUpdate

    user = user_manager.get_user_by_token(token_data['token'])
    if not user:
        raise PreventUpdate

    assigned_folders = session_data['assigned_folders']
    reviewed_folders = set(session_data['reviewed'])
    unreviewed = [folder for folder in assigned_folders if folder not in reviewed_folders]

    if not unreviewed:
        return None, None, 100, "All folders reviewed!", {'display': 'none'}

    current_folder_name = unreviewed[0]

    folder_data = review_app.folders.get(current_folder_name)
    if not folder_data:
        return None, None, 0, f"Error loading folder {current_folder_name}", {'display': 'none'}

    before_image_url = folder_data['before_image_url']
    after_image_url = folder_data['after_image_url']

    total_folders = len(assigned_folders)
    reviewed_count = len(reviewed_folders)
    progress = (reviewed_count / total_folders) * 100
    status_message = f"Reviewed {reviewed_count} of {total_folders} folders"

    return before_image_url, after_image_url, progress, status_message, {'display': 'block'}


if __name__ == '__main__':
    app.run_server(debug=True, port=8050)
