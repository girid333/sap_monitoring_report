import json
import sys

log_path = "/Users/giri/.gemini/antigravity/brain/fb63ad3e-2330-449d-93f7-efd8134a405d/.system_generated/logs/transcript.jsonl"
with open(log_path, "r") as f:
    for line in f:
        if "click_tree_node" in line and "ReplacementContent" in line:
            try:
                data = json.loads(line)
                tool_calls = data.get("tool_calls", [])
                for tc in tool_calls:
                    args = tc.get("args", {})
                    rep = args.get("ReplacementContent", "")
                    if "click_tree_node" in rep:
                        with open("extracted_js.txt", "w") as out:
                            out.write(rep)
                        print("Saved to extracted_js.txt")
                        sys.exit(0)
            except Exception as e:
                pass
