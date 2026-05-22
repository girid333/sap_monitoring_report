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
    
    tcodes = ['SM21', 'ST22', 'SMICM', 'STRUST']
    print(f"Testing execution speed for {len(tcodes)} transactions...")
    start_time = time.time()
    
    screenshots = await automator.take_screenshots(tcodes)
    
    end_time = time.time()
    print(f"\nCompleted in {end_time - start_time:.2f} seconds!")
    print(f"Screenshots saved: {len(screenshots)}")
    
if __name__ == "__main__":
    asyncio.run(main())
