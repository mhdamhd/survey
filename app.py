# Part 1: Imports and Constants Setup
import dash
from dash import html, dcc, dash_table, Input, Output, State, callback_context
from dash.dependencies import ALL, MATCH
import dash_bootstrap_components as dbc
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
import base64
import io
from datetime import datetime
from typing import Dict, List, Any

# Color scheme for better visual hierarchy
COLORS = {
    'primary': '#1e40af',      # Deep blue
    'secondary': '#3b82f6',    # Bright blue
    'success': '#059669',      # Green
    'warning': '#d97706',      # Orange
    'danger': '#dc2626',       # Red
    'background': '#f8fafc',   # Light gray
    'text': '#1e293b',         # Dark gray
    'border': '#e2e8f0',       # Border gray
    'highlight': '#dbeafe',    # Light blue
    'chart_colors': px.colors.qualitative.Set3
}

# Task thresholds (in hours) with default values
TASK_THRESHOLDS = {
    'Apply for entry Visa': 24,
    'Apply for Work Permit - Stage 1': 10000,
    'Check Entry Visa Immigration Approval': 24,
    'Check ID application type': 24,
    'Collect Documents (with missing documents)': 10000,
    'Fill Information': 10000,
    'Fix the problem of entry visa (MV)': 48,
    'Modify EID Application': 240,
    'Pending medical certificate approval from DHA': 72,
    'Prepare EID Application (Receival Automated)': 48,
    'Prepare EID application (Receival Automated)': 48,
    'Prepare EID Application for Modification': 48,
    'Prepare folder containing E-visa medical application and EID': 72,
    'Receipt of EID Card (Card is not printed)': 168,
    'Receipt of EID Card (Card is printed)': 168,
    'Repeat Medical': 72,
    'Upload Contract to Tasheel (Tawjeeh is done)': 10000,
    'Waiting for Personal Photo': 10000,
    'Waiting for the maid to go to medical test(CC)': 72,
    'Waiting for the maid to go to medical test(MV)': 72
}

# Assignees list
ASSIGNEES = [
    'Chekri Khalife',
    'Amin',
    'Mohammed',
    'Visa Dubai',
    'Razan',
    'Maya',
    'Unassigned'
]


# Priority levels with corresponding colors
PRIORITY_LEVELS = {
    'High': COLORS['danger'],
    'Medium': COLORS['warning'],
    'Low': COLORS['success']
}

class DelayedMaidsApp:
    def __init__(self):
        """Initialize the Dash application with configurations"""
        external_stylesheets = [
            dbc.themes.BOOTSTRAP,
            'https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css'
        ]
        
        self.app = dash.Dash(
            __name__,
            suppress_callback_exceptions=True,
            external_stylesheets=external_stylesheets,
            title='Delayed Maids Dashboard',
            update_title=None
        )
        
        # Initialize data storage
        self.current_data = pd.DataFrame()
        self.task_thresholds = TASK_THRESHOLDS.copy()
        self.last_update = datetime.now()

    def calculate_priority(self, row: pd.Series) -> str:
        """Calculate priority based on delay threshold"""
        try:
            delay = float(row['Real Delay (hours)'])
            threshold = self.task_thresholds.get(row['Task'], 24)
            
            if delay > threshold * 2:
                return 'High'
            elif delay > threshold:
                return 'Medium'
            return 'Low'
        except:
            return 'Low'

    def process_data(self, df: pd.DataFrame) -> pd.DataFrame:
        """Process the uploaded data with proper task handling"""
        try:
            # Clean column names
            df.columns = df.columns.str.strip()
            
            # Forward fill Task column (handle grouped tasks)
            current_task = None
            tasks = []
            
            for task in df['Task']:
                if pd.notna(task) and str(task).strip():
                    current_task = str(task).strip()
                tasks.append(current_task)
            
            df['Task'] = tasks
            
            # Add required columns
            df['Threshold Hours'] = df['Task'].map(self.task_thresholds)
            
            # Set default values for tracking columns
            if 'Assignee' not in df.columns:
                df['Assignee'] = 'Unassigned'
            if 'Notes' not in df.columns:
                df['Notes'] = ''
            
            df['Last Updated'] = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            
            # Convert date columns
            date_columns = ['Task Move in Date', 'Work Permit Expiry Date']
            for col in date_columns:
                if col in df.columns:
                    df[col] = pd.to_datetime(df[col], format='%m/%d/%Y %I:%M:%S %p', errors='coerce')
            
            # Process numeric columns
            if 'Real Delay (hours)' in df.columns:
                df['Real Delay (hours)'] = pd.to_numeric(df['Real Delay (hours)'], errors='coerce')
            
            # Calculate delay status and priority
            df['Is Delayed'] = df.apply(
                lambda row: row['Real Delay (hours)'] > self.task_thresholds.get(row['Task'], 24) 
                if pd.notna(row['Real Delay (hours)']) and pd.notna(row['Task']) 
                else False,
                axis=1
            )
            
            df['Priority'] = df.apply(self.calculate_priority, axis=1)
            
            return df
            
        except Exception as e:
            print(f"Error processing data: {e}")
            return pd.DataFrame()
    def create_summary_charts(self, df: pd.DataFrame) -> Dict[str, go.Figure]:
        """Create improved summary charts for the dashboard"""
        charts = {}
        
        try:
            # Only process delayed cases
            delayed_df = df[df['Is Delayed']]
            
            if len(delayed_df) == 0:
                # Return empty figures if no delayed cases
                return {
                    'type': go.Figure(),
                    'status': go.Figure(),
                    'task': go.Figure()
                }
            
            # 1. Type Distribution (Pie Chart)
            type_counts = delayed_df['Housemaid Type'].value_counts()
            type_percentages = (type_counts / len(delayed_df) * 100).round(1)
            
            charts['type'] = px.pie(
                values=type_counts.values,
                names=type_counts.index,
                title='Type Distribution of Delayed Cases',
                color_discrete_sequence=px.colors.qualitative.Set3
            )
            charts['type'].update_traces(
                textinfo='value+percent',
                hovertemplate="<b>%{label}</b><br>" +
                             "Count: %{value}<br>" +
                             "Percentage: %{percent}<extra></extra>"
            )
            
            # 2. Status Distribution (Simplified Bar Chart)
            status_data = delayed_df['Housemaid Status'].value_counts()
            status_df = pd.DataFrame({
                'Status': status_data.index,
                'Count': status_data.values,
                'Percentage': (status_data.values / len(delayed_df) * 100).round(1)
            }).sort_values('Count', ascending=True)  # Sort for better visualization
            
            charts['status'] = go.Figure(data=[
                go.Bar(
                    x=status_df['Count'],
                    y=status_df['Status'],
                    orientation='h',
                    text=[f"{count} ({pct}%)" for count, pct in zip(status_df['Count'], status_df['Percentage'])],
                    textposition='auto',
                    marker_color=COLORS['secondary']
                )
            ])
            
            charts['status'].update_layout(
                title='Status Distribution of Delayed Cases',
                xaxis_title='Number of Cases',
                yaxis_title='',
                showlegend=False,
                height=max(len(status_df) * 40 + 100, 400)  # Dynamic height based on number of statuses
            )
            
            # 3. Task Distribution (Table format instead of graph)
            task_data = delayed_df['Task'].value_counts()
            task_df = pd.DataFrame({
                'Task': task_data.index,
                'Count': task_data.values,
                'Percentage': (task_data.values / len(delayed_df) * 100).round(1)
            }).sort_values('Count', ascending=False)
            
            charts['task'] = go.Figure(data=[
                go.Table(
                    header=dict(
                        values=['<b>Task</b>', '<b>Count</b>', '<b>Percentage</b>'],
                        fill_color=COLORS['primary'],
                        align='left',
                        font=dict(color='white', size=12)
                    ),
                    cells=dict(
                        values=[
                            task_df['Task'],
                            task_df['Count'],
                            task_df['Percentage'].apply(lambda x: f"{x}%")
                        ],
                        align='left',
                        font=dict(size=11),
                        height=30,
                        fill_color=[
                            [COLORS['background'] if i % 2 == 0 else 'white' for i in range(len(task_df))]
                        ]
                    )
                )
            ])
            
            charts['task'].update_layout(
                title='Current Visa Step Distribution',
                margin=dict(l=10, r=10, t=40, b=10),
                height=max(len(task_df) * 30 + 100, 400)  # Dynamic height based on number of tasks
            )
            
            # Update layout for all charts
            for chart in charts.values():
                chart.update_layout(
                    plot_bgcolor='white',
                    paper_bgcolor='white',
                    font_family='system-ui',
                    title={
                        'x': 0.5,
                        'xanchor': 'center',
                        'font': {'size': 16}
                    },
                    margin=dict(t=50, l=10, r=10, b=10)
                )
            
        except Exception as e:
            print(f"Error creating charts: {e}")
            charts = {
                'type': go.Figure(),
                'status': go.Figure(),
                'task': go.Figure()
            }
        
        return charts
    
    def create_datatable_columns(self):
        """Create columns configuration for the DataTable"""
        return [
            {'name': 'Task', 'id': 'Task'},
            {'name': 'Housemaid Name', 'id': 'Housemaid Name'},
            {'name': 'Nationality', 'id': 'Housemaid Nationality'},
            {'name': 'Type', 'id': 'Housemaid Type'},
            {'name': 'Status', 'id': 'Housemaid Status'},
            {
                'name': 'Real Delay (hours)', 
                'id': 'Real Delay (hours)',
                'type': 'numeric',
                'format': {'specifier': '.1f'}
            },
            {
                'name': 'Threshold Hours', 
                'id': 'Threshold Hours',
                'type': 'numeric'
            },
            {'name': 'Duration in Task', 'id': 'Duration in The Task'},
            {
                'name': 'Assignee', 
                'id': 'Assignee', 
                'presentation': 'dropdown',
                'editable': True
            },
            {
                'name': 'Notes', 
                'id': 'Notes', 
                'presentation': 'markdown',
                'editable': True
            },
            {'name': 'Last Updated', 'id': 'Last Updated'}
        ]

    def create_datatable_style_conditions(self):
        """Create style conditions for the DataTable"""
        return [
            # Priority-based styling
            {
                'if': {
                    'column_id': 'Priority',
                    'filter_query': '{Priority} eq "High"'
                },
                'backgroundColor': 'rgba(220, 38, 38, 0.1)',
                'color': COLORS['danger']
            },
            {
                'if': {
                    'column_id': 'Priority',
                    'filter_query': '{Priority} eq "Medium"'
                },
                'backgroundColor': 'rgba(217, 119, 6, 0.1)',
                'color': COLORS['warning']
            },
            {
                'if': {
                    'column_id': 'Priority',
                    'filter_query': '{Priority} eq "Low"'
                },
                'backgroundColor': 'rgba(5, 150, 105, 0.1)',
                'color': COLORS['success']
            },
            # Unassigned cases styling
            {
                'if': {
                    'column_id': 'Assignee',
                    'filter_query': '{Assignee} eq "Unassigned"'
                },
                'backgroundColor': 'rgba(239, 68, 68, 0.1)',
                'color': COLORS['danger']
            },
            # Delay threshold styling
            {
                'if': {
                    'column_id': 'Real Delay (hours)',
                    'filter_query': f'{{Real Delay (hours)}} >= {{Threshold Hours}}'
                },
                'backgroundColor': 'rgba(220, 38, 38, 0.1)',
                'color': COLORS['danger']
            }
        ]
    
    def create_datatable_style_header(self):
        """Create header style for the DataTable"""
        return {
            'backgroundColor': COLORS['primary'],
            'color': 'white',
            'fontWeight': 'bold',
            'textAlign': 'left',
            'padding': '12px 15px',
            'whiteSpace': 'normal',
            'height': 'auto',
        }
    
    def create_datatable_style_cell(self):
        """Create cell style for the DataTable"""
        return {
            'padding': '12px 15px',
            'textAlign': 'left',
            'fontFamily': 'system-ui',
            'fontSize': '14px',
            'color': COLORS['text'],
            'whiteSpace': 'normal',
            'height': 'auto',
        }
    def setup_layout(self):
        """Setup the dashboard layout with enhanced UI"""
        self.app.layout = html.Div([
            # Navigation Bar
            html.Div([
                html.Div([
                    html.H1("Delayed Maids Dashboard", 
                           className='text-2xl font-bold text-white'),
                    html.P(id='last-update-time',
                          className='text-sm text-blue-100')
                ]),
                html.Div([
                    dcc.Upload(
                        id='upload-data',
                        children=html.Div([
                            html.I(className="fas fa-upload mr-2"),
                            "Upload Excel"
                        ], className='bg-white text-blue-600 px-4 py-2 rounded-lg hover:bg-blue-50 transition-colors duration-200 cursor-pointer flex items-center'),
                        multiple=False,
                        accept='.xlsx, .xls'
                    ),
                    html.Button([
                        html.I(className="fas fa-download mr-2"),
                        "Export Data"
                    ],
                    id='export-button',
                    className='ml-4 bg-green-500 text-white px-4 py-2 rounded-lg hover:bg-green-600 transition-colors duration-200 flex items-center'
                    ),
                    dcc.Download(id='download-dataframe-xlsx'),
                ], className='flex items-center')
            ], className='flex justify-between items-center p-4 bg-gradient-to-r from-blue-600 to-blue-800 shadow-lg'),
    
            # Main Content
            html.Div([
                # Statistics Cards
                html.Div([
                    dbc.Row([
                        dbc.Col([
                            dbc.Card([
                                html.Div([
                                    html.H3("Total Delayed Cases", 
                                           className='text-gray-600 font-semibold'),
                                    html.Div([
                                        html.P(id='total-delayed-cases',
                                              className='text-3xl font-bold text-blue-600 mb-1'),
                                        html.P("cases requiring attention", 
                                              className='text-sm text-gray-500')
                                    ])
                                ], className='p-4')
                            ], className='h-100 shadow-lg border-l-4 border-blue-600')
                        ], width=4),
                        
                        dbc.Col([
                            dbc.Card([
                                html.Div([
                                    html.H3("Critical Delays", 
                                           className='text-gray-600 font-semibold'),
                                    html.Div([
                                        html.P(id='critical-cases',
                                              className='text-3xl font-bold text-red-600 mb-1'),
                                        html.P("high priority cases", 
                                              className='text-sm text-gray-500')
                                    ])
                                ], className='p-4')
                            ], className='h-100 shadow-lg border-l-4 border-red-600')
                        ], width=4),
                        
                        dbc.Col([
                            dbc.Card([
                                html.Div([
                                    html.H3("Unassigned Cases", 
                                           className='text-gray-600 font-semibold'),
                                    html.Div([
                                        html.P(id='unassigned-cases',
                                              className='text-3xl font-bold text-orange-500 mb-1'),
                                        html.P("need assignment", 
                                              className='text-sm text-gray-500')
                                    ])
                                ], className='p-4')
                            ], className='h-100 shadow-lg border-l-4 border-orange-500')
                        ], width=4),
                    ], className='mb-4'),
                ]),
    
                # Task Thresholds Settings
                dbc.Collapse([
                    dbc.Card([
                        dbc.CardHeader([
                            html.H2("Task Delay Thresholds", className='text-xl font-bold mb-0'),
                            html.P("Set delay thresholds for each task (in hours)", 
                                 className='text-sm text-gray-500 mt-1 mb-0')
                        ]),
                        dbc.CardBody([
                            dbc.Row([
                                dbc.Col([
                                    html.Div([
                                        html.Label(
                                            task,
                                            className='text-sm font-medium text-gray-700 mb-1'
                                        ),
                                        dbc.Input(
                                            id={'type': 'threshold-input', 'task': task},
                                            type='number',
                                            value=hours,
                                            min=0,
                                            className='mb-2'
                                        )
                                    ]) for task, hours in self.task_thresholds.items()
                                ], width=12, className='grid grid-cols-4 gap-4')
                            ]),
                            dbc.Button(
                                "Update Thresholds",
                                id='update-thresholds-button',
                                color='primary',
                                className='mt-3'
                            )
                        ])
                    ], className='mb-4')
                ], id='threshold-settings-collapse', is_open=False),
                
                dbc.Button(
                    "Toggle Threshold Settings",
                    id='toggle-threshold-settings',
                    color='secondary',
                    className='mb-4'
                ),
    
                # Filters Section
                dbc.Card([
                    dbc.CardHeader("Filters"),
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Label(
                                    "Task Filter",
                                    className='font-medium text-gray-700'
                                ),
                                dcc.Dropdown(
                                    id='task-filter',
                                    multi=True,
                                    placeholder="Select tasks...",
                                    style={'width': '250px'}  # adjust width as needed
                                )
                            ], width=3),
                            
                            dbc.Col([
                                html.Label(
                                    "Nationality Filter",
                                    className='font-medium text-gray-700'
                                ),
                                dcc.Dropdown(
                                    id='nationality-filter',
                                    multi=True,
                                    placeholder="Select nationalities...",
                                    className='mb-2'
                                )
                            ], width=3),
                            
                            dbc.Col([
                                html.Label(
                                    "Status Filter",
                                    className='font-medium text-gray-700'
                                ),
                                dcc.Dropdown(
                                    id='status-filter',
                                    multi=True,
                                    placeholder="Select statuses...",
                                    className='mb-2'
                                )
                            ], width=3),
                            
                            dbc.Col([
                                html.Label(
                                    "Type Filter",
                                    className='font-medium text-gray-700'
                                ),
                                dcc.Dropdown(
                                    id='type-filter',
                                    multi=True,
                                    placeholder="Select types...",
                                    className='mb-2'
                                )
                            ], width=3),
                        ])
                    ])
                ], className='mb-4'),
    
                # Charts Grid
                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader("Type Distribution"),
                            dbc.CardBody([
                                dcc.Graph(id='type-chart')
                            ])
                        ], className='h-100')
                    ], width=6),
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader("Status Distribution"),
                            dbc.CardBody([
                                dcc.Graph(id='status-chart')
                            ])
                        ], className='h-100')
                    ], width=6),
                ], className='mb-4'),
                
                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardHeader("Current Visa Step Distribution"),
                            dbc.CardBody([
                                dcc.Graph(id='task-chart')
                            ])
                        ], className='h-100')
                    ], width=12),
                ], className='mb-4'),
    
                # Data Table
                dbc.Card([
                    dbc.CardHeader([
                        html.Div([
                            html.H3("Delayed Cases", className='text-lg font-bold mb-0'),
                            html.P("Cases exceeding their threshold delays", 
                                className='text-sm text-gray-500 mt-1 mb-0')
                        ], className='flex-grow'),
                        html.Div([
                            html.Button([
                                html.I(className="fas fa-table mr-2"),
                                "Download Table Data"
                            ],
                            id='download-table-button',
                            className='bg-blue-500 text-white px-4 py-2 rounded-lg hover:bg-blue-600 transition-colors duration-200 flex items-center'
                            ),
                            dcc.Download(id='download-table-data-xlsx')
                        ], className='flex items-center')
                    ], className='flex justify-between items-center'),
                    dbc.CardBody([
                        dash_table.DataTable(
                            id='delayed-maids-table',
                            columns=self.create_datatable_columns(),
                            dropdown={
                                'Assignee': {
                                    'options': [{'label': name, 'value': name} for name in ASSIGNEES]
                                }
                            },
                            editable=True,
                            row_deletable=True,
                            sort_action='native',
                            sort_mode='multi',
                            filter_action='native',
                            page_size=15,
                            style_table={'overflowX': 'auto'},
                            style_data_conditional=self.create_datatable_style_conditions(),
                            style_header=self.create_datatable_style_header(),
                            style_cell=self.create_datatable_style_cell()
                        )
                    ])
                ])
            ], className='p-4 bg-gray-50')
        ])
    def setup_callbacks(self):
        """Setup all callbacks for the dashboard"""
        @self.app.callback(
        Output('download-table-data-xlsx', 'data'),
        Input('download-table-button', 'n_clicks'),
        State('delayed-maids-table', 'data'),
        prevent_initial_call=True
    )
        def download_table_data(n_clicks, table_data):
            """Handle downloading current table data to Excel with specific columns excluded"""
            if n_clicks is None or not table_data:
                return None
            
            try:
                # Convert table data to DataFrame
                df = pd.DataFrame(table_data)
                
                # List of columns to exclude
                columns_to_exclude = [
                    'Number of Pending Tasks',
                    'Work Permit Expiry Date',
                    'Notes',
                    'Priority',
                    'Is Delayed',
                    'Last Updated'
                ]
                
                # Remove specified columns if they exist in the DataFrame
                columns_to_keep = [col for col in df.columns if col not in columns_to_exclude]
                df_filtered = df[columns_to_keep]
                
                # Format timestamp for filename
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                
                # Prepare Excel file
                return dcc.send_data_frame(
                    df_filtered.to_excel,
                    f'delayed_maids_table_export_{timestamp}.xlsx',
                    sheet_name='Delayed Cases',
                    index=False
                )
            except Exception as e:
                print(f"Error exporting table data: {e}")
                return None
        # Callback for threshold settings collapse
        @self.app.callback(
            Output('threshold-settings-collapse', 'is_open'),
            [Input('toggle-threshold-settings', 'n_clicks')],
            [State('threshold-settings-collapse', 'is_open')]
        )
        def toggle_threshold_settings(n_clicks, is_open):
            if n_clicks:
                return not is_open
            return is_open
    
        # Main dashboard update callback
        @self.app.callback(
            [Output('delayed-maids-table', 'data'),
             Output('type-chart', 'figure'),
             Output('status-chart', 'figure'),
             Output('task-chart', 'figure'),
             Output('total-delayed-cases', 'children'),
             Output('critical-cases', 'children'),
             Output('unassigned-cases', 'children'),
             Output('task-filter', 'options'),
             Output('nationality-filter', 'options'),
             Output('status-filter', 'options'),
             Output('type-filter', 'options'),
             Output('last-update-time', 'children')],
            [Input('upload-data', 'contents'),
             Input('task-filter', 'value'),
             Input('nationality-filter', 'value'),
             Input('status-filter', 'value'),
             Input('type-filter', 'value'),
             Input('update-thresholds-button', 'n_clicks')],
            [State('upload-data', 'filename'),
             State({'type': 'threshold-input', 'task': ALL}, 'value'),
             State({'type': 'threshold-input', 'task': ALL}, 'id')]
        )
        def update_dashboard(contents, task_filter, nat_filter, status_filter, 
                           type_filter, n_clicks, filename, threshold_values, threshold_ids):
            """Main callback to update the dashboard"""
            trigger = callback_context.triggered[0] if callback_context.triggered else None
            triggered_id = trigger['prop_id'] if trigger else None
            
            try:
                # Update thresholds if button was clicked
                if triggered_id == 'update-thresholds-button.n_clicks' and threshold_values and threshold_ids:
                    for threshold_id, value in zip(threshold_ids, threshold_values):
                        task = threshold_id['task']
                        if value is not None and value > 0:
                            self.task_thresholds[task] = value
                    
                    if not self.current_data.empty:
                        self.current_data['Threshold Hours'] = self.current_data['Task'].map(self.task_thresholds)
                        self.current_data['Priority'] = self.current_data.apply(self.calculate_priority, axis=1)
                        self.current_data['Is Delayed'] = self.current_data.apply(
                            lambda row: float(row['Real Delay (hours)']) > self.task_thresholds.get(row['Task'], 24)
                            if pd.notna(row['Real Delay (hours)']) and pd.notna(row['Task'])
                            else False,
                            axis=1
                        )
    
                # Process new file upload
                if contents is not None:
                    content_type, content_string = contents.split(',')
                    decoded = base64.b64decode(content_string)
                    
                    if filename.lower().endswith('.csv'):
                        df = pd.read_csv(io.StringIO(decoded.decode('utf-8')))
                    elif filename.lower().endswith(('.xls', '.xlsx')):
                        df = pd.read_excel(io.BytesIO(decoded))
                    else:
                        raise ValueError("Unsupported file format")
                    
                    self.current_data = self.process_data(df)
    
                # Return empty state if no data
                if self.current_data.empty:
                    return [], {}, {}, {}, '0', '0', '0', [], [], [], [], 'No data loaded'
    
                # Get only delayed cases
                filtered_df = self.current_data[self.current_data['Is Delayed'] == True].copy()
                
                # Apply filters
                if task_filter:
                    filtered_df = filtered_df[filtered_df['Task'].isin(task_filter)]
                if nat_filter:
                    filtered_df = filtered_df[filtered_df['Housemaid Nationality'].isin(nat_filter)]
                if status_filter:
                    filtered_df = filtered_df[filtered_df['Housemaid Status'].isin(status_filter)]
                if type_filter:
                    filtered_df = filtered_df[filtered_df['Housemaid Type'].isin(type_filter)]
    
                # Calculate statistics
                total_delayed = len(filtered_df)
                critical_cases = len(filtered_df[
                    filtered_df['Real Delay (hours)'] > filtered_df['Threshold Hours'] * 2
                ])
                unassigned_cases = len(filtered_df[filtered_df['Assignee'] == 'Unassigned'])
    
                # Create charts
                charts = self.create_summary_charts(filtered_df)
    
                # Prepare filter options with counts
                def prepare_filter_options(column):
                    counts = filtered_df[column].value_counts()
                    return [
                        {'label': f"{val} ({counts[val]})", 'value': val}
                        for val in sorted(counts.index)
                    ]
    
                # Update timestamp
                last_update = f"Last updated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    
                return (
                    filtered_df.to_dict('records'),
                    charts['type'],
                    charts['status'],
                    charts['task'],
                    str(total_delayed),
                    str(critical_cases),
                    str(unassigned_cases),
                    prepare_filter_options('Task'),
                    prepare_filter_options('Housemaid Nationality'),
                    prepare_filter_options('Housemaid Status'),
                    prepare_filter_options('Housemaid Type'),
                    last_update
                )
    
            except Exception as e:
                print(f"Error updating dashboard: {e}")
                return [], {}, {}, {}, '0', '0', '0', [], [], [], [], f'Error: {str(e)}'
    
        # Callback for table cell updates
        @self.app.callback(
            Output('delayed-maids-table', 'data', allow_duplicate=True),
            [Input('delayed-maids-table', 'data_timestamp')],
            [State('delayed-maids-table', 'data'),
             State('delayed-maids-table', 'data_previous')],
            prevent_initial_call=True
        )
        def update_table_data(timestamp, current_data, previous_data):
            """Update table when data changes"""
            if not current_data:
                return []
    
            try:
                # Find changed rows
                if previous_data:
                    changed_rows = [
                        i for i, (curr, prev) in enumerate(zip(current_data, previous_data))
                        if curr != prev
                    ]
                else:
                    changed_rows = range(len(current_data))
    
                # Update changed rows
                current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                
                for idx in changed_rows:
                    row = current_data[idx]
                    row['Last Updated'] = current_time
                    
                    # Update priority based on current delay
                    try:
                        delay = float(row['Real Delay (hours)'])
                        threshold = float(row['Threshold Hours'])
                        
                        if delay > threshold * 2:
                            row['Priority'] = 'High'
                        elif delay > threshold:
                            row['Priority'] = 'Medium'
                        else:
                            row['Priority'] = 'Low'
                    except:
                        row['Priority'] = 'Low'
    
                return current_data
    
            except Exception as e:
                print(f"Error updating table data: {e}")
                return current_data
    
        # Callback for data export
        @self.app.callback(
            Output('download-dataframe-xlsx', 'data'),
            Input('export-button', 'n_clicks'),
            prevent_initial_call=True
        )
        def export_data(n_clicks):
            """Handle exporting data to Excel"""
            if n_clicks is None or self.current_data.empty:
                return None
            
            try:
                timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
                return dcc.send_data_frame(
                    self.current_data.to_excel,
                    f'delayed_maids_export_{timestamp}.xlsx',
                    sheet_name='Delayed Maids'
                )
            except Exception as e:
                print(f"Error exporting data: {e}")
                return None
    
    def run_server(self, debug=True, port=8050, host='0.0.0.0'):
        """Run the Dash server"""
        print(f"\nStarting Delayed Maids Dashboard...")
        print(f"Server initialization time: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print(f"\nServer Configuration:")
        print(f"- Host: {host}")
        print(f"- Port: {port}")
        print(f"- Debug Mode: {debug}")
        print(f"\nDashboard is available at:")
        print(f"http://{host if host != '0.0.0.0' else 'localhost'}:{port}")
        
        self.app.run_server(debug=debug, port=port, host=host)

app = DelayedMaidsApp()
app.setup_layout()
app.setup_callbacks()
server = app.app.server
# Main execution
if __name__ == '__main__':
    try:      
        app.run_server(debug=True, port=8075)
    except Exception as e:
        print(f"\nError starting server: {e}")
        raise