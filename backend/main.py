from fastapi import FastAPI, BackgroundTasks
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
import asyncio
import os

from orchestrator import ReportOrchestrator
from report_generator import ReportGenerator
from sap_rfc_client import SAPRfcClient

app = FastAPI(title="SAP BASIS Monitoring API")

# Setup CORS for the Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "http://localhost:3000",
        "http://127.0.0.1:3000",
        "http://10.147.15.11:3000"
    ],
    allow_origin_regex="https?://.*:3000",
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RunConfig(BaseModel):
    hostname: str
    sid: str
    instance_number: str
    sap_client: str
    sap_username: str
    sap_password: str
    webgui_url: str = ""
    ssh_username: str = ""
    ssh_password: str = ""
    db_host: str = ""
    servers: List[str] = []
    url_checks: List[str] = []

# Store the status of the current run
run_status = {
    "is_running": False,
    "status": "idle",
    "word_report": None,
    "pdf_report": None,
    "results": None
}

async def execute_monitoring_run(config: dict):
    global run_status
    run_status["is_running"] = True
    run_status["status"] = "Starting execution..."
    
    def status_callback(msg: str):
        run_status["status"] = msg
        
    try:
        # Run orchestration
        orchestrator = ReportOrchestrator(config, status_callback=status_callback)
        results = await orchestrator.generate_report()
        run_status["results"] = results
        
        # Generate reports
        run_status["status"] = "Generating Reports..."
        generator = ReportGenerator(results)
        word_path = generator.generate_word()
        pdf_path = generator.generate_pdf()
        
        run_status["word_report"] = word_path
        run_status["pdf_report"] = pdf_path
        run_status["status"] = "Completed"
    except Exception as e:
        run_status["status"] = f"Error: {str(e)}"
    finally:
        run_status["is_running"] = False

@app.post("/api/run")
async def trigger_run(config: RunConfig, background_tasks: BackgroundTasks):
    global run_status
    if run_status["is_running"]:
        return JSONResponse(status_code=400, content={"message": "A run is already in progress."})
    
    # Reset status
    run_status["status"] = "Starting..."
    run_status["word_report"] = None
    run_status["pdf_report"] = None
    run_status["results"] = None
    
    background_tasks.add_task(execute_monitoring_run, config.model_dump())
    return {"message": "Run started successfully."}

@app.post("/api/test-connection")
async def test_connection(config: RunConfig):
    client = SAPRfcClient(
        ashost=config.hostname,
        sysnr=config.instance_number,
        client=config.sap_client,
        user=config.sap_username,
        passwd=config.sap_password
    )
    
    success = client.connect()
    client.disconnect()
    
    if success:
        return {"success": True, "message": "RFC Connection successful!"}
    else:
        return JSONResponse(status_code=400, content={"success": False, "message": "RFC Login failed. Check credentials or connection."})

@app.get("/api/status")
async def get_status():
    return run_status

@app.get("/api/download/word")
async def download_word():
    if run_status["word_report"] and os.path.exists(run_status["word_report"]):
        return FileResponse(run_status["word_report"], filename="SAP_BASIS_Report.docx")
    return JSONResponse(status_code=404, content={"message": "Report not found."})

@app.get("/api/download/pdf")
async def download_pdf():
    if run_status["pdf_report"] and os.path.exists(run_status["pdf_report"]):
        return FileResponse(run_status["pdf_report"], filename="SAP_BASIS_Report.pdf")
    return JSONResponse(status_code=404, content={"message": "Report not found."})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
