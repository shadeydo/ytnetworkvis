# @title
import pandas as pd
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
import pickle
import os
import re
from pyvis.network import Network
import networkx as nx
import math
from randomcolor import RandomColor

SCOPES = ['https://www.googleapis.com/auth/youtube.readonly']

def authenticate_youtube():
    creds = None

    if not creds or not creds.valid:
        credentials_file = '/content/drive/MyDrive/yt network/client_secret.json'
        flow = InstalledAppFlow.from_client_secrets_file(credentials_file, SCOPES)
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

            channel_response = youtube.channels().list(
                part='statistics,snippet,topicDetails',
                id=channel_id
            ).execute()

            if channel_response['items']:
                channel_info = channel_response['items'][0]
                s = channel_info['statistics']
                snippet = channel_info['snippet']

                # Get category - YouTube stores this in topicDetails or snippet
                category = snippet.get('customUrl', '')  # fallback
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

# Main execution
def ui():
    print("YouTube Subscriptions Fetcher\n")

    youtube = authenticate_youtube()
    username = input("\nEnter your name: ").strip() or "user"

    print(f"\nFetching subscriptions...")
    df = get_subscriptions_data(youtube)

    print(f"✓ Found {len(df)} subscriptions")

    # Save and download
    safe_username = re.sub(r'[^\w\s-]', '', username).strip().replace(' ', '_')
    output_dir = '/content/drive/MyDrive/yt network/users'
    os.makedirs(output_dir, exist_ok=True)
    filename = f'{output_dir}/{safe_username}.csv'
    df.to_csv(filename, index=False)
    print(f"✓ Saved to {filename}")





nxgraph = nx.Graph()
personlist = []
channellist = []
DISPLAY_DEGREE_ONE = False


class Channel:
  def __init__(self,channel_name="Channel",channel_id="aaa",num_subs=100,category=None,icon="https://",owners=None):
    self.name = channel_name
    self.id = channel_id
    self.num_subs = num_subs
    self.category = category
    self.owners = []
    self.icon = icon

  def addOwner(self,person):
    self.owners.append(person)

  def makeNode(self):
    #g.add_node(self.id, label=self.name)
    nxgraph.add_node(self.id,
                     label=self.name,
                     shape="circularImage",
                     image=self.icon,
                     physics=True,
                     font={"size":10},
                     group=self.category




                )

class Person:
  def __init__(self,name="p1",color="red",channels=None):
    self.name = name
    self.channels = []
    self.color = color

  def makeNode(self):
    nxgraph.add_node(self.name,
                     color=self.color,
                     shape="triangle",
                     physics=True,
                     group="user",
                     size=30)

  def generateChannels(self, dataframe):
    for index, row in dataframe.iterrows():
      channel_id = row["channel_id"]

      # Check if channel with this ID already exists
      existing_channel = next((c for c in channellist if c.id == channel_id), None)

      if existing_channel:
        ch = existing_channel
      else:
        ch = Channel(channel_name=row["channel_title"],
                     channel_id=channel_id,
                     num_subs=row["subscribers_numeric"],
                     category=str(row["category"]).split(",")[0],
                     icon=row['thumbnail'])
        channellist.append(ch)
      if ch not in self.channels:
        self.channels.append(ch)
      ch.addOwner(self)



for entry in os.scandir("users/"):
    if entry.is_file():
        df = pd.read_csv(entry.path,encoding_errors='ignore')
        user = entry.name.replace(".csv","")
        p = Person(user, RandomColor().generate()[0])
        p.generateChannels(df)
        personlist.append(p)

if DISPLAY_DEGREE_ONE:
    validlist = channellist
else:
    validlist = [ch for ch in channellist if len(ch.owners) > 1]

# generate all nodes
for channel in validlist:
    channel.makeNode()

for person in personlist:
    person.makeNode()
    for channel in person.channels:
        if channel in validlist:
            nxgraph.add_edge(person.name, channel.id, color=person.color)





# channel node scaling
max_owners = max(len(channel.owners) for channel in validlist)
for channel in validlist:
    nxgraph.nodes[channel.id]["size"] = ((len(channel.owners) / max_owners)+2)*8



def create_network_graph(nxgraph, output_path="static/graph.html"):
  os.makedirs(os.path.dirname(output_path), exist_ok=True)
    
  g = Network(
      height="800px", 
      width="100%", 
      notebook=False,
      bgcolor="#1a1a1a",
      font_color="#ffffff"
    )
    
  g.toggle_physics(True)
  g.barnes_hut(
      gravity=-50000,
      central_gravity=0,
      spring_length=200,
      spring_strength=0.1,
      damping=0.7
  )
    
  g.from_nx(nxgraph)
  g.save_graph(output_path)
    
  return output_path

# Usage
graph_path = create_network_graph(nxgraph)
print(f"Graph saved to {graph_path}")