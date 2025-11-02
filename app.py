import os
os.environ['OAUTHLIB_INSECURE_TRANSPORT'] = '1'  # Allow HTTP for local dev

from flask import Flask, render_template, redirect, url_for, session, request, send_from_directory
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
import google.oauth2.credentials
import re
from main import get_subscriptions_data, load_users_from_csv, build_network_graph, create_network_visualization

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'dev-secret-key-change-in-prod')

CLIENT_SECRETS_FILE = "client_secret.json"
SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']

os.makedirs('users', exist_ok=True)
os.makedirs('static', exist_ok=True)


def credentials_to_dict(credentials):
    return {
        'token': credentials.token,
        'refresh_token': credentials.refresh_token,
        'token_uri': credentials.token_uri,
        'client_id': credentials.client_id,
        'client_secret': credentials.client_secret,
        'scopes': credentials.scopes
    }


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/login')
def login():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        redirect_uri=url_for('callback', _external=True)
    )
    
    authorization_url, state = flow.authorization_url(
        access_type='offline',
        include_granted_scopes='true'
    )
    
    session['state'] = state
    return redirect(authorization_url)


@app.route('/callback')
def callback():
    flow = Flow.from_client_secrets_file(
        CLIENT_SECRETS_FILE,
        scopes=SCOPES,
        state=session['state'],
        redirect_uri=url_for('callback', _external=True)
    )
    
    flow.fetch_token(authorization_response=request.url)
    session['credentials'] = credentials_to_dict(flow.credentials)
    
    return redirect(url_for('get_username'))


@app.route('/username', methods=['GET', 'POST'])
def get_username():
    if 'credentials' not in session:
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        if username:
            session['username'] = username
            return redirect(url_for('fetch_subscriptions'))
    
    return render_template('username.html')


@app.route('/fetch')
def fetch_subscriptions():
    if 'credentials' not in session or 'username' not in session:
        return redirect(url_for('login'))
    
    credentials = google.oauth2.credentials.Credentials(**session['credentials'])
    youtube = build('youtube', 'v3', credentials=credentials)
    
    df = get_subscriptions_data(youtube)
    
    safe_username = re.sub(r'[^\w\s-]', '', session['username']).strip().replace(' ', '_')
    df.to_csv(f'users/{safe_username}.csv', index=False)
    
    return redirect(url_for('visualize'))


@app.route('/visualize')
def visualize():
    try:
        personlist, channellist = load_users_from_csv()
        
        if not personlist:
            return render_template('error.html', 
                message="No user data found. Please add subscriptions first.")
        
        # Get list of usernames for the UI
        usernames = [person.name for person in personlist]
        
        nxgraph = build_network_graph(personlist, channellist)
        create_network_visualization(nxgraph)  # Remove usernames parameter for now
        
        return render_template('visualize.html')
    
    except Exception as e:
        import traceback
        error_details = traceback.format_exc()
        print(error_details)  # Print to console
        return render_template('error.html', message=f"{str(e)}<br><br><pre>{error_details}</pre>")


@app.route('/static/<path:filename>')
def serve_static(filename):
    return send_from_directory('static', filename)


if __name__ == '__main__':
    app.run(debug=True, host='0.0.0.0', port=5001)