"""
YouTube Subscription Network Visualizer
Fetches user subscriptions and creates an interactive network graph
"""

import os
import re
import pickle
import pandas as pd
import networkx as nx
from pyvis.network import Network
from randomcolor import RandomColor
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Config
SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']
DISPLAY_DEGREE_ONE = False  # Show channels with only 1 subscriber
DATA_DIR = 'users'
STATIC_DIR = 'static'
CREDENTIALS_FILE = 'client_secret.json'


def authenticate_youtube():
    """Authenticate with YouTube API"""
    creds = None

    if os.path.exists('token.pickle'):
        with open('token.pickle', 'rb') as token:
            creds = pickle.load(token)

    if not creds or not creds.valid:
        flow = InstalledAppFlow.from_client_secrets_file(CREDENTIALS_FILE, SCOPES)
        flow.redirect_uri = 'urn:ietf:wg:oauth:2.0:oob'

        auth_url, _ = flow.authorization_url(prompt='consent')
        print("Visit this URL to authorize:")
        print(auth_url)
        auth_code = input('\nEnter authorization code: ')

        flow.fetch_token(code=auth_code)
        creds = flow.credentials

        with open('token.pickle', 'wb') as token:
            pickle.dump(creds, token)

    return build('youtube', 'v3', credentials=creds)


def get_subscriptions_data(youtube):
    """Fetch all subscriptions with pagination"""
    stats = []
    next_page_token = None

    while True:
        response = youtube.subscriptions().list(
            part='snippet',
            mine=True,
            maxResults=50,
            pageToken=next_page_token
        ).execute()

        for item in response['items']:
            snip = item['snippet']
            channel_id = snip['resourceId']['channelId']

            # Get detailed channel info
            channel_response = youtube.channels().list(
                part='statistics,snippet,topicDetails',
                id=channel_id
            ).execute()

            if channel_response['items']:
                channel_info = channel_response['items'][0]
                s = channel_info['statistics']
                snippet = channel_info['snippet']

                # Extract category from topic details if available
                category = snippet.get('customUrl', '')
                if 'topicDetails' in channel_info and 'topicCategories' in channel_info['topicDetails']:
                    topics = channel_info['topicDetails']['topicCategories']
                    category = ', '.join([t.split('/')[-1].replace('_', ' ') for t in topics])

                stats.append({
                    'channel_id': channel_id,
                    'channel_title': snip['title'],
                    'subscribers': s.get('subscriberCount', 'Hidden'),
                    'thumbnail': snip['thumbnails']['default']['url'],
                    'category': category
                })

        next_page_token = response.get('nextPageToken')
        if not next_page_token:
            break

    df = pd.DataFrame(stats)
    df['subscribers_numeric'] = pd.to_numeric(df['subscribers'], errors='coerce')
    return df


class Channel:
    """YouTube channel node"""
    
    def __init__(self, channel_name="Channel", channel_id="aaa", num_subs=100, 
                 category=None, icon="https://", owners=None):
        self.name = channel_name
        self.id = channel_id
        self.num_subs = num_subs
        self.category = category
        self.owners = []
        self.icon = icon

    def addOwner(self, person):
        self.owners.append(person)

    def makeNode(self, graph):
        graph.add_node(
            self.id,
            label=self.name,
            shape="circularImage",
            image=self.icon,
            physics=True,
            font={"size": 10},
            group=self.category
        )


class Person:
    def __init__(self, name="p1", color="red", channels=None):
        self.name = name
        self.channels = []
        self.color = color

    
    def makeNode(self, graph):
        graph.add_node(
            self.name,
            color={'background': self.color, 'border': self.color},
            shape="star",
            physics=True,
            group="user",
            size=30,
            borderWidth=2
        )

    def generateChannels(self, dataframe, channellist):
        """Create channels from CSV data, reusing existing channel objects"""
        for index, row in dataframe.iterrows():
            channel_id = row["channel_id"]

            # Check if we've already created this channel
            existing_channel = next((c for c in channellist if c.id == channel_id), None)

            if existing_channel:
                ch = existing_channel
            else:
                ch = Channel(
                    channel_name=row["channel_title"],
                    channel_id=channel_id,
                    num_subs=row["subscribers_numeric"],
                    category=str(row["category"]).split(",")[0],
                    icon=row['thumbnail']
                )
                channellist.append(ch)
            
            if ch not in self.channels:
                self.channels.append(ch)
            ch.addOwner(self)


def load_users_from_csv(data_dir=DATA_DIR):
    """Load all user CSV files"""
    personlist = []
    channellist = []

    os.makedirs(data_dir, exist_ok=True)

    for entry in os.scandir(data_dir):
        if entry.is_file() and entry.name.endswith('.csv'):
            df = pd.read_csv(entry.path, encoding_errors='ignore')
            user = entry.name.replace(".csv", "")
            p = Person(user, RandomColor().generate()[0])
            p.generateChannels(df, channellist)
            personlist.append(p)

    return personlist, channellist


def build_network_graph(personlist, channellist, display_degree_one=DISPLAY_DEGREE_ONE):
    """Build NetworkX graph from users and channels"""
    nxgraph = nx.Graph()

    # Filter out channels with only 1 subscriber unless config says otherwise
    if display_degree_one:
        validlist = channellist
    else:
        validlist = [ch for ch in channellist if len(ch.owners) > 1]

    if not validlist:
        print("Warning: No valid channels found")
        return nxgraph

    # Add all nodes
    for channel in validlist:
        channel.makeNode(nxgraph)

    for person in personlist:
        person.makeNode(nxgraph)
        for channel in person.channels:
            if channel in validlist:
                nxgraph.add_edge(person.name, channel.id, color=person.color)

    # Scale channel size based on popularity (number of owners)
    max_owners = max(len(channel.owners) for channel in validlist)
    for channel in validlist:
        nxgraph.nodes[channel.id]["size"] = ((len(channel.owners) / max_owners) + 2) * 8

    return nxgraph


def create_network_visualization(nxgraph, output_path="static/graph.html"):
    os.makedirs(os.path.dirname(output_path), exist_ok=True)

    g = Network(
        height="800px",
        width="100%",
        notebook=False,
        bgcolor="#ffffff",
        font_color="#1D1D1D"
    )

    g.toggle_physics(True)
    g.barnes_hut(
        gravity=-50000,      # Negative = repulsion
        central_gravity=0,
        spring_length=200,
        spring_strength=0.1,
        damping=0.7          # Higher = less movement
    )
    g.show_buttons(filter_=["physics","manipulation"])
    
    g.from_nx(nxgraph)
    
    for node in nxgraph.nodes():
        if nxgraph.nodes[node].get('group') == 'user':
            node_data = nxgraph.nodes[node]
            g.get_node(node)['color'] = node_data.get('color', 'red')
        
    g.save_graph(output_path)

    return output_path


def fetch_user_subscriptions():
    print("YouTube Subscriptions Fetcher\n")

    youtube = authenticate_youtube()
    username = input("\nEnter your name: ").strip() or "user"

    print(f"\nFetching subscriptions...")
    df = get_subscriptions_data(youtube)

    print(f"✓ Found {len(df)} subscriptions")

    # Save to CSV with sanitized filename
    safe_username = re.sub(r'[^\w\s-]', '', username).strip().replace(' ', '_')
    os.makedirs(DATA_DIR, exist_ok=True)
    filename = f'{DATA_DIR}/{safe_username}.csv'
    df.to_csv(filename, index=False)
    print(f"✓ Saved to {filename}")


def generate_visualization():

    print("\nGenerating network visualization...")
    
    personlist, channellist = load_users_from_csv()
    print(f"✓ Loaded {len(personlist)} users and {len(channellist)} unique channels")
    
    nxgraph = build_network_graph(personlist, channellist)
    print(f"✓ Created network with {nxgraph.number_of_nodes()} nodes and {nxgraph.number_of_edges()} edges")
    
    graph_path = create_network_visualization(nxgraph)
    print(f"✓ Graph saved to {graph_path}")
    
    return graph_path

if __name__ == "main":
    import sys
        
    if len(sys.argv) > 1 and sys.argv[1] == "fetch":
        fetch_user_subscriptions()
    else:
        generate_visualization()