import asyncio
from backend.sap_automator import SAPAutomator
import json

async def main():
    automator = SAPAutomator(
        webgui_url="https://nwrhel9.techlabhome.in/sap/bc/gui/sap/its/webgui/",
        username="DDIC",
        password="Winter786#"
    )
    
    # We will run this custom script using playwright directly via automator's context
    browser = await automator.init_browser()
    page = await automator.login(browser)
    
    await page.goto("https://nwrhel9.techlabhome.in/sap/bc/gui/sap/its/webgui/?sap-client=100&sap-language=en&~transaction=DB02", wait_until="networkidle")
    await asyncio.sleep(3)
    
    print("Clicking Performance...")
    # Click Performance
    perf_locator = page.get_by_text("Performance", exact=True)
    if await perf_locator.count() > 0:
        await perf_locator.first.click()
        await asyncio.sleep(5)
        
        # Now dump DOM
        dom_info = await page.evaluate("""() => {
            const results = [];
            const labels = ['Last 24 hours', '24 Hours', '24 hours', 'Last 24 Hours'];
            for (const el of document.querySelectorAll('span, div, a, input, select, option, button')) {
                const txt = el.textContent.trim() || el.value || '';
                for (const lbl of labels) {
                    if (txt.includes(lbl)) {
                        results.push({
                            tag: el.tagName, 
                            text: txt,
                            html: el.outerHTML.substring(0, 150)
                        });
                        break;
                    }
                }
            }
            return results;
        }""")
        print("Performance Elements:", json.dumps(dom_info, indent=2))
        
        # Take screenshot of what performance looks like
        await page.screenshot(path="performance_diagnostic.png")
    else:
        print("Could not find Performance node")

    await browser.close()

if __name__ == "__main__":
    asyncio.run(main())
