import sqlite3
import os
import json

# In Docker the DB lives in /data (a mounted volume).
# For local dev, fall back to the directory next to this file.
DB_FILE = os.environ.get("DB_PATH", os.path.join(os.path.dirname(__file__), "systems.db"))

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS systems (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            system_name TEXT NOT NULL,
            hostname TEXT NOT NULL,
            sid TEXT NOT NULL,
            instance_number TEXT NOT NULL,
            sap_client TEXT NOT NULL,
            sap_username TEXT NOT NULL,
            sap_password TEXT,
            webgui_url TEXT,
            ssh_auth_method TEXT DEFAULT 'password', 
            ssh_username TEXT,
            ssh_password TEXT,
            ssh_key_path TEXT,
            db_host TEXT,
            servers TEXT,
            url_checks TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    # === ADDITIVE: Custom T-Code Jobs table ===
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS custom_tcode_jobs (
            id          INTEGER PRIMARY KEY AUTOINCREMENT,
            job_name    TEXT NOT NULL,
            description TEXT,
            system_id   INTEGER,
            steps       TEXT NOT NULL DEFAULT '[]',
            created_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            updated_at  TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    ''')
    conn.commit()
    conn.close()

def get_all_systems():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM systems ORDER BY system_name ASC")
    rows = cursor.fetchall()
    conn.close()
    
    systems = []
    for row in rows:
        d = dict(row)
        d['servers'] = json.loads(d['servers']) if d['servers'] else []
        d['url_checks'] = json.loads(d['url_checks']) if d['url_checks'] else []
        systems.append(d)
    return systems

def get_system(system_id: int):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM systems WHERE id = ?", (system_id,))
    row = cursor.fetchone()
    conn.close()
    
    if row:
        d = dict(row)
        d['servers'] = json.loads(d['servers']) if d['servers'] else []
        d['url_checks'] = json.loads(d['url_checks']) if d['url_checks'] else []
        return d
    return None

def add_system(data: dict):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    servers = json.dumps(data.get('servers', []))
    url_checks = json.dumps(data.get('url_checks', []))
    
    cursor.execute('''
        INSERT INTO systems (
            system_name, hostname, sid, instance_number, sap_client, 
            sap_username, sap_password, webgui_url, ssh_auth_method, 
            ssh_username, ssh_password, ssh_key_path, db_host, servers, url_checks
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        data.get('system_name', data.get('sid', 'Unknown')),
        data.get('hostname', ''),
        data.get('sid', ''),
        data.get('instance_number', ''),
        data.get('sap_client', ''),
        data.get('sap_username', ''),
        data.get('sap_password', ''),
        data.get('webgui_url', ''),
        data.get('ssh_auth_method', 'password'),
        data.get('ssh_username', ''),
        data.get('ssh_password', ''),
        data.get('ssh_key_path', ''),
        data.get('db_host', ''),
        servers,
        url_checks
    ))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id

def update_system(system_id: int, data: dict):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    
    servers = json.dumps(data.get('servers', []))
    url_checks = json.dumps(data.get('url_checks', []))
    
    cursor.execute('''
        UPDATE systems SET
            system_name = ?, hostname = ?, sid = ?, instance_number = ?, sap_client = ?,
            sap_username = ?, sap_password = ?, webgui_url = ?, ssh_auth_method = ?,
            ssh_username = ?, ssh_password = ?, ssh_key_path = ?, db_host = ?,
            servers = ?, url_checks = ?
        WHERE id = ?
    ''', (
        data.get('system_name'), data.get('hostname'), data.get('sid'), data.get('instance_number'),
        data.get('sap_client'), data.get('sap_username'), data.get('sap_password'),
        data.get('webgui_url'), data.get('ssh_auth_method', 'password'), data.get('ssh_username'),
        data.get('ssh_password'), data.get('ssh_key_path'), data.get('db_host'),
        servers, url_checks, system_id
    ))
    conn.commit()
    conn.close()
    return True

def delete_system(system_id: int):
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM systems WHERE id = ?", (system_id,))
    conn.commit()
    conn.close()
    return True

# Initialize DB on load
init_db()

# =============================================================================
# CUSTOM T-CODE JOBS — Additive CRUD functions (new table, existing untouched)
# =============================================================================

def get_all_jobs():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM custom_tcode_jobs ORDER BY updated_at DESC")
    rows = cursor.fetchall()
    conn.close()
    jobs = []
    for row in rows:
        d = dict(row)
        d['steps'] = json.loads(d['steps']) if d['steps'] else []
        jobs.append(d)
    return jobs

def get_job(job_id: int):
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM custom_tcode_jobs WHERE id = ?", (job_id,))
    row = cursor.fetchone()
    conn.close()
    if row:
        d = dict(row)
        d['steps'] = json.loads(d['steps']) if d['steps'] else []
        return d
    return None

def add_job(data: dict) -> int:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    steps_json = json.dumps(data.get('steps', []))
    cursor.execute('''
        INSERT INTO custom_tcode_jobs (job_name, description, system_id, steps)
        VALUES (?, ?, ?, ?)
    ''', (
        data.get('job_name', 'Unnamed Job'),
        data.get('description', ''),
        data.get('system_id'),
        steps_json
    ))
    conn.commit()
    new_id = cursor.lastrowid
    conn.close()
    return new_id

def update_job(job_id: int, data: dict) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    steps_json = json.dumps(data.get('steps', []))
    cursor.execute('''
        UPDATE custom_tcode_jobs SET
            job_name = ?, description = ?, system_id = ?, steps = ?,
            updated_at = CURRENT_TIMESTAMP
        WHERE id = ?
    ''', (
        data.get('job_name'),
        data.get('description', ''),
        data.get('system_id'),
        steps_json,
        job_id
    ))
    conn.commit()
    conn.close()
    return True

def delete_job(job_id: int) -> bool:
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute("DELETE FROM custom_tcode_jobs WHERE id = ?", (job_id,))
    conn.commit()
    conn.close()
    return True
