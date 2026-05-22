import asyncio
import os
from datetime import datetime, timedelta
from playwright.async_api import async_playwright

class SAPAutomator:
    def __init__(self, webgui_url, username, password, client="100", output_dir=None):
        self.webgui_url = webgui_url
        self.username = username
        self.password = password
        self.client = client
        
        if output_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
            self.output_dir = os.path.join(base_dir, "screenshots")
        else:
            self.output_dir = os.path.abspath(output_dir)
            
        os.makedirs(self.output_dir, exist_ok=True)

    async def _wait_for_sap_ready(self, page, timeout=10000):
        """Intelligently waits for SAP WebGUI loading spinners to disappear."""
        try:
            # Wait for ls-loading and lsBlockLayer to disappear
            for frame in page.frames:
                try:
                    await frame.evaluate("""() => {
                        return new Promise((resolve) => {
                            let checkInterval = setInterval(() => {
                                let overlay = document.querySelector('.lsBlockLayer');
                                let loading = document.getElementById('ls-loading');
                                let isOverlayGone = !overlay || window.getComputedStyle(overlay).display === 'none';
                                let isLoadingGone = !loading || window.getComputedStyle(loading).display === 'none';
                                
                                if (isOverlayGone && isLoadingGone) {
                                    clearInterval(checkInterval);
                                    resolve(true);
                                }
                            }, 200);
                            
                            // Timeout fallback internally inside JS just in case
                            setTimeout(() => {
                                clearInterval(checkInterval);
                                resolve(false);
                            }, 8000);
                        });
                    }""")
                except:
                    pass
            await page.wait_for_timeout(1000)
        except Exception as e:
            print(f"      ⚠ Smart wait fallback: {e}")
            await page.wait_for_timeout(2000)

    async def take_screenshots(self, tcodes, status_callback=None):
        screenshots = {}
        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                ignore_https_errors=True
            )
            page = await context.new_page()

            try:
                if status_callback:
                    status_callback("Logging into SAP WebGUI...")
                
                print(f"\n{'='*60}")
                print(f"SAP WebGUI Screenshot Engine")
                print(f"URL: {self.webgui_url}")
                print(f"{'='*60}")
                
                # Step 1: Navigate to WebGUI
                print("\n[Step 1] Navigating to WebGUI URL...")
                await page.goto(self.webgui_url, wait_until="networkidle", timeout=30000)
                await asyncio.sleep(3)
                
                # Step 2: Login via JavaScript (bypasses SAP's CSS visibility tricks)
                print("\n[Step 2] Logging in via JavaScript (bypassing CSS visibility)...")
                
                login_result = await page.evaluate(f"""() => {{
                    // Find and fill username
                    const userField = document.querySelector('input[name="sap-user"]');
                    const passField = document.querySelector('input[name="sap-password"]');
                    
                    if (!userField) return {{ success: false, error: 'sap-user field not found' }};
                    if (!passField) return {{ success: false, error: 'sap-password field not found' }};
                    
                    // Set values directly on the DOM elements
                    userField.value = '{self.username}';
                    passField.value = '{self.password}';
                    
                    // Dispatch events so SAP's JS picks up the changes
                    userField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    userField.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    passField.dispatchEvent(new Event('input', {{ bubbles: true }}));
                    passField.dispatchEvent(new Event('change', {{ bubbles: true }}));
                    
                    return {{ 
                        success: true, 
                        userName: userField.name,
                        passName: passField.name
                    }};
                }}""")
                
                print(f"  Login form fill result: {login_result}")
                
                if not login_result.get('success'):
                    print(f"  ✗ Cannot fill login form: {login_result.get('error')}")
                    if status_callback:
                        status_callback("Warning: SAP login form not found")
                    await browser.close()
                    return screenshots
                
                # Step 3: Submit the form via JavaScript
                print("\n[Step 3] Submitting login form...")
                
                await page.evaluate("""() => {
                    // Try to find and click the login button
                    const loginBtn = document.querySelector('#sapwp_BUTTON_LOGIN') 
                                  || document.querySelector('span.urBtnCnt');
                    if (loginBtn) {
                        loginBtn.click();
                        return 'clicked button';
                    }
                    
                    // Try to find the form and submit it
                    const form = document.querySelector('form');
                    if (form) {
                        form.submit();
                        return 'submitted form';
                    }
                    
                    return 'no button or form found';
                }""")
                
                # Wait for navigation/login to complete
                print("  Waiting for login to complete...")
                await self._wait_for_sap_ready(page)
                try:
                    await page.wait_for_load_state("networkidle", timeout=15000)
                except:
                    pass
                
                await asyncio.sleep(3)
                
                # Check post-login state
                post_url = page.url
                post_title = await page.title()
                print(f"  Post-login URL: {post_url}")
                print(f"  Post-login title: {post_title}")
                
                # Save diagnostic screenshot after login
                diag_path = os.path.join(self.output_dir, "diag_after_login.png")
                await page.screenshot(path=diag_path, full_page=True)
                diag_size = os.path.getsize(diag_path)
                print(f"  Post-login screenshot: {diag_size} bytes ({'real content' if diag_size > 5000 else 'possibly blank'})")
                
                # Check for multiple logon popup
                for frame in page.frames:
                    try:
                        popup_result = await frame.evaluate("""() => {
                            const spans = document.querySelectorAll('span, button, input[type="submit"]');
                            for (const el of spans) {
                                const text = el.textContent || el.value || '';
                                if (text.trim() === 'Continue' || text.trim() === 'Yes') {
                                    el.click();
                                    return 'clicked: ' + text.trim();
                                }
                            }
                            return null;
                        }""")
                        if popup_result:
                            print(f"  → Handled popup: {popup_result}")
                            await asyncio.sleep(3)
                            break
                    except:
                        continue
                
                # Step 4: Verify login by checking for command field
                print("\n[Step 4] Verifying login...")
                
                login_verified = False
                active_frame = None
                
                for frame in page.frames:
                    try:
                        has_cmd = await frame.evaluate("""() => {
                            const cmd = document.querySelector('input[id="ToolbarOkCode"]') 
                                     || document.querySelector('input[id*="OKCode"]')
                                     || document.querySelector('input[title*="command" i]')
                                     || document.querySelector('input[name*="okcode" i]');
                            if (cmd) return cmd.id || cmd.name || 'found';
                            return null;
                        }""")
                        if has_cmd:
                            login_verified = True
                            active_frame = frame
                            print(f"  ✓ LOGIN VERIFIED - command field '{has_cmd}' in frame '{frame.name}'")
                            break
                    except:
                        continue
                
                if not login_verified:
                    print("  ✗ LOGIN NOT VERIFIED - no command field found")
                    print("  Dumping all frames for diagnosis:")
                    for i, f in enumerate(page.frames):
                        try:
                            info = await f.evaluate("""() => {
                                return {
                                    url: location.href.substring(0, 80),
                                    inputs: Array.from(document.querySelectorAll('input'))
                                        .map(el => el.id || el.name || el.type)
                                        .filter(x => x).slice(0, 10),
                                    body: document.body ? document.body.innerText.substring(0, 200) : 'no body'
                                };
                            }""")
                            print(f"    Frame {i} ({f.name}): {info}")
                        except:
                            print(f"    Frame {i} ({f.name}): [cannot access]")
                    
                    if status_callback:
                        status_callback("Warning: WebGUI login not verified - screenshots may be blank")
                
                # Step 5: Navigate to each T-code via URL and capture
                # SAP WebGUI supports ~transaction parameter in the URL
                # Session cookies maintain login, so each URL opens the correct transaction
                print(f"\n[Step 5] Capturing {len(tcodes)} T-code screenshots via URL navigation...")
                
                # Extract the base WebGUI URL (remove any existing params)
                from urllib.parse import urlparse, parse_qs, urlencode, urlunparse
                parsed = urlparse(self.webgui_url)
                base_path = parsed.path
                existing_params = parse_qs(parsed.query)
                
                # Get sap-client from existing URL params or use default
                sap_client = existing_params.get('sap-client', [self.client])[0]
                sap_lang = existing_params.get('sap-language', ['en'])[0]
                
                # Helper to click a tree node container robustly by text (used by DB02 and ST03N)
                async def st03n_click_tree_node(frm, text, action_type="click"):
                    return await frm.evaluate("""([nodeText, actionType]) => {
                        const xpath = `//span[text()="${nodeText}"] | //a[text()="${nodeText}"] | //div[text()="${nodeText}"]`;
                        const result = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                        
                        for (let i = 0; i < result.snapshotLength; i++) {
                            const el = result.snapshotItem(i);
                            let current = el;
                            let container = null;
                            
                            for (let d = 0; d < 6; d++) {
                                if (!current) break;
                                const className = current.className || '';
                                const id = current.id || '';
                                const tagName = current.tagName.toLowerCase();
                                const role = current.getAttribute('role') || '';
                                
                                if (className.includes('TreeNode') || 
                                    className.includes('TreeItem') || 
                                    className.includes('TreeNodeName') ||
                                    id.includes('tree') || 
                                    role === 'treeitem' ||
                                    current.getAttribute('ct') === 'TreeNode') {
                                    container = current;
                                    break;
                                }
                                current = current.parentElement;
                            }
                            
                            if (container) {
                                const isExpanded = container.getAttribute('aria-expanded') === 'true' || 
                                                  container.className.includes('Expanded') || 
                                                  container.getAttribute('lsdata')?.includes('"expanded":true');
                                
                                if (actionType === 'expand' && isExpanded) {
                                    return 'already_expanded';
                                }
                                
                                container.focus();
                                
                                const events = ['mousedown', 'mouseup', 'click'];
                                for (const evName of events) {
                                    const ev = new MouseEvent(evName, {
                                        bubbles: true,
                                        cancelable: true,
                                        view: window
                                    });
                                    container.dispatchEvent(ev);
                                }
                                
                                if (actionType === 'dblclick' || (actionType === 'expand' && !isExpanded)) {
                                    const dbl = new MouseEvent('dblclick', {
                                        bubbles: true,
                                        cancelable: true,
                                        view: window
                                    });
                                    container.dispatchEvent(dbl);
                                }
                                return actionType + '_dispatched';
                            }
                        }
                        return 'not_found';
                    }""", [text, action_type])

                for tcode in tcodes:
                    if status_callback:
                        status_callback(f"Capturing screenshot for {tcode}...")
                    
                    print(f"\n  --- {tcode} ---")
                    
                    # Build the URL with ~transaction parameter
                    tcode_params = {
                        'sap-client': sap_client,
                        'sap-language': sap_lang,
                        '~transaction': tcode
                    }
                    tcode_url = f"{parsed.scheme}://{parsed.netloc}{base_path}?{urlencode(tcode_params)}"
                    print(f"    URL: {tcode_url}")
                    
                    try:
                        # Attempt OK-Code Navigation First (Massive performance boost)
                        navigated_via_okcode = False
                        for frame in page.frames:
                            try:
                                res = await frame.evaluate(f"""(tc) => {{
                                    let okField = document.querySelector('input[title="Command Field"]') || 
                                                  document.querySelector('input[name="~OkCode"]') || 
                                                  document.querySelector('input[id*="okcd"]');
                                    if (okField) {{
                                        okField.value = '/n' + tc;
                                        // Trigger change events
                                        okField.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                        
                                        // Find and click the enter/confirm button next to it if available, else simulate Enter
                                        let btn = document.querySelector('div[title="Enter"]') || 
                                                  document.querySelector('a[title="Enter"]');
                                        if (btn) {{
                                            btn.click();
                                        }} else {{
                                            // simulate enter form submit if possible, or trigger keyboard event
                                            okField.dispatchEvent(new KeyboardEvent('keydown', {{'key': 'Enter', 'keyCode': 13}}));
                                            okField.dispatchEvent(new KeyboardEvent('keyup', {{'key': 'Enter', 'keyCode': 13}}));
                                        }}
                                        return true;
                                    }}
                                    return false;
                                }}""", tcode)
                                
                                if res:
                                    print(f"    → Navigated to {tcode} via OK-Code command field")
                                    navigated_via_okcode = True
                                    break
                            except:
                                pass
                        
                        if navigated_via_okcode:
                            await self._wait_for_sap_ready(page)
                        else:
                            # Fallback: Navigate to the transaction URL directly
                            print(f"    → Navigating via URL reload fallback")
                            await page.goto(tcode_url, wait_until="networkidle", timeout=20000)
                            await self._wait_for_sap_ready(page)
                        
                        # Check for multiple logon popup and handle it
                        try:
                            popup_handled = await page.evaluate("""() => {
                                const spans = document.querySelectorAll('span, button, input[type="submit"]');
                                for (const el of spans) {
                                    const text = (el.textContent || el.value || '').trim();
                                    if (text === 'Continue' || text === 'Yes') {
                                        el.click();
                                        return text;
                                    }
                                }
                                return null;
                            }""")
                            if popup_handled:
                                print(f"    → Handled popup: {popup_handled}")
                                await self._wait_for_sap_ready(page)
                        except:
                            pass
                        
                        # Special handling for SM21: Fill date/time and execute
                        if tcode == "SM21":
                            print("    Performing SM21 interaction (Last 24h)...")
                            now = datetime.now()
                            yesterday = now - timedelta(days=1)
                            today_str = now.strftime("%d.%m.%Y")
                            yesterday_str = yesterday.strftime("%d.%m.%Y")
                            time_str = now.strftime("%H:%M:%S")
                            
                            # Step 1: Find the frame containing SM21 form inputs
                            target_frame = None
                            target_inputs = []
                            for fi, frame in enumerate(page.frames):
                                try:
                                    input_dump = await frame.evaluate("""() => {
                                        const inputs = Array.from(document.querySelectorAll('input'));
                                        const formInputs = inputs.filter(el => {
                                            const id = el.id || '';
                                            return el.type === 'text' && !id.includes('Toolbar') && !id.includes('theme') && !id.includes('sap-');
                                        });
                                        return formInputs.map((el, idx) => ({
                                            idx: idx,
                                            id: el.id,
                                            name: el.name,
                                            value: el.value,
                                            type: el.type
                                        }));
                                    }""")
                                    print(f"    Frame {fi} ('{frame.name}'): {len(input_dump)} inputs")
                                    for inp in input_dump[:10]:
                                        print(f"      [{inp['idx']}] id={inp['id']} val='{inp['value']}'")
                                    
                                    if len(input_dump) >= 5 and not target_frame:
                                        target_frame = frame
                                        target_inputs = input_dump
                                except Exception as e:
                                    print(f"    Frame {fi}: cannot access - {e}")
                            
                            if target_frame:
                                print(f"    ✓ Target frame: '{target_frame.name}' ({len(target_inputs)} inputs)")
                                
                                # Step 2: Fill date/time fields using click + page.keyboard.type
                                # (Frame has no .keyboard - must use page.keyboard after clicking in frame)
                                field_values = [
                                    (0, yesterday_str, "From Date"),
                                    (1, time_str, "From Time"),
                                    (2, today_str, "To Date"),
                                    (3, time_str, "To Time"),
                                ]
                                
                                for idx, val, label in field_values:
                                    try:
                                        inp = target_inputs[idx]
                                        selector = f'[id="{inp["id"]}"]' if inp['id'] else f"input:nth-of-type({idx+1})"
                                        print(f"      {label}: clicking {selector}, typing '{val}'")
                                        # Use Playwright's native fill, which replaces text without triggering SAP triple-click popups
                                        await target_frame.fill(selector, val)
                                        await asyncio.sleep(0.3)
                                        # Tab to next field to commit the value
                                        await page.keyboard.press("Tab")
                                        await asyncio.sleep(0.5)
                                        print(f"      ✓ {label} filled")
                                    except Exception as e:
                                        print(f"      ✗ {label} FAILED: {e}")
                                
                                # Step 3: Clear Extended Instance Name
                                for inp in target_inputs:
                                    if inp['value'] and '_' in inp['value'] and len(inp['value']) > 5:
                                        try:
                                            selector = f'[id="{inp["id"]}"]' if inp['id'] else f"input:nth-of-type({inp['idx']+1})"
                                            print(f"      Clearing Instance: {selector} (was '{inp['value']}')")
                                            # Use fill to clear the field natively
                                            await target_frame.fill(selector, "")
                                            await asyncio.sleep(0.3)
                                            await page.keyboard.press("Tab")
                                            await asyncio.sleep(0.5)
                                            print(f"      ✓ Instance field cleared")
                                        except Exception as e:
                                            print(f"      ✗ Clear Instance FAILED: {e}")
                                
                                # Step 4: Diagnostic screenshot of filled form
                                diag_path = os.path.join(self.output_dir, "SM21_debug_filled.png")
                                await page.screenshot(path=diag_path, full_page=True)
                                print(f"    Diagnostic screenshot: {os.path.getsize(diag_path)} bytes")
                                
                                # Step 5: Click "Execute" link (top-left of SAP screen)
                                # The Execute link has tooltip "Execute (F8)"
                                print("    Clicking Execute...")
                                
                                # Strategy A: Click the "Execute" text link via Playwright locator
                                executed = False
                                for frame in page.frames:
                                    try:
                                        exec_locator = frame.get_by_text("Execute", exact=True)
                                        count = await exec_locator.count()
                                        if count > 0:
                                            await exec_locator.first.click()
                                            print(f"    ✓ Clicked 'Execute' text in frame '{frame.name}'")
                                            executed = True
                                            break
                                    except Exception as e:
                                        pass
                                
                                # Strategy B: F8 keyboard (universal SAP execute)
                                if not executed:
                                    print("    Using F8 keyboard fallback...")
                                    await page.keyboard.press("F8")
                                
                                # Step 6: Wait for Syslog messages screen
                                print("    Waiting for SM21 results...")
                                await self._wait_for_sap_ready(page)
                                try:
                                    await page.wait_for_load_state("networkidle", timeout=15000)
                                except:
                                    pass
                                await asyncio.sleep(3)
                                
                                # Step 7: Scroll through SM21 results using SAP table pagination
                                print("    Scrolling through SM21 results...")
                                sm21_screenshots = []
                                sm21_log_text = []
                                seen_lines = set()
                                
                                # Find the frame that contains the actual Syslog table
                                log_frame = None
                                for frame in page.frames:
                                    try:
                                        row_count = await frame.evaluate("""() => {
                                            return document.querySelectorAll('tr').length;
                                        }""")
                                        if row_count and row_count > 2:
                                            log_frame = frame
                                            print(f"      Found log table in frame '{frame.name}' ({row_count} rows)")
                                            break
                                    except:
                                        continue
                                
                                SM21_MAX_PAGES = 25
                                prev_page_text = None
                                
                                for scroll_page in range(SM21_MAX_PAGES):
                                    # Take screenshot of current view
                                    ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                    ss_path = os.path.join(self.output_dir, f"SM21_page{scroll_page+1}_{ts}.png")
                                    await page.screenshot(path=ss_path, full_page=False)
                                    file_size = os.path.getsize(ss_path)
                                    
                                    if file_size > 15000:
                                        sm21_screenshots.append(ss_path)
                                        print(f"      Page {scroll_page+1}: {file_size:,} bytes")
                                    
                                    # Extract visible text from the log table
                                    page_text = None
                                    if log_frame:
                                        try:
                                            page_text = await log_frame.evaluate("""() => {
                                                const rows = document.querySelectorAll('tr');
                                                return Array.from(rows).map(r => {
                                                    return Array.from(r.querySelectorAll('td, th')).map(c => c.innerText.trim()).join(' | ');
                                                }).filter(t => t.length > 10);
                                            }""")
                                        except:
                                            pass
                                    
                                    # Scroll unchanged check (indicating bottom of results grid reached)
                                    if scroll_page > 0 and page_text and page_text == prev_page_text:
                                        print(f"      No change in page text detected. Waiting 2s for late render retry...")
                                        await asyncio.sleep(2)
                                        try:
                                            page_text = await log_frame.evaluate("""() => {
                                                const rows = document.querySelectorAll('tr');
                                                return Array.from(rows).map(r => {
                                                    return Array.from(r.querySelectorAll('td, th')).map(c => c.innerText.trim()).join(' | ');
                                                }).filter(t => t.length > 10);
                                            }""")
                                        except:
                                            pass
                                        if page_text == prev_page_text:
                                            print(f"      Scroll position unchanged on page {scroll_page+1} — reached end of results")
                                            if sm21_screenshots and sm21_screenshots[-1] == ss_path:
                                                sm21_screenshots.pop()
                                                try:
                                                    os.remove(ss_path)
                                                except:
                                                    pass
                                            break
                                    
                                    prev_page_text = page_text
                                    
                                    # Analyze log text lines
                                    new_lines_this_page = 0
                                    if page_text:
                                        for line in page_text:
                                            if any(noise in line for noise in [
                                                'select a row', 'press the space bar',
                                                'To select', 'To deselect',
                                                'Column Settings', 'Sort Ascending',
                                                'Sort Descending', 'Set Filter',
                                                'Refresh display', 'Display Statistics',
                                                'Display details', 'Show Error Log',
                                            ]):
                                                continue
                                            if line not in seen_lines:
                                                seen_lines.add(line)
                                                sm21_log_text.append(line)
                                                new_lines_this_page += 1
                                                
                                    print(f"        ({new_lines_this_page} new log lines extracted)")
                                    
                                    # Scroll SAP table: click into the table, then press PageDown
                                    # SAP WebGUI tables use virtual scrolling - must use keyboard
                                    # to trigger SAP server to load next page of data
                                    if log_frame:
                                        try:
                                            # Target only visible content rows in the scrollable grid body
                                            # to prevent clicking layout or toolbar elements which toggle headers.
                                            visible_rows = log_frame.locator('tr[id*="-mrss-cont-"]:visible')
                                            count = await visible_rows.count()
                                            
                                            clicked = False
                                            # Click a row in the data area (avoid first row if possible, or fallback)
                                            for idx in [2, 3, 1, 0]:
                                                if idx < count:
                                                    try:
                                                        row_loc = visible_rows.nth(idx)
                                                        td_loc = row_loc.locator('td:visible').first
                                                        if await td_loc.count() > 0:
                                                            await td_loc.click(timeout=1500)
                                                        else:
                                                            await row_loc.click(timeout=1500)
                                                        clicked = True
                                                        await asyncio.sleep(0.5)
                                                        break
                                                    except:
                                                        continue
                                            
                                            if not clicked:
                                                # Fallback to general visible cell elements if target rows not found
                                                for selector in ['tr[class*="Row"]:visible', 'td:visible', '.lsTextView:visible', 'span:visible', 'body']:
                                                    try:
                                                        loc = log_frame.locator(selector).first
                                                        if await loc.count() > 0:
                                                            await loc.click(timeout=1500)
                                                            await asyncio.sleep(0.5)
                                                            clicked = True
                                                            break
                                                    except:
                                                        continue
                                        except Exception as click_err:
                                            print(f"      Focus click failed: {click_err}")
                                    
                                    # Send PageDown to scroll SAP's virtual table
                                    await page.keyboard.press("PageDown")
                                    await self._wait_for_sap_ready(page)
                                
                                # Store SM21 screenshots list and log text
                                if sm21_screenshots:
                                    screenshots[tcode] = sm21_screenshots[0]  # Primary screenshot
                                    screenshots["SM21_pages"] = sm21_screenshots  # All pages
                                    screenshots["SM21_log_text"] = sm21_log_text  # Raw text for analysis
                                    print(f"    ✓ SM21: {len(sm21_screenshots)} pages, {len(sm21_log_text)} log lines captured")
                                
                                print("    SM21 interaction complete.")
                            else:
                                print("    ✗ SM21: No frame found with >= 5 inputs")

                        # Special handling for SM12: Fill Client/User with * and search
                        if tcode == "SM12":
                            print("    Performing SM12 interaction (Search all lock entries)...")
                            
                            # Find the frame with the SM12 form inputs
                            sm12_frame = None
                            sm12_inputs = []
                            
                            for fi, frame in enumerate(page.frames):
                                try:
                                    inputs = await frame.evaluate("""() => {
                                        const els = Array.from(document.querySelectorAll('input'));
                                        return els.map((el, idx) => ({
                                            idx: idx,
                                            id: el.id,
                                            value: el.value,
                                            type: el.type,
                                            visible: el.offsetParent !== null,
                                            width: el.offsetWidth
                                        })).filter(e => e.visible && e.type !== 'hidden');
                                    }""")
                                    if len(inputs) >= 3 and not sm12_frame:
                                        sm12_frame = frame
                                        sm12_inputs = inputs
                                        print(f"      Found SM12 in frame {fi} ('{frame.name}') — {len(inputs)} visible inputs:")
                                        for inp in inputs[:8]:
                                            print(f"        [{inp['idx']}] id='{inp['id']}' val='{inp['value']}' type={inp['type']} w={inp['width']}")
                                except:
                                    continue
                            
                            if sm12_frame and len(sm12_inputs) >= 2:
                                # Strategy: Set values via JavaScript directly on the DOM inputs
                                # Then click+type as a backup to trigger SAP's event handlers
                                
                                # Step 1: Set values via JS (using global input index)
                                try:
                                    result = await sm12_frame.evaluate("""() => {
                                        const allInputs = Array.from(document.querySelectorAll('input'));
                                        const visible = allInputs.filter(el => el.offsetParent !== null && el.type !== 'hidden');
                                        const results = [];
                                        
                                        // First visible input = Client, second = User Name
                                        for (let i = 0; i < Math.min(2, visible.length); i++) {
                                            const inp = visible[i];
                                            const oldVal = inp.value;
                                            inp.focus();
                                            inp.value = '*';
                                            inp.dispatchEvent(new Event('input', {bubbles: true}));
                                            inp.dispatchEvent(new Event('change', {bubbles: true}));
                                            inp.blur();
                                            results.push({idx: i, id: inp.id, oldVal: oldVal, newVal: inp.value});
                                        }
                                        return results;
                                    }""")
                                    for r in result:
                                        print(f"      JS fill [{r['idx']}] '{r['oldVal']}' → '{r['newVal']}' (id={r['id']})")
                                except Exception as e:
                                    print(f"      JS fill failed: {e}")
                                
                                # Take debug screenshot
                                debug_path = os.path.join(self.output_dir, "SM12_debug_filled.png")
                                await page.screenshot(path=debug_path)
                                print(f"      Debug screenshot: {debug_path}")
                                
                                # Step 3: Click "Search" button
                                print("    Clicking Search...")
                                searched = False
                                for frame in page.frames:
                                    try:
                                        search_locator = frame.get_by_text("Search", exact=True)
                                        count = await search_locator.count()
                                        if count > 0:
                                            await search_locator.first.click()
                                            print(f"    ✓ Clicked 'Search' in frame '{frame.name}'")
                                            searched = True
                                            break
                                    except:
                                        pass
                                
                                if not searched:
                                    print("    Using F8 keyboard fallback...")
                                    await page.keyboard.press("F8")
                                
                                # Wait for results
                                print("    Waiting for SM12 results...")
                                await self._wait_for_sap_ready(page)
                                try:
                                    await page.wait_for_load_state("networkidle", timeout=10000)
                                except:
                                    pass
                                await asyncio.sleep(2)
                                print("    SM12 interaction complete.")
                            else:
                                print(f"    ✗ SM12: Found {len(sm12_inputs)} inputs, need at least 2")

                        # Special handling for SM37: Cancelled jobs from yesterday to today
                        if tcode == "SM37":
                            print("    Performing SM37 interaction (Cancelled jobs, last 24h)...")
                            yesterday = (datetime.now() - timedelta(days=1)).strftime("%d.%m.%Y")
                            today = datetime.now().strftime("%d.%m.%Y")
                            print(f"      From: {yesterday}  To: {today}")
                            
                            # === STEP 1: Fill text fields ===
                            text_frame = None
                            for fi, frame in enumerate(page.frames):
                                try:
                                    text_count = await frame.evaluate("""() => {
                                        const els = Array.from(document.querySelectorAll('input'));
                                        return els.filter(el => {
                                            const t = (el.type || 'text').toLowerCase();
                                            return (t === 'text' || t === '') && el.offsetParent !== null;
                                        }).length;
                                    }""")
                                    if text_count >= 4 and not text_frame:
                                        text_frame = frame
                                        print(f"      Found {text_count} text inputs in frame {fi} ('{frame.name}')")
                                        result = await frame.evaluate("""(params) => {
                                            const allInputs = Array.from(document.querySelectorAll('input'));
                                            const textInputs = allInputs.filter(el => {
                                                const t = (el.type || 'text').toLowerCase();
                                                return (t === 'text' || t === '') && el.offsetParent !== null;
                                            });
                                            const results = [];
                                            const fillField = (idx, newVal, label) => {
                                                if (textInputs.length > idx) {
                                                    const inp = textInputs[idx];
                                                    const oldVal = inp.value;
                                                    inp.focus();
                                                    inp.value = newVal;
                                                    inp.dispatchEvent(new Event('input', {bubbles: true}));
                                                    inp.dispatchEvent(new Event('change', {bubbles: true}));
                                                    inp.blur();
                                                    results.push({field: label, oldVal, newVal: inp.value});
                                                }
                                            };
                                            fillField(0, '*', 'Job Name');
                                            fillField(1, '*', 'User Name');
                                            fillField(2, params.yesterday, 'From Date');
                                            fillField(3, params.today, 'To Date');
                                            return results;
                                        }""", {"yesterday": yesterday, "today": today})
                                        for r in result:
                                            print(f"      ✓ {r['field']}: '{r['oldVal']}' → '{r['newVal']}'")
                                except:
                                    continue
                            
                            if not text_frame:
                                print("      ✗ Could not find text inputs in any frame")
                            
                            # === STEP 2: Handle checkboxes ===
                            # SAP WebGUI uses <SPAN role="checkbox" aria-checked="true/false">
                            # NOT standard <input type="checkbox">
                            labels = ['Sched.', 'Released', 'Ready', 'Active', 'Finished', 'Canceled']
                            print("      === CHECKBOX HANDLING ===")
                            
                            target_frame = text_frame if text_frame else page.frames[0]
                            
                            try:
                                role_chk = target_frame.get_by_role("checkbox")
                                role_count = await role_chk.count()
                                print(f"      Found {role_count} role='checkbox' elements")
                                
                                if role_count >= 6:
                                    # Log initial state and determine which need toggling
                                    for i in range(6):
                                        aria_val = await role_chk.nth(i).get_attribute("aria-checked")
                                        is_checked = (aria_val == "true")
                                        lbl = labels[i] if i < len(labels) else f"chk[{i}]"
                                        mark = "☑" if is_checked else "☐"
                                        print(f"        {mark} {lbl} (aria-checked={aria_val})")
                                    
                                    # Only Cancelled (index 5) should be checked
                                    # Click only checkboxes whose state needs to CHANGE
                                    for i in range(6):
                                        should_be_checked = (i == 5)  # Only Cancelled
                                        aria_val = await role_chk.nth(i).get_attribute("aria-checked")
                                        is_checked = (aria_val == "true")
                                        lbl = labels[i] if i < len(labels) else f"chk[{i}]"
                                        
                                        if is_checked and not should_be_checked:
                                            # Currently checked, needs to be UNCHECKED → click to toggle off
                                            await role_chk.nth(i).click()
                                            await asyncio.sleep(0.8)
                                            print(f"      ✓ {lbl}: UNCHECKED (was checked)")
                                        elif not is_checked and should_be_checked:
                                            # Currently unchecked, needs to be CHECKED → click to toggle on
                                            await role_chk.nth(i).click()
                                            await asyncio.sleep(0.8)
                                            print(f"      ✓ {lbl}: CHECKED (was unchecked)")
                                        else:
                                            state = "checked" if is_checked else "unchecked"
                                            print(f"      ○ {lbl}: already {state}, no change needed")
                                    
                                    # Verify final state
                                    await asyncio.sleep(0.5)
                                    print("      Final checkbox state:")
                                    for i in range(6):
                                        aria_val = await role_chk.nth(i).get_attribute("aria-checked")
                                        is_checked = (aria_val == "true")
                                        lbl = labels[i] if i < len(labels) else f"chk[{i}]"
                                        mark = "☑" if is_checked else "☐"
                                        print(f"        {mark} {lbl}")
                                else:
                                    print(f"      ✗ Expected 6 checkboxes, found {role_count}")
                                    
                            except Exception as e:
                                print(f"      ✗ Checkbox handling failed: {e}")
                                import traceback
                                traceback.print_exc()
                            
                            await asyncio.sleep(1)
                            
                            # === STEP 3: Click Execute ===
                            print("    Clicking Execute...")
                            executed = False
                            for frame in page.frames:
                                try:
                                    exec_locator = frame.get_by_text("Execute", exact=True)
                                    count = await exec_locator.count()
                                    if count > 0:
                                        await exec_locator.first.click()
                                        print(f"    ✓ Clicked 'Execute' in frame '{frame.name}'")
                                        executed = True
                                        break
                                except:
                                    pass
                            
                            if not executed:
                                print("    Using F8 keyboard fallback...")
                                await page.keyboard.press("F8")
                            
                            # Wait for results
                            print("    Waiting for SM37 results...")
                            await self._wait_for_sap_ready(page)
                            try:
                                await page.wait_for_load_state("networkidle", timeout=10000)
                            except:
                                pass
                            await asyncio.sleep(2)
                            print("    SM37 interaction complete.")
                            
                            # Extract SM37 log text from frames
                            sm37_log_text = []
                            for frame in page.frames:
                                try:
                                    dump_text = await frame.evaluate("""() => {
                                        const rows = document.querySelectorAll('tr');
                                        if (rows.length < 2) return null;
                                        return Array.from(rows).map(r => {
                                            return Array.from(r.querySelectorAll('td, th')).map(c => c.innerText.trim()).join(' | ');
                                        }).filter(t => t.length > 10);
                                    }""")
                                    if dump_text and len(dump_text) > 1:
                                        for line in dump_text:
                                            # Filter out some noisy rows if needed
                                            if not any(noise in line for noise in [
                                                'select a row', 'press the space bar',
                                                'To select', 'To deselect',
                                                'Column Settings'
                                            ]):
                                                sm37_log_text.append(line)
                                        break
                                except:
                                    continue
                            
                            if sm37_log_text:
                                screenshots["SM37_log_text"] = sm37_log_text
                                print(f"    ✓ SM37: {len(sm37_log_text)} lines captured")

                        # Special handling for DB02 (Initial screen and Overview screenshots)
                        if tcode == "DB02":
                            print("    Performing DB02 tree interaction & screenshots...")
                            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                            
                            # 1. Capture the default/initial screen (Missing Database Indexes)
                            init_shot = os.path.join(self.output_dir, f"DB02_{ts}.png")
                            await page.screenshot(path=init_shot)
                            screenshots[tcode] = init_shot
                            print("      ✓ Captured initial DB02 screen (Missing Indexes)")
                            
                            db02_extra_shots = []
                            db02_log_text = []
                            
                            # Extract log text from the initial screen for anomaly detection
                            for frame in page.frames:
                                try:
                                    dump_text = await frame.evaluate("""() => {
                                        const rows = document.querySelectorAll('tr');
                                        if (rows.length === 0) return null;
                                        return Array.from(rows).map(r => {
                                            return Array.from(r.querySelectorAll('td, th')).map(c => c.innerText.trim()).join(' | ');
                                        }).filter(t => t.length > 5);
                                    }""")
                                    if dump_text:
                                        db02_log_text.extend(dump_text)
                                except:
                                    pass
                            
                            # Helper to click a tree node container robustly by text
                            async def click_tree_node(frm, text, action_type="click"):
                                return await frm.evaluate("""([nodeText, actionType]) => {
                                    const xpath = `//span[text()="${nodeText}"] | //a[text()="${nodeText}"] | //div[text()="${nodeText}"]`;
                                    const result = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                                    
                                    for (let i = 0; i < result.snapshotLength; i++) {
                                        const el = result.snapshotItem(i);
                                        let current = el;
                                        let container = null;
                                        
                                        for (let d = 0; d < 6; d++) {
                                            if (!current) break;
                                            const className = current.className || '';
                                            const id = current.id || '';
                                            const tagName = current.tagName.toLowerCase();
                                            const role = current.getAttribute('role') || '';
                                            
                                            if (className.includes('TreeNode') || 
                                                className.includes('TreeItem') || 
                                                className.includes('TreeNodeName') ||
                                                id.includes('tree') || 
                                                role === 'treeitem' ||
                                                current.getAttribute('ct') === 'TreeNode') {
                                                container = current;
                                                break;
                                            }
                                            current = current.parentElement;
                                        }
                                        
                                        if (container) {
                                            const isExpanded = container.getAttribute('aria-expanded') === 'true' || 
                                                              container.className.includes('Expanded') || 
                                                              container.getAttribute('lsdata')?.includes('"expanded":true');
                                            
                                            if (actionType === 'expand' && isExpanded) {
                                                return 'already_expanded';
                                            }
                                            
                                            container.focus();
                                            
                                            const events = ['mousedown', 'mouseup', 'click'];
                                            for (const evName of events) {
                                                const ev = new MouseEvent(evName, {
                                                    bubbles: true,
                                                    cancelable: true,
                                                    view: window
                                                });
                                                container.dispatchEvent(ev);
                                            }
                                            
                                            if (actionType === 'dblclick' || (actionType === 'expand' && !isExpanded)) {
                                                const dbl = new MouseEvent('dblclick', {
                                                    bubbles: true,
                                                    cancelable: true,
                                                    view: window
                                                });
                                                container.dispatchEvent(dbl);
                                            }
                                            return actionType + '_dispatched';
                                        }
                                    }
                                    return 'not_found';
                                }""", [text, action_type])

                            # 2. Navigate tree to click 'Current Status' -> 'Overview'
                            try:
                                tree_frame = None
                                for frame in page.frames:
                                    try:
                                        has_tree = await frame.evaluate("() => document.body.innerText.includes('Current Status') && document.body.innerText.includes('Diagnostics')")
                                        if has_tree:
                                            tree_frame = frame
                                            break
                                    except:
                                        continue
                                
                                if tree_frame:
                                    print("      Found DB02 tree in frame:", tree_frame.name)
                                    
                                    # Expand 'Current Status' folder
                                    expand_res = await st03n_click_tree_node(tree_frame, "Current Status", "expand")
                                    print(f"      ✓ Clicked 'Current Status' expand: {expand_res}")
                                    await self._wait_for_sap_ready(page)
                                    dblclick_res = await st03n_click_tree_node(tree_frame, "Overview", "dblclick")
                                    print(f"      ✓ Double-clicked 'Overview': {dblclick_res}")
                                    
                                    # Wait for overview pane to load
                                    print("      Waiting for Overview pane to load...")
                                    await self._wait_for_sap_ready(page)
                                    try:
                                        await page.wait_for_load_state("networkidle", timeout=8000)
                                    except:
                                        pass
                                    await asyncio.sleep(2)
                                    
                                    # Capture Overview - Initial
                                    overview_init = os.path.join(self.output_dir, f"DB02_Overview_Init_{ts}.png")
                                    await page.screenshot(path=overview_init)
                                    db02_extra_shots.append(overview_init)
                                    print("      ✓ Captured Overview Initial screenshot")
                                    
                                    # Extract Overview screen text for anomaly detection
                                    try:
                                        dump_text = await tree_frame.evaluate("""() => {
                                            const elems = document.querySelectorAll('tr, div.urTxtStd, div.urTxtCaption');
                                            if (elems.length === 0) return null;
                                            return Array.from(elems).map(el => el.innerText.trim()).filter(t => t.length > 5);
                                        }""")
                                        if dump_text:
                                            db02_log_text.extend(dump_text)
                                    except Exception as e:
                                        print(f"      Error extracting Overview text: {e}")
                                    
                                    # ── DB02 Third Logic: SQL Editor Performance Graph ──
                                    try:
                                        print("      --- DB02 SQL Editor Graph ---")
                                        
                                        # 3a. Expand 'Diagnostics' folder
                                        diag_res = await st03n_click_tree_node(tree_frame, "Diagnostics", "expand")
                                        print(f"      ✓ Expanded 'Diagnostics': {diag_res}")
                                        await self._wait_for_sap_ready(page)
                                        sql_res = await st03n_click_tree_node(tree_frame, "SQL Editor", "dblclick")
                                        print(f"      ✓ Double-clicked 'SQL Editor': {sql_res}")
                                        
                                        print("      Waiting for SQL Editor pane to load...")
                                        await self._wait_for_sap_ready(page)
                                        try:
                                            await page.wait_for_load_state("networkidle", timeout=8000)
                                        except:
                                            pass
                                        await asyncio.sleep(3)
                                        
                                        # 3c. Input the SQL Query
                                        sql_query = """SELECT 
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
ORDER BY SNAPSHOT_ID DESC;"""

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
                                                    res = await frame.evaluate(f"""(query) => {{
                                                        const ta = document.querySelector('textarea');
                                                        if (ta && ta.offsetParent !== null) {{
                                                            ta.value = query;
                                                            ta.dispatchEvent(new Event('input', {{bubbles: true}}));
                                                            ta.dispatchEvent(new Event('change', {{bubbles: true}}));
                                                            return true;
                                                        }}
                                                        return false;
                                                    }}""", sql_query)
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
                                        await self._wait_for_sap_ready(page)
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
                                                data = await frame.evaluate("""() => {
                                                    const rows = document.querySelectorAll('tr');
                                                    const extracted = [];
                                                    for (const row of rows) {
                                                        const cells = Array.from(row.querySelectorAll('td, th')).map(c => c.innerText.trim());
                                                        if (cells.length >= 4) { 
                                                            let hasSnapshot = false;
                                                            for (let i = 0; i < cells.length; i++) {
                                                                if (cells[i].length > 12 && /^[0-9]+$/.test(cells[i])) {
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
                                                }""")
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
                                                # Fix x-axis ticks to avoid overlapping text
                                                step = max(1, len(timestamps) // 10)
                                                ax1.set_xticks(range(0, len(timestamps), step))
                                                ax1.set_xticklabels([timestamps[i] for i in range(0, len(timestamps), step)], rotation=45, ha='right')
                                                
                                                ax2 = ax1.twinx()
                                                color = 'tab:orange'
                                                ax2.set_ylabel('Memory Used GB', color=color)
                                                ax2.plot(timestamps, mem_usage, color=color, marker='x', label='Memory Used GB', linestyle='--')
                                                ax2.tick_params(axis='y', labelcolor=color)
                                                ax2.set_ylim(bottom=0)
                                                
                                                plt.title('Database Performance (Last 24 Hours)', pad=15)
                                                fig.tight_layout()
                                                plt.subplots_adjust(top=0.92, right=0.92, bottom=0.15)
                                                
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
                                        print(f"      ⚠ SQL Editor logic failed (non-fatal): {e}")
                                    
                                else:
                                    print("      WARNING: DB02 tree structure not found in any frame!")
                            except Exception as e:
                                print(f"      Error during DB02 tree interaction: {e}")
                            
                            if db02_extra_shots:
                                screenshots["DB02_pages"] = db02_extra_shots
                            if db02_log_text:
                                screenshots["DB02_log_text"] = db02_log_text
                            continue


                        # Special handling for execute-only transactions (just click Execute, no input)
                        if tcode in ("SM13", "SM58", "WE02", "SMQ1", "SMQ2"):
                            print(f"    Performing {tcode} interaction (Execute)...")
                            
                            # Click "Execute" text link at top-left
                            executed = False
                            for frame in page.frames:
                                try:
                                    exec_locator = frame.get_by_text("Execute", exact=True)
                                    count = await exec_locator.count()
                                    if count > 0:
                                        await exec_locator.first.click()
                                        print(f"    ✓ Clicked 'Execute' in frame '{frame.name}'")
                                        executed = True
                                        break
                                except:
                                    pass
                            
                            # Fallback: F8 keyboard
                            if not executed:
                                print("    Using F8 keyboard fallback...")
                                await page.keyboard.press("F8")
                            
                            # Wait for results
                            print(f"    Waiting for {tcode} results...")
                            await self._wait_for_sap_ready(page)
                            try:
                                await page.wait_for_load_state("networkidle", timeout=10000)
                            except:
                                pass
                            await asyncio.sleep(2)
                            print(f"    {tcode} interaction complete.")

                        # Special handling for ST22: Click Today, screenshot, go back, click Yesterday, screenshot
                        if tcode == "ST22":
                            print("    Performing ST22 interaction (Today + Yesterday dumps)...")
                            st22_screenshots = []
                            st22_log_text = []
                            
                            for day_label in ["Today", "Yesterday"]:
                                print(f"      Clicking '{day_label}'...")
                                clicked = False
                                
                                # Find and click the day button
                                for frame in page.frames:
                                    try:
                                        btn = frame.get_by_text(day_label, exact=True)
                                        count = await btn.count()
                                        if count > 0:
                                            await btn.first.click()
                                            print(f"      ✓ Clicked '{day_label}' in frame '{frame.name}'")
                                            clicked = True
                                            break
                                    except:
                                        pass
                                
                                if not clicked:
                                    # Fallback: JS click
                                    for frame in page.frames:
                                        try:
                                            result = await frame.evaluate(f"""() => {{
                                                const els = Array.from(document.querySelectorAll('a, button, span, td'));
                                                const btn = els.find(e => e.textContent.trim() === '{day_label}');
                                                if (btn) {{ btn.click(); return true; }}
                                                return false;
                                            }}""")
                                            if result:
                                                print(f"      ✓ Clicked '{day_label}' via JS")
                                                clicked = True
                                                break
                                        except:
                                            pass
                                
                                if not clicked:
                                    print(f"      ✗ Could not find '{day_label}' button")
                                    continue
                                
                                # Wait for results page
                                await self._wait_for_sap_ready(page)
                                try:
                                    await page.wait_for_load_state("networkidle", timeout=10000)
                                except:
                                    pass
                                await asyncio.sleep(3)
                                
                                # Take screenshot
                                ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                ss_path = os.path.join(self.output_dir, f"ST22_{day_label}_{ts}.png")
                                await page.screenshot(path=ss_path, full_page=False)
                                file_size = os.path.getsize(ss_path)
                                if file_size > 15000:
                                    st22_screenshots.append(ss_path)
                                    print(f"      Screenshot: {ss_path} ({file_size:,} bytes)")
                                
                                # Extract dump list text from frames
                                for frame in page.frames:
                                    try:
                                        dump_text = await frame.evaluate("""() => {
                                            const rows = document.querySelectorAll('tr');
                                            if (rows.length < 2) return null;
                                            return Array.from(rows).map(r => {
                                                return Array.from(r.querySelectorAll('td, th')).map(c => c.innerText.trim()).join(' | ');
                                            }).filter(t => t.length > 10);
                                        }""")
                                        if dump_text and len(dump_text) > 1:
                                            st22_log_text.append(f"--- {day_label} ---")
                                            for line in dump_text:
                                                if not any(noise in line for noise in [
                                                    'select a row', 'press the space bar',
                                                    'To select', 'To deselect',
                                                ]):
                                                    st22_log_text.append(line)
                                            break
                                    except:
                                        continue
                                
                                # Go back to initial screen (for Yesterday click)
                                if day_label == "Today":
                                    print("      Going back to ST22 initial screen...")
                                    # Press F3 (Back) or click Back arrow
                                    await page.keyboard.press("F3")
                                    await self._wait_for_sap_ready(page)
                                    try:
                                        await page.wait_for_load_state("networkidle", timeout=10000)
                                    except:
                                        pass
                                    await asyncio.sleep(2)
                            
                            # Store ST22 screenshots and text
                            if st22_screenshots:
                                screenshots[tcode] = st22_screenshots[0]
                                screenshots["ST22_pages"] = st22_screenshots
                                screenshots["ST22_log_text"] = st22_log_text
                                print(f"    ✓ ST22: {len(st22_screenshots)} pages, {len(st22_log_text)} lines captured")
                            
                            print("    ST22 interaction complete.")


                        if tcode == "ST03N":
                            print("    Performing ST03N tree interaction & screenshots...")
                            st03n_pages = []
                            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                            # Capture Initial Screen
                            init_path = os.path.join(self.output_dir, f"ST03N_{ts}.png")
                            await page.screenshot(path=init_path)
                            st03n_pages.append(init_path)
                            print("      ✓ Captured initial ST03N screen")
                            
                            try:
                                tree_frame = None
                                for f in page.frames:
                                    try:
                                        has_tree = await f.evaluate("() => document.body.innerText.includes('Workload') && document.body.innerText.includes('Total')")
                                        if has_tree:
                                            tree_frame = f
                                            break
                                    except:
                                        continue
                                
                                if tree_frame:
                                    print("      Found ST03N tree frame.")
                                    # 1. Expand "Workload"
                                    await st03n_click_tree_node(tree_frame, "Workload", "expand")
                                    await asyncio.sleep(2)
                                    # 2. Expand "Total"
                                    await st03n_click_tree_node(tree_frame, "Total", "expand")
                                    await asyncio.sleep(2)
                                    # 3. Expand "Day"
                                    await st03n_click_tree_node(tree_frame, "Day", "expand")
                                    await asyncio.sleep(3)
                                    
                                    # Click "Yesterday"
                                    res_date = await tree_frame.evaluate(r'''() => {
                                        let allSpans = document.querySelectorAll('span');
                                        let dateNodes = [];
                                        for (let s of allSpans) {
                                            if (/^[0-9]{2}\.[0-9]{2}\.[0-9]{4}$/.test(s.innerText.trim())) {
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
                                    
                                    print("      Checking for calculation popup...")
                                    await self._wait_for_sap_ready(page)
                                    popup_clicked = False
                                    
                                    # Use JS to reliably find the exact Dialog button and tag it
                                    try:
                                        has_btn = await tree_frame.evaluate('''() => {
                                            let buttons = document.querySelectorAll('span, div');
                                            for (let b of buttons) {
                                                if (b.innerText && b.innerText.trim() === 'Dialog') {
                                                    let btn = b.closest('.lsButton') || b.closest('.urBtnStd') || b;
                                                    btn.id = "my-unique-dialog-btn";
                                                    return true;
                                                }
                                            }
                                            return false;
                                        }''')
                                        if has_btn:
                                            # Use Playwright's native locator to physically click the exact element
                                            await tree_frame.locator('#my-unique-dialog-btn').click(force=True)
                                            popup_clicked = True
                                        else:
                                            # Fallback to main page frame
                                            has_btn_main = await page.evaluate('''() => {
                                                let buttons = document.querySelectorAll('span, div');
                                                for (let b of buttons) {
                                                    if (b.innerText && b.innerText.trim() === 'Dialog') {
                                                        let btn = b.closest('.lsButton') || b.closest('.urBtnStd') || b;
                                                        btn.id = "my-unique-dialog-btn";
                                                        return true;
                                                    }
                                                }
                                                return false;
                                            }''')
                                            if has_btn_main:
                                                await page.locator('#my-unique-dialog-btn').click(force=True)
                                                popup_clicked = True
                                    except Exception as e:
                                        print("      Popup logic failed:", e)
                                    if popup_clicked:
                                        print("      ✓ Clicked 'Dialog' to calculate data. Waiting dynamically for processing to finish...")
                                        # Poll up to 120 seconds (60 iterations of 2s) for the popup to disappear
                                        for _ in range(60):
                                            await asyncio.sleep(2)
                                            still_there = await tree_frame.evaluate('''() => {
                                                let buttons = document.querySelectorAll('span, div');
                                                for (let b of buttons) {
                                                    if (b.innerText && b.innerText.trim() === 'Dialog') return true;
                                                }
                                                return false;
                                            }''')
                                            if not still_there:
                                                print("      ✓ Calculation finished. Popup disappeared.")
                                                break
                                    print("      Waiting for Workload Overview to load...")
                                    await self._wait_for_sap_ready(page)
                                    try:
                                        await page.wait_for_load_state("networkidle", timeout=8000)
                                    except:
                                        pass
                                    # --- ALV Grid Sorting & Anomaly Extraction ---
                                    print("      Sorting Response Time (ms) column descending...")
                                    try:
                                        # Click the column header to select it
                                        await tree_frame.locator('span:has-text("Response Time (ms)")').first.click(force=True)
                                        await asyncio.sleep(1)
                                        # Click the Sort Descending button in the ALV toolbar
                                        await tree_frame.locator('[title*="Descending"]').first.click(force=True)
                                        await asyncio.sleep(3) # Wait for table to sort
                                    except Exception as e:
                                        print("      Failed to sort ALV grid:", e)
                                        
                                    ov_path = os.path.join(self.output_dir, f"ST03N_Overview_{ts}.png")
                                    await page.screenshot(path=ov_path)
                                    st03n_pages.append(ov_path)
                                    print("      ✓ Captured Workload Overview (Sorted)")
                                    
                                    # DEBUG: Dump the raw text to see why the regex failed
                                    raw_body_text = await tree_frame.evaluate('() => document.body.innerText')
                                    try:
                                        with open(os.path.join(self.output_dir, 'st03n_debug.txt'), 'w', encoding='utf-8') as f:
                                            f.write(raw_body_text or "EMPTY")
                                    except:
                                        pass

                                    # Scrape DIALOG response time using raw text regex
                                    dialog_rt_str = await tree_frame.evaluate('''() => {
                                        let match = document.body.innerText.match(/DIALOG\\s+([\\d\\.,]+)\\s+([\\d\\.,]+)/);
                                        if (match) {
                                            return match[2]; 
                                        }
                                        return null;
                                    }''')
                                    
                                    if dialog_rt_str:
                                        try:
                                            # Convert European format (e.g. 1.403,5) to float (1403.5)
                                            val_str = dialog_rt_str.replace('.', '').replace(',', '.')
                                            dialog_rt_val = float(val_str)
                                            print(f"      Scraped DIALOG Response Time: {dialog_rt_val} ms")
                                            if dialog_rt_val > 1500.0:
                                                anomaly_msg = f"Critical Anomaly: DIALOG average response time is {dialog_rt_val} ms, which exceeds the 1500 ms threshold."
                                                print(f"      {anomaly_msg}")
                                                self.screenshots['ST03N_anomalies'] = [anomaly_msg]
                                        except Exception as e:
                                            print("      Failed to parse DIALOG response time:", e)
                                    
                                    # 1. Expand "Transaction Profile"
                                    await st03n_click_tree_node(tree_frame, "Transaction Profile", "expand")
                                    await asyncio.sleep(2)
                                    # 2. Double-click "Standard"
                                    await st03n_click_tree_node(tree_frame, "Standard", "dblclick")
                                    print("      ✓ Double-clicked 'Standard' transaction profile")
                                    
                                    print("      Waiting for Transaction Profile to load...")
                                    await self._wait_for_sap_ready(page)
                                    try:
                                        await page.wait_for_load_state("networkidle", timeout=8000)
                                    except:
                                        pass
                                        
                                    tp_path = os.path.join(self.output_dir, f"ST03N_TransactionProfile_{ts}.png")
                                    await page.screenshot(path=tp_path)
                                    st03n_pages.append(tp_path)
                                    print("      ✓ Captured Transaction Profile")
                                    
                                    # Time Profile
                                    await st03n_click_tree_node(tree_frame, "Time Profile", "dblclick")
                                    print("      ✓ Double-clicked 'Time Profile'")
                                    
                                    print("      Waiting for Time Profile to load...")
                                    await self._wait_for_sap_ready(page)
                                    try:
                                        await page.wait_for_load_state("networkidle", timeout=8000)
                                    except:
                                        pass
                                        
                                    timep_path = os.path.join(self.output_dir, f"ST03N_TimeProfile_{ts}.png")
                                    await page.screenshot(path=timep_path)
                                    st03n_pages.append(timep_path)
                                    print("      ✓ Captured Time Profile")
                                    
                                    # Response Time Distribution
                                    await st03n_click_tree_node(tree_frame, "Response Time Distribution", "dblclick")
                                    print("      ✓ Double-clicked 'Response Time Distribution'")
                                    
                                    print("      Waiting for Response Time Distribution to load...")
                                    await self._wait_for_sap_ready(page)
                                    try:
                                        await page.wait_for_load_state("networkidle", timeout=8000)
                                    except:
                                        pass
                                        
                                    rtd_path = os.path.join(self.output_dir, f"ST03N_ResponseTimeDist_{ts}.png")
                                    await page.screenshot(path=rtd_path)
                                    st03n_pages.append(rtd_path)
                                    print("      ✓ Captured Response Time Distribution")
                                    
                            except Exception as e:
                                print(f"      ⚠ ST03N detailed capture failed: {e}")
                            
                            if st03n_pages:
                                screenshots[tcode] = st03n_pages[0]
                                screenshots["ST03N_pages"] = st03n_pages
                            print("    ST03N interaction complete.")

                        if tcode == "SCC4":
                            print("    Performing SCC4 specific interaction...")
                            scc4_pages = []
                            scc4_anomalies = []
                            
                            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                            
                            # 1. Take initial overview screenshot
                            init_path = os.path.join(self.output_dir, f"SCC4_Overview_{ts}.png")
                            await page.screenshot(path=init_path)
                            scc4_pages.append(init_path)
                            print("      ✓ Captured initial SCC4 screen")
                            
                            try:
                                # 2. Double click the first row
                                clicked = False
                                for frame in page.frames:
                                    try:
                                        res = await frame.evaluate("""() => {
                                            const cells = document.querySelectorAll('span, div');
                                            for (let c of cells) {
                                                if (c.innerText && (c.innerText.trim() === '000' || c.innerText.trim().match(/^\\d{3}$/))) {
                                                    const events = ['mousedown', 'mouseup', 'click', 'dblclick'];
                                                    for (const evName of events) {
                                                        const ev = new MouseEvent(evName, {
                                                            bubbles: true,
                                                            cancelable: true,
                                                            view: window
                                                        });
                                                        c.dispatchEvent(ev);
                                                    }
                                                    return true;
                                                }
                                            }
                                            return false;
                                        }""")
                                        if res:
                                            clicked = True
                                            print(f"      ✓ Double-clicked first client row in frame: {frame.name}")
                                            break
                                    except:
                                        continue
                                
                                if clicked:
                                    print("      Waiting for Details screen to load...")
                                    await self._wait_for_sap_ready(page)
                                    last_client_num = None
                                    
                                    for i in range(15):
                                        try:
                                            await page.wait_for_load_state("networkidle", timeout=5000)
                                        except:
                                            pass
                                            
                                        detail_ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                                        detail_path = os.path.join(self.output_dir, f"SCC4_ClientDetail_{i}_{detail_ts}.png")
                                        await page.screenshot(path=detail_path)
                                        scc4_pages.append(detail_path)
                                        client_info = None
                                        for frame in page.frames:
                                            try:
                                                client_info = await frame.evaluate("""() => {
                                                    let clientInput = document.querySelector('input[title="Client"]');
                                                    if (!clientInput) return null;
                                                    
                                                    let clientNum = clientInput.value || 'Unknown';
                                                    
                                                    let changesAllowed = "Unknown";
                                                    let rb = document.querySelector('[role="radio"][aria-checked="true"]');
                                                    if (rb) { changesAllowed = rb.getAttribute('aria-label') || rb.innerText; }
                                                    
                                                    let crossClient = "Unknown";
                                                    let sel1 = document.querySelector('input[title="Maintenance authorization for objects in all clients"]');
                                                    if (sel1) { crossClient = sel1.value; }
                                                    
                                                    let protection = "Unknown";
                                                    let sel2 = document.querySelector('input[title="Protection reg. client copy program and comparison tools"]');
                                                    if (sel2) { protection = sel2.value; }
                                                    
                                                    let ecatt = "Unknown";
                                                    let sel3 = document.querySelector('input[title="Client Control: CATT und eCATT Start Authorization"]');
                                                    if (sel3) { ecatt = sel3.value; }
                                                    
                                                    return {
                                                        client: clientNum,
                                                        changes: changesAllowed,
                                                        cross: crossClient,
                                                        protection: protection,
                                                        ecatt: ecatt
                                                    };
                                                }""")
                                                if client_info:
                                                    break
                                            except:
                                                continue
                                                
                                        if client_info:
                                            if client_info['client'] == last_client_num:
                                                print("      Reached end of clients list (Client number stopped changing).")
                                                # Remove the duplicate screenshot that was just taken
                                                scc4_pages.pop()
                                                if os.path.exists(detail_path):
                                                    try: os.remove(detail_path)
                                                    except: pass
                                                break
                                            last_client_num = client_info['client']
                                            
                                            print(f"      ✓ Extracted Client {client_info['client']}:")
                                            print(f"        Changes: {client_info['changes']}")
                                            print(f"        Cross-Client: {client_info['cross']}")
                                            print(f"        Protection: {client_info['protection']}")
                                            print(f"        eCATT: {client_info['ecatt']}")
                                            
                                            anomalies = []
                                            if "no changes allowed" not in client_info['changes'].lower():
                                                anomalies.append(f"Client {client_info['client']}: Changes and Transports -> {client_info['changes']} (Expected: No changes allowed)")
                                            if "no changes to repository" not in client_info['cross'].lower():
                                                anomalies.append(f"Client {client_info['client']}: Cross-Client Object Changes -> {client_info['cross']} (Expected: No changes to repository...)")
                                            if "protection level 1" not in client_info['protection'].lower():
                                                anomalies.append(f"Client {client_info['client']}: Protection -> {client_info['protection']} (Expected: Protection level 1: No overwriting)")
                                            if "ecatt and catt not allowed" not in client_info['ecatt'].lower():
                                                anomalies.append(f"Client {client_info['client']}: eCATT Restrictions -> {client_info['ecatt']} (Expected: eCATT and CATT not allowed)")
                                                
                                            if anomalies:
                                                scc4_anomalies.extend(anomalies)
                                        else:
                                            print("      ⚠ Could not extract client details.")
                                            
                                        # Click Next Entry
                                        next_clicked = False
                                        for frame in page.frames:
                                            try:
                                                res = await frame.evaluate("""() => {
                                                    const nextBtn = document.querySelector('[title="Next Entry (F8)"]');
                                                    if (nextBtn) {
                                                        if (nextBtn.className.includes('Dsbl') || nextBtn.getAttribute('aria-disabled') === 'true') {
                                                            return 'disabled';
                                                        }
                                                        const events = ['mousedown', 'mouseup', 'click'];
                                                        for (const evName of events) {
                                                            const ev = new MouseEvent(evName, { bubbles: true, cancelable: true, view: window });
                                                            nextBtn.dispatchEvent(ev);
                                                        }
                                                        return 'clicked';
                                                    }
                                                    return 'not_found';
                                                }""")
                                                if res == 'clicked':
                                                    next_clicked = True
                                                    break
                                                elif res == 'disabled':
                                                    next_clicked = 'disabled'
                                                    break
                                            except:
                                                continue
                                                
                                        if next_clicked == True:
                                            print("      ✓ Clicked 'Next Entry'")
                                            await asyncio.sleep(3)
                                        elif next_clicked == 'disabled':
                                            print("      Next Entry button is disabled. Reached last client.")
                                            break
                                        else:
                                            print("      Next Entry button not found. Assuming end of list.")
                                            break
                                        
                            except Exception as e:
                                print(f"      ⚠ SCC4 detailed capture failed: {e}")
                                
                            if scc4_pages:
                                screenshots[tcode] = scc4_pages[0]
                                screenshots["SCC4_pages"] = scc4_pages
                            if scc4_anomalies:
                                screenshots["SCC4_anomalies"] = scc4_anomalies
                            print("    SCC4 interaction complete.")

                        if tcode == "SMLG":
                            print("    Performing SMLG specific interaction...")
                            smlg_pages = []
                            smlg_anomalies = []
                            
                            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                            
                            # 1. Take initial overview screenshot
                            init_path = os.path.join(self.output_dir, f"SMLG_Overview_{ts}.png")
                            await page.screenshot(path=init_path)
                            smlg_pages.append(init_path)
                            print("      ✓ Captured initial SMLG screen")
                            
                            try:
                                # 2. Click Load Distribution button
                                clicked = False
                                for frame in page.frames:
                                    try:
                                        res = await frame.evaluate("""() => {
                                            const btn = document.querySelector('[title="Load distribution (F5)"]');
                                            if (btn) {
                                                const events = ['mousedown', 'mouseup', 'click'];
                                                for (const evName of events) {
                                                    const ev = new MouseEvent(evName, { bubbles: true, cancelable: true, view: window });
                                                    btn.dispatchEvent(ev);
                                                }
                                                return true;
                                            }
                                            return false;
                                        }""")
                                        if res:
                                            clicked = True
                                            break
                                    except:
                                        continue
                                        
                                if clicked:
                                    print("      ✓ Clicked 'Load distribution'")
                                    await self._wait_for_sap_ready(page)
                                    try:
                                        await page.wait_for_load_state("networkidle", timeout=5000)
                                    except:
                                        pass
                                        
                                    load_dist_path = os.path.join(self.output_dir, f"SMLG_LoadDistribution_{ts}.png")
                                    await page.screenshot(path=load_dist_path)
                                    smlg_pages.append(load_dist_path)
                                    print("      ✓ Captured Load distribution screen")
                                    
                                    # Dump DOM to file for debugging
                                    for frame in page.frames:
                                        try:
                                            # We use innerText to capture the formatted visual representation of the ALV grid
                                            inner_text = await frame.evaluate("() => document.body.innerText")
                                            if inner_text and "Dialog steps" in inner_text and "* Summary" in inner_text:
                                                import re
                                                # Extract the text between "Dialog steps" and "* Summary"
                                                match = re.search(r"Dialog steps(.*?)\*\s*Summary", inner_text, re.IGNORECASE | re.DOTALL)
                                                if match:
                                                    raw_data = match.group(1).strip()
                                                    # Look for pattern: <ServerName> <ResponseTime> <Threshold> <Time>
                                                    # e.g., nwrhel9_F4H_00           34  13 12:24:19
                                                    rows = re.findall(r"([a-zA-Z0-9_]+)\s+(\d+)\s+\d+\s+\d{1,2}:\d{2}:\d{2}", raw_data)
                                                    for server, resp_time in rows:
                                                        resp_time_int = int(resp_time)
                                                        print(f"      ✓ Parsed SMLG Server: {server} | Response Time: {resp_time_int}ms")
                                                        if resp_time_int > 1000:
                                                            smlg_anomalies.append(f"Server {server}: Response time is {resp_time_int}ms (Expected: < 1000ms)")
                                                    if rows:
                                                        break
                                        except Exception as e:
                                            print(f"      ⚠ Failed to parse text in frame: {e}")
                                            continue
                                            
                                    print("      ✓ Completed SMLG Load Distribution parsing")
                                    
                                else:
                                    print("      ⚠ 'Load distribution' button not found.")
                            except Exception as e:
                                print(f"      ⚠ SMLG detailed capture failed: {e}")
                                
                            if smlg_pages:
                                screenshots[tcode] = smlg_pages[0]
                                screenshots["SMLG_pages"] = smlg_pages
                            if smlg_anomalies:
                                screenshots["SMLG_anomalies"] = smlg_anomalies
                            print("    SMLG interaction complete.")

                        if tcode == "SMGW":
                            print("    Performing SMGW specific interaction...")
                            smgw_anomalies = []

                            ts = datetime.now().strftime("%Y%m%d_%H%M%S")

                            # 1. Take screenshot of current active connections screen
                            smgw_path = os.path.join(self.output_dir, f"SMGW_Overview_{ts}.png")
                            await page.screenshot(path=smgw_path)
                            smgw_pages = [smgw_path]
                            screenshots[tcode] = smgw_path
                            print("      ✓ Captured SMGW Active Connections screen")
                            
                            # 2. Navigate to Logged on Clients via More -> Goto -> Logged on Clients
                            try:
                                clicked = False
                                for frame in page.frames:
                                    try:
                                        res = await frame.evaluate("""() => {
                                            let more = Array.from(document.querySelectorAll('span, div, a')).find(e => e.innerText && e.innerText.trim() === 'More');
                                            if (more) { more.click(); return true; }
                                            return false;
                                        }""")
                                        if res: 
                                            clicked = True
                                            break
                                    except: pass
                                
                                if clicked:
                                    await page.wait_for_timeout(1000)
                                    for frame in page.frames:
                                        try:
                                            await frame.evaluate("""() => {
                                                let gotoMenu = Array.from(document.querySelectorAll('span, div, td')).find(e => e.innerText && e.innerText.trim() === 'Goto');
                                                if (gotoMenu) gotoMenu.click();
                                            }""")
                                        except: pass
                                    await page.wait_for_timeout(1000)
                                    for frame in page.frames:
                                        try:
                                            await frame.evaluate("""() => {
                                                let loggedOn = Array.from(document.querySelectorAll('span, div, td')).find(e => e.innerText && e.innerText.trim() === 'Logged on Clients');
                                                if (loggedOn) loggedOn.click();
                                            }""")
                                        except: pass
                                    await page.wait_for_timeout(2000)
                                    
                                    clients_path = os.path.join(self.output_dir, f"SMGW_Clients_{ts}.png")
                                    await page.screenshot(path=clients_path)
                                    smgw_pages.append(clients_path)
                                    print("      ✓ Captured SMGW Logged on Clients screen")
                                else:
                                    print("      ⚠ 'More' menu not found in SMGW")
                            except Exception as e:
                                print(f"      ⚠ Failed to navigate to Logged on Clients: {e}")


                            # 2. Scrape connection statuses from the ALV grid via innerText
                            try:
                                for frame in page.frames:
                                    try:
                                        inner_text = await frame.evaluate("() => document.body.innerText")
                                        if inner_text and "Connection Status" in inner_text:
                                            import re
                                            # Extract section between the header row and end-of-grid
                                            # Look for rows containing known status values after the header
                                            bad_statuses = ["disconnecting", "error", "broken", "rejected"]
                                            # Find lines that contain a known bad status keyword
                                            lines = inner_text.splitlines()
                                            for line in lines:
                                                line_lower = line.lower()
                                                for bad in bad_statuses:
                                                    if bad in line_lower:
                                                        # Try to extract a server/LU name from the line
                                                        # Lines typically look like: RLPDWRQW Python nwrhel9... disconnecting NWRFC ...
                                                        parts = line.split()
                                                        server_name = ""
                                                        for part in parts:
                                                            if "." in part or "_" in part or len(part) > 6:
                                                                server_name = part
                                                                break
                                                        status_word = bad.capitalize()
                                                        entry = f"Gateway Connection: {server_name or 'Unknown'} — Status '{status_word}' detected (Expected: Connected)"
                                                        if entry not in smgw_anomalies:
                                                            smgw_anomalies.append(entry)
                                                        break
                                            if smgw_anomalies or "Connection Status" in inner_text:
                                                break
                                    except:
                                        continue
                                print(f"      ✓ SMGW connection scan complete. Anomalies found: {len(smgw_anomalies)}")
                            except Exception as e:
                                print(f"      ⚠ SMGW DOM scraping failed: {e}")

                            if smgw_anomalies:
                                screenshots["SMGW_anomalies"] = smgw_anomalies
                            screenshots["SMGW_pages"] = smgw_pages
                            print("    SMGW interaction complete.")

                        if tcode == "SMICM":
                            print("    Performing SMICM specific interaction...")
                            smicm_pages = []
                            smicm_anomalies = []

                            ts = datetime.now().strftime("%Y%m%d_%H%M%S")

                            # 1. Take initial ICM Monitor overview screenshot
                            init_path = os.path.join(self.output_dir, f"SMICM_Overview_{ts}.png")
                            await page.screenshot(path=init_path)
                            smicm_pages.append(init_path)
                            print("      ✓ Captured SMICM initial screen")

                            try:
                                # 2. Click 'Services (Shift F1)' button
                                clicked = False
                                for frame in page.frames:
                                    try:
                                        res = await frame.evaluate("""() => {
                                            // Try by title attribute first
                                            let btn = document.querySelector('[title="Services (Shift+F1)"]') ||
                                                      document.querySelector('[title="Services (Shift F1)"]') ||
                                                      document.querySelector('[title="Services"]');
                                            
                                            // Also look by innerText
                                            if (!btn) {
                                                btn = Array.from(document.querySelectorAll('div, span, td')).find(
                                                    e => e.innerText && e.innerText.trim() === 'Services'
                                                );
                                            }
                                            
                                            if (btn) {
                                                btn.click();
                                                return true;
                                            }
                                            return false;
                                        }""")
                                        if res:
                                            clicked = True
                                            break
                                    except Exception as ex:
                                        pass
                                
                                if clicked:
                                    await page.wait_for_timeout(3000)
                                    services_path = os.path.join(self.output_dir, f"SMICM_Services_{ts}.png")
                                    await page.screenshot(path=services_path)
                                    smicm_pages.append(services_path)
                                    print("      ✓ Captured ICM Services screen")

                                    # 3. Inspect active state using SAP ALV absolute coordinate parsing
                                    # ALV renders cells as absolute positioned divs, e.g., style="top: 135px; left: 80px;"
                                    # The 'Actv' checkmark is an SVG with xlink:href="#_SAPGUI-icons_0_s_s_okay"
                                    for frame in page.frames:
                                        try:
                                            service_data = await frame.evaluate("""() => {
                                                const divs = Array.from(document.querySelectorAll('div[style*="top:"]'));
                                                
                                                // Find column X (left) coordinates from headers
                                                let protoX = null;
                                                let portX = null;
                                                let actvX = null;
                                                
                                                for (const div of divs) {
                                                    const text = div.innerText.trim();
                                                    if (!text) continue;
                                                    const match = div.style.left.match(/(\\d+)px/);
                                                    if (!match) continue;
                                                    const left = parseInt(match[1], 10);
                                                    
                                                    if (text === 'Protocol') protoX = left;
                                                    if (text === 'Service Name/Port') portX = left;
                                                    if (text === 'Actv') actvX = left;
                                                }
                                                
                                                if (protoX === null || actvX === null) return { error: 'Headers not found' };

                                                // Find all protocol values and their Y (top) coordinates
                                                const servicesMap = {};
                                                for (const div of divs) {
                                                    const text = div.innerText.trim();
                                                    if (/^(HTTPS?|SMTP|FTP|IIOP)$/i.test(text)) {
                                                        const leftMatch = div.style.left.match(/(\\d+)px/);
                                                        const topMatch = div.style.top.match(/(\\d+)px/);
                                                        if (leftMatch && topMatch) {
                                                            const left = parseInt(leftMatch[1], 10);
                                                            const top = parseInt(topMatch[1], 10);
                                                            // Provide a small tolerance for left coordinate (SAP ALV can be slightly off)
                                                            if (Math.abs(left - protoX) < 10) {
                                                                servicesMap[top] = { proto: text, port: '?', isActive: false };
                                                            }
                                                        }
                                                    }
                                                }

                                                // Extract ports and checkmarks using the Y coordinates
                                                for (const div of divs) {
                                                    const topMatch = div.style.top.match(/(\\d+)px/);
                                                    const leftMatch = div.style.left.match(/(\\d+)px/);
                                                    if (!topMatch || !leftMatch) continue;
                                                    
                                                    const top = parseInt(topMatch[1], 10);
                                                    const left = parseInt(leftMatch[1], 10);
                                                    
                                                    if (servicesMap[top]) {
                                                        // Check for Port
                                                        if (portX !== null && Math.abs(left - portX) < 10) {
                                                            if (div.innerText.trim()) {
                                                                servicesMap[top].port = div.innerText.trim();
                                                            }
                                                        }
                                                        
                                                        // Check for Actv checkmark
                                                        // ALV cell might be a div containing the SVG, or empty
                                                        if (Math.abs(left - actvX) < 10) {
                                                            const html = div.innerHTML;
                                                            if (html.includes('s_s_okay') || html.includes('s_b_chck')) {
                                                                servicesMap[top].isActive = true;
                                                            }
                                                        }
                                                    }
                                                }

                                                return { services: Object.values(servicesMap) };
                                            }""")

                                            if service_data and service_data.get('services'):
                                                for svc in service_data['services']:
                                                    print(f"      ✓ Service: {svc['proto']} port {svc['port']} | Active={svc['isActive']}")
                                                    if svc['isActive'] is False:
                                                        entry = f"ICM Service {svc['proto']} (Port {svc['port']}): Inactive (Expected: Active)"
                                                        if entry not in smicm_anomalies:
                                                            smicm_anomalies.append(entry)
                                                break
                                        except Exception as ex:
                                            print(f"      ⚠ Frame JS eval error: {ex}")
                                            continue


                                    print(f"      ✓ SMICM services scan complete. Anomalies: {len(smicm_anomalies)}")
                                else:
                                    print("      ⚠ 'Services' button not found in SMICM")

                            except Exception as e:
                                screenshots["SMICM_pages"] = smicm_pages
                            if smicm_anomalies:
                                screenshots["SMICM_anomalies"] = smicm_anomalies
                            print("    SMICM interaction complete.")

                        if tcode == "STRUST":
                            print("    Performing STRUST specific interaction...")
                            strust_anomalies = []
                            strust_pages = []
                            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                            
                            init_path = os.path.join(self.output_dir, f"STRUST_Overview_{ts}.png")
                            await page.screenshot(path=init_path)
                            strust_pages.append(init_path)
                            screenshots[tcode] = init_path
                            print("      ✓ Captured STRUST initial screen")
                            
                            # Helper for date parsing
                            def parse_date(date_str):
                                date_str = date_str.strip()
                                for fmt in ("%d.%m.%Y", "%Y/%m/%d", "%Y-%m-%d"):
                                    try:
                                        return datetime.strptime(date_str, fmt)
                                    except ValueError:
                                        pass
                                return None
                            
                            thirty_days_from_now = datetime.now() + timedelta(days=30)
                            
                            try:
                                for frame in page.frames:
                                    try:
                                        # 1. Identify active PSEs (they have a folder icon, not a red X)
                                        active_pses = await frame.evaluate("""() => {
                                            let rows = Array.from(document.querySelectorAll('tr[id*="Row-"]'));
                                            let pses = [];
                                            for (let row of rows) {
                                                if (row.innerHTML.includes('s_folder')) {
                                                    let textNode = row.querySelector('.lsTextView--nowrap');
                                                    if (textNode && textNode.innerText.trim()) {
                                                        pses.push(textNode.innerText.trim());
                                                    }
                                                }
                                            }
                                            return pses;
                                        }""")
                                        
                                        if active_pses:
                                            print(f"      ✓ Found {len(active_pses)} Active PSEs.")
                                            
                                            # 2. Iterate each active PSE
                                            for pse in active_pses:
                                                print(f"      Checking PSE: {pse}")
                                                
                                                # Double click the PSE node
                                                await frame.evaluate("""(name) => {
                                                    let nodes = Array.from(document.querySelectorAll('.lsTextView--nowrap'));
                                                    let node = nodes.find(n => n.innerText.trim() === name);
                                                    if (node) {
                                                        let ev = new MouseEvent('dblclick', { bubbles: true, cancelable: true, view: window });
                                                        node.click();
                                                        node.dispatchEvent(ev);
                                                    }
                                                }""", pse)
                                                
                                                # Wait for the certificate list to load
                                                await page.wait_for_timeout(3000)
                                                
                                                # 3. Parse the Certificate List (ALV Grid)
                                                # Handle scrolling if needed (scroll down 2 times just in case)
                                                for _ in range(3):
                                                    certs = await frame.evaluate("""() => {
                                                        const divs = Array.from(document.querySelectorAll('div[style*="top:"]'));
                                                        let validToX = null;
                                                        let ownerX = null;
                                                        
                                                        for (const div of divs) {
                                                            const text = div.innerText.trim();
                                                            if (text === 'Valid To') {
                                                                const match = div.style.left.match(/(\\d+)px/);
                                                                if (match) validToX = parseInt(match[1], 10);
                                                            }
                                                            if (text === 'Owner') {
                                                                const match = div.style.left.match(/(\\d+)px/);
                                                                if (match) ownerX = parseInt(match[1], 10);
                                                            }
                                                        }
                                                        
                                                        if (validToX === null) {
                                                            // Fallback for standard HTML tables
                                                            let trs = Array.from(document.querySelectorAll('tr'));
                                                            let results = [];
                                                            for(let tr of trs) {
                                                                if(tr.innerText.includes('Valid To')) continue;
                                                                let tds = Array.from(tr.querySelectorAll('td'));
                                                                // Usually Owner is col 0, Valid To is col 4 or 5. Look for date pattern.
                                                                for (let td of tds) {
                                                                    if (td.innerText.match(/\\d{2}\\.\\d{2}\\.\\d{4}/)) {
                                                                        results.push({owner: tds[0].innerText.trim(), validTo: td.innerText.trim()});
                                                                        break;
                                                                    }
                                                                }
                                                            }
                                                            return results;
                                                        }

                                                        const certMap = {};
                                                        for (const div of divs) {
                                                            const topMatch = div.style.top.match(/(\\d+)px/);
                                                            const leftMatch = div.style.left.match(/(\\d+)px/);
                                                            if (!topMatch || !leftMatch) continue;
                                                            
                                                            const top = parseInt(topMatch[1], 10);
                                                            const left = parseInt(leftMatch[1], 10);
                                                            
                                                            if (!certMap[top]) certMap[top] = { owner: 'Unknown', validTo: '' };
                                                            
                                                            if (Math.abs(left - validToX) < 10) {
                                                                if(div.innerText.trim()) certMap[top].validTo = div.innerText.trim();
                                                            }
                                                            if (ownerX !== null && Math.abs(left - ownerX) < 10) {
                                                                if(div.innerText.trim()) certMap[top].owner = div.innerText.trim();
                                                            }
                                                        }
                                                        
                                                        return Object.values(certMap).filter(c => c.validTo.match(/\\d{2}\\.\\d{2}\\.\\d{4}/));
                                                    }""")
                                                    
                                                    anomaly_found = False
                                                    if certs:
                                                        for cert in certs:
                                                            cert_date = parse_date(cert['validTo'])
                                                            if cert_date:
                                                                # Check expiration
                                                                if cert_date <= thirty_days_from_now:
                                                                    entry = f"STRUST: PSE '{pse}' Certificate '{cert['owner']}' is expired or expiring soon (Valid To: {cert['validTo']})"
                                                                    if entry not in strust_anomalies:
                                                                        strust_anomalies.append(entry)
                                                                        anomaly_found = True
                                                                        print(f"      ⚠ Anomaly Found: {entry}")
                                                    
                                                    # If anomaly found, take a screenshot of the current view showing this PSE and certificates
                                                    if anomaly_found:
                                                        pse_path = os.path.join(self.output_dir, f"STRUST_Anomaly_{ts}.png")
                                                        await page.screenshot(path=pse_path)
                                                        strust_pages.append(pse_path)
                                                        # Break the scroll loop, we found an anomaly on this PSE
                                                        break
                                                    
                                                    # Try scrolling the certificate list
                                                    scrolled = await frame.evaluate("""() => {
                                                        let grid = document.querySelector('.urST5BaseBorder');
                                                        if (grid && grid.scrollTop < grid.scrollHeight - grid.clientHeight) {
                                                            grid.scrollTop += grid.clientHeight;
                                                            return true;
                                                        }
                                                        return false;
                                                    }""")
                                                    if scrolled:
                                                        await page.wait_for_timeout(1000)
                                                    else:
                                                        break
                                        break
                                    except Exception as ex:
                                        pass
                            except Exception as e:
                                print(f"      ⚠ STRUST interaction failed: {e}")

                            screenshots["STRUST_pages"] = strust_pages
                            if strust_anomalies:
                                screenshots["STRUST_anomalies"] = strust_anomalies
                            print("    STRUST interaction complete.")

                        # Verify the page loaded
                        new_title = await page.title()
                        print(f"    Page title: {new_title}")
                        
                        if tcode == "SM21" and "SM21" in screenshots:
                            print(f"    SM21 already captured via scroll handler")
                            continue
                        
                        if tcode == "ST22" and "ST22" in screenshots:
                            print(f"    ST22 already captured via Today/Yesterday handler")
                            continue
                            
                        if tcode == "ST03N" and "ST03N" in screenshots:
                            print(f"    ST03N already captured via ST03N handler")
                            continue
                            
                        if tcode == "SCC4" and "SCC4" in screenshots:
                            print(f"    SCC4 already captured via SCC4 handler")
                            continue
                            
                        if tcode == "SMLG" and "SMLG" in screenshots:
                            print(f"    SMLG already captured via SMLG handler")
                            continue

                        if tcode == "SMGW" and "SMGW" in screenshots:
                            print(f"    SMGW already captured via SMGW handler")
                            continue

                        if tcode == "STRUST" and "STRUST" in screenshots:
                            print(f"    STRUST already captured via STRUST handler")
                            continue

                        if tcode == "SMICM" and "SMICM" in screenshots:
                            print(f"    SMICM already captured via SMICM handler")
                            continue
                        
                        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
                        screenshot_filename = f"{tcode}_{ts}.png"
                        screenshot_path = os.path.join(self.output_dir, screenshot_filename)
                        await page.screenshot(path=screenshot_path, full_page=False)
                        
                        file_size = os.path.getsize(screenshot_path)
                        
                        if file_size > 5000:
                            screenshots[tcode] = screenshot_path
                            print(f"    ✓ Valid: {file_size:,} bytes")
                        else:
                            print(f"    ✗ Blank: {file_size:,} bytes, discarding")
                            
                    except Exception as e:
                        print(f"    ✗ Error capturing {tcode}: {e}")
                        continue


                
            except Exception as e:
                print(f"\n✗ Screenshot engine error: {e}")
                import traceback
                traceback.print_exc()
                if status_callback:
                    status_callback(f"Warning: Screenshot engine error - {str(e)}")
            finally:
                await browser.close()
        
        print(f"\n{'='*60}")
        print(f"Screenshot Summary: {len(screenshots)}/{len(tcodes)} valid captures")
        print(f"{'='*60}\n")
        
        return screenshots
