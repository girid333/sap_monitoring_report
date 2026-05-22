import asyncio
import json
import time
from backend.sap_automator import SAPAutomator

async def main():
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    automator = SAPAutomator(
        webgui_url=config['webgui_url'],
        username=config['sap_username'],
        password=config['sap_password']
    )
    
    await automator._ensure_browser()
    await automator._login()
    
    # Go to home first
    start = time.time()
    await automator.page.goto(config['webgui_url'])
    await automator.page.wait_for_load_state('networkidle')
    print(f"Home load: {time.time() - start:.2f}s")
    
    # Try typing into OK-Code field
    start = time.time()
    for frame in automator.page.frames:
        try:
            ok_code = await frame.query_selector('input[title="Command Field"]')
            if not ok_code:
                ok_code = await frame.query_selector('input[name="~OkCode"]')
            if not ok_code:
                ok_code = await frame.query_selector('[id*="okcd"]')
                
            if ok_code:
                await ok_code.fill('/nSMICM')
                await ok_code.press('Enter')
                await automator.page.wait_for_timeout(3000)
                print(f"OkCode nav to SMICM: {time.time() - start:.2f}s")
                title = await automator.page.title()
                print("Title:", title)
                break
        except Exception as e:
            pass
            
    await automator.playwright.stop()

if __name__ == "__main__":
    asyncio.run(main())
