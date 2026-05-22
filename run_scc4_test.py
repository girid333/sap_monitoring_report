import asyncio
from backend.sap_automator import SAPAutomator
import json

async def main():
    with open('config.json', 'r') as f:
        config = json.load(f)
    
    automator = SAPAutomator(
        webgui_url=config['webgui_url'],
        username=config['sap_username'],
        password=config['sap_password']
    )
    
    screenshots = await automator.take_screenshots(['SCC4'])
    print("Screenshots saved:", screenshots)

if __name__ == "__main__":
    asyncio.run(main())
