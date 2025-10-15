
!pip install --quiet --upgrade langchain langchain-community langgraph langgraph-checkpoint-sqlite langchain-tavily langchain-openai openai faiss-cpu requests google-auth-oauthlib google-api-python-client beautifulsoup4 serpapi tldextract

# @title Set Up Environment and Import Libraries
import os
import re
import json
import time
import requests
from typing import List, Dict, TypedDict
from bs4 import BeautifulSoup
import urllib.parse
from datetime import datetime

# Azure OpenAI and LangChain imports
from openai import AzureOpenAI
from langchain_community.vectorstores import FAISS
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.docstore.document import Document
from langchain_openai import AzureChatOpenAI, AzureOpenAIEmbeddings
from langchain_community.tools.tavily_search import TavilySearchResults
from langchain.tools import tool
from langgraph.graph import StateGraph
from langgraph.prebuilt import create_react_agent
from langgraph.checkpoint.memory import MemorySaver

# Google API imports
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build

# Configuration
API_KEY = "api key"
API_VERSION = "2025-04-01-preview"
AZURE_ENDPOINT = "https://iit-internship2025-5.openai.azure.com/"
DEPLOYMENT_NAME_CHAT = "gpt-5-mini"
DEPLOYMENT_NAME_EMBED = "text-embedding-ada-002"
SERPAPI_KEY = "key"
TAVILY_API_KEY = "key"  # Replace with your actual Tavily API key!
os.environ["TAVILY_API_KEY"] = TAVILY_API_KEY
GOOGLE_CLIENT_SECRETS = "/content/my-project-01-418012-80bbcaae89e3.json"
COMMONLY_BLOCKED_DOMAINS = ['linkedin.com', 'crunchbase.com', 'bloomberg.com', 'wsj.com', 'ft.com']

# State Definition
class AgentState(TypedDict):
    company: str
    research_data: List[Dict]
    summary: str
    recent_projects: str
    contacts: Dict
    meet_details: Dict
    trip_itinerary: Dict

# Initialize LLM and Tools
llm = AzureChatOpenAI(azure_endpoint=AZURE_ENDPOINT, api_key=API_KEY, api_version=API_VERSION, deployment_name=DEPLOYMENT_NAME_CHAT)
embeddings = AzureOpenAIEmbeddings(azure_endpoint=AZURE_ENDPOINT, api_key=API_KEY, api_version=API_VERSION, deployment=DEPLOYMENT_NAME_EMBED) if DEPLOYMENT_NAME_EMBED else None

# Tools
@tool
def search_web(query: str) -> List[Dict]:
    """Searches the web for a given query."""
    try:
        search = TavilySearchResults(max_results=5)
        return search.invoke(query)
    except Exception as e:
        return [{"error": str(e)}]

@tool
def fetch_wikipedia(company: str) -> Dict:
    """Fetches Wikipedia content for a given company."""
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
    """Fetches recent IT system integration projects for a given company."""
    query = f"{company} IT system integration Japan recent projects global 2024 2025"
    try:
        results = serpapi_search(query, num=5)
        return json.dumps(results)
    except Exception as e:
        return json.dumps({"error": str(e)})

def serpapi_search(query: str, num: int = 5) -> List[Dict]:
    params = {"engine": "google", "q": query, "api_key": SERPAPI_KEY, "num": num}
    response = requests.get("https://serpapi.com/search", params=params)
    return response.json().get("organic_results", []) if response.status_code == 200 else []

@tool
def schedule_meet(title: str, start_time: str, end_time: str, attendees: List[str]) -> Dict:
    """Schedules a meeting with the given details."""
    try:
        with open(GOOGLE_CLIENT_SECRETS, 'r') as f:
            secrets = json.load(f)
            if 'installed' not in secrets:
                raise ValueError("Client secrets must be for an installed (Desktop) app. Regenerate in Google Console as 'Desktop app'.")
        flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CLIENT_SECRETS, ['https://www.googleapis.com/auth/calendar.events', 'https://www.googleapis.com/auth/calendar'])
        creds = flow.run_local_server(port=0)
        service = build('calendar', 'v3', credentials=creds)
        event = {
            'summary': title,
            'start': {'dateTime': start_time, 'timeZone': 'UTC'},
            'end': {'dateTime': end_time, 'timeZone': 'UTC'},
            'attendees': [{'email': email.strip()} for email in attendees],
            'conferenceData': {'createRequest': {'requestId': 'random-id', 'conferenceSolutionKey': {'type': 'hangoutsMeet'}}}
        }
        event = service.events().insert(calendarId='primary', body=event, conferenceDataVersion=1).execute()
        return {'meet_link': event.get('hangoutLink')}
    except Exception as e:
        return {'error': str(e)}

@tool
def plan_trip(origin: str, destination: str, depart_date: str, return_date: str) -> Dict:
    """Plans a trip with flight details."""
    query = f"flights from {origin} to {destination} {depart_date} to {return_date}"
    try:
        results = serpapi_search(query, num=3)
        return {'itinerary': results}
    except Exception as e:
        return {'error': str(e)}

# Agent Workflow
tools = [search_web, fetch_wikipedia, fetch_recent_projects, schedule_meet, plan_trip]
memory = MemorySaver()
agent_executor = create_react_agent(llm, tools, checkpointer=memory)

# Interactive Chat Function (Until 'ok i am done' with Date/Time)
def chat_with_agent():
    current_time = datetime(2025, 10, 15, 18, 15)  # 06:15 PM IST
    formatted_time = current_time.strftime("%I:%M %p IST on %B %d, %Y (%A)")

    thread_id = input("Enter a unique thread ID for this conversation (e.g., otsuka_chat): ")
    config = {"configurable": {"thread_id": thread_id}}

    print(f"\nChat with the Agent! Current date and time is {formatted_time}. Type 'ok i am done' to stop.")
    while True:
        user_input = input("You: ")
        if user_input.lower() == 'ok i am done':
            print("Agent: Goodbye! I'm here if you need me later.")
            break

        input_message = {"messages": [{"role": "user", "content": user_input}]}

        print("Agent thinking...")
        for step in agent_executor.stream(input_message, config, stream_mode="values"):
            for msg in step["messages"]:
                if hasattr(msg, "content") and msg.content:
                    print(f"Agent: {msg.content}")
                elif hasattr(msg, "tool_calls") and msg.tool_calls:
                    print(f"Agent: Tool Call - {msg.tool_calls}")
                elif hasattr(msg, "additional_kwargs") and msg.additional_kwargs.get("tool_calls"):
                    print(f"Agent: Tool Call - {msg.additional_kwargs['tool_calls']}")
                else:
                    print(f"Agent: {step}")

# Run the interactive chat
if __name__ == "__main__":
    chat_with_agent()

# State Definition
class AgentState(TypedDict):
    company: str
    research_data: List[Dict]
    summary: str
    recent_projects: str
    contacts: Dict
    meet_details: Dict
    trip_itinerary: Dict

# Initialize LLM and Tools
llm = AzureChatOpenAI(azure_endpoint=AZURE_ENDPOINT, api_key=API_KEY, api_version=API_VERSION, deployment_name=DEPLOYMENT_NAME_CHAT)
embeddings = AzureOpenAIEmbeddings(azure_endpoint=AZURE_ENDPOINT, api_key=API_KEY, api_version=API_VERSION, deployment=DEPLOYMENT_NAME_EMBED) if DEPLOYMENT_NAME_EMBED else None

# Tools
@tool
def search_web(query: str) -> List[Dict]:
    """Search the web for global company information using Tavily API."""
    try:
        search = TavilySearchResults(max_results=5)
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
    try:
        with open(GOOGLE_CLIENT_SECRETS, 'r') as f:
            secrets = json.load(f)
            if 'installed' not in secrets:
                raise ValueError("Client secrets must be for an installed (Desktop) app. Regenerate in Google Console as 'Desktop app'.")
        flow = InstalledAppFlow.from_client_secrets_file(GOOGLE_CLIENT_SECRETS, ['https://www.googleapis.com/auth/calendar.events', 'https://www.googleapis.com/auth/calendar'])
        creds = flow.run_local_server(port=0)
        service = build('calendar', 'v3', credentials=creds)
        event = {
            'summary': title,
            'start': {'dateTime': start_time, 'timeZone': 'UTC'},
            'end': {'dateTime': end_time, 'timeZone': 'UTC'},
            'attendees': [{'email': email.strip()} for email in attendees],
            'conferenceData': {'createRequest': {'requestId': 'random-id', 'conferenceSolutionKey': {'type': 'hangoutsMeet'}}}
        }
        event = service.events().insert(calendarId='primary', body=event, conferenceDataVersion=1).execute()
        return {'meet_link': event.get('hangoutLink')}
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
tools = [search_web, fetch_wikipedia, fetch_recent_projects, schedule_meet, plan_trip]
memory = MemorySaver()
agent_executor = create_react_agent(llm, tools, checkpointer=memory)

# Interactive Chat Function (Until 'ok i am done' with Date/Time)
def chat_with_agent():
    current_time = datetime(2025, 10, 15, 18, 21)  # 06:21 PM IST
    formatted_time = current_time.strftime("%I:%M %p IST on %B %d, %Y (%A)")

    thread_id = input("Enter a unique thread ID for this conversation (e.g., otsuka_chat): ")
    config = {"configurable": {"thread_id": thread_id}}

    print(f"\nChat with the Agent! Current date and time is {formatted_time}. Type 'ok i am done' to stop.")
    while True:
        user_input = input("You: ")
        if user_input.lower() == 'ok i am done':
            print("Agent: Goodbye! I'm here if you need me later.")
            break

        input_message = {"messages": [{"role": "user", "content": user_input}]}

        print("Agent thinking...")
        for step in agent_executor.stream(input_message, config, stream_mode="values"):
            for msg in step["messages"]:
                if hasattr(msg, "content") and msg.content:
                    print(f"Agent: {msg.content}")
                elif hasattr(msg, "tool_calls") and msg.tool_calls:
                    print(f"Agent: Tool Call - {msg.tool_calls}")
                elif hasattr(msg, "additional_kwargs") and msg.additional_kwargs.get("tool_calls"):
                    print(f"Agent: Tool Call - {msg.additional_kwargs['tool_calls']}")
                else:
                    print(f"Agent: {step}")

# Run the interactive chat
if __name__ == "__main__":
    chat_with_agent()

