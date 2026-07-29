import asyncio
import base64
import os
from datetime import datetime
from typing import List, Dict, Any, Optional


class BrowserRecorder:
    """
    Playwright-based live browser recorder.
    Launches a headless browser, streams screenshots, and captures SAP interactions
    as replayable steps. All interaction is forwarded via WebSocket from the frontend.
    """

    VIEWPORT = {"width": 1280, "height": 800}
    SAP_FKEYS = {"F3","F4","F5","F6","F7","F8","F9","F10","F11","F12","Enter"}

    def __init__(self, session_id: str, system: dict, output_dir: str = None):
        self.session_id = session_id
        self.system = system
        self.output_dir = output_dir or os.path.join(os.path.dirname(__file__), "custom_recordings")
        os.makedirs(self.output_dir, exist_ok=True)

        self._playwright = None
        self._browser = None
        self._context = None
        self.page = None

        self.steps: List[Dict] = []
        self.is_running: bool = False
        self.is_ready: bool = False
        self._last_url: str = ""
        self._shot_count: int = 0
        self.error: Optional[str] = None

    # -------------------------------------------------------------------------
    # Public lifecycle
    # -------------------------------------------------------------------------

    async def start(self, tcode: str = "") -> None:
        """Launch browser, login to SAP, optionally navigate to T-code."""
        try:
            print(f"[BrowserRecorder] Starting async_playwright...", flush=True)
            from playwright.async_api import async_playwright
            self._playwright = await async_playwright().start()
            print(f"[BrowserRecorder] Launching chromium...", flush=True)
            self._browser = await self._playwright.chromium.launch(
                headless=True,
                args=[
                    "--no-sandbox",
                    "--disable-setuid-sandbox",
                    "--disable-dev-shm-usage",
                    "--disable-gpu",
                ],
            )
            print(f"[BrowserRecorder] Chromium launched, creating context...", flush=True)
            self._context = await self._browser.new_context(
                viewport=self.VIEWPORT,
                ignore_https_errors=True,
            )
            self.page = await self._context.new_page()

            # Auto-accept dialogs so they don't block screenshots
            self.page.on("dialog", lambda dialog: asyncio.create_task(dialog.accept()))

            # Navigate to SAP WebGUI
            webgui_url = self.system.get("webgui_url", "")
            if not webgui_url:
                raise ValueError("System has no WebGUI URL configured.")
                
            await self.page.goto(webgui_url, timeout=45_000, wait_until="domcontentloaded")

            # Login
            await self._login()

            # Navigate to T-code if given
            if tcode:
                await self._navigate_tcode(tcode)
                self.steps.append({"type": "navigate_tcode", "tcode": tcode.upper()})

            # Inject JS event recorder
            await self._inject_recorder()

            # Listen for navigations to re-inject recorder
            self.page.on("framenavigated", self._on_frame_navigated)

            self.is_running = True
            self.is_ready = True
        except Exception as e:
            self.error = f"Browser startup failed: {str(e)}"
            print(f"[BrowserRecorder] start error: {e}", flush=True)
            self.is_ready = False
            # Clean up if failed
            if self._browser:
                await self._browser.close()
            if self._playwright:
                await self._playwright.stop()

    async def stop(self) -> List[Dict]:
        """Stop recording, close browser, return captured steps."""
        self.is_running = False
        self.is_ready = False
        # Final poll
        try:
            await self._poll_js_events()
        except Exception:
            pass
        for obj in (self._browser, self._playwright):
            try:
                await obj.close() if obj else None
            except Exception:
                pass
        return self.steps

    # -------------------------------------------------------------------------
    # Stream loop (called from WebSocket handler)
    # -------------------------------------------------------------------------

    async def run_stream_loop(self, on_frame, on_step) -> None:
        """
        Continuously stream screenshots and poll JS events.
        on_frame(base64_str) and on_step(step_dict) are coroutines.
        """
        while self.is_running:
            try:
                frame = await self._screenshot_b64()
                if frame:
                    await on_frame(frame)
                new_steps = await self._poll_js_events()
                for step in new_steps:
                    await on_step(step)
            except Exception as exc:
                print(f"[BrowserRecorder] stream error: {exc}")
                break
            await asyncio.sleep(0.15)   # ~7 FPS

    # -------------------------------------------------------------------------
    # Input handlers (called per WebSocket message)
    # -------------------------------------------------------------------------

    async def handle_click(self, x: float, y: float) -> Optional[Dict]:
        """Forward mouse click to Playwright; detect the element and record step."""
        try:
            info = await self._element_info_at(x, y)
            await self.page.mouse.click(x, y)
            await asyncio.sleep(0.25)

            step = None
            if info:
                tag = info.get("tagName", "").upper()
                text = (info.get("text") or info.get("title") or "").strip()
                if tag in ("BUTTON", "A", "SPAN", "TD", "LI") and text and len(text) > 1:
                    step = {"type": "click_button", "button_text": text[:60]}
                elif tag == "INPUT" and info.get("inputType") in ("checkbox", "radio"):
                    step = {"type": "click_button", "button_text": info.get("id", "checkbox")}
            if step:
                self.steps.append(step)
            return step
        except Exception as exc:
            print(f"[BrowserRecorder] handle_click error: {exc}")
            return None

    async def handle_keypress(self, key: str) -> Optional[Dict]:
        """Forward key press to Playwright and record as step."""
        try:
            await self.page.keyboard.press(key)
            await asyncio.sleep(0.2)
            if key in self.SAP_FKEYS:
                step = {"type": "press_fkey", "key": key}
                self.steps.append(step)
                return step
        except Exception as exc:
            print(f"[BrowserRecorder] handle_keypress error: {exc}")
        return None

    async def handle_type(self, text: str) -> None:
        """Type text character by character."""
        try:
            await self.page.keyboard.type(text, delay=25)
        except Exception as exc:
            print(f"[BrowserRecorder] handle_type error: {exc}")

    async def mark_screenshot(self, caption: str) -> Dict:
        """Capture screenshot now and add a screenshot step."""
        try:
            ts = datetime.now().strftime("%Y%m%d_%H%M%S")
            fname = f"rec_{self.session_id}_{self._shot_count}_{ts}.png"
            fpath = os.path.join(self.output_dir, fname)
            self._shot_count += 1
            await self.page.screenshot(path=fpath, full_page=False)
            step = {"type": "screenshot", "caption": caption, "path": fpath}
            self.steps.append(step)
            return step
        except Exception as exc:
            print(f"[BrowserRecorder] mark_screenshot error: {exc}")
            return {"type": "screenshot", "caption": caption}

    # -------------------------------------------------------------------------
    # Private helpers
    # -------------------------------------------------------------------------

    async def _login(self) -> None:
        """Fill SAP WebGUI login form."""
        page = self.page
        client   = self.system.get("sap_client",   "100")
        username = self.system.get("sap_username", "")
        password = self.system.get("sap_password", "")

        # Wait briefly for login page
        try:
            await page.wait_for_load_state("domcontentloaded", timeout=10_000)
        except Exception:
            pass

        # Client
        for sel in ['input[name="sap-client"]', 'input[id*="client"]', 'input[id*="CLIENT"]']:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.fill(client)
                    break
            except Exception:
                pass

        # Username
        for sel in ['input[name="sap-user"]', 'input[id*="user"]', 'input[id*="USER"]', 'input[type="text"]']:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.fill(username)
                    break
            except Exception:
                pass

        # Password
        for sel in ['input[name="sap-password"]', 'input[type="password"]']:
            try:
                el = page.locator(sel).first
                if await el.count() > 0:
                    await el.fill(password)
                    break
            except Exception:
                pass

        # Submit
        try:
            await page.keyboard.press("Enter")
            try:
                await page.wait_for_load_state("networkidle", timeout=3_000)
            except Exception:
                await asyncio.sleep(2)
        except Exception:
            pass

    async def _navigate_tcode(self, tcode: str) -> None:
        """Enter T-code into the SAP command field."""
        page = self.page
        
        # 1. Modern Themes (Belize/Fiori): The command field is often hidden behind a Search/Command icon.
        # We must click it first to reveal the input field.
        open_cmd_selectors = [
            'div[title*="Command" i]',
            'a[title*="Command" i]',
            'span[title*="Command" i]',
            '.lsAppHeaderSearchBtn'
        ]
        for frame in page.frames:
            for sel in open_cmd_selectors:
                try:
                    el = frame.locator(sel).first
                    if await el.count() > 0:
                        await el.click(force=True)
                        await asyncio.sleep(0.5)
                except Exception:
                    pass

        cmd_selectors = [
            'input[id*="okcd" i]',
            'input[title*="Command" i]',
            'input[title*="Transaction" i]',
            'input[name="sap-startapp"]',
            'input.urEdtBx',
            'input.urTxfOkCd',
            'input.lsField--standalone',
            '#CMD_FIELD',
        ]
        
        # 2. Search across all frames for the command field
        for frame in page.frames:
            for sel in cmd_selectors:
                try:
                    el = frame.locator(sel).first
                    if await el.count() > 0:
                        print(f"[BrowserRecorder] Found command field using {sel} in frame {frame.name}", flush=True)
                        await el.fill(f"/n{tcode}", force=True)
                        await frame.keyboard.press("Enter")
                        # Return immediately so the user can see the navigation happening live!
                        await asyncio.sleep(1)
                        return
                except Exception:
                    pass
                    
        print("[BrowserRecorder] Could not find command field, attempting Ctrl+/ keyboard shortcut...", flush=True)
        # Fallback 1: Keyboard shortcut to focus command field
        try:
            # Click the body first to ensure the frame has focus
            await page.locator("body").click(force=True)
            await page.keyboard.press("Control+/")
            await asyncio.sleep(0.5)
            await page.keyboard.type(f"/n{tcode}")
            await page.keyboard.press("Enter")
            await asyncio.sleep(1)
            return
        except Exception as exc:
            print(f"[BrowserRecorder] Ctrl+/ fallback error: {exc}", flush=True)

        print("[BrowserRecorder] Keyboard shortcut failed, falling back to URL...", flush=True)
        # Fallback 2: URL with transaction param
        try:
            base = self.system.get("webgui_url", "").rstrip("?&")
            sep  = "&" if "?" in base else "?"
            url  = f"{base}{sep}~transaction={tcode}&sap-client={self.system.get('sap_client','100')}"
            # Do not wait for load state, let it load in the background
            await page.goto(url)
        except Exception as exc:
            print(f"[BrowserRecorder] _navigate_tcode fallback error: {exc}", flush=True)

    async def _inject_recorder(self) -> None:
        """Inject lightweight JS event listener into every frame."""
        script = r"""
        (function () {
            if (window.__brecAttached) return;
            window.__brecAttached = true;
            window.__brecEvents = window.__brecEvents || [];

            function cap(type, data) {
                window.__brecEvents.push(Object.assign({ type: type, ts: Date.now() }, data));
            }

            function attachDoc(doc) {
                if (!doc || doc.__brecDoc) return;
                doc.__brecDoc = true;

                doc.addEventListener('change', function (e) {
                    var el = e.target;
                    if (el.tagName !== 'INPUT' && el.tagName !== 'SELECT' && el.tagName !== 'TEXTAREA') return;
                    var label = '';
                    if (el.id) {
                        var l = doc.querySelector('label[for="' + el.id + '"]');
                        if (l) label = l.textContent.trim();
                    }
                    if (!label && el.title) label = el.title;
                    if (!label && el.placeholder) label = el.placeholder;
                    cap('fill', { id: el.id || '', name: el.name || '', label: label, value: el.value });
                }, true);

                doc.addEventListener('keydown', function (e) {
                    var fk = ['F3','F4','F5','F6','F7','F8','F9','F10','F11','F12','Enter'];
                    if (fk.indexOf(e.key) >= 0) cap('keypress', { key: e.key });
                }, true);
            }

            attachDoc(document);

            function attachFrames() {
                Array.from(document.querySelectorAll('iframe')).forEach(function (f) {
                    try { attachDoc(f.contentDocument); } catch (ex) {}
                });
            }
            attachFrames();
            setInterval(attachFrames, 1500);
        })();
        """
        try:
            await self.page.evaluate(script)
        except Exception as exc:
            print(f"[BrowserRecorder] inject error: {exc}")

    async def _on_frame_navigated(self, frame) -> None:
        """Re-inject recorder after navigation."""
        try:
            if frame.url and frame.url != self._last_url and frame.url != "about:blank":
                self._last_url = frame.url
                await asyncio.sleep(0.6)
                await self._inject_recorder()
        except Exception:
            pass

    async def _poll_js_events(self) -> List[Dict]:
        """Collect raw JS events and convert to step dicts."""
        new_steps: List[Dict] = []
        try:
            raw: list = await self.page.evaluate(
                "var e = window.__brecEvents || []; window.__brecEvents = []; e;"
            )
            for ev in raw:
                step = self._convert_event(ev)
                if step:
                    new_steps.append(step)
                    self.steps.append(step)
        except Exception:
            pass
        return new_steps

    def _convert_event(self, event: dict) -> Optional[Dict]:
        etype = event.get("type", "")
        if etype == "fill":
            value = str(event.get("value", "")).strip()
            if not value:
                return None
            label    = str(event.get("label",  "")).strip()
            elem_id  = str(event.get("id",     "")).strip()
            if label:
                return {"type": "fill_by_label", "label": label,      "value": value}
            if elem_id:
                return {"type": "fill_by_id",    "element_id": elem_id, "value": value}
            return {"type": "fill_by_position", "position": 0, "value": value}
        elif etype == "keypress":
            key = event.get("key", "")
            if key in self.SAP_FKEYS:
                return {"type": "press_fkey", "key": key}
        return None

    async def _screenshot_b64(self) -> Optional[str]:
        if not self.page or not self.is_running:
            return None
        try:
            raw = await self.page.screenshot(type="jpeg", quality=65, full_page=False)
            return base64.b64encode(raw).decode("utf-8")
        except Exception:
            return None

    async def _element_info_at(self, x: float, y: float) -> Optional[Dict]:
        """Return element info at screen coordinates, checking main page + iframes."""
        js = f"""
        (function() {{
            var el = document.elementFromPoint({x}, {y});
            if (!el) return null;
            return {{
                tagName: el.tagName || '',
                text: (el.innerText || el.textContent || '').trim().replace(/\\s+/g,' ').substring(0,100),
                id: el.id || '',
                title: el.getAttribute('title') || '',
                inputType: el.type || ''
            }};
        }})()
        """
        try:
            info = await self.page.evaluate(js)
            if info:
                return info
        except Exception:
            pass
        # Check iframes
        for frame in self.page.frames:
            try:
                info = await frame.evaluate(js)
                if info and info.get("text"):
                    return info
            except Exception:
                pass
        return None
