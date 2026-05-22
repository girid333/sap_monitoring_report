import sys

with open("backend/sap_automator.py", "r") as f:
    lines = f.readlines()

start_idx = -1
end_idx = -1

for i, line in enumerate(lines):
    if "── DB02 Third Logic:" in line:
        start_idx = i
    if "WARNING: DB02 tree structure not found" in line and start_idx != -1:
        # We want to keep the else: print("WARNING...") part but replace the block before it.
        # Actually, let's find the `except Exception as e:` that closes the Load History block.
        pass

# Let's find the exact bounds:
for i, line in enumerate(lines):
    if "── DB02 Third Logic: Performance → Load History ──" in line:
        start_idx = i
        break

for i in range(start_idx, len(lines)):
    if "Load History logic failed (non-fatal)" in line:
        end_idx = i
        break

if start_idx != -1 and end_idx != -1:
    print(f"Found bounds: {start_idx} to {end_idx}")
    
    new_code = """                                    # ── DB02 Third Logic: SQL Editor Performance Graph ──
                                    try:
                                        print("      --- DB02 SQL Editor Graph ---")
                                        
                                        # 3a. Expand 'Diagnostics' folder
                                        diag_res = await click_tree_node(tree_frame, "Diagnostics", "expand")
                                        print(f"      ✓ Expanded 'Diagnostics': {diag_res}")
                                        await asyncio.sleep(4)
                                        
                                        # 3b. Double-click 'SQL Editor'
                                        sql_res = await click_tree_node(tree_frame, "SQL Editor", "dblclick")
                                        print(f"      ✓ Double-clicked 'SQL Editor': {sql_res}")
                                        
                                        print("      Waiting for SQL Editor pane to load...")
                                        await asyncio.sleep(8)
                                        try:
                                            await page.wait_for_load_state("networkidle", timeout=8000)
                                        except:
                                            pass
                                        await asyncio.sleep(3)
                                        
                                        # 3c. Input the SQL Query
                                        sql_query = \"\"\"SELECT 
    SNAPSHOT_ID, 
    HOST, 
    ROUND(
        (TOTAL_CPU_USER_TIME_DELTA + TOTAL_CPU_SYSTEM_TIME_DELTA + TOTAL_CPU_WIO_TIME_DELTA) / 
        NULLIF(TOTAL_CPU_USER_TIME_DELTA + TOTAL_CPU_SYSTEM_TIME_DELTA + TOTAL_CPU_WIO_TIME_DELTA + TOTAL_CPU_IDLE_TIME_DELTA, 0) * 100, 
        2
    ) AS "CPU_USAGE__", 
    ROUND(USED_PHYSICAL_MEMORY / 1024 / 1024 / 1024, 2) AS "MEMORY_USED_GB"
FROM _SYS_STATISTICS.HOST_RESOURCE_UTILIZATION_STATISTICS
WHERE SNAPSHOT_ID >= ADD_DAYS(CURRENT_TIMESTAMP, -1)
ORDER BY SNAPSHOT_ID DESC;\"\"\"

                                        print("      Inputting SQL query...")
                                        query_filled = False
                                        for frame in page.frames:
                                            try:
                                                textareas = frame.locator("textarea:visible")
                                                count = await textareas.count()
                                                if count > 0:
                                                    await textareas.first.fill(sql_query)
                                                    query_filled = True
                                                    print(f"      ✓ Filled SQL query in textarea in frame '{frame.name}'")
                                                    break
                                            except Exception as e:
                                                pass
                                        
                                        if not query_filled:
                                            print("      Using fallback: keyboard typing into active area...")
                                            for frame in page.frames:
                                                try:
                                                    res = await frame.evaluate(f\"\"\"(query) => {{
                                                        const ta = document.querySelector('textarea');
                                                        if (ta && ta.offsetParent !== null) {{
                                                            ta.value = query;
                                                            ta.dispatchEvent(new Event('input', {{bubbles: true}}));
                                                            ta.dispatchEvent(new Event('change', {{bubbles: true}}));
                                                            return true;
                                                        }}
                                                        return false;
                                                    }}\"\"\", sql_query)
                                                    if res:
                                                        query_filled = True
                                                        print(f"      ✓ Filled SQL via JS in frame '{frame.name}'")
                                                        break
                                                except:
                                                    pass

                                        # 3d. Click Execute (F8)
                                        print("      Clicking Execute...")
                                        executed = False
                                        for frame in page.frames:
                                            try:
                                                exec_btn = frame.get_by_text("Execute", exact=True)
                                                if await exec_btn.count() > 0:
                                                    await exec_btn.first.click()
                                                    executed = True
                                                    print(f"      ✓ Clicked Execute button in frame '{frame.name}'")
                                                    break
                                            except:
                                                pass
                                        
                                        if not executed:
                                            print("      Using F8 keyboard fallback...")
                                            await page.keyboard.press("F8")
                                        
                                        print("      Waiting for SQL execution to complete...")
                                        await asyncio.sleep(8)
                                        try:
                                            await page.wait_for_load_state("networkidle", timeout=10000)
                                        except:
                                            pass
                                        await asyncio.sleep(2)
                                        
                                        # 3e. Extract Result Data
                                        print("      Extracting result data...")
                                        table_data = []
                                        for frame in page.frames:
                                            try:
                                                data = await frame.evaluate(\"\"\"() => {
                                                    const rows = document.querySelectorAll('tr');
                                                    const extracted = [];
                                                    for (const row of rows) {
                                                        const cells = Array.from(row.querySelectorAll('td, th')).map(c => c.innerText.trim());
                                                        if (cells.length >= 4) { 
                                                            let hasSnapshot = false;
                                                            for (let i = 0; i < cells.length; i++) {
                                                                if (cells[i].length > 12 && /^\\d+$/.test(cells[i])) {
                                                                    hasSnapshot = true;
                                                                    break;
                                                                }
                                                            }
                                                            if (hasSnapshot) {
                                                                extracted.push(cells);
                                                            }
                                                        }
                                                    }
                                                    return extracted;
                                                }\"\"\")
                                                if data and len(data) > 0:
                                                    table_data = data
                                                    print(f"      ✓ Found {len(data)} rows in frame '{frame.name}'")
                                                    break
                                            except:
                                                pass
                                        
                                        if table_data:
                                            timestamps = []
                                            cpu_usage = []
                                            mem_usage = []
                                            for row in table_data:
                                                try:
                                                    row_numbers = []
                                                    ts_val = None
                                                    for cell in row:
                                                        if len(cell) >= 14 and cell.isdigit():
                                                            ts_val = f"{cell[8:10]}:{cell[10:12]}"
                                                        else:
                                                            val_str = cell.replace(',', '.')
                                                            try:
                                                                val = float(val_str)
                                                                row_numbers.append(val)
                                                            except:
                                                                pass
                                                    
                                                    if ts_val and len(row_numbers) >= 2:
                                                        timestamps.append(ts_val)
                                                        cpu_usage.append(row_numbers[0])
                                                        mem_usage.append(row_numbers[1])
                                                except Exception as ex:
                                                    print(f"      Skipping row parse error: {ex}")
                                                    continue
                                            
                                            if timestamps:
                                                timestamps.reverse()
                                                cpu_usage.reverse()
                                                mem_usage.reverse()
                                                
                                                print(f"      Parsed {len(timestamps)} data points. Generating graph...")
                                                import matplotlib.pyplot as plt
                                                
                                                fig, ax1 = plt.subplots(figsize=(10, 6))
                                                
                                                color = 'tab:blue'
                                                ax1.set_xlabel('Time (HH:MM)')
                                                ax1.set_ylabel('CPU Usage %', color=color)
                                                ax1.plot(timestamps, cpu_usage, color=color, marker='o', label='CPU Usage %', linestyle='-')
                                                ax1.tick_params(axis='y', labelcolor=color)
                                                for index, label in enumerate(ax1.xaxis.get_ticklabels()):
                                                    if index % max(1, len(timestamps)//10) != 0:
                                                        label.set_visible(False)
                                                
                                                ax2 = ax1.twinx()
                                                color = 'tab:orange'
                                                ax2.set_ylabel('Memory Used GB', color=color)
                                                ax2.plot(timestamps, mem_usage, color=color, marker='x', label='Memory Used GB', linestyle='--')
                                                ax2.tick_params(axis='y', labelcolor=color)
                                                ax2.set_ylim(bottom=0)
                                                
                                                fig.tight_layout()
                                                plt.title('Database Performance (Last 24 Hours)')
                                                
                                                graph_path = os.path.join(self.output_dir, f"DB02_Performance_Graph_{ts}.png")
                                                plt.savefig(graph_path)
                                                plt.close()
                                                
                                                db02_extra_shots.append(graph_path)
                                                print(f"      ✓ Saved graph to {graph_path}")
                                            else:
                                                print("      ⚠ No numerical data parsed from table.")
                                                graph_path = os.path.join(self.output_dir, f"DB02_SQLResult_Fallback_{ts}.png")
                                                await page.screenshot(path=graph_path)
                                                db02_extra_shots.append(graph_path)
                                        else:
                                            print("      ⚠ No result table extracted. Saving fallback screenshot.")
                                            graph_path = os.path.join(self.output_dir, f"DB02_SQLResult_Fallback_{ts}.png")
                                            await page.screenshot(path=graph_path)
                                            db02_extra_shots.append(graph_path)
                                            
                                    except Exception as e:
                                        print(f"      ⚠ SQL Editor logic failed (non-fatal): {e}")\n"""

    new_lines = lines[:start_idx] + [new_code] + lines[end_idx+1:]
    with open("backend/sap_automator.py", "w") as f:
        f.writelines(new_lines)
    print("Replacement successful.")
else:
    print("Could not find bounds.")

