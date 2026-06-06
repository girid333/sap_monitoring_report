from fastapi import FastAPI, BackgroundTasks, HTTPException
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import asyncio
import os
import zipfile
import shutil

from orchestrator import ReportOrchestrator
from report_generator import ReportGenerator
from sap_rfc_client import SAPRfcClient
import database

app = FastAPI(title="SAP BASIS Monitoring API (Enterprise)")

# Setup CORS for the Next.js frontend
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for enterprise local dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class RunConfig(BaseModel):
    id: Optional[int] = None
    system_name: str = ""
    hostname: str
    sid: str
    instance_number: str
    sap_client: str
    sap_username: str
    sap_password: Optional[str] = None
    webgui_url: str = ""
    ssh_auth_method: str = "password"
    ssh_username: str = ""
    ssh_password: Optional[str] = None
    ssh_key_path: Optional[str] = None
    db_host: str = ""
    servers: List[Any] = []
    url_checks: List[str] = []

class BulkRunRequest(BaseModel):
    system_ids: List[int]

# Store the status of the current run
run_status = {
    "is_running": False,
    "status": "idle",
    "progress": 0,
    "total": 0,
    "current_system": "",
    "zip_report": None,
    "results": {}
}

async def execute_bulk_monitoring(system_ids: List[int]):
    global run_status
    run_status["is_running"] = True
    run_status["total"] = len(system_ids)
    run_status["progress"] = 0
    
    reports_dir = os.path.join(os.path.dirname(__file__), "batch_reports")
    os.makedirs(reports_dir, exist_ok=True)
    
    generated_files = []
    
    try:
        for idx, sys_id in enumerate(system_ids):
            sys_data = database.get_system(sys_id)
            if not sys_data:
                continue
                
            run_status["current_system"] = sys_data.get("system_name", sys_data.get("sid", "Unknown"))
            run_status["status"] = f"Processing {run_status['current_system']}..."
            
            def status_callback(msg: str):
                run_status["status"] = f"[{run_status['current_system']}] {msg}"
            
            # Map db dictionary to RunConfig dictionary format
            orchestrator = ReportOrchestrator(sys_data, status_callback=status_callback)
            results = await orchestrator.generate_report()
            run_status["results"][sys_id] = "Success"
            
            run_status["status"] = f"Generating Reports for {run_status['current_system']}..."
            generator = ReportGenerator(results, output_dir=reports_dir)
            word_path = generator.generate_word()
            pdf_path = generator.generate_pdf()
            
            generated_files.extend([word_path, pdf_path])
            run_status["progress"] = idx + 1

        # Zip all reports
        run_status["status"] = "Zipping reports..."
        zip_path = os.path.join(reports_dir, "SAP_Batch_Reports.zip")
        with zipfile.ZipFile(zip_path, 'w') as zipf:
            for file in generated_files:
                if os.path.exists(file):
                    zipf.write(file, os.path.basename(file))
                    
        run_status["zip_report"] = zip_path
        run_status["status"] = "Completed"
        
    except Exception as e:
        run_status["status"] = f"Error: {str(e)}"
    finally:
        run_status["is_running"] = False

# --- SYSTEMS API (CRUD) ---

@app.get("/api/systems")
async def list_systems():
    return database.get_all_systems()

@app.post("/api/systems")
async def create_system(config: RunConfig):
    new_id = database.add_system(config.model_dump())
    return {"message": "System created", "id": new_id}

@app.put("/api/systems/{system_id}")
async def update_system(system_id: int, config: RunConfig):
    database.update_system(system_id, config.model_dump())
    return {"message": "System updated"}

@app.delete("/api/systems/{system_id}")
async def delete_system(system_id: int):
    database.delete_system(system_id)
    return {"message": "System deleted"}

# --- EXECUTION API ---

@app.post("/api/run/bulk")
async def trigger_bulk_run(req: BulkRunRequest, background_tasks: BackgroundTasks):
    global run_status
    if run_status["is_running"]:
        return JSONResponse(status_code=400, content={"message": "A run is already in progress."})
    
    run_status["status"] = "Starting batch run..."
    run_status["zip_report"] = None
    run_status["results"] = {}
    run_status["progress"] = 0
    run_status["total"] = len(req.system_ids)
    
    background_tasks.add_task(execute_bulk_monitoring, req.system_ids)
    return {"message": "Batch run started successfully."}

@app.get("/api/status")
async def get_status():
    return run_status

@app.get("/api/download/zip")
async def download_zip():
    if run_status["zip_report"] and os.path.exists(run_status["zip_report"]):
        return FileResponse(run_status["zip_report"], filename="SAP_Batch_Reports.zip")
    return JSONResponse(status_code=404, content={"message": "Report zip not found."})

@app.post("/api/test-connection")
async def test_connection(config: RunConfig):
    client = SAPRfcClient(
        ashost=config.hostname,
        sysnr=config.instance_number,
        client=config.sap_client,
        user=config.sap_username,
        passwd=config.sap_password or ""
    )
    success = client.connect()
    client.disconnect()
    
    if success:
        return {"success": True, "message": "RFC Connection successful!"}
    else:
        return JSONResponse(status_code=400, content={"success": False, "message": "RFC Login failed."})

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
