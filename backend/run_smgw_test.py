import asyncio
from sap_automator import SAPAutomator

async def main():
    automator = SAPAutomator()
    results = await automator.run_monitoring(selected_tcodes=["SMGW"])
    print(results)

if __name__ == "__main__":
    asyncio.run(main())
