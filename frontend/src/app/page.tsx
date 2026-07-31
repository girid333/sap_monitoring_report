"use client";

import { useState, useEffect } from "react";
import styles from "./page.module.css";

export default function Home() {
  const [view, setView] = useState("inventory");
  const [systems, setSystems] = useState<any[]>([]);
  const [selectedSystems, setSelectedSystems] = useState<number[]>([]);
  
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
    const interval = setInterval(async () => {
      try {
        const res = await fetch(`${apiBase}/api/status`);
        const data = await res.json();
        setStatus(data);
      } catch (e) {}
    }, 2000);
    return () => clearInterval(interval);
  }, []);

  const fetchSystems = async () => {
    try {
      const res = await fetch(`${apiBase}/api/systems`);
      const data = await res.json();
      setSystems(data);
    } catch (e) {
      console.error("Failed to fetch systems");
    }
  };

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
      </div>

      <div className={styles.mainContent}>
        <div className={styles.header}>
          <h1>{view === 'inventory' ? 'Connection Management' : 'Execution Dashboard'}</h1>
          <p>{view === 'inventory' ? 'Manage SAP instances and credentials securely.' : 'Monitor bulk diagnostic executions and download reports.'}</p>
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
