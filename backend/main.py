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


# =============================================================================
# CUSTOM T-CODE RECORDER ROUTES
# Appended below. Zero changes to any route above this block.
# =============================================================================

class JobDefinition(BaseModel):
    job_name: str
    description: Optional[str] = ""
    system_id: Optional[int] = None
    steps: List[Dict[str, Any]] = []

class RunJobRequest(BaseModel):
    system_id: int

# Track custom job run status separately from basis monitoring
custom_run_status: Dict[str, Any] = {
    "is_running": False,
    "job_id": None,
    "status": "idle",
    "steps_executed": 0,
    "screenshots": [],
    "report_path": None,
    "error": None
}

@app.get("/api/custom/jobs")
def list_jobs():
    """Return all custom T-code job definitions."""
    return database.get_all_jobs()

@app.post("/api/custom/jobs")
def create_job(job: JobDefinition):
    """Create a new custom T-code job definition."""
    new_id = database.add_job(job.dict())
    created = database.get_job(new_id)
    return created

@app.put("/api/custom/jobs/{job_id}")
def update_job(job_id: int, job: JobDefinition):
    """Update an existing custom T-code job definition."""
    existing = database.get_job(job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")
    database.update_job(job_id, job.dict())
    return database.get_job(job_id)

@app.delete("/api/custom/jobs/{job_id}")
def delete_job(job_id: int):
    """Delete a custom T-code job."""
    existing = database.get_job(job_id)
    if not existing:
        raise HTTPException(status_code=404, detail="Job not found")
    database.delete_job(job_id)
    return {"success": True}

@app.get("/api/custom/status")
def get_custom_status():
    """Return current custom job run status."""
    return custom_run_status

@app.post("/api/custom/jobs/{job_id}/run")
async def run_job(job_id: int, req: RunJobRequest, background_tasks: BackgroundTasks):
    """Execute a custom T-code job against a SAP system."""
    global custom_run_status
    if custom_run_status.get("is_running"):
        raise HTTPException(status_code=409, detail="A custom job is already running")

    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    system = database.get_system(req.system_id)
    if not system:
        raise HTTPException(status_code=404, detail="System not found")

    background_tasks.add_task(_execute_custom_job, job, system)
    return {"success": True, "message": f"Job '{job['job_name']}' started"}

@app.get("/api/custom/download")
def download_custom_report():
    """Download the last generated custom recording report."""
    path = custom_run_status.get("report_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No report available")
    return FileResponse(path, media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
                        filename=os.path.basename(path))

async def _execute_custom_job(job: dict, system: dict):
    """Background task: runs the custom engine and generates the report."""
    global custom_run_status
    custom_run_status = {
        "is_running": True,
        "job_id": job["id"],
        "status": f"Starting job: {job['job_name']}",
        "steps_executed": 0,
        "screenshots": [],
        "report_path": None,
        "error": None
    }
    try:
        from custom_tcode_engine import CustomTcodeEngine
        from custom_report_generator import CustomReportGenerator

        output_dir = os.path.join(os.path.dirname(__file__), "custom_recordings")
        os.makedirs(output_dir, exist_ok=True)

        def status_cb(msg):
            custom_run_status["status"] = msg

        engine = CustomTcodeEngine(
            webgui_url=system.get("webgui_url", ""),
            username=system.get("sap_username", ""),
            password=system.get("sap_password", ""),
            client=system.get("sap_client", "100"),
            output_dir=output_dir
        )

        result = await engine.run_job(
            steps=job["steps"],
            system_config=system,
            status_callback=status_cb
        )

        custom_run_status["steps_executed"] = result.get("steps_executed", 0)
        custom_run_status["screenshots"] = result.get("screenshots", [])

        if result.get("success"):
            reporter = CustomReportGenerator(output_dir=output_dir)
            report_path = reporter.generate(
                job_name=job["job_name"],
                job_description=job.get("description", ""),
                system_name=system.get("system_name", system.get("sid", "")),
                sid=system.get("sid", ""),
                steps=job["steps"],
                screenshots=result.get("screenshots", [])
            )
            custom_run_status["report_path"] = report_path
            custom_run_status["status"] = f"Complete. {len(result.get('screenshots',[]))} screenshots captured."
        else:
            custom_run_status["error"] = result.get("error", "Unknown error")
            custom_run_status["status"] = "Failed"

    except Exception as e:
        custom_run_status["error"] = str(e)
        custom_run_status["status"] = f"Error: {e}"
        print(f"Custom job error: {e}")
    finally:
        custom_run_status["is_running"] = False
