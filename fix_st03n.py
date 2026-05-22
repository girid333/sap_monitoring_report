import sys

with open("backend/sap_automator.py", "r") as f:
    content = f.read()

st03n_target = '''
                            try:
                                tree_frame = None
                                for f in page.frames:
                                    if f.name == "application":
                                        tree_frame = f
                                        break
'''

st03n_replacement = '''
                            try:
                                # Helper to click a tree node container robustly by text
                                async def st03n_click_tree_node(frm, text, action_type="click"):
                                    return await frm.evaluate("""([nodeText, actionType]) => {
                                        const xpath = `//span[text()="${nodeText}"] | //a[text()="${nodeText}"] | //div[text()="${nodeText}"]`;
                                        const result = document.evaluate(xpath, document, null, XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null);
                                        
                                        for (let i = 0; i < result.snapshotLength; i++) {
                                            const el = result.snapshotItem(i);
                                            let current = el;
                                            let container = null;
                                            
                                            for (let d = 0; d < 6; d++) {
                                                if (!current) break;
                                                const className = current.className || '';
                                                const id = current.id || '';
                                                const tagName = current.tagName.toLowerCase();
                                                const role = current.getAttribute('role') || '';
                                                
                                                if (className.includes('TreeNode') || 
                                                    className.includes('TreeItem') || 
                                                    className.includes('TreeNodeName') ||
                                                    id.includes('tree') || 
                                                    role === 'treeitem' ||
                                                    current.getAttribute('ct') === 'TreeNode') {
                                                    container = current;
                                                    break;
                                                }
                                                current = current.parentElement;
                                            }
                                            
                                            if (container) {
                                                const isExpanded = container.getAttribute('aria-expanded') === 'true' || 
                                                                  container.className.includes('Expanded') || 
                                                                  container.getAttribute('lsdata')?.includes('"expanded":true');
                                                
                                                if (actionType === 'expand' && isExpanded) {
                                                    return 'already_expanded';
                                                }
                                                
                                                container.focus();
                                                
                                                const events = ['mousedown', 'mouseup', 'click'];
                                                for (const evName of events) {
                                                    const ev = new MouseEvent(evName, {
                                                        bubbles: true,
                                                        cancelable: true,
                                                        view: window
                                                    });
                                                    container.dispatchEvent(ev);
                                                }
                                                
                                                if (actionType === 'dblclick' || (actionType === 'expand' && !isExpanded)) {
                                                    const dbl = new MouseEvent('dblclick', {
                                                        bubbles: true,
                                                        cancelable: true,
                                                        view: window
                                                    });
                                                    container.dispatchEvent(dbl);
                                                }
                                                return actionType + '_dispatched';
                                            }
                                        }
                                        return 'not_found';
                                    }""", [text, action_type])

                                tree_frame = None
                                for f in page.frames:
                                    try:
                                        has_tree = await f.evaluate("() => document.body.innerText.includes('Workload') && document.body.innerText.includes('Total')")
                                        if has_tree:
                                            tree_frame = f
                                            break
                                    except:
                                        continue
'''

content = content.replace(st03n_target, st03n_replacement)
content = content.replace('click_tree_node(tree_frame, ', 'st03n_click_tree_node(tree_frame, ')

with open("backend/sap_automator.py", "w") as f:
    f.write(content)

print("Fix applied.")
