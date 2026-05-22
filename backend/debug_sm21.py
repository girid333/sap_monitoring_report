import asyncio
import os
from playwright.async_api import async_playwright

async def debug_sm21():
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(viewport={'width': 1920, 'height': 1080})
        page = await context.new_page()
        
        # URL for SM21
        url = "http://192.168.0.189:8000/sap/bc/gui/sap/its/webgui?sap-client=100&sap-language=en&~transaction=SM21"
        
        print(f"Navigating to {url}...")
        await page.goto(url)
        await asyncio.sleep(5)
        
        # Login
        await page.evaluate("""(u, p) => {
            const user = document.querySelector('input[name="sap-user"]');
            const pass = document.querySelector('input[name="sap-password"]');
            if (user && pass) {
                user.value = u;
                pass.value = p;
                user.dispatchEvent(new Event('input', { bubbles: true }));
                pass.dispatchEvent(new Event('input', { bubbles: true }));
                const btn = document.querySelector('#sapwp_BUTTON_LOGIN') || document.querySelector('span.urBtnCnt');
                if (btn) btn.click();
            }
        }""", "giri", "Giri@123")
        
        await asyncio.sleep(8)
        
        # Dump frame info
        print(f"Frames: {len(page.frames)}")
        for i, frame in enumerate(page.frames):
            print(f"Frame {i}: {frame.name} - {frame.url[:100]}")
            inputs = await frame.evaluate("""() => {
                return Array.from(document.querySelectorAll('input')).map(i => ({
                    id: i.id,
                    name: i.name,
                    value: i.value,
                    title: i.title,
                    type: i.type
                }));
            }""")
            print(f"  Inputs: {inputs}")
            
            # Look for Execute button
            buttons = await frame.evaluate("""() => {
                return Array.from(document.querySelectorAll('div, span, button')).filter(el => 
                    el.innerText.trim() === 'Execute' || (el.title && el.title.includes('Execute'))
                ).map(el => ({ id: el.id, text: el.innerText, title: el.title }));
            }""")
            print(f"  Buttons: {buttons}")

        await browser.close()

if __name__ == "__main__":
    asyncio.run(debug_sm21())
