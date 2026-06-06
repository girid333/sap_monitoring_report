import sqlite3
import os
import json

DB_FILE = os.path.join(os.path.dirname(__file__), "systems.db")

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
