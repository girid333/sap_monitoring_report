import asyncio
import json
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
    
    await automator.page.goto(config['webgui_url'])
    await automator.page.wait_for_load_state('networkidle')
    
    for frame in automator.page.frames:
        html = await frame.evaluate("""() => {
            let input = document.querySelector('input');
            if (input) return document.body.innerHTML.substring(0, 50000);
            return null;
        }""")
        if html:
            with open("okcode_dump.html", "w") as f:
                f.write(html)
            print("Dumped.")
            break
            
    await automator.playwright.stop()

if __name__ == "__main__":
    asyncio.run(main())
