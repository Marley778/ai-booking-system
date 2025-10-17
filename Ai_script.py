from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from datetime import datetime, timedelta
import requests
from googleapiclient.discovery import build
from google.oauth2.service_account import Credentials
import os
from dotenv import load_dotenv

# -----------------------------
# LOAD ENV VARIABLES
# -----------------------------
# Load local .env for development
load_dotenv("variables.env")

SERVICE_ACCOUNT_FILE = os.environ.get("GOOGLE_SERVICE_ACCOUNT_FILE", "service-account.json")
CALENDAR_ID = os.environ.get("GOOGLE_CALENDAR_ID")
GOOGLE_MAPS_API_KEY = os.environ.get("GOOGLE_MAPS_API_KEY")
BASE_ADDRESS = os.environ.get("BASE_ADDRESS")

# -----------------------------
# JOB DURATIONS
# -----------------------------
JOB_DURATIONS = {
    "pipe burst": 120,
    "leak": 60,
    "boiler service": 90,
    "tap replacement": 60,
    "electrical repair": 90,
    "socket installation": 60,
    "fuse replacement": 30,
    "general maintenance": 60,
    "painting": 120
}

# -----------------------------
# INITIALIZE GOOGLE CALENDAR
# -----------------------------
credentials = Credentials.from_service_account_file(
    SERVICE_ACCOUNT_FILE,
    scopes=["https://www.googleapis.com/auth/calendar"]
)
calendar_service = build("calendar", "v3", credentials=credentials)

# -----------------------------
# FASTAPI APP
# -----------------------------
app = FastAPI(title="AI Trades Booking Backend")

# -----------------------------
# MODELS
# -----------------------------
class JobRequest(BaseModel):
    job_type: str
    requested_time: datetime
    job_address: str

# -----------------------------
# UTILITY FUNCTIONS
# -----------------------------
def get_travel_time(origin, destination):
    url = "https://maps.googleapis.com/maps/api/distancematrix/json"
    params = {
        "origins": origin,
        "destinations": destination,
        "key": GOOGLE_MAPS_API_KEY
    }
    res = requests.get(url, params=params).json()

    if "rows" not in res or not res["rows"]:
        return 0

    elements = res["rows"][0].get("elements")
    if not elements or elements[0].get("status") != "OK":
        return 0

    return elements[0]["duration"]["value"] / 60  # minutes

def get_job_duration(job_type):
    return JOB_DURATIONS.get(job_type.lower(), 60)

def get_calendar_events(start_time, end_time):
    events_result = calendar_service.events().list(
        calendarId=CALENDAR_ID,
        timeMin=start_time.isoformat() + "Z",
        timeMax=end_time.isoformat() + "Z",
        singleEvents=True,
        orderBy="startTime"
    ).execute()
    return events_result.get("items", [])

def find_available_slot(job_type, requested_time, job_address):
    start_location = BASE_ADDRESS

    travel_time = get_travel_time(start_location, job_address)
    job_duration = get_job_duration(job_type)
    end_time = requested_time + timedelta(minutes=travel_time + job_duration)

    events = get_calendar_events(requested_time, end_time)
    conflict = any(
        datetime.fromisoformat(e['start'].get('dateTime', e['start'].get('date'))) < end_time and
        datetime.fromisoformat(e['end'].get('dateTime', e['end'].get('date'))) > requested_time
        for e in events
    )

    if conflict:
        return None

    return {
        "engineer": "Tom",
        "start": requested_time,
        "end": end_time,
        "travel_time_minutes": travel_time,
        "job_duration_minutes": job_duration
    }

# -----------------------------
# API ENDPOINT
# -----------------------------
@app.post("/get_open_slots")
async def get_open_slots(request: Request):
    data = await request.json()
    try:
        job = JobRequest(**data)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Invalid input: {str(e)}")

    slot = find_available_slot(job.job_type, job.requested_time, job.job_address)
    if not slot:
        return JSONResponse({"available": False, "message": "No slots available"})
    return JSONResponse({"available": True, "slot": slot})

# -----------------------------
# RUN SERVER (for local testing)
# -----------------------------
if __name__ == "__main__":
    import uvicorn
    port = int(os.environ.get("PORT", 8050))
    uvicorn.run(app, host="0.0.0.0", port=port, reload=True)
