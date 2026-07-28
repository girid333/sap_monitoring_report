from fastapi import FastAPI, BackgroundTasks, HTTPException, WebSocket, WebSocketDisconnect, Form, File, UploadFile
from fastapi.responses import FileResponse, JSONResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional, Dict, Any
import asyncio
import os
import zipfile
import shutil
import json
import uuid
import tempfile

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

# =============================================================================
# RECORD & REPLAY — WebSocket Recorder + Batch Runner
# Appended below. Zero changes to any existing code above.
# =============================================================================

# In-memory storage for recording sessions
recording_sessions: Dict[str, Dict] = {}

# In-memory batch run status (separate from single-job custom_run_status)
batch_run_status: Dict[str, Any] = {
    "is_running": False,
    "total_rows": 0,
    "completed_rows": 0,
    "current_run": "",
    "results": [],
    "report_path": None,
    "error": None
}

# ---- Recorder Session Management ----

@app.post("/api/custom/recorder/start")
def start_recorder_session():
    """Create a new recording session ID. Returns the session_id and JS snippet."""
    session_id = str(uuid.uuid4())[:8]
    recording_sessions[session_id] = {
        "events": [],
        "steps": [],
        "active": True,
        "event_count": 0
    }
    return {"session_id": session_id}

@app.get("/api/custom/recorder/status/{session_id}")
def get_recorder_status(session_id: str):
    """Poll this to get live recording status."""
    if session_id not in recording_sessions:
        return {"active": False, "steps": [], "event_count": 0}
    s = recording_sessions[session_id]
    return {"active": s["active"], "steps": s["steps"], "event_count": s["event_count"]}

@app.post("/api/custom/recorder/stop/{session_id}")
def stop_recorder_session(session_id: str):
    """Finalize the session and return captured steps."""
    if session_id not in recording_sessions:
        raise HTTPException(status_code=404, detail="Session not found")
    s = recording_sessions[session_id]
    s["active"] = False
    return {"steps": s["steps"], "event_count": s["event_count"]}

@app.websocket("/ws/recorder/{session_id}")
async def recorder_websocket(websocket: WebSocket, session_id: str):
    """WebSocket endpoint: receives raw browser events from the JS recorder snippet."""
    await websocket.accept()
    # Ensure session exists
    if session_id not in recording_sessions:
        recording_sessions[session_id] = {"events": [], "steps": [], "active": True, "event_count": 0}
    session = recording_sessions[session_id]
    session["active"] = True
    try:
        while True:
            try:
                data = await asyncio.wait_for(websocket.receive_text(), timeout=600)
                event = json.loads(data)
                if event.get("type") == "stop":
                    break
                session["events"].append(event)
                session["event_count"] += 1
                step = _convert_event_to_step(event)
                if step:
                    session["steps"].append(step)
            except asyncio.TimeoutError:
                break
    except (WebSocketDisconnect, Exception) as e:
        print(f"Recorder WS closed: {e}")
    finally:
        session["active"] = False
        try:
            await websocket.close()
        except Exception:
            pass

def _convert_event_to_step(event: dict) -> Optional[dict]:
    """Convert a raw browser event dict into a step definition."""
    etype = event.get("type", "")
    if etype == "fill":
        value = str(event.get("value", "")).strip()
        if not value:
            return None  # Ignore empty fills
        label = str(event.get("label", "")).strip()
        elem_id = str(event.get("id", "")).strip()
        if label:
            return {"type": "fill_by_label", "label": label, "value": value}
        elif elem_id:
            return {"type": "fill_by_id", "element_id": elem_id, "value": value}
        else:
            return {"type": "fill_by_position", "position": 0, "value": value}
    elif etype == "keypress":
        key = event.get("key", "")
        valid = {"F3","F4","F5","F6","F7","F8","F9","F10","F11","F12","Enter"}
        if key in valid:
            return {"type": "press_fkey", "key": key}
    elif etype == "click":
        text = (str(event.get("text") or event.get("title") or "")).strip()
        if text and 2 < len(text) < 80:
            return {"type": "click_button", "button_text": text}
    elif etype == "navigate":
        tcode = str(event.get("tcode", "")).strip().upper()
        if tcode:
            return {"type": "navigate_tcode", "tcode": tcode}
    elif etype == "screenshot_marker":
        return {"type": "screenshot", "caption": str(event.get("caption", "Screenshot"))}
    return None

# ---- Excel Template Download ----

@app.get("/api/custom/jobs/{job_id}/excel-template")
def download_excel_template(job_id: int):
    """Generate and download an Excel data-input template for this job."""
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    from excel_handler import ExcelHandler
    handler = ExcelHandler()
    template_path = handler.generate_template(job)
    safe_name = job["job_name"].replace(" ", "_")[:40]
    return FileResponse(
        template_path,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        filename=f"{safe_name}_template.xlsx"
    )

# ---- Batch Run ----

@app.get("/api/custom/batch/status")
def get_batch_status():
    """Return current batch run status."""
    return batch_run_status

@app.get("/api/custom/batch/download")
def download_batch_report():
    """Download the latest batch report."""
    path = batch_run_status.get("report_path")
    if not path or not os.path.exists(path):
        raise HTTPException(status_code=404, detail="No batch report available")
    return FileResponse(
        path,
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
        filename=os.path.basename(path)
    )

@app.post("/api/custom/jobs/{job_id}/batch-run")
async def batch_run_job(
    job_id: int,
    background_tasks: BackgroundTasks,
    system_id: int = Form(...),
    file: UploadFile = File(...)
):
    """Upload an Excel file and run the job once for every data row."""
    global batch_run_status
    if batch_run_status.get("is_running"):
        raise HTTPException(status_code=409, detail="A batch job is already running")
    job = database.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    system = database.get_system(system_id)
    if not system:
        raise HTTPException(status_code=404, detail="System not found")

    # Save uploaded Excel to a temp file
    content = await file.read()
    tmp = tempfile.NamedTemporaryFile(suffix=".xlsx", delete=False)
    tmp.write(content)
    tmp.close()

    background_tasks.add_task(_execute_batch_job, job, system, tmp.name)
    return {"success": True, "message": f"Batch run started for job '{job['job_name']}'"}

async def _execute_batch_job(job: dict, system: dict, excel_path: str):
    """Background task: run the job for every row in the Excel file."""
    global batch_run_status
    batch_run_status = {
        "is_running": True,
        "total_rows": 0,
        "completed_rows": 0,
        "current_run": "Reading Excel...",
        "results": [],
        "report_path": None,
        "error": None
    }
    try:
        from excel_handler import ExcelHandler
        from custom_tcode_engine import CustomTcodeEngine
        from custom_report_generator import CustomReportGenerator

        handler = ExcelHandler()
        rows = handler.read_batch_data(excel_path)

        if not rows:
            batch_run_status["error"] = "No data rows found in Excel file"
            return

        batch_run_status["total_rows"] = len(rows)
        output_dir = os.path.join(os.path.dirname(__file__), "custom_recordings")
        os.makedirs(output_dir, exist_ok=True)

        all_results = []
        for i, row_data in enumerate(rows):
            run_name = row_data.get("Run_Name", f"Run_{i+1}")
            batch_run_status["current_run"] = f"{run_name} ({i+1}/{len(rows)})"

            modified_steps = handler.substitute_values(job["steps"], row_data)

            engine = CustomTcodeEngine(
                webgui_url=system.get("webgui_url", ""),
                username=system.get("sap_username", ""),
                password=system.get("sap_password", ""),
                client=system.get("sap_client", "100"),
                output_dir=output_dir
            )

            result = await engine.run_job(
                steps=modified_steps,
                system_config=system
            )

            all_results.append({
                "run_name": run_name,
                "row_data": row_data,
                "success": result.get("success", False),
                "screenshots": result.get("screenshots", [])
            })
            batch_run_status["completed_rows"] = i + 1

        batch_run_status["results"] = all_results

        # Generate combined batch report
        reporter = CustomReportGenerator(output_dir=output_dir)
        report_path = reporter.generate_batch(
            job_name=job["job_name"],
            system_name=system.get("system_name", system.get("sid", "")),
            sid=system.get("sid", ""),
            all_results=all_results
        )
        batch_run_status["report_path"] = report_path
        batch_run_status["current_run"] = f"Complete — {len(all_results)} runs finished"

    except Exception as e:
        batch_run_status["error"] = str(e)
        print(f"Batch job error: {e}")
        import traceback; traceback.print_exc()
    finally:
        batch_run_status["is_running"] = False
        if os.path.exists(excel_path):
            try:
                os.remove(excel_path)
            except Exception:
                pass

# =============================================================================
# LIVE BROWSER RECORDER (Canvas Streaming)
# =============================================================================

from browser_recorder import BrowserRecorder

# In-memory storage for active browser recording sessions
live_browser_sessions: Dict[str, BrowserRecorder] = {}

class StartBrowserRequest(BaseModel):
    system_id: int
    tcode: str = ""

@app.post("/api/custom/recorder/start-browser")
async def start_browser_recording(req: StartBrowserRequest):
    print(f"[{datetime.now()}] /api/custom/recorder/start-browser called for system {req.system_id}", flush=True)
    system = database.get_system(req.system_id)
    if not system:
        print("System not found!", flush=True)
        raise HTTPException(status_code=404, detail="System not found")
    
    session_id = str(uuid.uuid4())[:8]
    print(f"[{datetime.now()}] Initializing BrowserRecorder for session {session_id}", flush=True)
    recorder = BrowserRecorder(session_id=session_id, system=system)
    live_browser_sessions[session_id] = recorder
    
    # Start the browser async
    asyncio.create_task(recorder.start(req.tcode))
    
    print(f"[{datetime.now()}] Returning session {session_id} to frontend", flush=True)
    return {"session_id": session_id}

@app.websocket("/ws/browser/{session_id}")
async def browser_websocket(websocket: WebSocket, session_id: str):
    print(f"[{datetime.now()}] WebSocket connection requested for session {session_id}", flush=True)
    await websocket.accept()
    recorder = live_browser_sessions.get(session_id)
    if not recorder:
        print(f"[{datetime.now()}] Session {session_id} not found", flush=True)
        await websocket.close(code=1008, reason="Session not found")
        return
    
    print(f"[{datetime.now()}] Waiting for browser to be ready...", flush=True)
    for _ in range(60):
        if recorder.is_ready or recorder.error:
            break
        await asyncio.sleep(0.5)
    
    if not recorder.is_ready:
        err_msg = recorder.error or "Browser failed to start (timeout)"
        await websocket.send_json({"type": "error", "message": err_msg})
        await websocket.close()
        return

    # Callbacks for stream loop
    async def on_frame(b64_img):
        try:
            await websocket.send_json({"type": "frame", "data": b64_img})
        except Exception:
            pass

    async def on_step(step_dict):
        try:
            await websocket.send_json({"type": "step", "step": step_dict})
        except Exception:
            pass
            
    # Start stream loop in background
    stream_task = asyncio.create_task(recorder.run_stream_loop(on_frame, on_step))

    try:
        while True:
            data = await websocket.receive_json()
            msg_type = data.get("type")
            
            if msg_type == "click":
                step = await recorder.handle_click(data.get("x", 0), data.get("y", 0))
                if step:
                    await on_step(step)
            elif msg_type == "key":
                step = await recorder.handle_keypress(data.get("key", ""))
                if step:
                    await on_step(step)
            elif msg_type == "type":
                await recorder.handle_type(data.get("text", ""))
            elif msg_type == "screenshot":
                step = await recorder.mark_screenshot(data.get("caption", ""))
                if step:
                    await on_step(step)
            elif msg_type == "stop":
                break
    except WebSocketDisconnect:
        pass
    except Exception as e:
        print(f"[{datetime.now()}] Browser WS error: {e}", flush=True)
    finally:
        print(f"[{datetime.now()}] Closing WebSocket and stopping recorder", flush=True)
        stream_task.cancel()
        steps = await recorder.stop()
        live_browser_sessions.pop(session_id, None)
        try:
            await websocket.send_json({"type": "stopped", "steps": steps})
            await websocket.close()
        except Exception:
            pass

