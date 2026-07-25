"use client";

import { useState, useEffect } from "react";
import styles from "./page.module.css";

export default function Home() {
  const [view, setView] = useState("inventory");
  const [systems, setSystems] = useState<any[]>([]);
  const [selectedSystems, setSelectedSystems] = useState<number[]>([]);

  // === CUSTOM T-CODE STATE (additive, does not touch existing state) ===
  const [jobs, setJobs] = useState<any[]>([]);
  const [isJobModalOpen, setIsJobModalOpen] = useState(false);
  const [editingJobId, setEditingJobId] = useState<number | null>(null);
  const [jobForm, setJobForm] = useState({ job_name: "", description: "", system_id: "" as any, steps: [] as any[] });
  const [customStatus, setCustomStatus] = useState<any>({ is_running: false, status: "idle", steps_executed: 0, screenshots: [], report_path: null, error: null });
  const [runningJobId, setRunningJobId] = useState<number | null>(null);
  // Step builder step type selector
  type StepField = { key: string; label: string; placeholder?: string; type?: string; options?: string[] };
  type StepTypeDef = { value: string; label: string; fields: StepField[] };
  const STEP_TYPES: StepTypeDef[] = [
    { value: "navigate_tcode",   label: "🔀 Navigate T-Code",         fields: [{ key: "tcode", label: "T-Code", placeholder: "SE16" }] },
    { value: "press_fkey",       label: "⌨️ Press Key",               fields: [{ key: "key", label: "Key", type: "select", options: ["Enter","F3","F4","F5","F6","F7","F8","F9","F10","F11","F12"] }] },
    { value: "fill_by_label",    label: "✏️ Fill by Label",           fields: [{ key: "label", label: "Field Label", placeholder: "Material" }, { key: "value", label: "Value", placeholder: "1000" }] },
    { value: "fill_by_id",       label: "✏️ Fill by Element ID",      fields: [{ key: "element_id", label: "Element ID", placeholder: "wnd[0]/usr/..." }, { key: "value", label: "Value" }] },
    { value: "fill_by_position", label: "✏️ Fill by Position",        fields: [{ key: "position", label: "Position (0=first)", placeholder: "0" }, { key: "value", label: "Value" }] },
    { value: "select_dropdown",  label: "📋 Select Dropdown",         fields: [{ key: "label_or_id", label: "Label/ID" }, { key: "option", label: "Option Value" }] },
    { value: "clear_field",      label: "🗑️ Clear Field",             fields: [{ key: "label_or_id", label: "Label/ID" }] },
    { value: "click_button",     label: "🖱️ Click Button",            fields: [{ key: "button_text", label: "Button Text", placeholder: "Execute" }] },
    { value: "click_menu_path",  label: "📁 Click Menu Path",         fields: [{ key: "path", label: "Menu Path (comma separated)", placeholder: "Edit,Select All" }] },
    { value: "click_tab",        label: "📑 Click Tab",               fields: [{ key: "tab_text", label: "Tab Text" }] },
    { value: "click_table_row",  label: "📊 Click Table Row",         fields: [{ key: "row_text", label: "Row contains text" }] },
    { value: "double_click",     label: "🖱️ Double Click",            fields: [{ key: "target", label: "Target text/ID" }] },
    { value: "expand_tree_node", label: "🌳 Expand Tree Node",         fields: [{ key: "node_text", label: "Node Text" }] },
    { value: "click_tree_node",  label: "🌳 Click Tree Node",          fields: [{ key: "node_text", label: "Node Text" }] },
    { value: "confirm_dialog",   label: "✅ Confirm Dialog (OK/Yes)", fields: [] },
    { value: "dismiss_dialog",   label: "❌ Dismiss Dialog (Cancel)", fields: [] },
    { value: "handle_f4_help",   label: "🔍 F4 Value Help",           fields: [{ key: "field_label", label: "Field Label" }, { key: "search_value", label: "Search Value" }] },
    { value: "scroll_table_down",label: "⬇️ Scroll Table Down",       fields: [{ key: "times", label: "Times", placeholder: "1" }] },
    { value: "filter_column",    label: "🔍 Filter Column",           fields: [{ key: "column_name", label: "Column Name" }, { key: "filter_value", label: "Filter Value" }] },
    { value: "wait_seconds",     label: "⏱️ Wait",                    fields: [{ key: "seconds", label: "Seconds", placeholder: "2" }] },
    { value: "wait_for_element", label: "⏳ Wait For Element",         fields: [{ key: "text", label: "Element Text" }, { key: "timeout", label: "Timeout (s)", placeholder: "10" }] },
    { value: "scroll_page_down", label: "⬇️ Scroll Page Down",        fields: [] },
    { value: "screenshot",       label: "📸 Screenshot",              fields: [{ key: "caption", label: "Caption", placeholder: "Overview screen" }] },
    { value: "screenshot_full_page", label: "📸 Full-Page Screenshot", fields: [{ key: "caption", label: "Caption" }] },
  ];
  const [newStepType, setNewStepType] = useState("navigate_tcode");

  
  // Modal State
  const [isModalOpen, setIsModalOpen] = useState(false);
  const [editingId, setEditingId] = useState<number | null>(null);
  const [formData, setFormData] = useState({
    system_name: "", hostname: "", sid: "", instance_number: "", sap_client: "",
    sap_username: "", sap_password: "", webgui_url: "",
    ssh_auth_method: "password", ssh_username: "", ssh_password: "", ssh_key_path: "", db_host: "",
    servers: [] as any[], url_checks: [] as string[]
  });

  // Run State
  const [status, setStatus] = useState<any>({ is_running: false, status: "idle", progress: 0, total: 0 });
  const apiBase = typeof window !== "undefined" ? `http://${window.location.hostname}:8000` : "http://localhost:8000";

  useEffect(() => {
    fetchSystems();
    fetchJobs();
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${apiBase}/api/status`);
        const data = await res.json();
        setStatus(data);
        const cres = await fetch(`${apiBase}/api/custom/status`);
        const cdata = await cres.json();
        setCustomStatus(cdata);
      } catch (e) {}
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  const fetchSystems = async () => {
    try {
      const res = await fetch(`${apiBase}/api/systems`);
      const data = await res.json();
      setSystems(data);
    } catch (e) { console.error("Failed to fetch systems"); }
  };

  const fetchJobs = async () => {
    try {
      const res = await fetch(`${apiBase}/api/custom/jobs`);
      const data = await res.json();
      setJobs(data);
    } catch (e) { console.error("Failed to fetch jobs"); }
  };

  const saveJob = async () => {
    const payload = { ...jobForm, system_id: jobForm.system_id ? Number(jobForm.system_id) : null };
    try {
      const method = editingJobId ? "PUT" : "POST";
      const url = editingJobId ? `${apiBase}/api/custom/jobs/${editingJobId}` : `${apiBase}/api/custom/jobs`;
      await fetch(url, { method, headers: { "Content-Type": "application/json" }, body: JSON.stringify(payload) });
      setIsJobModalOpen(false);
      fetchJobs();
    } catch (e) { alert("Error saving job"); }
  };

  const deleteJob = async (id: number) => {
    if (!confirm("Delete this job?")) return;
    await fetch(`${apiBase}/api/custom/jobs/${id}`, { method: "DELETE" });
    fetchJobs();
  };

  const runJob = async (job: any) => {
    if (!job.system_id) return alert("Please set a target system for this job before running.");
    setRunningJobId(job.id);
    try {
      await fetch(`${apiBase}/api/custom/jobs/${job.id}/run`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ system_id: job.system_id })
      });
    } catch (e) { alert("Error starting job"); setRunningJobId(null); }
  };

  const addStep = () => {
    const stepDef = STEP_TYPES.find(s => s.value === newStepType);
    const newStep: any = { type: newStepType };
    if (stepDef) stepDef.fields.forEach(f => { newStep[f.key] = f.type === "select" ? f.options![0] : ""; });
    setJobForm({ ...jobForm, steps: [...jobForm.steps, newStep] });
  };

  const updateStep = (idx: number, key: string, val: string) => {
    const steps = [...jobForm.steps];
    steps[idx] = { ...steps[idx], [key]: val };
    setJobForm({ ...jobForm, steps });
  };

  const removeStep = (idx: number) => setJobForm({ ...jobForm, steps: jobForm.steps.filter((_, i) => i !== idx) });
  const moveStep = (idx: number, dir: -1 | 1) => {
    const steps = [...jobForm.steps];
    const to = idx + dir;
    if (to < 0 || to >= steps.length) return;
    [steps[idx], steps[to]] = [steps[to], steps[idx]];
    setJobForm({ ...jobForm, steps });
  };

  const openNewJob = () => { setEditingJobId(null); setJobForm({ job_name: "", description: "", system_id: "", steps: [] }); setIsJobModalOpen(true); };
  const openEditJob = (j: any) => { setEditingJobId(j.id); setJobForm({ job_name: j.job_name, description: j.description || "", system_id: j.system_id || "", steps: j.steps || [] }); setIsJobModalOpen(true); };


  const handleFormChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    setFormData({ ...formData, [e.target.name]: e.target.value });
  };

  const handleServerChange = (index: number, field: string, value: any) => {
    const newServers = [...formData.servers];
    if (typeof newServers[index] === 'string') {
        newServers[index] = { hostname: newServers[index] };
    }
    newServers[index][field] = value;
    setFormData({ ...formData, servers: newServers });
  };
  const handleAddServer = () => setFormData({ ...formData, servers: [...formData.servers, { hostname: "", use_custom_auth: false }] });
  const handleRemoveServer = (index: number) => setFormData({ ...formData, servers: formData.servers.filter((_, i) => i !== index) });

  const handleUrlChange = (index: number, value: string) => {
    const newUrls = [...formData.url_checks];
    newUrls[index] = value;
    setFormData({ ...formData, url_checks: newUrls });
  };
  const handleAddUrl = () => setFormData({ ...formData, url_checks: [...formData.url_checks, ""] });
  const handleRemoveUrl = (index: number) => setFormData({ ...formData, url_checks: formData.url_checks.filter((_, i) => i !== index) });

  const saveSystem = async () => {
    try {
      const method = editingId ? "PUT" : "POST";
      const url = editingId ? `${apiBase}/api/systems/${editingId}` : `${apiBase}/api/systems`;
      await fetch(url, {
        method,
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(formData)
      });
      setIsModalOpen(false);
      fetchSystems();
    } catch (e) {
      alert("Error saving system");
    }
  };

  const deleteSystem = async (id: number) => {
    if(!confirm("Are you sure you want to delete this system?")) return;
    try {
      await fetch(`${apiBase}/api/systems/${id}`, { method: "DELETE" });
      fetchSystems();
    } catch(e) {
      alert("Error deleting system");
    }
  };

  const openAddModal = () => {
    setEditingId(null);
    setFormData({
      system_name: "", hostname: "", sid: "", instance_number: "", sap_client: "",
      sap_username: "", sap_password: "", webgui_url: "",
      ssh_auth_method: "password", ssh_username: "", ssh_password: "", ssh_key_path: "", db_host: "",
      servers: [], url_checks: []
    });
    setIsModalOpen(true);
  };

  const openEditModal = (sys: any) => {
    setEditingId(sys.id);
    setFormData({ 
      ...sys,
      servers: sys.servers || [],
      url_checks: sys.url_checks || []
    });
    setIsModalOpen(true);
  };

  const toggleSelection = (id: number) => {
    if (selectedSystems.includes(id)) {
      setSelectedSystems(selectedSystems.filter(sid => sid !== id));
    } else {
      setSelectedSystems([...selectedSystems, id]);
    }
  };

  const executeBulkRun = async () => {
    if (selectedSystems.length === 0) return alert("Select at least one system.");
    try {
      const res = await fetch(`${apiBase}/api/run/bulk`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ system_ids: selectedSystems })
      });
      if (res.ok) {
        setStatus({ ...status, is_running: true, status: "Initializing Batch Run..." });
        setView("execution");
      }
    } catch (e) {
      alert("Error triggering run");
    }
  };

  return (
    <div className={styles.dashboard}>
      <div className={styles.sidebar}>
        <div className={styles.sidebarTitle}>SAP Auto-Monitor</div>
        <div className={`${styles.navItem} ${view === 'inventory' ? styles.active : ''}`} onClick={() => setView('inventory')}>
          System Inventory
        </div>
        <div className={`${styles.navItem} ${view === 'execution' ? styles.active : ''}`} onClick={() => setView('execution')}>
          Batch Execution
        </div>
        <div style={{borderTop:'1px solid rgba(255,255,255,0.1)', margin:'0.5rem 0'}} />
        <div style={{padding:'0.4rem 1rem', fontSize:'0.7rem', color:'rgba(255,255,255,0.4)', textTransform:'uppercase', letterSpacing:'0.08em'}}>Custom Recorder</div>
        <div className={`${styles.navItem} ${view === 'custom' ? styles.active : ''}`} onClick={() => setView('custom')}>
          Custom T-Codes
        </div>
      </div>

      <div className={styles.mainContent}>
        <div className={styles.header}>
          <h1>{view === 'inventory' ? 'Connection Management' : view === 'execution' ? 'Execution Dashboard' : 'Custom T-Code Recorder'}</h1>
          <p>{view === 'inventory' ? 'Manage SAP instances and credentials securely.' : view === 'execution' ? 'Monitor bulk diagnostic executions and download reports.' : 'Define, run and document custom T-code navigation flows for any BASIS or Functional transaction.'}</p>
        </div>

        {view === 'inventory' && (
          <div className={styles.card}>
            <div style={{ display: 'flex', justifyContent: 'space-between', marginBottom: '1rem' }}>
              <h2>Configured Systems ({systems.length})</h2>
              <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={openAddModal}>+ Add System</button>
            </div>
            
            <table className={styles.dataTable}>
              <thead>
                <tr>
                  <th>System Name</th>
                  <th>Hostname</th>
                  <th>SID</th>
                  <th>Client</th>
                  <th>SSH Auth</th>
                  <th>Actions</th>
                </tr>
              </thead>
              <tbody>
                {systems.map(sys => (
                  <tr key={sys.id}>
                    <td>{sys.system_name}</td>
                    <td>{sys.hostname}</td>
                    <td>{sys.sid} ({sys.instance_number})</td>
                    <td>{sys.sap_client}</td>
                    <td>{sys.ssh_auth_method}</td>
                    <td>
                      <button className={`${styles.btn} ${styles.btnOutline}`} style={{ marginRight: '0.5rem', padding: '0.25rem 0.5rem' }} onClick={() => openEditModal(sys)}>Edit</button>
                      <button className={`${styles.btn} ${styles.btnDanger}`} style={{ padding: '0.25rem 0.5rem' }} onClick={() => deleteSystem(sys.id)}>Delete</button>
                    </td>
                  </tr>
                ))}
                {systems.length === 0 && (
                  <tr><td colSpan={6} style={{ textAlign: 'center', padding: '2rem' }}>No systems configured.</td></tr>
                )}
              </tbody>
            </table>
          </div>
        )}

        {view === 'execution' && (
          <div className={styles.formGrid}>
            <div className={styles.card}>
              <h2>Select Targets</h2>
              <table className={styles.dataTable}>
                <thead>
                  <tr>
                    <th><input type="checkbox" onChange={(e) => setSelectedSystems(e.target.checked ? systems.map(s => s.id) : [])} checked={selectedSystems.length === systems.length && systems.length > 0} /></th>
                    <th>System</th>
                    <th>Status</th>
                  </tr>
                </thead>
                <tbody>
                  {systems.map(sys => (
                    <tr key={sys.id}>
                      <td><input type="checkbox" checked={selectedSystems.includes(sys.id)} onChange={() => toggleSelection(sys.id)} /></td>
                      <td>{sys.system_name}</td>
                      <td>
                         {status.results && status.results[sys.id] ? <span style={{color: '#28a745'}}>Processed</span> : '-'}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
              <button className={`${styles.btn} ${styles.btnPrimary}`} style={{ marginTop: '1rem', width: '100%' }} onClick={executeBulkRun} disabled={status.is_running}>
                Execute {selectedSystems.length} Systems
              </button>
            </div>

            <div className={styles.card}>
              <h2>Execution Status</h2>
              <div className={styles.statusPanel}>
                <h3 style={{ margin: '0 0 1rem 0' }}>{status.is_running ? "Running..." : "Idle"}</h3>
                <p><strong>Status:</strong> {status.status}</p>
                {status.total > 0 && (
                  <div style={{ marginTop: '1rem' }}>
                    <p>Progress: {status.progress} / {status.total} systems completed</p>
                    <div style={{ background: '#ddd', height: '10px', borderRadius: '5px', marginTop: '0.5rem', overflow: 'hidden' }}>
                      <div style={{ background: '#0066cc', height: '100%', width: `${(status.progress / status.total) * 100}%`, transition: 'width 0.3s' }}></div>
                    </div>
                  </div>
                )}

                {!status.is_running && status.zip_report && (
                   <div style={{ marginTop: '2rem' }}>
                     <button className={`${styles.btn} ${styles.btnSuccess}`} onClick={() => window.open(`${apiBase}/api/download/zip`)}>
                        Download All Reports (ZIP)
                     </button>
                   </div>
                )}
              </div>
            </div>
          </div>
        )}
        {/* ============================================================
            CUSTOM T-CODE VIEW — Additive. Existing views untouched.
            ============================================================ */}
        {view === 'custom' && (
          <div className={styles.card}>
            {/* Live status bar */}
            {customStatus.is_running && (
              <div className={styles.ctStatusBar}>
                <span className={styles.ctSpinner} />
                <span>{customStatus.status}</span>
              </div>
            )}
            {!customStatus.is_running && customStatus.report_path && (
              <div className={styles.ctSuccessBanner}>
                ✅ Recording complete — {customStatus.steps_executed} steps, {customStatus.screenshots?.length} screenshots captured.
                <a href={`${apiBase}/api/custom/download`} target="_blank" className={`${styles.btn} ${styles.btnSuccess}`} style={{marginLeft:'1rem'}}>⬇ Download Report</a>
              </div>
            )}
            {!customStatus.is_running && customStatus.error && (
              <div className={styles.ctErrorBanner}>⚠️ {customStatus.error}</div>
            )}

            <div style={{display:'flex', justifyContent:'space-between', alignItems:'center', marginBottom:'1.5rem'}}>
              <div style={{fontWeight:600, fontSize:'1.1rem'}}>Job Library</div>
              <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={openNewJob}>+ New Job</button>
            </div>

            {jobs.length === 0 && (
              <div style={{textAlign:'center', padding:'3rem', color:'#999'}}>
                No custom jobs defined yet.<br />
                <button className={`${styles.btn} ${styles.btnOutline}`} style={{marginTop:'1rem'}} onClick={openNewJob}>Create your first job →</button>
              </div>
            )}

            <div className={styles.ctJobGrid}>
              {jobs.map(job => {
                const targetSys = systems.find(s => s.id === job.system_id);
                return (
                  <div key={job.id} className={styles.ctJobCard}>
                    <div className={styles.ctJobHeader}>
                      <span className={styles.ctJobName}>{job.job_name}</span>
                      <span className={styles.ctJobSteps}>{job.steps?.length || 0} steps</span>
                    </div>
                    {job.description && <p className={styles.ctJobDesc}>{job.description}</p>}
                    <div className={styles.ctJobMeta}>
                      🖥️ {targetSys ? `${targetSys.system_name} (${targetSys.sid})` : <span style={{color:'#f59e0b'}}>No system assigned</span>}
                    </div>
                    <div className={styles.ctJobActions}>
                      <button className={`${styles.btn} ${styles.btnOutline}`} style={{fontSize:'0.8rem'}} onClick={() => openEditJob(job)}>✏️ Edit</button>
                      <button className={`${styles.btn} ${styles.btnDanger}`} style={{fontSize:'0.8rem'}} onClick={() => deleteJob(job.id)}>Delete</button>
                      <button
                        className={`${styles.btn} ${styles.btnSuccess}`}
                        style={{fontSize:'0.8rem', marginLeft:'auto'}}
                        onClick={() => runJob(job)}
                        disabled={customStatus.is_running}
                      >
                        {customStatus.is_running && runningJobId === job.id ? '⏳ Running…' : '▶ Run'}
                      </button>
                    </div>
                  </div>
                );
              })}
            </div>
          </div>
        )}

        {/* ---- Job Editor Modal ---- */}
        {isJobModalOpen && (
          <div className={styles.modalOverlay}>
            <div className={styles.modalContent} style={{maxWidth:'780px', width:'95vw', maxHeight:'92vh', overflow:'auto'}}>
              <h2 style={{marginTop:0}}>{editingJobId ? 'Edit Job' : 'New Custom T-Code Job'}</h2>

              <div className={styles.formGrid}>
                <div className={styles.formGroup}>
                  <label>Job Name *</label>
                  <input className={styles.formControl} value={jobForm.job_name} onChange={e => setJobForm({...jobForm, job_name: e.target.value})} placeholder="SE16 MARA Table Browse" />
                </div>
                <div className={styles.formGroup}>
                  <label>Target System</label>
                  <select className={styles.formControl} value={jobForm.system_id} onChange={e => setJobForm({...jobForm, system_id: e.target.value})}>
                    <option value="">— Select System —</option>
                    {systems.map(s => <option key={s.id} value={s.id}>{s.system_name} ({s.sid})</option>)}
                  </select>
                </div>
              </div>
              <div className={styles.formGroup}>
                <label>Description</label>
                <input className={styles.formControl} value={jobForm.description} onChange={e => setJobForm({...jobForm, description: e.target.value})} placeholder="Optional notes about this recording" />
              </div>

              {/* Step Builder */}
              <div style={{marginTop:'1.5rem'}}>
                <div style={{fontWeight:600, marginBottom:'0.75rem', fontSize:'1rem'}}>Steps ({jobForm.steps.length})</div>

                {jobForm.steps.map((step, idx) => {
                  const defn = STEP_TYPES.find(s => s.value === step.type);
                  return (
                    <div key={idx} className={styles.ctStepCard}>
                      <div className={styles.ctStepHeader}>
                        <span className={styles.ctStepNum}>{idx + 1}</span>
                        <span style={{fontWeight:600, flexGrow:1}}>{defn?.label || step.type}</span>
                        <button onClick={() => moveStep(idx, -1)} disabled={idx === 0} style={{background:'none',border:'none',cursor:'pointer',fontSize:'1rem'}}>▲</button>
                        <button onClick={() => moveStep(idx, 1)} disabled={idx === jobForm.steps.length - 1} style={{background:'none',border:'none',cursor:'pointer',fontSize:'1rem'}}>▼</button>
                        <button onClick={() => removeStep(idx)} style={{background:'none',border:'none',cursor:'pointer',color:'#ef4444',fontSize:'1rem'}}>✕</button>
                      </div>
                      {defn && defn.fields.length > 0 && (
                        <div className={styles.ctStepFields}>
                          {defn.fields.map(f => (
                            <div key={f.key} className={styles.formGroup} style={{marginBottom:'0.5rem'}}>
                              <label style={{fontSize:'0.8rem'}}>{f.label}</label>
                              {f.type === 'select' ?
                                <select className={styles.formControl} style={{fontSize:'0.85rem'}} value={step[f.key] || ''} onChange={e => updateStep(idx, f.key, e.target.value)}>
                                  {f.options!.map(o => <option key={o} value={o}>{o}</option>)}
                                </select> :
                                <input className={styles.formControl} style={{fontSize:'0.85rem'}} value={step[f.key] || ''} placeholder={f.placeholder} onChange={e => updateStep(idx, f.key, e.target.value)} />
                              }
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  );
                })}

                {/* Add Step Row */}
                <div className={styles.ctAddStep}>
                  <select className={styles.formControl} style={{flex:1}} value={newStepType} onChange={e => setNewStepType(e.target.value)}>
                    {STEP_TYPES.map(s => <option key={s.value} value={s.value}>{s.label}</option>)}
                  </select>
                  <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={addStep}>+ Add Step</button>
                </div>
              </div>

              <div className={styles.modalActions}>
                <button className={`${styles.btn} ${styles.btnOutline}`} onClick={() => setIsJobModalOpen(false)}>Cancel</button>
                <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={saveJob} disabled={!jobForm.job_name}>Save Job</button>
              </div>
            </div>
          </div>
        )}
      </div>

      {/* Modal */}
      {isModalOpen && (
        <div className={styles.modalOverlay}>
          <div className={styles.modalContent}>
            <h2 style={{marginTop: 0}}>{editingId ? "Edit System" : "Add New System"}</h2>
            <div className={styles.formGrid}>
              <div className={styles.formGroup}>
                <label>System Name</label>
                <input className={styles.formControl} name="system_name" value={formData.system_name} onChange={handleFormChange} placeholder="e.g. PRD North America" />
              </div>
              <div className={styles.formGroup}>
                <label>Hostname</label>
                <input className={styles.formControl} name="hostname" value={formData.hostname} onChange={handleFormChange} />
              </div>
              <div className={styles.formGroup}>
                <label>SID</label>
                <input className={styles.formControl} name="sid" value={formData.sid} onChange={handleFormChange} />
              </div>
              <div className={styles.formGroup}>
                <label>Instance Number</label>
                <input className={styles.formControl} name="instance_number" value={formData.instance_number} onChange={handleFormChange} />
              </div>
            </div>

            <h3 style={{ fontSize: '1rem', marginTop: '1.5rem', borderBottom: '1px solid #eee', paddingBottom: '0.5rem' }}>SAP Credentials</h3>
            <div className={styles.formGrid}>
              <div className={styles.formGroup}>
                <label>Client</label>
                <input className={styles.formControl} name="sap_client" value={formData.sap_client} onChange={handleFormChange} />
              </div>
              <div className={styles.formGroup}>
                <label>SAP Username</label>
                <input className={styles.formControl} name="sap_username" value={formData.sap_username} onChange={handleFormChange} />
              </div>
              <div className={styles.formGroup}>
                <label>SAP Password</label>
                <input type="password" className={styles.formControl} name="sap_password" value={formData.sap_password} onChange={handleFormChange} />
              </div>
              <div className={styles.formGroup}>
                <label>SAP WebGUI URL</label>
                <input className={styles.formControl} name="webgui_url" value={formData.webgui_url} onChange={handleFormChange} placeholder="http://<host>:<port>/sap/bc/gui/sap/its/webgui" />
              </div>
            </div>

            <h3 style={{ fontSize: '1rem', marginTop: '1.5rem', borderBottom: '1px solid #eee', paddingBottom: '0.5rem' }}>SSH & OS Connectivity</h3>
            <div className={styles.formGrid}>
              <div className={styles.formGroup}>
                <label>DB Host (if different from App Host)</label>
                <input className={styles.formControl} name="db_host" value={formData.db_host} onChange={handleFormChange} placeholder="e.g. hdb-server-01" />
              </div>
              <div className={styles.formGroup}>
                <label>Auth Method</label>
                <select className={styles.formControl} name="ssh_auth_method" value={formData.ssh_auth_method} onChange={handleFormChange}>
                  <option value="password">Standard Password</option>
                  <option value="key">SSH Key File</option>
                  <option value="mfa">Citadel MFA / Token</option>
                </select>
              </div>
              <div className={styles.formGroup}>
                <label>SSH Username</label>
                <input className={styles.formControl} name="ssh_username" value={formData.ssh_username} onChange={handleFormChange} />
              </div>
              
              {formData.ssh_auth_method === 'password' && (
                 <div className={styles.formGroup}>
                   <label>SSH Password</label>
                   <input type="password" className={styles.formControl} name="ssh_password" value={formData.ssh_password} onChange={handleFormChange} />
                 </div>
              )}
              {formData.ssh_auth_method === 'key' && (
                 <div className={styles.formGroup}>
                   <label>Absolute Key Path (.pem / id_rsa)</label>
                   <input className={styles.formControl} name="ssh_key_path" value={formData.ssh_key_path} onChange={handleFormChange} placeholder="/home/user/.ssh/id_rsa" />
                 </div>
              )}
              {formData.ssh_auth_method === 'mfa' && (
                 <div className={styles.formGroup}>
                   <label>Citadel Auth Token (Generated)</label>
                   <input type="password" className={styles.formControl} name="ssh_password" value={formData.ssh_password} onChange={handleFormChange} placeholder="Enter token..." />
                   <small style={{color: '#666'}}>Provided token will be injected during interactive prompt.</small>
                 </div>
              )}
            </div>

            <h3 style={{ fontSize: '1rem', marginTop: '1.5rem', borderBottom: '1px solid #eee', paddingBottom: '0.5rem' }}>Additional Endpoints</h3>
            <div className={styles.formGrid}>
              <div className={styles.formGroup}>
                <label>SSH App/Dialog Servers</label>
                {formData.servers.map((server, index) => {
                  const srv = typeof server === 'string' ? { hostname: server, use_custom_auth: false } : server;
                  return (
                  <div key={index} style={{ marginBottom: "1rem", padding: "1rem", border: "1px solid #ccc", borderRadius: "8px" }}>
                    <div style={{ display: "flex", gap: "0.5rem", marginBottom: "0.5rem" }}>
                      <input type="text" className={styles.formControl} value={srv.hostname || ""} onChange={(e) => handleServerChange(index, "hostname", e.target.value)} placeholder="app_server_1" />
                      <button type="button" className={`${styles.btn} ${styles.btnDanger}`} onClick={() => handleRemoveServer(index)} style={{ padding: "0 0.5rem" }}>-</button>
                    </div>
                    
                    <div style={{ display: 'flex', alignItems: 'center', gap: '0.5rem', marginBottom: '1rem', fontSize: '0.9rem' }}>
                      <input type="checkbox" id={`custom_auth_${index}`} checked={srv.use_custom_auth || false} onChange={(e) => handleServerChange(index, "use_custom_auth", e.target.checked)} />
                      <label htmlFor={`custom_auth_${index}`} style={{ margin: 0 }}>Use Custom SSH Credentials for this Server</label>
                    </div>
                    
                    {srv.use_custom_auth && (
                      <div style={{ background: '#f9fafc', padding: '1rem', borderRadius: '4px', border: '1px solid #eee' }}>
                        <div className={styles.formGrid}>
                          <div className={styles.formGroup}>
                            <label>Auth Method</label>
                            <select className={styles.formControl} value={srv.ssh_auth_method || "password"} onChange={(e) => handleServerChange(index, "ssh_auth_method", e.target.value)}>
                              <option value="password">Standard Password</option>
                              <option value="key">SSH Key File</option>
                              <option value="mfa">Citadel MFA / Token</option>
                            </select>
                          </div>
                          <div className={styles.formGroup}>
                            <label>SSH Username</label>
                            <input className={styles.formControl} value={srv.ssh_username || ""} onChange={(e) => handleServerChange(index, "ssh_username", e.target.value)} />
                          </div>
                        </div>
                        
                        {(srv.ssh_auth_method === "password" || !srv.ssh_auth_method) && (
                           <div className={styles.formGroup}>
                             <label>SSH Password</label>
                             <input type="password" className={styles.formControl} value={srv.ssh_password || ""} onChange={(e) => handleServerChange(index, "ssh_password", e.target.value)} />
                           </div>
                        )}
                        {srv.ssh_auth_method === "key" && (
                           <div className={styles.formGroup}>
                             <label>Absolute Key Path (.pem / id_rsa)</label>
                             <input className={styles.formControl} value={srv.ssh_key_path || ""} onChange={(e) => handleServerChange(index, "ssh_key_path", e.target.value)} placeholder="/home/user/.ssh/id_rsa" />
                           </div>
                        )}
                        {srv.ssh_auth_method === "mfa" && (
                           <div className={styles.formGroup}>
                             <label>Citadel Auth Token (Generated)</label>
                             <input type="password" className={styles.formControl} value={srv.ssh_password || ""} onChange={(e) => handleServerChange(index, "ssh_password", e.target.value)} placeholder="Enter token..." />
                           </div>
                        )}
                      </div>
                    )}
                  </div>
                )})}
                <button type="button" className={`${styles.btn} ${styles.btnOutline}`} onClick={handleAddServer} style={{ width: "100%", borderStyle: "dashed" }}>+ Add Server</button>
              </div>

              <div className={styles.formGroup}>
                <label>Health Check URLs</label>
                {formData.url_checks.map((url, index) => (
                  <div key={index} style={{ display: "flex", gap: "0.5rem", marginBottom: "0.5rem" }}>
                    <input type="text" className={styles.formControl} value={url} onChange={(e) => handleUrlChange(index, e.target.value)} placeholder="https://..." />
                    <button type="button" className={`${styles.btn} ${styles.btnDanger}`} onClick={() => handleRemoveUrl(index)} style={{ padding: "0 0.5rem" }}>-</button>
                  </div>
                ))}
                <button type="button" className={`${styles.btn} ${styles.btnOutline}`} onClick={handleAddUrl} style={{ width: "100%", borderStyle: "dashed" }}>+ Add URL</button>
              </div>
            </div>

            <div className={styles.modalActions}>
              <button className={`${styles.btn} ${styles.btnOutline}`} onClick={() => setIsModalOpen(false)}>Cancel</button>
              <button className={`${styles.btn} ${styles.btnPrimary}`} onClick={saveSystem}>Save Configuration</button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
