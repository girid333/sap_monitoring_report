import re

with open('backend/sap_automator.py', 'r') as f:
    content = f.read()

# We want to replace await asyncio.sleep(X) where X is 5, 8, 10
# with await self._wait_for_sap_ready(page)
# We need to make sure we keep the indentation.

def replacer(match):
    indent = match.group(1)
    return indent + "await self._wait_for_sap_ready(page)"

# Replace sleep(8), sleep(10), sleep(5)
content = re.sub(r'^(\s*)await asyncio\.sleep\((?:10|8|5|4|6)\)\s*(?:#.*)?$', replacer, content, flags=re.MULTILINE)

with open('backend/sap_automator.py', 'w') as f:
    f.write(content)

print("Replaced long sleeps.")
