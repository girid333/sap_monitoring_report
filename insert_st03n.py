import sys

with open("backend/sap_automator.py", "r") as f:
    content = f.read()

st03n_code = """
                        if tcode == "ST03N":
                            print("    Performing ST03N tree interaction & screenshots...")
                            st03n_pages = []
                            # Capture Initial Screen
                            init_path = os.path.join(self.output_dir, f"ST03N_{ts}.png")
                            await page.screenshot(path=init_path)
                            st03n_pages.append(init_path)
                            print("      ✓ Captured initial ST03N screen")
                            
                            try:
                                tree_frame = None
                                for f in page.frames:
                                    if f.name == "application":
                                        tree_frame = f
                                        break
                                
                                if tree_frame:
                                    print("      Found ST03N tree frame.")
                                    # 1. Expand "Workload"
                                    await click_tree_node(tree_frame, "Workload", "expand")
                                    await asyncio.sleep(2)
                                    # 2. Expand "Total"
                                    await click_tree_node(tree_frame, "Total", "expand")
                                    await asyncio.sleep(2)
                                    # 3. Expand "Day"
                                    await click_tree_node(tree_frame, "Day", "expand")
                                    await asyncio.sleep(3)
                                    
                                    # Click "Yesterday"
                                    res_date = await tree_frame.evaluate('''() => {
                                        let allSpans = document.querySelectorAll('span');
                                        let dateNodes = [];
                                        for (let s of allSpans) {
                                            if (/^[0-9]{2}\\.[0-9]{2}\\.[0-9]{4}$/.test(s.innerText.trim())) {
                                                dateNodes.push(s);
                                            }
                                        }
                                        if (dateNodes.length >= 2) {
                                            let target = dateNodes[1]; // Yesterday
                                            target.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
                                            return target.innerText.trim();
                                        } else if (dateNodes.length === 1) {
                                            let target = dateNodes[0]; // Today
                                            target.dispatchEvent(new MouseEvent('dblclick', {bubbles: true}));
                                            return target.innerText.trim();
                                        }
                                        return null;
                                    }''')
                                    print(f"      ✓ Double-clicked date: {res_date}")
                                    
                                    print("      Waiting for Workload Overview to load...")
                                    await asyncio.sleep(10)
                                    try:
                                        await page.wait_for_load_state("networkidle", timeout=8000)
                                    except:
                                        pass
                                    
                                    ov_path = os.path.join(self.output_dir, f"ST03N_Overview_{ts}.png")
                                    await page.screenshot(path=ov_path)
                                    st03n_pages.append(ov_path)
                                    print("      ✓ Captured Workload Overview")
                                    
                                    # 1. Expand "Transaction Profile"
                                    await click_tree_node(tree_frame, "Transaction Profile", "expand")
                                    await asyncio.sleep(2)
                                    # 2. Double-click "Standard"
                                    await click_tree_node(tree_frame, "Standard", "dblclick")
                                    print("      ✓ Double-clicked 'Standard' transaction profile")
                                    
                                    print("      Waiting for Transaction Profile to load...")
                                    await asyncio.sleep(8)
                                    try:
                                        await page.wait_for_load_state("networkidle", timeout=8000)
                                    except:
                                        pass
                                        
                                    tp_path = os.path.join(self.output_dir, f"ST03N_TransactionProfile_{ts}.png")
                                    await page.screenshot(path=tp_path)
                                    st03n_pages.append(tp_path)
                                    print("      ✓ Captured Transaction Profile")
                                    
                                    # Time Profile
                                    await click_tree_node(tree_frame, "Time Profile", "dblclick")
                                    print("      ✓ Double-clicked 'Time Profile'")
                                    
                                    print("      Waiting for Time Profile to load...")
                                    await asyncio.sleep(8)
                                    try:
                                        await page.wait_for_load_state("networkidle", timeout=8000)
                                    except:
                                        pass
                                        
                                    timep_path = os.path.join(self.output_dir, f"ST03N_TimeProfile_{ts}.png")
                                    await page.screenshot(path=timep_path)
                                    st03n_pages.append(timep_path)
                                    print("      ✓ Captured Time Profile")
                                    
                            except Exception as e:
                                print(f"      ⚠ ST03N detailed capture failed: {e}")
                            
                            if st03n_pages:
                                screenshots[tcode] = st03n_pages[0]
                                screenshots["ST03N_pages"] = st03n_pages
                            print("    ST03N interaction complete.")
"""

target = '                        # Verify the page loaded\n                        new_title = await page.title()'
content = content.replace(target, st03n_code + '\n' + target)

skip_target = '                        if tcode == "DB02" and "DB02_pages" in screenshots:\n                            print(f"    DB02 already captured via specific handler")\n                            continue'
skip_code = '                        if tcode == "ST03N" and "ST03N_pages" in screenshots:\n                            print(f"    ST03N already captured via specific handler")\n                            continue\n'

content = content.replace(skip_target, skip_target + '\n' + skip_code)

with open("backend/sap_automator.py", "w") as f:
    f.write(content)

print("Insertion complete.")
