"                             db02_extra_shots = []
                             db02_log_text = []
                             
                             # Helper to click a tree node container robustly by text
                             async def click_tree_node(frm, text):
                                 return await frm.evaluate("""(nodeText) => {
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
                                                 current.getAttribute('ct')
<truncated 6827 bytes>