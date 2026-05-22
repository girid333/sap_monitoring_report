import asyncio
from backend.sap_automator import SAPAutomator
import json

async def main():
    automator = SAPAutomator(
        webgui_url="https://nwrhel9.techlabhome.in/sap/bc/gui/sap/its/webgui/",
        username="DDIC",
        password="Winter786#"
    )
    
    screenshots = await automator.take_screenshots(['DB02'])
    print("Screenshots saved:", screenshots)

if __name__ == "__main__":
    asyncio.run(main())
