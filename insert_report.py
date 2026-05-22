import sys

with open("backend/report_generator.py", "r") as f:
    content = f.read()

word_st03n = """
            # ST03N special
            st03n_pages = tcode_result.get("ST03N_pages", [])
            if tcode_result['tcode'] == 'ST03N' and st03n_pages:
                st03n_labels = ["Workload Overview", "Transaction Profile", "Time Profile"]
                doc.add_paragraph("Additional ST03N Views:")
                for pi in range(1, len(st03n_pages)):
                    ss_path = st03n_pages[pi]
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            try:
                                label = st03n_labels[pi-1] if (pi-1) < len(st03n_labels) else f"Page {pi+1}"
                                doc.add_paragraph(f"{label}:")
                                doc.add_picture(ss_path, width=Inches(14.0))
                                print(f"DEBUG WORD: ST03N {label} embedded ({file_size} bytes)")
                            except Exception as e:
                                print(f"DEBUG WORD: ST03N error: {e}")
"""

pdf_st03n = """
            # ST03N special
            st03n_pages = tcode_result.get("ST03N_pages", [])
            if tcode_result['tcode'] == 'ST03N' and st03n_pages:
                st03n_labels = ["Workload Overview", "Transaction Profile", "Time Profile"]
                elements.append(Paragraph("Additional ST03N Views:", styles['Normal']))
                for pi in range(1, len(st03n_pages)):
                    ss_path = st03n_pages[pi]
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            label = st03n_labels[pi-1] if (pi-1) < len(st03n_labels) else f"Page {pi+1}"
                            print(f"DEBUG PDF: ST03N {label} embedded ({file_size} bytes)")
                            elements.append(Paragraph(f"{label}:", styles['Normal']))
                            try:
                                img = Image(ss_path, width=14.0*inch, height=7.5*inch)
                                elements.append(img)
                            except Exception as e:
                                print(f"DEBUG PDF: ST03N error: {e}")
                            elements.append(Spacer(1, 10))
"""

target_word = '                            except Exception as e:\n                                print(f"DEBUG WORD: DB02 {label} error: {e}")'
content = content.replace(target_word, target_word + "\n" + word_st03n)

target_pdf = '                            except Exception as e:\n                                print(f"DEBUG PDF: DB02 {label} error: {e}")\n                            elements.append(Spacer(1, 10))'
content = content.replace(target_pdf, target_pdf + "\n" + pdf_st03n)

with open("backend/report_generator.py", "w") as f:
    f.write(content)

print("Insertion complete.")
