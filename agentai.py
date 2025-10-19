# Cell 1: Install required libraries
!pip install --quiet fastapi uvicorn nest_asyncio pyngrok langchain langchain-community langgraph langchain-openai openai google-auth-oauthlib google-api-python-client beautifulsoup4 serpapi tldextract requests langchain-tavily

# Cell 2: Imports
import os
import json
import requests
from typing import List, Dict, TypedDict
from fastapi import FastAPI, Request
import nest_asyncio
import uvicorn
from pyngrok import ngrok
from datetime import datetime
import asyncio
# LangChain, LangGraph and OpenAI imports
from openai import AzureOpenAI
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_tavily import TavilySearch
from langchain.tools import tool
from langgraph.graph import StateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver
# Google API imports
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import base64
from email.mime.text import MIMEText
from google.colab import userdata

# Cell 3: Configuration
API_KEY = userdata.get('AZURE_API_KEY')
API_VERSION = "2025-04-01-preview"
AZURE_ENDPOINT = "https://iit-internship2025-5.openai.azure.com/"
DEPLOYMENT_NAME_CHAT = "gpt-5-mini"
DEPLOYMENT_NAME_EMBED = "text-embedding-ada-002"
SERPAPI_KEY = userdata.get('SERPAPI_KEY')
TAVILY_API_KEY = userdata.get('TAVILY_API_KEY')
os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY
GOOGLE_CLIENT_SECRETS = "/content/client_secret_42550855283-4lcg1rbn9ceg7s6j7ufot6o510ckbocm.apps.googleusercontent.com.json"  # Replace with path to your secrets file
GOOGLE_SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.send'
]
COMMONLY_BLOCKED_DOMAINS = ['linkedin.com', 'crunchbase.com', 'bloomberg.com', 'wsj.com', 'ft.com']
os.environ["NGROK_AUTHTOKEN"] = "33xZwoPZLJ5Dtkh83ZwCYFqEAsv_7k7LdBDg3tUPAkx7m7Xwp"  # Replace with your actual ngrok token

# Cell 4: Agent Setup and Tools
# Define the AgentState TypedDict
class AgentState(TypedDict):
    company: str
    research_data: List[Dict]
    summary: str
    recent_projects: str
    contacts: Dict
    meet_details: Dict
    trip_itinerary: Dict

# Initialize LLM and embeddings
llm = AzureChatOpenAI(azure_endpoint=AZURE_ENDPOINT, api_key=API_KEY, api_version=API_VERSION, deployment_name=DEPLOYMENT_NAME_CHAT)
embeddings = AzureOpenAIEmbeddings(azure_endpoint=AZURE_ENDPOINT, api_key=API_KEY, api_version=API_VERSION, deployment=DEPLOYMENT_NAME_EMBED) if DEPLOYMENT_NAME_EMBED else None

# Google API credentials
creds = None
def get_credentials():
    global creds
    if creds and creds.valid:
        return creds
    try:
        flow = Flow.from_client_secrets_file(
            GOOGLE_CLIENT_SECRETS,
            scopes=GOOGLE_SCOPES,
            redirect_uri='urn:ietf:wg:oauth:2.0:oob'
        )
        auth_url, _ = flow.authorization_url(prompt='consent')
        print(f"Please go to this URL and authorize: {auth_url}")
        code = input("Enter the authorization code: ")
        flow.fetch_token(code=code)
        creds = flow.credentials
        return creds
    except Exception as e:
        print(f"Error: {str(e)}. Please check the code or secrets file.")
        return None

# Run get_credentials once to cache creds (run this manually before starting server)
creds = get_credentials()

# Tools
@tool
def search_web(query: str) -> List[Dict]:
    """Search the web for global company information using Tavily API."""
    try:
        search = TavilySearch(max_results=5)
        return search.invoke(query)
    except Exception as e:
        return [{"error": str(e)}]

@tool
def fetch_wikipedia(company: str) -> Dict:
    """Fetch a global company summary from Wikipedia based on the company name."""
    try:
        search_url = "https://en.wikipedia.org/w/api.py"
        headers = {"User-Agent": "Mozilla/5.0 (compatible; ResearchBot/1.0)"}
        srsearch = f"{company} IT system integration Japan company global"
        search_params = {"action": "query", "list": "search", "srsearch": srsearch, "format": "json", "srlimit": 1}
        search_response = requests.get(search_url, params=search_params, headers=headers, timeout=10)
        search_data = search_response.json()
        if not search_data.get("query", {}).get("search"):
            return {"content": None}
        page_title = search_data["query"]["search"][0]["title"]
        content_params = {"action": "query", "prop": "extracts|info", "exintro": True, "explaintext": True, "titles": page_title, "format": "json", "inprop": "url"}
        content_response = requests.get(search_url, params=content_params, headers=headers, timeout=10)
        content_data = content_response.json()
        pages = content_data.get("query", {}).get("pages", {})
        page_id = list(pages.keys())[0]
        page = pages[page_id]
        return {"content": page.get("extract", "")}
    except Exception as e:
        return {"error": str(e)}

@tool
def fetch_recent_projects(company: str) -> str:
    """Search for recent global projects of the company using SerpAPI."""
    query = f"{company} IT system integration Japan recent projects global 2024 2025"
    try:
        results = serpapi_search(query, num=5)
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": str(e)})

def serpapi_search(query: str, num: int = 5) -> List[Dict]:
    """Perform a Google search using SerpAPI (helper function)."""
    params = {"engine": "google", "q": query, "api_key": SERPAPI_KEY, "num": num}
    response = requests.get("https://serpapi.com/search", params=params)
    return response.json().get("organic_results", []) if response.status_code == 200 else []

@tool
def schedule_meet(title: str, start_time: str, end_time: str, attendees: List[str]) -> Dict:
    """Schedule a Google Meet event using Google Calendar API."""
    global creds
    if not creds or not creds.valid:
        creds = get_credentials()
        if not creds:
            return {"error": "Failed to obtain valid credentials"}
    try:
        service = build('calendar', 'v3', credentials=creds)
        event = {
            'summary': title,
            'start': {'dateTime': start_time, 'timeZone': 'Asia/Kolkata'},
            'end': {'dateTime': end_time, 'timeZone': 'Asia/Kolkata'},
            'attendees': [{'email': email.strip()} for email in attendees],
            'conferenceData': {'createRequest': {'requestId': 'random-id', 'conferenceSolutionKey': {'type': 'hangoutsMeet'}}}
        }
        event = service.events().insert(calendarId='primary', body=event, conferenceDataVersion=1).execute()
        return {'meet_link': event.get('hangoutLink')}
    except Exception as e:
        return {'error': str(e)}

@tool
def send_email(to: str, subject: str, body: str) -> Dict:
    """Send an email using Gmail API."""
    global creds
    if not creds or not creds.valid:
        creds = get_credentials()
        if not creds:
            return {"error": "Failed to obtain valid credentials"}
    try:
        service = build('gmail', 'v1', credentials=creds)
        message = MIMEText(body)
        message['to'] = to
        message['subject'] = subject
        raw_message = base64.urlsafe_b64encode(message.as_bytes()).decode()
        send_message = service.users().messages().send(userId="me", body={'raw': raw_message}).execute()
        return {'status': 'Email sent successfully', 'message_id': send_message['id']}
    except HttpError as e:
        return {'error': f"HTTP error: {str(e)}"}
    except Exception as e:
        return {'error': str(e)}

@tool
def plan_trip(origin: str, destination: str, depart_date: str, return_date: str) -> Dict:
    """Plan a business trip itinerary using SerpAPI for flight information."""
    query = f"flights from {origin} to {destination} {depart_date} to {return_date}"
    try:
        results = serpapi_search(query, num=3)
        return {'itinerary': results}
    except Exception as e:
        return {'error': str(e)}

# Agent Workflow
tools = [search_web, fetch_wikipedia, fetch_recent_projects, schedule_meet, send_email, plan_trip]
memory = MemorySaver()
agent_executor = create_react_agent(llm, tools, checkpointer=memory)

# Cell 5: FastAPI Server - Fixed for Colab
from fastapi import FastAPI, Request, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pyngrok import ngrok
import nest_asyncio
from threading import Thread
import uvicorn
import json

# Allow nested event loops in Colab
nest_asyncio.apply()

# Create FastAPI app
app = FastAPI(title="AgentAI API")

# Add CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Chat endpoint - fixed version
@app.post("/chat")
async def chat(request: Request):
    try:
        data = await request.json()
        thread_id = data.get("thread_id")
        user_message = data.get("message")

        if not thread_id or not user_message:
            raise HTTPException(status_code=400, detail="Missing thread_id or message")

        config = {"configurable": {"thread_id": thread_id}}
        input_message = {"messages": [{"role": "user", "content": user_message}]}

        response_content = ""

        # Debugging: check what agent_executor.stream returns
        try:
            for step in agent_executor.stream(input_message, config, stream_mode="values"):
                print("DEBUG - STEP:", step)  # Print each step for inspection
                if "messages" in step:
                    for msg in step["messages"]:
                        # Works if msg is dict or object
                        content = msg.get("content") if isinstance(msg, dict) else getattr(msg, "content", "")
                        if content:
                            response_content = content  # take last content
                            print("DEBUG - MSG CONTENT:", content)
        except Exception as e:
            print("DEBUG - AGENT EXECUTOR ERROR:", str(e))
            response_content = f"Error in agent_executor: {str(e)}"

        # Fallback if no content generated
        if not response_content:
            response_content = "Sorry, I could not generate a response."

        return {"response": response_content.strip()}

    except Exception as e:
        return {"response": f"Error: {str(e)}"}


# Health check
@app.get("/health")
def health():
    return {"status": "API is running"}

# Kill any existing ngrok tunnels
print("Stopping any existing tunnels...")
ngrok.kill()

# Start ngrok tunnel on port 8000
print("\nStarting ngrok tunnel...")
tunnel = ngrok.connect(8000, bind_tls=True)
public_url = tunnel.public_url

# Display the URL prominently
print("\n" + "="*80)
print("🎉 SUCCESS! YOUR API IS READY!")
print("="*80)
print(f"\n📋 COPY THIS URL (without /health or /chat):\n")
print(f"    {public_url}\n")
print(f"🔗 Test it here: {public_url}/health")
print("\n" + "="*80)
print("✋ IMPORTANT: Keep this cell running! Don't interrupt it.")
print("="*80 + "\n")

# Function to run uvicorn in background thread
def run_server():
    uvicorn.run(app, host="0.0.0.0", port=8000, log_level="info")

# Start server in background thread
server_thread = Thread(target=run_server, daemon=True)
server_thread.start()

print("✅ Server is running in background!")
print("📱 You can now use this URL in your app!\n")

# Keep the cell running
import time
try:
    while True:
        time.sleep(1)
except KeyboardInterrupt:
    print("\n🛑 Stopping server...")
    ngrok.kill()
