# app.py

import json
import os
import dash
from dash import html, dcc, Input, Output, State, callback
import dash_bootstrap_components as dbc
from dash.exceptions import PreventUpdate
import uuid
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from io import BytesIO
from PIL import Image
import base64
from googleapiclient.http import MediaIoBaseDownload
import time

# Initialize the Dash app with Bootstrap
app = dash.Dash(
    __name__,
    external_stylesheets=[dbc.themes.BOOTSTRAP],
    url_base_pathname='/',
    suppress_callback_exceptions=True
)

server = app.server  # For production deployment

# Google Sheets and Drive Configuration
SHEET_ID = '1dzWJ5vqYjIu5UuqwRTdxCf58aIAiQGNntMrXPNf5U2I'
# DRIVE_FOLDER_ID = '1yRERxJiQ86CvkS7vp2qCwPUyg1HK95SW'
DRIVE_FOLDER_ID = '1AUmkb2SnbayhMGW_xa6NacNfDHY0MDgV'
# SERVICE_ACCOUNT_FILE = './service_account_key.json'
service_account_key = os.environ.get('SERVICE_ACCOUNT_KEY', '{}')
SERVICE_ACCOUNT_INFO = json.loads(service_account_key)

# Global configurations
CONFIG = {
    'BASE_URL': 'http://localhost:8050',  # Change this in production
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
drive_service = build('drive', 'v3', credentials=creds)

def get_column_letter(n):
        """Convert a number to a Google Sheets-style column letter."""
        result = ""
        while n > 0:
            n, remainder = divmod(n - 1, 26)
            result = chr(65 + remainder) + result  # Ensures letters are A-Z only
        return result

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
        """Load all users from Google Sheets at startup."""
        try:
            response = self.sheets_service.spreadsheets().values().get(
                spreadsheetId=self.sheet_id,
                range='Users!A2:D'  # Assuming the data is in columns A through D
            ).execute()
            
            if 'values' in response:
                for row in response['values']:
                    user_id, username, email, access_token = row
                    self.users[user_id] = {
                        'username': username,
                        'email': email,
                        'access_token': access_token,
                        'assigned_folders': set()  # Initialize with empty set
                    }
                    self.access_tokens[access_token] = user_id
            print("Users loaded from Google Sheets successfully.")

        except Exception as e:
            print(f"Error loading users from Google Sheets: {e}")


    def distribute_folders(self, folders, selected_user_ids):
        """
        Distribute folders among selected users evenly and log each distribution in the Distribution sheet.
        """
        try:
            if not folders or not selected_user_ids:
                print("No folders or users to distribute")
                return False

            # Initialize distribution sheet if needed
            self.initialize_distribution_sheet()

            # Distribute folders evenly among users
            num_users = len(selected_user_ids)
            folders_per_user = len(folders) // num_users
            extra_folders = len(folders) % num_users
            folder_index = 0
            rows_to_append = []

            for i, user_id in enumerate(selected_user_ids):
                if user_id not in self.users:
                    continue

                # Calculate the number of folders for this user
                num_folders = folders_per_user + (1 if i < extra_folders else 0)
                user_folders = [folders[folder_index + j]['name'] for j in range(num_folders)]
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
    """Application class with folder management, retrieving images from Google Drive."""

    def __init__(self, sheets_manager, user_manager, drive_service):
        self.folders = {}
        self.sheets_manager = sheets_manager
        self.user_manager = user_manager
        self.drive_service = drive_service
        # Fetch folders and create name-to-ID mapping
        self.folder_name_to_id = self.create_folder_name_to_id_map(DRIVE_FOLDER_ID)

    def create_folder_name_to_id_map(self, drive_folder_id):
        """Fetch folders and create a mapping of folder names to IDs."""
        folders = get_drive_folders(drive_folder_id)
        folder_name_to_id = {folder['name']: folder['id'] for folder in folders}
        return folder_name_to_id

    def fetch_drive_image(self, file_id):
        """Retrieve image data from Google Drive as a base64-encoded string."""
        try:
            request = self.drive_service.files().get_media(fileId=file_id)
            fh = BytesIO()
            downloader = MediaIoBaseDownload(fh, request)
            done = False
            while not done:
                status, done = downloader.next_chunk()
            fh.seek(0)
            img = Image.open(fh)
            buffered = BytesIO()
            img.save(buffered, format="JPEG")
            encoded_image = base64.b64encode(buffered.getvalue()).decode('utf-8')
            return f"data:image/jpeg;base64,{encoded_image}"
        except HttpError as e:
            print(f"Error fetching image from Drive: {e}")
            return None
        except Exception as e:
            print(f"Unexpected error while fetching image: {e}")
            return None

    def process_folder(self, folder_id):
        """Process a Google Drive folder to retrieve images."""
        try:
            print(f"Processing Google Drive folder with ID: {folder_id}")
            results = self.drive_service.files().list(
                q=f"'{folder_id}' in parents",
                fields="files(id, name)"
            ).execute()

            files = results.get('files', [])
            photo_file = next((f for f in files if 'photo.jpeg' in f['name'].lower()), None)
            enhanced_file = next((f for f in files if 'photo_enhanced.jpeg' in f['name'].lower()), None)

            # Check if both required images are found
            if not photo_file or not enhanced_file:
                print(f"Missing required images in folder {folder_id}")
                raise ValueError("Folder must contain 'photo.jpeg' and 'photo_enhanced.jpeg'.")

            # Fetch images, checking if any retrieval fails
            before_image = self.fetch_drive_image(photo_file['id'])
            after_image = self.fetch_drive_image(enhanced_file['id'])

            if not before_image or not after_image:
                print(f"Failed to retrieve one or both images in folder {folder_id}")
                raise ValueError("Failed to retrieve 'photo.jpeg' or 'photo_enhanced.jpeg'.")

            # Store images if successfully retrieved
            self.folders[folder_id] = {
                'before_image': before_image,
                'after_image': after_image,
                'processed': True,
                'error': None
            }
            print(f"Successfully processed folder with ID: {folder_id}")
            return True

        except Exception as e:
            error_msg = str(e)
            print(f"Error processing folder {folder_id}: {error_msg}")
            self.folders[folder_id] = {'processed': False, 'error': error_msg}
            return False


# Helper function to retrieve folders from Google Drive
def get_drive_folders(folder_id):
    """Retrieve all subfolders in the given Google Drive folder, handling pagination."""
    folders = []
    page_token = None
    try:
        while True:
            query = f"'{folder_id}' in parents and mimeType = 'application/vnd.google-apps.folder'"
            response = drive_service.files().list(
                q=query,
                fields="nextPageToken, files(id, name)",
                pageToken=page_token
            ).execute()
            
            # Append current page of folders to the list
            folders.extend(response.get('files', []))
            page_token = response.get('nextPageToken')

            # Exit if there are no more pages
            if not page_token:
                break
        
        print(f"Retrieved {len(folders)} folders from Drive.")
        return folders
    except Exception as e:
        print(f"Error retrieving folders: {e}")
        return []

# Initialize managers
user_manager = UserManager(sheets_service=sheets_service, sheet_id='1VsNv9kAVl-JEA5m8jS2ZNSCrvi8m0GThBZ5b_N9dxII')
sheets_manager = GoogleSheetsManager(SHEET_ID, sheets_service)
review_app = ImageReviewApp(sheets_manager, user_manager, drive_service)

# Layout Components
def create_admin_layout():
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
                        html.Div(id='user-list'),
                        html.Hr(),
                        html.H6("Registered Users"),
                        dbc.Checklist(id='user-selection-checklist', options=[], value=[])
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

    # Fetch assigned folders from Distribution sheet
    assigned_folders = user_manager.get_user_assignments(user['access_token'])
    
    # Debugging statement
    print(f"Assigned folders for user {user['username']}: {assigned_folders}")

    if not assigned_folders:
        return html.Div(f"Welcome, {user['username']}! No folders assigned.", className='text-center p-5')

    # Get the first assigned folder name (we'll start here in the sequence)
    current_folder_name = assigned_folders[0]
    current_folder_id = review_app.folder_name_to_id.get(current_folder_name)
    
    if not current_folder_id:
        print(f"Error: Folder ID for name '{current_folder_name}' not found.")
        return html.Div(f"Error loading data for folder: {current_folder_name}", className='text-danger')

    # Process the folder if not already done
    if current_folder_id not in review_app.folders:
        success = review_app.process_folder(current_folder_id)
        if not success:
            return html.Div(f"Error processing folder: {current_folder_name}", className='text-danger')

    # Retrieve folder data
    folder_data = review_app.folders.get(current_folder_id)
    before_image = folder_data['before_image']
    after_image = folder_data['after_image']

    return dbc.Container([
        html.H2(f"Welcome, {user['username']}!", className='text-center mb-4'),
        dcc.Store(id='user-token-store', data={'token': token}),  # Store for token
        dcc.Store(id='review-session-store', data={'reviewed': []}),  # Store for review session

        dbc.Row([
            dbc.Col([
                html.H5("Before", className='text-center'),
                html.Img(id='before-image', src=before_image, className='img-fluid', style={'height': '300px', 'width': 'auto', 'margin-left': '200px'}),
            ], md=6),
            dbc.Col([
                html.H5("After", className='text-center'),
                html.Img(id='after-image', src=after_image, className='img-fluid', style={'height': '300px', 'width': 'auto', 'margin-left': '200px'}),
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
     Output('user-selection-checklist', 'options')],
    [Input('add-user-button', 'n_clicks')],
    [State('username-input', 'value'),
     State('email-input', 'value')]
)
def handle_add_user(n_clicks, username, email):
    if not n_clicks or not username or not email:
        users = user_manager.users
        user_list = html.Div([
            dbc.ListGroup([dbc.ListGroupItem(f"{info['username']} ({info['email']})") for info in users.values()])
        ])
        options = [{'label': f"{info['username']} ({info['email']})", 'value': user_id} for user_id, info in users.items()]
        return user_list, options

    user_id, _ = user_manager.add_user(username, email)
    users = user_manager.users
    user_list = html.Div([
        dbc.ListGroup([dbc.ListGroupItem(f"{info['username']} ({info['email']})") for info in users.values()])
    ])
    options = [{'label': f"{info['username']} ({info['email']})", 'value': user_id} for user_id, info in users.items()]
    return user_list, options

@callback(
    [Output('distribution-status', 'children'),
     Output('user-links', 'children')],
    Input('distribute-button', 'n_clicks'),
    [State('user-selection-checklist', 'value')]
)
def distribute_folders_callback(n_clicks, selected_users):
    if not n_clicks or not selected_users:
        raise PreventUpdate

    folders = get_drive_folders(DRIVE_FOLDER_ID)
    
    if not folders:
        return html.Div("No folders available.", className='text-warning'), None

    success = user_manager.distribute_folders(folders, selected_users)
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

    reviewed_folders = get_reviewed_folders_from_sheet()
    return {'reviewed': list(reviewed_folders)}


@callback(
    Output('review-session-store', 'data', allow_duplicate=True),
    [Input('accept-button', 'n_clicks'), Input('reject-button', 'n_clicks')],
    [State('user-token-store', 'data'), State('review-session-store', 'data')],
    prevent_initial_call=True
)
def log_review_to_sheets_and_session(accept_clicks, reject_clicks, token_data, review_data):
    if not token_data:
        raise PreventUpdate

    user = user_manager.get_user_by_token(token_data['token'])
    if not user:
        raise PreventUpdate

    # Determine the current folder based on unreviewed list
    assigned_folders = user_manager.get_user_assignments(user['access_token'])
    reviewed_set = set(review_data['reviewed']) if review_data else set()
    unreviewed = [folder for folder in assigned_folders if folder not in reviewed_set]

    # Check if there are folders left to review
    if not unreviewed:
        return dash.no_update  # No update needed if all folders reviewed

    # Prepare to log the current folder
    current_folder_name = unreviewed[0]

    # Determine which button was pressed
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
            return dash.no_update  # Avoid updating on error

        # Update the reviewed data in session
        reviewed_set.add(current_folder_name)
        return {'reviewed': list(reviewed_set)}

    return dash.no_update




def get_reviewed_folders_from_sheet(retries=3, delay=1):
    """Retrieve reviewed folders from the Google Sheet with retries."""
    for attempt in range(retries):
        try:
            response = sheets_service.spreadsheets().values().get(
                spreadsheetId=SHEET_ID,
                range='Sheet1!A2:A'
            ).execute()
            # Convert list of rows to a set of reviewed folder names
            reviewed_folders = {row[0] for row in response.get('values', []) if row}
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
def handle_review(review_data, token_data):
    if not token_data:
        raise PreventUpdate

    user = user_manager.get_user_by_token(token_data['token'])
    if not user:
        raise PreventUpdate

    # Retrieve assigned folders for the user from the Distribution sheet
    assigned_folders = user_manager.get_user_assignments(user['access_token'])
    if not assigned_folders:
        return None, None, 100, "No folders assigned.", {'display': 'none'}

    # Retrieve the reviewed folders from the session store
    reviewed_folders = set(review_data['reviewed']) if review_data else set()
    unreviewed = [folder for folder in assigned_folders if folder not in reviewed_folders]

    # If all folders are reviewed, return the completed message
    if not unreviewed:
        return None, None, 100, "All folders reviewed!", {'display': 'none'}

    # Process the first unreviewed folder
    current_folder_name = unreviewed[0]
    current_folder_id = review_app.folder_name_to_id.get(current_folder_name)
    if not current_folder_id or not review_app.process_folder(current_folder_id):
        return None, None, 0, f"Error loading folder {current_folder_name}", {'display': 'none'}

    # Retrieve the images for display
    folder_data = review_app.folders.get(current_folder_id)
    before_image = folder_data['before_image']
    after_image = folder_data['after_image']

    # Calculate progress
    total_folders = len(assigned_folders)
    reviewed_count = len(reviewed_folders)
    progress = (reviewed_count / total_folders) * 100
    status_message = f"Reviewed {reviewed_count} of {total_folders} folders"

    # Show the buttons now that images are ready
    return before_image, after_image, progress, status_message, {'display': 'block'}


if __name__ == '__main__':
    app.run_server(debug=True, port=8050)
