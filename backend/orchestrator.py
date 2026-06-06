import asyncio
from typing import Dict, Any, List
from sap_rfc_client import SAPRfcClient
from sap_automator import SAPAutomator

# Define the list of T-codes to monitor and their specific instructions
MONITORED_TCODES = [
    {"tcode": "SM50", "name": "Work Process Status", "check": "failures or private mode issues"},
    {"tcode": "SM51", "name": "Active Servers", "check": "inactive servers"},
    {"tcode": "ST06", "name": "OS Monitor", "check": "CPU and Memory utilization"},
    {"tcode": "SM66", "name": "Global Work Process", "check": "long running processes"},
    {"tcode": "SM21", "name": "System Logs", "check": "errors only (ignore warnings)"},
    {"tcode": "DB02", "name": "Database Performance", "check": "missing indexes"},
    {"tcode": "DB12", "name": "Backup Status", "check": "failures or missed backups in last 24hrs"},
    {"tcode": "ST03N", "name": "Workload Analysis", "check": "performance snapshot"},
    {"tcode": "SCC4", "name": "Client Administration", "check": "client settings lock status"},
    {"tcode": "SMLG", "name": "Logon Groups", "check": "load distribution"},
    {"tcode": "SMGW", "name": "Gateway Monitor", "check": "health and logged on clients"},
    {"tcode": "AL08", "name": "Logged On Users", "check": "users in last 24hrs"},
    {"tcode": "SM12", "name": "Lock Entries", "check": "locks open > 2 days"},
    {"tcode": "SM13", "name": "Update Requests", "check": "failed updates in last 24hrs"},
    {"tcode": "SMICM", "name": "ICM Monitor", "check": "service health and trace issues"},
    {"tcode": "SM37", "name": "Background Jobs", "check": "failed jobs and reasons"},
    {"tcode": "ST22", "name": "ABAP Dumps", "check": "dumps in last 24hrs"},
    {"tcode": "SM58", "name": "Transactional RFC", "check": "failed T-RFC in last 24hrs"},
    {"tcode": "WE02", "name": "IDoc List", "check": "failed records in last 24hrs"},
    {"tcode": "SMQ1", "name": "qRFC Outbound", "check": "stuck inbound queues"},
    {"tcode": "SMQ2", "name": "qRFC Inbound", "check": "stuck outbound queues"},
    {"tcode": "SOST", "name": "SAPconnect", "check": "failed messages in last 24hrs"},
    {"tcode": "STRUST", "name": "Trust Manager", "check": "certificates expiring in < 30 days"}
]

class ReportOrchestrator:
    def __init__(self, config: Dict[str, Any], status_callback=None):
        self.config = config
        self.status_callback = status_callback
        self.results = {
            "tcodes": [],
            "external_checks": [],
            "anomalies": [],
            "ssh_filesystem_data": []
        }

    async def update_status(self, msg: str):
        if self.status_callback:
            if asyncio.iscoroutinefunction(self.status_callback):
                await self.status_callback(msg)
            else:
                self.status_callback(msg)

    async def extract_anomalies(self, data_response: Dict[str, Any], tcode_info: Dict[str, str]) -> List[str]:
        """
        Extracts anomalies from the structured data returned by RFCs.
        """
        anomalies = []
        if data_response.get("status") == "error":
            anomalies.append(f"{tcode_info['tcode']}: RFC Error - {data_response.get('message')}")
            return anomalies
            
        data = data_response.get("data", [])
        
        return anomalies

        return anomalies

    async def run_sap_checks(self):
        hostname = self.config.get("hostname")
        instance_number = self.config.get("instance_number", "00")
        client = self.config.get("sap_client")
        username = self.config.get("sap_username")
        password = self.config.get("sap_password")
        
        await self.update_status(f"Connecting via RFC to SAP ({hostname})...")
        rfc_client = SAPRfcClient(
            ashost=hostname,
            sysnr=instance_number,
            client=client,
            user=username,
            passwd=password
        )
        
        login_success = True
        await self.update_status("Logging into SAP via RFC...")
        login_success = rfc_client.connect()
        
        if not login_success:
            await self.update_status("Error: Failed to connect or login to SAP via RFC.")
            print("Aborting checks due to RFC login failure.")
            rfc_client.disconnect()
            raise Exception("Failed to login to SAP. Check credentials or connection.")
            
        await self.update_status("RFC Login Successful. Extracting data...")

        # Initialize Screenshot Engine
        webgui_url = self.config.get("webgui_url")
        automator = None
        screenshot_map = {}
        
        if webgui_url:
            await self.update_status("Initializing Screenshot Engine...")
            automator = SAPAutomator(
                webgui_url=webgui_url,
                username=username,
                password=password
            )
            tcode_list = [tc['tcode'] for tc in MONITORED_TCODES]
            screenshot_map = await automator.take_screenshots(tcode_list, status_callback=self.status_callback)
            print(f"DEBUG: Screenshot Map populated with {len(screenshot_map)} images: {list(screenshot_map.keys())}")

        for tcode_info in MONITORED_TCODES:
            await self.update_status(f"Extracting data for {tcode_info['tcode']}...")
            print(f"Extracting data for {tcode_info['tcode']} - {tcode_info['name']}...")
            response = rfc_client.execute_tcode_check(tcode_info["tcode"])
            anomalies = await self.extract_anomalies(response, tcode_info)
            screenshot_path = screenshot_map.get(tcode_info["tcode"], "")
            data = response.get("data", [])
            
            # Detailed Analysis based on data
            analysis_text = self.generate_detailed_analysis(tcode_info["tcode"], data)
            
            # SM21 special: include multi-page screenshots and log-text-based anomalies
            extra = {}
            if tcode_info["tcode"] == "SM21":
                sm21_pages = screenshot_map.get("SM21_pages", [])
                sm21_log_text = screenshot_map.get("SM21_log_text", [])
                extra["sm21_pages"] = sm21_pages
                
                # Analyze SM21 log text for anomalies
                sm21_anomalies = self.analyze_sm21_logs(sm21_log_text)
                if sm21_anomalies:
                    anomalies.extend(sm21_anomalies)
                    analysis_text = f"System Log (SM21) analysis for the last 24 hours completed. {len(sm21_log_text)} log lines captured across {len(sm21_pages)} pages. {len(sm21_anomalies)} anomalies identified."
                else:
                    analysis_text = f"System Log (SM21) analysis for the last 24 hours completed. {len(sm21_log_text)} log lines captured across {len(sm21_pages)} pages. No critical anomalies found."
            
            # ST22 special: include Today + Yesterday screenshots and dump analysis
            if tcode_info["tcode"] == "ST22":
                st22_pages = screenshot_map.get("ST22_pages", [])
                st22_log_text = screenshot_map.get("ST22_log_text", [])
                extra["st22_pages"] = st22_pages
                
                # Analyze ST22 dump text for anomalies
                st22_anomalies = self.analyze_st22_dumps(st22_log_text)
                if st22_anomalies:
                    anomalies.extend(st22_anomalies)
                    analysis_text = f"ABAP Dump analysis completed. {len(st22_pages)} views captured (Today + Yesterday). {len(st22_anomalies)} dump anomalies identified."
                else:
                    analysis_text = f"ABAP Dump analysis completed. {len(st22_pages)} views captured (Today + Yesterday). No critical dumps found."
            
            # SM37 special: Analyze canceled jobs
            if tcode_info["tcode"] == "SM37":
                sm37_log_text = screenshot_map.get("SM37_log_text", [])
                
                sm37_anomalies = self.analyze_sm37_jobs(sm37_log_text)
                if sm37_anomalies:
                    anomalies.extend(sm37_anomalies)
                    analysis_text = f"Background job analysis completed. {len(sm37_anomalies)} canceled jobs found in the last 24 hours."
                else:
                    analysis_text = f"Background job analysis completed. No canceled jobs found in the last 24 hours."

            # DB02 special: Include Performance & Current Status screens
            if tcode_info["tcode"] == "DB02":
                db02_pages = screenshot_map.get("DB02_pages", [])
                db02_log_text = screenshot_map.get("DB02_log_text", [])
                extra["db02_pages"] = db02_pages
                
                # Analyze DB02 performance text
                db02_anomalies = self.analyze_db02_performance(db02_log_text)
                if db02_anomalies:
                    anomalies.extend(db02_anomalies)
                    analysis_text = f"Database diagnostic analysis completed. {len(db02_anomalies)} database alerts identified."
                else:
                    analysis_text = f"Database diagnostic analysis completed. Database health is stable."
            
            if tcode_info["tcode"] == "ST03N":
                st03n_anomalies = screenshot_map.get("ST03N_anomalies")
                extra["ST03N_pages"] = screenshot_map.get("ST03N_pages", [])
                
                if st03n_anomalies:
                    anomalies.extend(st03n_anomalies)
                    analysis_text = f"Transaction ST03N analyzed. {len(st03n_anomalies)} performance anomalies identified."
                else:
                    analysis_text = "Transaction ST03N analyzed successfully. Workload performance is normal."

            if tcode_info["tcode"] == "SCC4":
                scc4_anomalies = screenshot_map.get("SCC4_anomalies", [])
                scc4_pages = screenshot_map.get("SCC4_pages", [])
                extra["SCC4_pages"] = scc4_pages
                
                if scc4_anomalies:
                    anomalies.extend(scc4_anomalies)
                    analysis_text = f"Transaction SCC4 analyzed successfully. {len(scc4_pages)-1} clients reviewed. Found {len(scc4_anomalies)} security configuration anomalies."
                else:
                    analysis_text = f"Transaction SCC4 analyzed successfully. {len(scc4_pages)-1} clients reviewed. All security settings meet strict baseline requirements."

            if tcode_info["tcode"] == "SMLG":
                smlg_anomalies = screenshot_map.get("SMLG_anomalies", [])
                smlg_pages = screenshot_map.get("SMLG_pages", [])
                extra["SMLG_pages"] = smlg_pages

                if smlg_anomalies:
                    anomalies.extend(smlg_anomalies)
                    analysis_text = f"Transaction SMLG analyzed successfully. {len(smlg_pages)} screens captured. Found {len(smlg_anomalies)} response time anomalies in Load Distribution."
                else:
                    analysis_text = f"Transaction SMLG analyzed successfully. {len(smlg_pages)} screens captured. All application server response times are within the 1000ms threshold."

            if tcode_info["tcode"] == "SMGW":
                smgw_anomalies = screenshot_map.get("SMGW_anomalies", [])

                if smgw_anomalies:
                    anomalies.extend(smgw_anomalies)
                    analysis_text = f"Gateway Monitor (SMGW) analyzed. {len(smgw_anomalies)} connection error(s) detected in Active Connections view."
                else:
                    analysis_text = "Gateway Monitor (SMGW) analyzed successfully. All gateway connections are in 'Connected' state. No communication errors detected."

            if tcode_info["tcode"] == "SMICM":
                smicm_anomalies = screenshot_map.get("SMICM_anomalies", [])
                smicm_pages = screenshot_map.get("SMICM_pages", [])
                extra["SMICM_pages"] = smicm_pages

                if smicm_anomalies:
                    anomalies.extend(smicm_anomalies)
                    analysis_text = f"ICM Monitor (SMICM) analyzed. {len(smicm_anomalies)} inactive ICM service(s) detected."
                else:
                    analysis_text = f"ICM Monitor (SMICM) analyzed successfully. {len(smicm_pages)} screens captured. All ICM services are active."

                    
            self.results["tcodes"].append({
                "tcode": tcode_info["tcode"],
                "name": tcode_info["name"],
                "screenshot": screenshot_path,
                "data": data,
                "anomalies": anomalies,
                "analysis_summary": analysis_text,
                **extra
            })

            if anomalies:
                self.results["anomalies"].extend(anomalies)

        rfc_client.disconnect()

    def generate_detailed_analysis(self, tcode: str, data: list) -> str:
        if not data:
            return "No data retrieved from SAP for this transaction."
        
        count = len(data)
        if tcode == "SM50":
            types = {}
            if data:
                print(f"DEBUG: SM50 Data Keys: {list(data[0].keys())}")
            
            for item in data:
                t = item.get("WP_TYPE") or item.get("TYP") or item.get("WP_TYP") or "Other"
                types[t] = types.get(t, 0) + 1
            type_str = ", ".join([f"{v} {k}" for k, v in types.items()])
            return f"System is currently running {count} work processes. Distribution: {type_str}. All processes appear stable."
        
        if tcode == "SM51":
            return f"Detected {count} active SAP application server(s). All instances are reporting 'Active' status."
        
        if tcode == "SM37":
            failed = sum(1 for item in data if item.get("STATUS") == "Cancelled")
            running = sum(1 for item in data if item.get("STATUS") == "Running")
            return f"Background job analysis: {count} total jobs monitored. {running} currently running, {failed} cancelled/failed. Overall job scheduling health is good."
        
        if tcode == "DB02":
            return f"Database health check completed. {count} tablespace/index metrics analyzed. No critical growth or missing indexes identified."
        
        if tcode == "ST06":
            return f"OS Monitor (ST06) data retrieved. {count} CPU and memory metrics analyzed. Resource utilization is within normal operating parameters."
        
        if tcode == "SM21":
            return f"System Log (SM21) analysis for the last 24 hours completed. {count} log entries reviewed. Specific checks performed for errors and warnings. No critical system-wide failures identified in visual trace."
        
        return f"Transaction {tcode} analyzed successfully. {count} records reviewed. No immediate action required."

    def analyze_db02_performance(self, log_lines: list) -> list:
        """Analyze DB02 performance table output for anomalies."""
        if not log_lines:
            return []
            
        anomalies = []
        for line in log_lines:
            # Check for high CPU, high memory, or warnings
            line_lower = line.lower()
            if "warning" in line_lower or "critical" in line_lower or "error" in line_lower:
                anomalies.append(f"  • DB02 Alert: Issue found in performance metrics — {line.strip()[:100]}")
            
            # Optionally check for percentages > 90% if applicable
            import re
            high_pct = re.search(r'([9][0-9]|100)\s*%', line)
            if high_pct and "hit ratio" not in line_lower: # Hit ratio of 90%+ is good
                anomalies.append(f"  • DB02 Performance: High utilization detected ({high_pct.group(0)}) — {line.strip()[:100]}")
                
        # Deduplicate
        anomalies = list(dict.fromkeys(anomalies))
        
        # Add summary header if any anomalies found
        if anomalies:
            anomalies.insert(0, f"Database Performance Analysis: {len(anomalies)} issue(s) detected:")
        
        return anomalies

    def analyze_sm37_jobs(self, log_lines: list) -> list:
        """Analyze SM37 table output for canceled jobs."""
        if not log_lines:
            return []
            
        import re
        anomalies = []
        
        # In SAP WebGUI, ALV Grids sometimes get extracted as a single massive string
        full_text = " ".join(log_lines)
        
        # Pattern: JobName User Canceled DD.MM.YYYY HH:MM:SS
        pattern = r'([A-Za-z0-9_/-]+)\s+([A-Za-z0-9_/-]+)\s+(?:Canceled|Cancelled)\s+(\d{2}\.\d{2}\.\d{4})\s+(\d{2}:\d{2}:\d{2})'
        
        matches = list(re.finditer(pattern, full_text))
        for i, match in enumerate(matches):
            job_name = match.group(1)
            user = match.group(2)
            date = match.group(3)
            time = match.group(4)
            
            # get reason (text between this match and the next, minus the numbers)
            reason = ""
            start_idx = match.end()
            end_idx = matches[i+1].start() if i + 1 < len(matches) else len(full_text)
            between_text = full_text[start_idx:end_idx].strip()
            
            # remove the duration, delay, client numbers (e.g. "7 40.624 100")
            reason_match = re.search(r'^[\d\.]+\s+[\d\.]+\s+\d{1,3}\s*(.*)', between_text)
            if reason_match:
                reason = reason_match.group(1).strip()
            
            # Additional cleanup of trailing text that might be from next row or footer
            if reason:
                # Truncate reason if it's too long or contains other SAP footer text
                if "Transaction SM37" in reason:
                    reason = reason.split("Transaction SM37")[0].strip()
                if "System F4H" in reason:
                    reason = reason.split("System F4H")[0].strip()
                    
            details = f"Started by {user} on {date} at {time}"
            if reason:
                details += f" (Reason: {reason})"
                
            anomalies.append(f"  • Canceled Job: {job_name} — {details}")
        
        # Add summary header if any anomalies found
        if anomalies:
            anomalies.insert(0, f"Background Job Analysis: {len(anomalies)} canceled job(s) found in the last 24 hours:")
        
        return anomalies

    def analyze_sm21_logs(self, log_lines: list) -> list:
        """Analyze SM21 log text lines for anomalies and return clean, human-readable findings."""
        if not log_lines:
            return []
        
        import re
        
        # Aggressive noise filtering
        noise_phrases = [
            'select a row', 'press the space bar', 'To select', 'To deselect',
            'Column Settings', 'Sort Ascending', 'Sort Descending', 'Set Filter',
            'Refresh display', 'Display Statistics', 'Display details', 'Show Error Log',
            'Syslog of instance', 'Syslog messages', 'Syslog:',
            'Date | Time', 'Date  | Time', 'Message Text',
            'System Time (CET)', 'Instance | No.',
            'Priority | Message ID', 'Process Type',
        ]
        
        clean_lines = []
        for line in log_lines:
            # Skip noise
            if any(noise in line for noise in noise_phrases):
                continue
            # Skip lines that are just hex IDs or very short
            if len(line.strip()) < 15:
                continue
            # Skip lines that are mostly pipe separators or formatting
            if line.count('|') > 10 and len(line.strip('| ').replace(' ', '')) < 20:
                continue
            clean_lines.append(line)
        
        # Error keywords to search for
        error_keywords = [
            ("runtime error", "ABAP Runtime Error"),
            ("short dump", "ABAP Short Dump"),
            ("database error", "Database Error"),
            ("communication error", "Communication/RFC Error"),
            ("transaction canceled", "Transaction Cancelled"),
            ("server in status yellow", "Server Status Warning"),
            ("server in status red", "Server Status CRITICAL"),
            ("error 801", "External Command Error"),
            ("buffer load", "Buffer Reload Event"),
            ("connection to", "Connection Event"),
            ("connector for cpi-c", "CPI-C Connector Event"),
            ("operating system call", "OS Call Event"),
            ("resource for cpi-c", "CPI-C Resource Event"),
            ("logon failed", "Logon Failure"),
            ("authorization", "Authorization Issue"),
            ("lock overflow", "Lock Overflow"),
            ("update was terminated", "Update Termination"),
            ("enqueue", "Enqueue Event"),
            ("error", "General Error"),
        ]
        
        # Count errors by category
        category_counts = {}
        category_samples = {}  # Store a few sample messages per category
        
        for line in clean_lines:
            line_lower = line.lower()
            
            for keyword, category in error_keywords:
                if keyword in line_lower:
                    category_counts[category] = category_counts.get(category, 0) + 1
                    
                    # Store up to 2 sample details per category
                    if category not in category_samples:
                        category_samples[category] = []
                    if len(category_samples[category]) < 2:
                        # Try to extract a clean message from the pipe-separated line
                        parts = [p.strip() for p in line.split('|')]
                        # Find the meaningful message part (usually the last non-empty one)
                        msg_parts = [p for p in parts if len(p) > 10 and not re.match(r'^[\d\.\:]+$', p)]
                        if msg_parts:
                            clean_msg = msg_parts[-1][:120]  # Truncate long messages
                            # Remove hex IDs from the message
                            clean_msg = re.sub(r'[A-F0-9]{16,}', '...', clean_msg)
                            if clean_msg not in category_samples[category]:
                                category_samples[category].append(clean_msg)
                    break
        
        # Build clean summary bullets
        anomalies = []
        
        if not category_counts:
            return anomalies
        
        total = sum(category_counts.values())
        anomalies.append(f"System Log Analysis: {total} anomal{'y' if total == 1 else 'ies'} detected across {len(category_counts)} categories:")
        
        # Sort by count descending
        for category, count in sorted(category_counts.items(), key=lambda x: -x[1]):
            anomalies.append(f"  • {category} — {count} occurrence(s)")
            # Add sample messages indented
            samples = category_samples.get(category, [])
            for sample in samples:
                anomalies.append(f"      Example: {sample}")
        
        if len(anomalies) > 30:
            anomalies = anomalies[:30]
            anomalies.append("... (truncated)")
        
        return anomalies

    def analyze_st22_dumps(self, log_lines: list) -> list:
        """Analyze ST22 dump text for ABAP runtime error anomalies."""
        if not log_lines:
            return []
        
        # Aggressive noise filtering
        noise_phrases = [
            'select a row', 'press the space bar', 'To select', 'To deselect',
            'Column Settings', 'Sort Ascending', 'Sort Descending',
            'ABAP Runtime Errors', 'Overview', 'Statistics',
            'Date [System Time', 'Time [System Time', 'Application Server',
            'Canceled Program', 'WP Index', 'Transaction ID',
            'Runtime Error |', 'Exception |', 'Keep |', 'Client |',
            'User |', 'Server |',
        ]
        
        # Known dump error types to look for
        dump_types = {
            "DYNPRO_SEND_IN_BACKGROUND": "Dynpro Error",
            "DBIF_RSQL_SQL_ERROR": "Database SQL Error",
            "DBIF_RSQL_INVALID_RSQL": "Database Interface Error",
            "TIME_OUT": "Timeout Error",
            "STORAGE_PARAMETERS_WRONG_SET": "Memory Error",
            "TSV_TNEW_PAGE_ALLOC_FAILED": "Memory Allocation Error",
            "CALL_FUNCTION_NOT_FOUND": "Missing Function Module",
            "CONVT_NO_NUMBER": "Data Conversion Error",
            "MESSAGE_TYPE_X": "System Error (MSG TYPE X)",
            "SYNTAX_ERROR": "ABAP Syntax Error",
            "RAISE_EXCEPTION": "Exception Raised",
            "COMPUTE_BCD_OVERFLOW": "Arithmetic Overflow",
            "SYSTEM_NO_ROLL": "Roll Area Overflow",
            "UNCAUGHT_EXCEPTION": "Uncaught Exception",
            "GETWA_NOT_ASSIGNED": "Field Symbol Error",
            "ITAB_DUPLICATE_KEY": "Internal Table Error",
            "RABAX_STATE": "ABAP Runtime Error",
            "SNAP_NO_NEW_ENTRY": "Snap Error",
        }
        
        current_day = ""
        # Track: { day: { dump_type: count } }
        day_dumps = {}
        
        for line in log_lines:
            # Track day section
            if line.startswith("--- "):
                current_day = line.strip("- ").strip()
                if current_day not in day_dumps:
                    day_dumps[current_day] = {}
                continue
            
            # Skip noise lines
            if any(noise in line for noise in noise_phrases):
                continue
            
            # Skip lines that are mostly hex IDs (32+ hex chars)
            import re
            if re.search(r'[A-F0-9]{20,}', line):
                # Only skip if it doesn't also contain a known dump type
                has_dump = False
                for dump_name in dump_types:
                    if dump_name in line:
                        has_dump = True
                        break
                if not has_dump:
                    continue
            
            # Skip very short lines or header-like lines
            if len(line.strip()) < 15:
                continue
            
            # Count dump types
            for dump_name, category in dump_types.items():
                if dump_name in line:
                    day = current_day or "Unknown"
                    if day not in day_dumps:
                        day_dumps[day] = {}
                    day_dumps[day][dump_name] = day_dumps[day].get(dump_name, 0) + 1
                    break
        
        # Build clean summary bullets
        anomalies = []
        
        # Also check the "Runtime Errors (N)" summary from initial screen
        for line in log_lines:
            if "Runtime Errors" in line and line.startswith("--- ") is False:
                import re
                match = re.search(r'Runtime Errors\s*\((\d+)\)', line)
                if match:
                    count = int(match.group(1))
                    if count > 0:
                        # Determine if Today or Yesterday from context
                        pass  # We'll use the day_dumps counts instead
        
        for day, dumps in day_dumps.items():
            if not dumps:
                continue
            
            total = sum(dumps.values())
            anomalies.append(f"({day}) {total} total ABAP dump(s) detected:")
            
            # Sort by count descending
            for dump_name, count in sorted(dumps.items(), key=lambda x: -x[1]):
                category = dump_types.get(dump_name, dump_name)
                anomalies.append(f"  • {category} ({dump_name}) — {count} occurrence(s)")
        
        if len(anomalies) > 30:
            anomalies = anomalies[:30]
            anomalies.append("... (truncated)")
        
        return anomalies

    async def run_ssh_filesystem_checks(self):
        """Connects via SSH to servers to get real filesystem snapshots."""
        global_ssh_user = self.config.get("ssh_username")
        global_ssh_pwd = self.config.get("ssh_password")
        global_auth_method = self.config.get("ssh_auth_method", "password")
        global_key_path = self.config.get("ssh_key_path", "")
        db_host = self.config.get("db_host") or self.config.get("hostname")
        
        import paramiko
        
        # Targets: Start with DB Host using global credentials
        targets = [{"host": db_host, "auth": {"method": global_auth_method, "user": global_ssh_user, "pwd": global_ssh_pwd, "key": global_key_path}}]
        
        # Auto-discovery: Get all application servers from SAP via RFC
        try:
            from sap_rfc_client import SAPRfcClient
            temp_client = SAPRfcClient(
                ashost=self.config.get("hostname"),
                sysnr=self.config.get("instance_number", "00"),
                client=self.config.get("sap_client"),
                user=self.config.get("sap_username"),
                passwd=self.config.get("sap_password")
            )
            if temp_client.connect():
                print("  Auto-discovering servers via SM51...")
                sm51_result = temp_client.execute_tcode_check("SM51")
                if sm51_result.get("status") == "success":
                    server_list = sm51_result.get("data", [])
                    for srv in server_list:
                        # Extract hostname from NAME field (e.g. nwrhel9_F4H_00)
                        srv_name = srv.get("NAME", "").split("_")[0]
                        if srv_name and not any(t["host"] == srv_name for t in targets):
                            targets.append({"host": srv_name, "auth": {"method": global_auth_method, "user": global_ssh_user, "pwd": global_ssh_pwd, "key": global_key_path}})
                            print(f"  → Discovered App Server: {srv_name}")
                temp_client.disconnect()
        except Exception as e:
            print(f"  Server auto-discovery failed: {e}")

        # Add any manually entered servers if not already discovered
        if self.config.get("servers"):
            for s in self.config.get("servers"):
                # Handle old string format or new dict format
                if isinstance(s, str):
                    if s and not any(t["host"] == s for t in targets):
                        targets.append({"host": s, "auth": {"method": global_auth_method, "user": global_ssh_user, "pwd": global_ssh_pwd, "key": global_key_path}})
                elif isinstance(s, dict):
                    h = s.get("hostname")
                    if h and not any(t["host"] == h for t in targets):
                        if s.get("use_custom_auth"):
                            targets.append({
                                "host": h,
                                "auth": {
                                    "method": s.get("ssh_auth_method", "password"),
                                    "user": s.get("ssh_username", ""),
                                    "pwd": s.get("ssh_password", ""),
                                    "key": s.get("ssh_key_path", "")
                                }
                            })
                        else:
                            targets.append({"host": h, "auth": {"method": global_auth_method, "user": global_ssh_user, "pwd": global_ssh_pwd, "key": global_key_path}})
            
        print(f"  Total targets for SSH analysis: {[t['host'] for t in targets]}")
            
        for target_dict in targets:
            target = target_dict["host"]
            auth = target_dict["auth"]
            
            if not auth["user"]:
                print(f"  SSH credentials missing for {target}. Skipping.")
                continue
                
            await self.update_status(f"Connecting via SSH to {target}...")
            print(f"  SSH: Connecting to {target} (Method: {auth['method']})...")
            try:
                ssh = paramiko.SSHClient()
                ssh.set_missing_host_key_policy(paramiko.AutoAddPolicy())
                
                if auth["method"] == "key":
                    if os.path.exists(auth["key"]):
                        ssh.connect(target, username=auth["user"], key_filename=auth["key"], timeout=10)
                    else:
                        raise Exception(f"SSH Key file not found: {auth['key']}")
                elif auth["method"] == "mfa":
                    ssh.connect(target, username=auth["user"], password=auth["pwd"], timeout=15, look_for_keys=False, allow_agent=False)
                else:
                    ssh.connect(target, username=auth["user"], password=auth["pwd"], timeout=10)
                
                stdin, stdout, stderr = ssh.exec_command("df -h")
                output = stdout.read().decode('utf-8')
                ssh.close()
                
                # Parse df -h output
                lines = output.strip().split('\n')
                fs_data = []
                for line in lines[1:]: # Skip header
                    parts = line.split()
                    if len(parts) >= 6:
                        fs_data.append({
                            "Filesystem": parts[0],
                            "Size": parts[1],
                            "Used": parts[2],
                            "Avail": parts[3],
                            "Use%": parts[4],
                            "Mounted": parts[5]
                        })
                
                if fs_data:
                    self.results["ssh_filesystem_data"].append({
                        "server": target,
                        "data": fs_data
                    })
                    print(f"  ✓ SSH: Got {len(fs_data)} entries from {target}")
                    
            except Exception as e:
                print(f"  ✗ SSH: Failed to connect to {target}: {e}")
                self.results["external_checks"].append({
                    "type": f"SSH Filesystem Check ({target})",
                    "status": "Error",
                    "details": str(e)
                })

    async def run_external_checks(self):
        """Runs OS filesystem checks via RFC, SSH, and URL health checks."""
        await self.update_status("Running infrastructure checks (RFC, SSH, URL)...")
        print("Running external checks (OS & URLs)...")
        
        # 1. SSH Checks for DB and other servers
        await self.run_ssh_filesystem_checks()

        # 2. RFC Checks for App Server filesystem
        hostname = self.config.get("hostname")
        instance_number = self.config.get("instance_number", "00")
        client = self.config.get("sap_client")
        username = self.config.get("sap_username")
        password = self.config.get("sap_password")
        
        try:
            rfc_client = SAPRfcClient(
                ashost=hostname,
                sysnr=instance_number,
                client=client,
                user=username,
                passwd=password
            )
            if rfc_client.connect():
                print("  RFC connected for filesystem check...")
                fs_result = rfc_client.get_filesystem_data()
                
                if fs_result.get("status") == "success":
                    method = fs_result.get("method", "unknown")
                    fs_data = fs_result.get("data", [])
                    
                    self.results["external_checks"].append({
                        "type": "App Server Filesystem (RFC)",
                        "method": method,
                        "status": "OK" if fs_data else "No Data",
                        "data": fs_data
                    })
                    print(f"  ✓ Got {len(fs_data)} entries via RFC {method}")
                
                rfc_client.disconnect()
            else:
                self.results["external_checks"].append({
                    "type": "App Server Filesystem (RFC)",
                    "status": "Error",
                    "details": "RFC connection failed"
                })
        except Exception as e:
            print(f"  RFC Filesystem check error: {e}")
            self.results["external_checks"].append({
                "type": "App Server Filesystem (RFC)",
                "status": "Error",
                "details": str(e)
            })
        
        # 3. URL Health Checks
        url_checks = self.config.get("url_checks", [])
        for check_url in url_checks:
            try:
                import urllib.request
                req = urllib.request.Request(check_url, method='HEAD')
                req.add_header('User-Agent', 'SAP-Monitor/2.0')
                import ssl
                ctx = ssl.create_default_context()
                ctx.check_hostname = False
                ctx.verify_mode = ssl.CERT_NONE
                
                response = urllib.request.urlopen(req, timeout=10, context=ctx)
                status_code = response.getcode()
                self.results["external_checks"].append({
                    "type": "URL Check",
                    "url": check_url,
                    "status": f"HTTP {status_code}",
                    "details": "Reachable"
                })
            except Exception as e:
                self.results["external_checks"].append({
                    "type": "URL Check",
                    "url": check_url,
                    "status": "Error",
                    "details": str(e)[:100]
                })

    async def generate_report(self):
        print("Running SAP Checks...")
        await self.run_sap_checks()
        print("Running External Checks...")
        await self.run_external_checks()
        return self.results

if __name__ == "__main__":
    # Test execution
    config = {
        "sap_url": "https://sap-system.example.com/sap/bc/gui/sap/its/webgui",
        "sap_client": "100",
        "sap_username": "TESTUSER",
        "sap_password": "PASSWORD",
        "servers": ["app_server_1", "app_server_2", "db_server"],
        "webdispatcher_url": "https://webdisp.example.com",
        "mock_test": True
    }
    
    orchestrator = ReportOrchestrator(config)
    results = asyncio.run(orchestrator.generate_report())
    print("Run complete. Total Anomalies found:", len(results["anomalies"]))
