import asyncio
import os
from datetime import datetime
from typing import List, Dict, Any, Optional, Callable
from playwright.async_api import async_playwright, Page

class CustomTcodeEngine:
    def __init__(self, webgui_url, username, password, client='100', output_dir=None):
        self.webgui_url = webgui_url
        self.username = username
        self.password = password
        self.client = client
        self.output_dir = output_dir or os.getcwd()
        if not os.path.exists(self.output_dir):
            os.makedirs(self.output_dir, exist_ok=True)

    async def _wait_for_sap_ready(self, page: Page, timeout=10000):
        try:
            # Wait for .lsBlockLayer and #ls-loading to disappear across frames
            await page.wait_for_function('''() => {
                const isOverlayGone = (doc) => {
                    if (!doc) return true;
                    const layer = doc.querySelector('.lsBlockLayer');
                    const loading = doc.querySelector('#ls-loading');
                    return (!layer || window.getComputedStyle(layer).display === 'none') &&
                           (!loading || window.getComputedStyle(loading).display === 'none');
                };
                const checkFrames = (win) => {
                    if (!isOverlayGone(win.document)) return false;
                    for (let i = 0; i < win.frames.length; i++) {
                        try {
                            if (!checkFrames(win.frames[i])) return false;
                        } catch(e) { }
                    }
                    return true;
                };
                return checkFrames(window);
            }''', timeout=timeout)
            await asyncio.sleep(1)
        except Exception as e:
            print(f"Error waiting for SAP ready: {e}")

    async def _find_sap_frame(self, page: Page):
        for frame in page.frames:
            try:
                has_input = await frame.evaluate('''() => {
                    return document.querySelectorAll('input').length > 0;
                }''')
                if has_input:
                    return frame
            except Exception:
                pass
        return page

    async def run_job(self, steps: List[Dict[str, Any]], system_config: Dict[str, Any], status_callback: Optional[Callable] = None) -> dict:
        result = {
            'success': False,
            'screenshots': [],
            'error': None,
            'steps_executed': 0
        }
        
        try:
            async with async_playwright() as p:
                browser = await p.chromium.launch(headless=True)
                context = await browser.new_context(viewport={'width': 1920, 'height': 1080}, ignore_https_errors=True)
                page = await context.new_page()
                
                await page.goto(self.webgui_url)
                await asyncio.sleep(3)
                
                # Login
                login_success = False
                for frame in page.frames:
                    try:
                        await frame.evaluate(f'''() => {{
                            let client = document.querySelector("input[name='sap-client'], #sap-client");
                            let user = document.querySelector("input[name='sap-user'], #sap-user");
                            let pwd = document.querySelector("input[name='sap-password'], #sap-password");
                            if (user && pwd) {{
                                if (client) client.value = '{self.client}';
                                user.value = '{self.username}';
                                pwd.value = '{self.password}';
                            }}
                        }}''')
                        
                        # Try to press Enter on password field
                        pwd_elem = await frame.query_selector("input[name='sap-password'], #sap-password")
                        if pwd_elem:
                            await pwd_elem.press("Enter")
                            login_success = True
                            break
                    except Exception:
                        pass
                
                if not login_success:
                    # fallback
                    await page.keyboard.press("Enter")
                
                await asyncio.sleep(3)
                await self._wait_for_sap_ready(page)
                
                for i, step in enumerate(steps):
                    await self._execute_step(page, step, result['screenshots'], self.output_dir, i + 1)
                    result['steps_executed'] += 1
                    
                result['success'] = True
                await browser.close()
                
        except Exception as e:
            result['error'] = str(e)
            
        return result

    async def _execute_step(self, page: Page, step: Dict[str, Any], screenshots: List[Dict[str, Any]], output_dir: str, step_index: int):
        step_type = step.get('type')
        try:
            if step_type == 'navigate_tcode':
                for frame in page.frames:
                    try:
                        cmd_field = await frame.query_selector("input[name='sap-wd-amf'], .urComboBoxInput, input[id*='OKCODE'], input[id*='okcd']")
                        if cmd_field:
                            await cmd_field.fill(step.get('value', ''))
                            await cmd_field.press('Enter')
                            break
                    except Exception:
                        pass
                await self._wait_for_sap_ready(page)
                
            elif step_type == 'press_fkey':
                key_map = {'F3': 'F3', 'F4': 'F4', 'F5': 'F5', 'F6': 'F6', 'F7': 'F7', 'F8': 'F8', 'F9': 'F9', 'F10': 'F10', 'F11': 'F11', 'F12': 'F12', 'Enter': 'Enter', 'back': 'F3', 'execute': 'F8'}
                mapped_key = key_map.get(step.get('key', ''), step.get('key'))
                await page.keyboard.press(mapped_key)
                await self._wait_for_sap_ready(page)
                
            elif step_type == 'fill_by_label':
                for frame in page.frames:
                    try:
                        success = await frame.evaluate(f'''(label_text) => {{
                            let labels = Array.from(document.querySelectorAll('label'));
                            let label = labels.find(l => l.textContent.toLowerCase().includes(label_text.toLowerCase()));
                            if (label) {{
                                let inputId = label.getAttribute('for');
                                let input = inputId ? document.getElementById(inputId) : label.nextElementSibling;
                                if (input && input.tagName === 'INPUT') {{
                                    input.value = '{step.get("value", "")}';
                                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    return true;
                                }}
                            }}
                            return false;
                        }}''', step.get('label', ''))
                        if success:
                            break
                    except Exception:
                        pass
                await asyncio.sleep(0.5)
                
            elif step_type == 'fill_by_id':
                for frame in page.frames:
                    try:
                        elem_id = step.get('element_id', '')
                        val = step.get('value', '')
                        if await frame.query_selector(f"#{elem_id}"):
                            await frame.fill(f"#{elem_id}", val)
                            break
                        elif await frame.query_selector(f"[name='{elem_id}']"):
                            await frame.fill(f"[name='{elem_id}']", val)
                            break
                    except Exception:
                        pass
                        
            elif step_type == 'fill_by_position':
                for frame in page.frames:
                    try:
                        success = await frame.evaluate(f'''(params) => {{
                            let inputs = Array.from(document.querySelectorAll('input:not([type="hidden"]):not([type="submit"]):not([type="button"]):not([type="checkbox"]):not([type="radio"])'));
                            let visibleInputs = inputs.filter(i => i.offsetWidth > 0 && i.offsetHeight > 0);
                            if (visibleInputs.length > params.position) {{
                                let input = visibleInputs[params.position];
                                input.value = params.value;
                                input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                return true;
                            }}
                            return false;
                        }}''', {'position': step.get('position', 0), 'value': step.get('value', '')})
                        if success:
                            break
                    except Exception:
                        pass
                        
            elif step_type == 'select_dropdown':
                for frame in page.frames:
                    try:
                        elem_id = step.get('element_id')
                        label_text = step.get('label')
                        val = step.get('value')
                        if elem_id:
                            if await frame.query_selector(f"select#{elem_id}"):
                                await frame.select_option(f"select#{elem_id}", val)
                                break
                        elif label_text:
                            sel_id = await frame.evaluate(f'''(lbl) => {{
                                let labels = Array.from(document.querySelectorAll('label'));
                                let label = labels.find(l => l.textContent.toLowerCase().includes(lbl.toLowerCase()));
                                if (label) {{
                                    let inputId = label.getAttribute('for');
                                    let select = inputId ? document.getElementById(inputId) : label.nextElementSibling;
                                    if (select && select.tagName === 'SELECT') return select.id;
                                }}
                                return null;
                            }}''', label_text)
                            if sel_id:
                                await frame.select_option(f"#{sel_id}", val)
                                break
                    except Exception:
                        pass
                        
            elif step_type == 'clear_field':
                for frame in page.frames:
                    try:
                        success = await frame.evaluate(f'''(label_text) => {{
                            let labels = Array.from(document.querySelectorAll('label'));
                            let label = labels.find(l => l.textContent.toLowerCase().includes(label_text.toLowerCase()));
                            if (label) {{
                                let inputId = label.getAttribute('for');
                                let input = inputId ? document.getElementById(inputId) : label.nextElementSibling;
                                if (input && input.tagName === 'INPUT') {{
                                    input.value = '';
                                    input.dispatchEvent(new Event('input', {{ bubbles: true }}));
                                    input.dispatchEvent(new Event('change', {{ bubbles: true }}));
                                    return true;
                                }}
                            }}
                            return false;
                        }}''', step.get('label', ''))
                        if success:
                            break
                    except Exception:
                        pass
                await asyncio.sleep(0.5)

            elif step_type == 'click_button':
                clicked = False
                for frame in page.frames:
                    try:
                        success = await frame.evaluate(f'''(btn_text) => {{
                            let btns = Array.from(document.querySelectorAll('button, input[type="submit"], a[title]'));
                            let btn = btns.find(b => (b.textContent || b.value || b.title || '').toLowerCase().includes(btn_text.toLowerCase()));
                            if (btn) {{
                                btn.click();
                                return true;
                            }}
                            return false;
                        }}''', step.get('button_text', ''))
                        if success:
                            clicked = True
                            break
                        
                        btn_sel = f'button:has-text("{step.get("button_text", "")}")'
                        if await frame.query_selector(btn_sel):
                            await frame.click(btn_sel)
                            clicked = True
                            break
                    except Exception:
                        pass
                if clicked:
                    await self._wait_for_sap_ready(page)
                    
            elif step_type == 'click_menu_path':
                path = step.get('path', [])
                for i, item in enumerate(path):
                    for frame in page.frames:
                        try:
                            success = await frame.evaluate(f'''(txt) => {{
                                let elems = Array.from(document.querySelectorAll('span, a, div'));
                                let el = elems.find(e => e.textContent.trim() === txt);
                                if (el) {{
                                    el.click();
                                    return true;
                                }}
                                return false;
                            }}''', item)
                            if success:
                                break
                        except Exception:
                            pass
                    await asyncio.sleep(0.5)
                    
            elif step_type == 'click_tab':
                for frame in page.frames:
                    try:
                        success = await frame.evaluate(f'''(tab_text) => {{
                            let tabs = Array.from(document.querySelectorAll('[role="tab"], [class*="Tab"], td[title]'));
                            let tab = tabs.find(t => (t.textContent || t.title || '').toLowerCase().includes(tab_text.toLowerCase()));
                            if (tab) {{
                                tab.click();
                                return true;
                            }}
                            return false;
                        }}''', step.get('tab_text', ''))
                        if success:
                            break
                    except Exception:
                        pass
                await self._wait_for_sap_ready(page)
                
            elif step_type == 'click_table_row':
                for frame in page.frames:
                    try:
                        success = await frame.evaluate(f'''(row_text) => {{
                            let rows = Array.from(document.querySelectorAll('tr'));
                            let row = rows.find(r => r.textContent.toLowerCase().includes(row_text.toLowerCase()));
                            if (row) {{
                                row.click();
                                return true;
                            }}
                            return false;
                        }}''', step.get('row_text', ''))
                        if success:
                            break
                    except Exception:
                        pass
                await asyncio.sleep(1)
                
            elif step_type == 'double_click':
                target = step.get('target', '')
                for frame in page.frames:
                    try:
                        success = await frame.evaluate(f'''(tgt) => {{
                            let elems = Array.from(document.querySelectorAll('*'));
                            let el = elems.find(e => e.id === tgt || (e.textContent || '').trim() === tgt);
                            if (el) {{
                                el.dispatchEvent(new MouseEvent('dblclick', {{ bubbles: true }}));
                                return true;
                            }}
                            return false;
                        }}''', target)
                        if success:
                            break
                    except Exception:
                        pass
                        
            elif step_type == 'expand_tree_node':
                for frame in page.frames:
                    try:
                        success = await frame.evaluate(f'''(node_text) => {{
                            let elems = Array.from(document.querySelectorAll('*'));
                            let el = elems.find(e => e.textContent.trim() === node_text);
                            if (el) {{
                                let p = el.parentElement;
                                let icon = p.querySelector('[title="Expand"], [class*="TreeExpand"], [aria-expanded="false"]');
                                if (!icon && p.parentElement) {{
                                    icon = p.parentElement.querySelector('[title="Expand"], [class*="TreeExpand"], [aria-expanded="false"]');
                                }}
                                if (icon) {{
                                    icon.click();
                                    return true;
                                }}
                            }}
                            return false;
                        }}''', step.get('node_text', ''))
                        if success:
                            break
                    except Exception:
                        pass
                await asyncio.sleep(1)
                
            elif step_type == 'click_tree_node':
                for frame in page.frames:
                    try:
                        success = await frame.evaluate(f'''(node_text) => {{
                            let elems = Array.from(document.querySelectorAll('*'));
                            let el = elems.find(e => e.textContent.trim() === node_text);
                            if (el) {{
                                el.click();
                                return true;
                            }}
                            return false;
                        }}''', step.get('node_text', ''))
                        if success:
                            break
                    except Exception:
                        pass
                await asyncio.sleep(1)

            elif step_type == 'confirm_dialog':
                for frame in page.frames:
                    try:
                        success = await frame.evaluate('''() => {
                            let btns = Array.from(document.querySelectorAll('button, span, a'));
                            let texts = ['ok', 'yes', 'continue', 'confirm'];
                            let btn = btns.find(b => texts.includes((b.textContent || '').trim().toLowerCase()));
                            if (btn) {
                                btn.click();
                                return true;
                            }
                            return false;
                        }''')
                        if success:
                            break
                    except Exception:
                        pass
                await asyncio.sleep(1)

            elif step_type == 'dismiss_dialog':
                for frame in page.frames:
                    try:
                        success = await frame.evaluate('''() => {
                            let btns = Array.from(document.querySelectorAll('button, span, a'));
                            let texts = ['cancel', 'no', 'close'];
                            let btn = btns.find(b => texts.includes((b.textContent || '').trim().toLowerCase()));
                            if (btn) {
                                btn.click();
                                return true;
                            }
                            return false;
                        }''')
                        if success:
                            break
                    except Exception:
                        pass
                await asyncio.sleep(1)

            elif step_type == 'handle_f4_help':
                field_label = step.get('field_label', '')
                for frame in page.frames:
                    try:
                        success = await frame.evaluate(f'''(lbl) => {{
                            let labels = Array.from(document.querySelectorAll('label'));
                            let label = labels.find(l => l.textContent.toLowerCase().includes(lbl.toLowerCase()));
                            if (label) {{
                                let inputId = label.getAttribute('for');
                                let input = inputId ? document.getElementById(inputId) : label.nextElementSibling;
                                if (input) {{
                                    input.focus();
                                    return true;
                                }}
                            }}
                            return false;
                        }}''', field_label)
                        if success:
                            break
                    except Exception:
                        pass
                
                await page.keyboard.press('F4')
                await asyncio.sleep(2)
                
                for frame in page.frames:
                    try:
                        await frame.evaluate(f'''(val) => {{
                            let inputs = Array.from(document.querySelectorAll('input[type="text"]'));
                            if (inputs.length > 0) {{
                                inputs[0].value = val;
                                inputs[0].dispatchEvent(new Event('input', {{ bubbles: true }}));
                            }}
                        }}''', step.get('search_value', ''))
                    except Exception:
                        pass
                
                await page.keyboard.press('Enter')
                await asyncio.sleep(1)
                
                for frame in page.frames:
                    try:
                        success = await frame.evaluate('''() => {
                            let rows = Array.from(document.querySelectorAll('tr'));
                            if (rows.length > 1) { 
                                rows[1].click();
                                return true;
                            }
                            return false;
                        }''')
                        if success:
                            break
                    except Exception:
                        pass
                await asyncio.sleep(1)

            elif step_type == 'scroll_table_down':
                times = step.get('times', 1)
                for _ in range(times):
                    await page.keyboard.press('PageDown')
                    await asyncio.sleep(0.5)
                    
            elif step_type == 'filter_column':
                col_name = step.get('column_name', '')
                success_click = False
                for frame in page.frames:
                    try:
                        success = await frame.evaluate(f'''(col) => {{
                            let ths = Array.from(document.querySelectorAll('th, td'));
                            let th = ths.find(t => (t.textContent || '').trim().toLowerCase() === col.toLowerCase());
                            if (th) {{
                                th.dispatchEvent(new MouseEvent('contextmenu', {{ bubbles: true }}));
                                return true;
                            }}
                            return false;
                        }}''', col_name)
                        if success:
                            success_click = True
                            break
                    except Exception:
                        pass
                if not success_click:
                    await page.keyboard.press('F4')
                
                await asyncio.sleep(1)
                await page.keyboard.type(step.get('value', ''))
                
            elif step_type == 'wait_seconds':
                await asyncio.sleep(step.get('seconds', 1))
                
            elif step_type == 'wait_for_element':
                try:
                    await page.wait_for_selector(f'text={step["text"]}', timeout=step.get('timeout', 10) * 1000)
                except Exception:
                    pass
                    
            elif step_type == 'scroll_page_down':
                await page.keyboard.press('PageDown')
                await asyncio.sleep(0.5)
                
            elif step_type == 'screenshot':
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"step_{step_index:03d}_{timestamp}.png"
                path = os.path.join(output_dir, filename)
                await page.screenshot(path=path)
                screenshots.append({
                    'path': path,
                    'caption': step.get('caption', f'Step {step_index}')
                })
                
            elif step_type == 'screenshot_full_page':
                timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
                filename = f"step_{step_index:03d}_{timestamp}.png"
                path = os.path.join(output_dir, filename)
                await page.screenshot(path=path, full_page=True)
                screenshots.append({
                    'path': path,
                    'caption': step.get('caption', f'Step {step_index}')
                })
                
            elif step_type == 'for_each_table_row':
                max_rows = step.get('max_rows', 10)
                sub_steps = step.get('sub_steps', [])
                
                row_count = 0
                for frame in page.frames:
                    try:
                        cnt = await frame.evaluate('''() => {
                            let rows = Array.from(document.querySelectorAll('tr'));
                            return rows.length;
                        }''')
                        if cnt > row_count:
                            row_count = cnt
                    except Exception:
                        pass
                
                limit = min(row_count, max_rows)
                for r_idx in range(limit):
                    clicked = False
                    for frame in page.frames:
                        try:
                            success = await frame.evaluate(f'''(idx) => {{
                                let rows = Array.from(document.querySelectorAll('tr'));
                                if (rows.length > idx) {{
                                    rows[idx].click();
                                    return true;
                                }}
                                return false;
                            }}''', r_idx)
                            if success:
                                clicked = True
                                break
                        except Exception:
                            pass
                    
                    if clicked:
                        await asyncio.sleep(1)
                        for s_idx, sub_step in enumerate(sub_steps):
                            await self._execute_step(page, sub_step, screenshots, output_dir, step_index * 100 + s_idx)
                        
                        await page.keyboard.press('F3')
                        await self._wait_for_sap_ready(page)
                        
            else:
                print(f"Unknown step type: {step_type}")
                
        except Exception as e:
            print(f"Error executing step {step_type}: {e}")
