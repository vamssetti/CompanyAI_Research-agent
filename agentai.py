import os
import json
import requests
from typing import List, Dict, TypedDict
from datetime import datetime
import uvicorn
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import RedirectResponse
import logging
import pickle
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
from google_auth_oauthlib.flow import Flow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from email.mime.text import MIMEText
import base64

# Set up logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Configuration (loaded from environment variables)
API_KEY = os.getenv("AZURE_OPENAI_API_KEY")
API_VERSION = "2025-04-01-preview"  # Restored to your working version
AZURE_ENDPOINT = os.getenv("AZURE_ENDPOINT", "https://iit-internship2025-5.openai.azure.com/")
DEPLOYMENT_NAME_CHAT = "gpt-5-mini"  # Restored to your deployment
DEPLOYMENT_NAME_EMBED = "text-embedding-ada-002"
SERPAPI_KEY = os.getenv("SERPAPI_KEY")
TAVILY_API_KEY = os.getenv("TAVILY_API_KEY")
GOOGLE_CLIENT_SECRETS = os.getenv("GOOGLE_CLIENT_SECRETS")  # JSON string from environment variable
GOOGLE_SCOPES = [
    'https://www.googleapis.com/auth/calendar.events',
    'https://www.googleapis.com/auth/calendar',
    'https://www.googleapis.com/auth/gmail.send'
]
COMMONLY_BLOCKED_DOMAINS = ['linkedin.com', 'crunchbase.com', 'bloomberg.com', 'wsj.com', 'ft.com']
CREDENTIALS_PATH = "token.pickle"  # Store Google OAuth credentials

# Validate environment variables
if not all([API_KEY, SERPAPI_KEY, TAVILY_API_KEY, GOOGLE_CLIENT_SECRETS]):
    raise ValueError(f"Missing required environment variables: "
                     f"AZURE_OPENAI_API_KEY={bool(API_KEY)}, "
                     f"SERPAPI_KEY={bool(SERPAPI_KEY)}, "
                     f"TAVILY_API_KEY={bool(TAVILY_API_KEY)}, "
                     f"GOOGLE_CLIENT_SECRETS={bool(GOOGLE_CLIENT_SECRETS)}")

# Ensure TAVILY_API_KEY is set in environment (optional, as Render should already set it)
if TAVILY_API_KEY:
    os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY
else:
    raise ValueError("TAVILY_API_KEY is not set")

# Initialize LLM and embeddings
llm = AzureChatOpenAI(
    azure_endpoint=AZURE_ENDPOINT,
    api_key=API_KEY,
    api_version=API_VERSION,
    deployment_name=DEPLOYMENT_NAME_CHAT
)
embeddings = AzureOpenAIEmbeddings(
    azure_endpoint=AZURE_ENDPOINT,
    api_key=API_KEY,
    api_version=API_VERSION,
    deployment=DEPLOYMENT_NAME_EMBED
) if DEPLOYMENT_NAME_EMBED else None

# Google API credentials
creds = None
def get_credentials():
    global creds
    if os.path.exists(CREDENTIALS_PATH):
        with open(CREDENTIALS_PATH, "rb") as token:
            creds = pickle.load(token)
    if not creds or not creds.valid:
        raise HTTPException(status_code=401, detail="Credentials not available. Visit /auth to authenticate.")
    return creds

# Initialize FastAPI app
app = FastAPI(title="AgentAI API", description="API for integrating AI agent with mobile apps")

# OAuth endpoints
@app.get("/auth")
async def auth():
    if not GOOGLE_CLIENT_SECRETS:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_SECRETS not configured")
    flow = Flow.from_client_config(
        json.loads(GOOGLE_CLIENT_SECRETS),
        scopes=GOOGLE_SCOPES,
        redirect_uri='https://agentai-api-vamsi.onrender.com/oauth2callback'
    )
    auth_url, state = flow.authorization_url(prompt='consent')
    with open("state.txt", "w") as f:
        f.write(state)
    return RedirectResponse(auth_url)

@app.get("/oauth2callback")
async def oauth2callback(code: str, state: str):
    if not GOOGLE_CLIENT_SECRETS:
        raise HTTPException(status_code=500, detail="GOOGLE_CLIENT_SECRETS not configured")
    with open("state.txt", "r") as f:
        saved_state = f.read()
    if state != saved_state:
        raise HTTPException(status_code=400, detail="Invalid state parameter")
    flow = Flow.from_client_config(
        json.loads(GOOGLE_CLIENT_SECRETS),
        scopes=GOOGLE_SCOPES,
        redirect_uri='https://agentai-api-vamsi.onrender.com/oauth2callback'
    )
    flow.fetch_token(code=code)
    global creds
    creds = flow.credentials
    with open(CREDENTIALS_PATH, "wb") as token:
        pickle.dump(creds, token)
    return {"status": "Authentication successful"}

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
        search_url = "https://en.wikipedia.org/w/api.php"
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
class AgentState(TypedDict):
    company: str
    research_data: List[Dict]
    summary: str
    recent_projects: str
    contacts: Dict
    meet_details: Dict
    trip_itinerary: Dict

tools = [search_web, fetch_wikipedia, fetch_recent_projects, schedule_meet, send_email, plan_trip]
memory = MemorySaver()
agent_executor = create_react_agent(llm, tools, checkpointer=memory)

# Endpoint for chatting with the agent
@app.post("/chat")
async def chat(request: Request):
    try:
        data = await request.json()
        thread_id = data.get("thread_id")
        user_message = data.get("message")
        if not thread_id or not user_message:
            logger.error("Missing thread_id or message in request")
            raise HTTPException(status_code=400, detail="Missing thread_id or message")
        config = {"configurable": {"thread_id": thread_id}}
        input_message = {"messages": [{"role": "user", "content": user_message}]}
        response_content = ""
        logger.info(f"Processing message: {user_message} for thread_id: {thread_id}")
        for step in agent_executor.stream(input_message, config, stream_mode="values"):
            for msg in step["messages"]:
                if hasattr(msg, "content") and msg.content:
                    response_content += msg.content + "\n"
                elif hasattr(msg, "tool_calls") and msg.tool_calls:
                    response_content += f"Tool Call: {json.dumps(msg.tool_calls)}\n"
                elif hasattr(msg, "additional_kwargs") and msg.additional_kwargs.get("tool_calls"):
                    response_content += f"Tool Call: {json.dumps(msg.additional_kwargs['tool_calls'])}\n"
        logger.info("Request processed successfully")
        return {"response": response_content.strip()}
    except Exception as e:
        logger.error(f"Error in /chat endpoint: {str(e)}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Internal Server Error: {str(e)}")

# Health check endpoint
@app.get("/health")
def health():
    logger.info("Health check requested")
    return {"status": "API is running"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))  # Render sets PORT
    uvicorn.run(app, host="0.0.0.0", port=port)
