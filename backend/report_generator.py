import os
from datetime import datetime
from docx import Document
from docx.shared import Inches, Pt, RGBColor
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.enum.section import WD_ORIENT
from reportlab.lib.pagesizes import A3, landscape
from reportlab.lib import colors
from reportlab.lib.units import inch
from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer, Image, Table, TableStyle, PageBreak
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle

class ReportGenerator:
    def __init__(self, results: dict, output_dir: str = "reports"):
        self.results = results
        self.output_dir = output_dir
        os.makedirs(self.output_dir, exist_ok=True)
        self.timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

    def generate_word(self) -> str:
        filepath = os.path.join(self.output_dir, f"SAP_BASIS_Report_{self.timestamp}.docx")
        doc = Document()
        
        # Set to A3 Landscape (16.5 x 11.7 inches)
        section = doc.sections[0]
        section.orientation = WD_ORIENT.LANDSCAPE
        section.page_width = Inches(16.5)
        section.page_height = Inches(11.7)
        
        # Set Default Styles (Gold/Orange for H1, Blue-Grey for H2)
        gold_orange = RGBColor(230, 159, 0)
        blue_grey = RGBColor(60, 123, 153)
        try:
            style1 = doc.styles['Heading 1']
            style1.font.color.rgb = gold_orange
            style2 = doc.styles['Heading 2']
            style2.font.color.rgb = blue_grey
        except KeyError:
            pass

        # Title
        title = doc.add_heading('SAP BASIS Premium Diagnostic Report v2.0', 0)
        title.alignment = WD_ALIGN_PARAGRAPH.CENTER
        title.runs[0].font.color.rgb = gold_orange
        
        doc.add_paragraph(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}").alignment = WD_ALIGN_PARAGRAPH.CENTER
        doc.add_paragraph("_" * 100).alignment = WD_ALIGN_PARAGRAPH.CENTER
        
        # Add Cover Image
        cover_image_path = "/Users/giri/.gemini/antigravity/brain/fb63ad3e-2330-449d-93f7-efd8134a405d/cover_image_1780331933563.png"
        if os.path.exists(cover_image_path):
            doc.add_picture(cover_image_path, width=Inches(10.0))
        
        doc.add_page_break()
        
        # Summary of Anomalies
        doc.add_heading('1. Executive Summary', level=1)
        total_anomalies = len(self.results.get("anomalies", []))
        if total_anomalies == 0:
            doc.add_paragraph("No anomalies detected in the last 24 hours. All monitored systems are operating normally.")
        else:
            doc.add_paragraph(f"A total of {total_anomalies} anomalies were detected. Please review the relevant sections below for detailed findings.")
            
            # Anomaly Summary Table
            table = doc.add_table(rows=1, cols=3)
            # Use 'Grid Table 4 Accent 4' which natively has a gold/orange header in standard Word templates
            # If not available, we use standard shading and manually color it (we'll stick to a robust standard style)
            table.style = 'Medium Shading 1 Accent 4'
            hdr_cells = table.rows[0].cells
            hdr_cells[0].text = 'Component'
            hdr_cells[1].text = 'Anomaly Count'
            hdr_cells[2].text = 'Status'
            
            for tc_result in self.results.get("tcodes", []):
                tc = tc_result["tcode"]
                tc_name = tc_result["name"]
                tc_anomalies = tc_result.get("anomalies", [])
                
                if tc_anomalies:
                    row_cells = table.add_row().cells
                    row_cells[0].text = f"{tc} ({tc_name})"
                    row_cells[1].text = str(len(tc_anomalies))
                    row_cells[2].text = "Action Required"
            
            doc.add_paragraph()

        doc.add_page_break()
        # External Checks
        doc.add_heading('2. Infrastructure & Server Health', level=1)
        for check in self.results.get("external_checks", []):
            check_type = check.get("type", "")
            check_status = check.get("status", "")
            check_data = check.get("data", [])
            
            if check_data and isinstance(check_data, list) and len(check_data) > 0:
                # Render as a proper data table
                p = doc.add_paragraph()
                p.add_run(f"{check_type}").bold = True
                p.add_run(f" (Source: {check.get('method', 'RFC')})")
                
                keys = list(check_data[0].keys())
                table = doc.add_table(rows=1, cols=len(keys))
                table.style = 'Medium Shading 1 Accent 4'
                hdr_cells = table.rows[0].cells
                for i, key in enumerate(keys):
                    hdr_cells[i].text = str(key)
                    for paragraph in hdr_cells[i].paragraphs:
                        for run in paragraph.runs:
                            run.font.size = Pt(8)
                            run.font.bold = True
                
                for item in check_data:
                    row_cells = table.add_row().cells
                    for i, key in enumerate(keys):
                        row_cells[i].text = str(item.get(key, ""))
                        for paragraph in row_cells[i].paragraphs:
                            for run in paragraph.runs:
                                run.font.size = Pt(7)
                doc.add_paragraph()
                
            elif "url" in check:
                p = doc.add_paragraph()
                p.add_run("URL Reachability Check").bold = True
                doc.add_paragraph(f"{check['url']} → {check_status} ({check.get('details', '')})")
                doc.add_paragraph()  # Spacing after URL check
            elif "details" in check:
                p = doc.add_paragraph()
                p.add_run(f"{check_type}").bold = True
                doc.add_paragraph(f"{check_status} - {check.get('details', '')}")
                doc.add_paragraph()  # Spacing
            else:
                p = doc.add_paragraph()
                p.add_run(f"{check_type}").bold = True
                doc.add_paragraph(f"{check_status}")
                doc.add_paragraph()  # Spacing
        
        # Add SSH Filesystem Snapshots
        ssh_fs = self.results.get("ssh_filesystem_data", [])
        if ssh_fs:
            for fs_entry in ssh_fs:
                server = fs_entry.get("server", "Unknown")
                data = fs_entry.get("data", [])
                if data:
                    p = doc.add_paragraph()
                    p.add_run(f"OS Filesystem Snapshot (via SSH): {server}").bold = True
                    
                    keys = list(data[0].keys())
                    table = doc.add_table(rows=1, cols=len(keys))
                    table.style = 'Medium Shading 2 Accent 2'
                    hdr_cells = table.rows[0].cells
                    for i, key in enumerate(keys):
                        hdr_cells[i].text = str(key)
                        for paragraph in hdr_cells[i].paragraphs:
                            for run in paragraph.runs:
                                run.font.size = Pt(8)
                    
                    for item in data:
                        row_cells = table.add_row().cells
                        for i, key in enumerate(keys):
                            row_cells[i].text = str(item.get(key, ""))
                            for paragraph in row_cells[i].paragraphs:
                                for run in paragraph.runs:
                                    run.font.size = Pt(7)
                    doc.add_paragraph()
        

        # Detailed Data
        doc.add_page_break()
        doc.add_heading('3. Detailed Status (RFC Data)', level=1)
        for i, tcode_result in enumerate(self.results.get("tcodes", [])):
            if i > 0:
                doc.add_page_break()
            doc.add_heading(f"{tcode_result['tcode']} - {tcode_result['name']}", level=2)
            
            # Add Analysis Summary
            analysis = tcode_result.get("analysis_summary", "Analysis completed.")
            p = doc.add_paragraph()
            p.add_run("System Analysis: ").bold = True
            p.add_run(analysis)
            
            # SM21 special: embed all scroll-page screenshots
            sm21_pages = tcode_result.get("sm21_pages", [])
            if tcode_result['tcode'] == 'SM21' and sm21_pages:
                doc.add_paragraph("Visual Evidence (SAP WebGUI - System Log Pages):")
                for pi, ss_path in enumerate(sm21_pages):
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            try:
                                doc.add_paragraph(f"Page {pi+1}:")
                                doc.add_picture(ss_path, width=Inches(14.0))
                                print(f"DEBUG WORD: SM21 page {pi+1} embedded ({file_size} bytes)")
                            except Exception as e:
                                print(f"DEBUG WORD: SM21 page {pi+1} error: {e}")
            
            # ST22 special: embed Today + Yesterday screenshots
            elif tcode_result['tcode'] == 'ST22' and tcode_result.get("st22_pages", []):
                st22_pages = tcode_result["st22_pages"]
                day_labels = ["Today", "Yesterday"]
                doc.add_paragraph("Visual Evidence (SAP WebGUI - ABAP Dumps):")
                for pi, ss_path in enumerate(st22_pages):
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            try:
                                label = day_labels[pi] if pi < len(day_labels) else f"Page {pi+1}"
                                doc.add_paragraph(f"{label}:")
                                doc.add_picture(ss_path, width=Inches(14.0))
                                print(f"DEBUG WORD: ST22 {label} embedded ({file_size} bytes)")
                            except Exception as e:
                                print(f"DEBUG WORD: ST22 page {pi+1} error: {e}")
            else:
                # Standard screenshot embedding for other tcodes
                screenshot_path = tcode_result.get("screenshot")
                if screenshot_path and os.path.exists(screenshot_path):
                    file_size = os.path.getsize(screenshot_path)
                    if file_size > 5000:
                        doc.add_paragraph("Visual Evidence (SAP WebGUI):")
                        try:
                            doc.add_picture(screenshot_path, width=Inches(14.0))
                            print(f"DEBUG WORD: Embedded screenshot {screenshot_path} ({file_size} bytes)")
                        except Exception as e:
                            print(f"DEBUG WORD: Image error: {e}")
                            doc.add_paragraph(f"[Image load error: {e}]")
                    else:
                        print(f"DEBUG WORD: Skipping blank screenshot {screenshot_path} ({file_size} bytes)")
                        doc.add_paragraph("[Screenshot not available - WebGUI capture returned blank]")

            # DB02 special: embed additional performance/status screenshots
            db02_pages = tcode_result.get("db02_pages", [])
            if tcode_result['tcode'] == 'DB02' and db02_pages:
                db02_labels = ["Overview", "Performance Graph"]
                doc.add_paragraph("Additional DB02 Views:")
                for pi, ss_path in enumerate(db02_pages):
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            try:
                                label = db02_labels[pi] if pi < len(db02_labels) else f"Page {pi+1}"
                                doc.add_paragraph(f"{label}:")
                                doc.add_picture(ss_path, width=Inches(14.0))
                                print(f"DEBUG WORD: DB02 {label} embedded ({file_size} bytes)")
                            except Exception as e:
                                print(f"DEBUG WORD: DB02 {label} error: {e}")

            # ST03N special
            st03n_pages = tcode_result.get("ST03N_pages", [])
            if tcode_result['tcode'] == 'ST03N' and st03n_pages:
                st03n_labels = ["Workload Overview", "Transaction Profile", "Time Profile", "Response Time Distribution"]
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

            # SCC4 special
            scc4_pages = tcode_result.get("SCC4_pages", [])
            if tcode_result['tcode'] == 'SCC4' and scc4_pages:
                doc.add_paragraph("SCC4 Client Configurations:")
                for pi in range(1, len(scc4_pages)):
                    ss_path = scc4_pages[pi]
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            try:
                                doc.add_paragraph(f"Client {pi}:")
                                doc.add_picture(ss_path, width=Inches(14.0))
                                print(f"DEBUG WORD: SCC4 Client {pi} embedded ({file_size} bytes)")
                            except Exception as e:
                                print(f"DEBUG WORD: SCC4 error: {e}")

            # SMLG special
            smlg_pages = tcode_result.get("SMLG_pages", [])
            if tcode_result['tcode'] == 'SMLG' and len(smlg_pages) > 1:
                doc.add_paragraph("SMLG Load Distribution Views:")
                smlg_labels = ["Load Distribution"]
                for pi in range(1, len(smlg_pages)):
                    ss_path = smlg_pages[pi]
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            try:
                                label = smlg_labels[pi-1] if (pi-1) < len(smlg_labels) else f"Page {pi+1}"
                                doc.add_paragraph(f"{label}:")
                                doc.add_picture(ss_path, width=Inches(14.0))
                                print(f"DEBUG WORD: SMLG {label} embedded ({file_size} bytes)")
                            except Exception as e:
                                print(f"DEBUG WORD: SMLG error: {e}")

            # SMGW special
            smgw_pages = tcode_result.get("SMGW_pages", [])
            if tcode_result['tcode'] == 'SMGW' and len(smgw_pages) > 1:
                doc.add_paragraph("SMGW Logged-On Clients:")
                smgw_labels = ["Logged On Clients"]
                for pi in range(1, len(smgw_pages)):
                    ss_path = smgw_pages[pi]
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            try:
                                label = smgw_labels[pi-1] if (pi-1) < len(smgw_labels) else f"Page {pi+1}"
                                doc.add_paragraph(f"{label}:")
                                doc.add_picture(ss_path, width=Inches(14.0))
                                print(f"DEBUG WORD: SMGW {label} embedded ({file_size} bytes)")
                            except Exception as e:
                                print(f"DEBUG WORD: SMGW error: {e}")

            # SMICM special
            smicm_pages = tcode_result.get("SMICM_pages", [])
            if tcode_result['tcode'] == 'SMICM' and len(smicm_pages) > 1:
                doc.add_paragraph("SMICM ICM Services Views:")
                smicm_labels = ["ICM Services List"]
                for pi in range(1, len(smicm_pages)):
                    ss_path = smicm_pages[pi]
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            try:
                                label = smicm_labels[pi-1] if (pi-1) < len(smicm_labels) else f"Page {pi+1}"
                                doc.add_paragraph(f"{label}:")
                                doc.add_picture(ss_path, width=Inches(14.0))
                                print(f"DEBUG WORD: SMICM {label} embedded ({file_size} bytes)")
                            except Exception as e:
                                print(f"DEBUG WORD: SMICM error: {e}")

            # STRUST special
            strust_pages = tcode_result.get("STRUST_pages", [])
            if tcode_result['tcode'] == 'STRUST' and len(strust_pages) > 1:
                doc.add_paragraph("STRUST Expiring Certificates:")
                for pi in range(1, len(strust_pages)):
                    ss_path = strust_pages[pi]
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            try:
                                doc.add_paragraph(f"Anomaly Detail {pi}:")
                                doc.add_picture(ss_path, width=Inches(14.0))
                                print(f"DEBUG WORD: STRUST Page {pi} embedded ({file_size} bytes)")
                            except Exception as e:
                                print(f"DEBUG WORD: STRUST error: {e}")

            if tcode_result["anomalies"]:
                doc.add_paragraph("Anomalies Detected:", style='List Bullet')
                for anom in tcode_result["anomalies"]:
                    doc.add_paragraph(anom, style='List Bullet 2')
            else:
                doc.add_paragraph("Status: Normal")

            data = tcode_result.get("data")
            # Skip tables for all monitored T-codes as requested (prefer screenshots and analysis)
            if False: # Keep original logic for future reference but disabled
                keys = list(data[0].keys())
                
                table = doc.add_table(rows=1, cols=len(keys))
                table.style = 'Table Grid'
                hdr_cells = table.rows[0].cells
                for i, key in enumerate(keys):
                    hdr_cells[i].text = str(key)
                    # Use very small font to fit all data
                    for paragraph in hdr_cells[i].paragraphs:
                        for run in paragraph.runs:
                            run.font.size = Pt(6)
                
                # Compact table if screenshot exists
                display_rows = 20 if screenshot_path else 100
                
                for item in data[:display_rows]:
                    row_cells = table.add_row().cells
                    for i, key in enumerate(keys):
                        row_cells[i].text = str(item.get(key, ""))
                        for paragraph in row_cells[i].paragraphs:
                            for run in paragraph.runs:
                                run.font.size = Pt(6)
            else:
                pass # No specific table data returned from RFC.

            doc.add_page_break()

        doc.save(filepath)
        return filepath

    def generate_pdf(self) -> str:
        filepath = os.path.join(self.output_dir, f"SAP_BASIS_Report_{self.timestamp}.pdf")
        doc = SimpleDocTemplate(filepath, pagesize=landscape(A3))
        styles = getSampleStyleSheet()
        elements = []
        
        gold_orange = colors.HexColor("#E69F00")
        blue_grey = colors.HexColor("#3C7B99")
        
        # Custom Heading Styles
        h1_style = ParagraphStyle(
            'StylishHeading1',
            parent=styles['Heading1'],
            textColor=gold_orange,
            fontSize=22,
            spaceAfter=12
        )
        h2_style = ParagraphStyle(
            'StylishHeading2',
            parent=styles['Heading2'],
            textColor=blue_grey,
            fontSize=16,
            spaceAfter=10
        )

        # Title
        title_style = ParagraphStyle('CoverTitle', parent=styles['Title'], textColor=gold_orange, fontSize=28)
        elements.append(Paragraph("SAP BASIS Premium Diagnostic Report v2.0", title_style))
        elements.append(Paragraph(f"Report Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
        elements.append(Spacer(1, 20))
        
        # Add Cover Image
        cover_image_path = "/Users/giri/.gemini/antigravity/brain/fb63ad3e-2330-449d-93f7-efd8134a405d/cover_image_1780331933563.png"
        if os.path.exists(cover_image_path):
            elements.append(Image(cover_image_path, width=8*inch, height=4*inch))
            
        elements.append(PageBreak())

        # Summary - grouped by T-code
        elements.append(Paragraph("1. Executive Summary", h1_style))
        total_anomalies = len(self.results.get("anomalies", []))
        if total_anomalies == 0:
            elements.append(Paragraph("No anomalies detected in the last 24 hours. All monitored systems are operating normally.", styles['Normal']))
        else:
            elements.append(Paragraph(f"A total of {total_anomalies} anomalies were detected. Please review the relevant sections below for detailed findings.", styles['Normal']))
            elements.append(Spacer(1, 10))
            
            table_data = [["Component", "Anomaly Count", "Status"]]
            for tcode_result in self.results.get("tcodes", []):
                tc = tcode_result["tcode"]
                tc_name = tcode_result["name"]
                tc_anomalies = tcode_result.get("anomalies", [])
                if tc_anomalies:
                    table_data.append([f"{tc} ({tc_name})", str(len(tc_anomalies)), "Action Required"])
            
            if len(table_data) > 1:
                t = Table(table_data)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), gold_orange),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.black),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0,0), (-1,0), 8),
                    ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#FFFFFF')),
                    ('GRID', (0,0), (-1,-1), 1, colors.black),
                ]))
                elements.append(t)
        
        elements.append(PageBreak())

        # External Checks
        elements.append(Paragraph("2. Infrastructure & Server Health", h1_style))
        
        for check in self.results.get("external_checks", []):
            check_type = check.get("type", "")
            check_status = check.get("status", "")
            check_data = check.get("data", [])
            
            if check_data and isinstance(check_data, list) and len(check_data) > 0:
                # Render as a proper data table
                method = check.get('method', 'RFC')
                elements.append(Paragraph(f"<b>{check_type}</b> (Source: {method})", styles['Normal']))
                elements.append(Spacer(1, 5))
                
                keys = list(check_data[0].keys())
                table_data = [keys]
                for item in check_data:
                    table_data.append([str(item.get(k, "")) for k in keys])
                
                t = Table(table_data)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#E69F00')),
                    ('TEXTCOLOR', (0,0), (-1,0), colors.black),
                    ('ALIGN', (0,0), (-1,-1), 'CENTER'),
                    ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                    ('BOTTOMPADDING', (0,0), (-1,0), 6),
                    ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#FFFFFF')),
                    ('GRID', (0,0), (-1,-1), 1, colors.black),
                    ('FONTSIZE', (0,0), (-1,0), 8),
                    ('FONTSIZE', (0,1), (-1,-1), 7),
                    ('BOTTOMPADDING', (0,0), (-1,0), 8),
                    ('TOPPADDING', (0,1), (-1,-1), 4),
                    ('BOTTOMPADDING', (0,1), (-1,-1), 4),
                    ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#ECF0F1')),
                    ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#ECF0F1'), colors.white]),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#BDC3C7'))
                ]))
                elements.append(t)
                elements.append(Spacer(1, 10))
                
            elif "url" in check:
                elements.append(Paragraph("<b>URL Reachability Check</b>", styles['Normal']))
                elements.append(Paragraph(f"{check['url']} → {check_status} ({check.get('details', '')})", styles['Normal']))
                elements.append(Spacer(1, 15))
            elif "details" in check:
                elements.append(Paragraph(f"<b>{check_type}</b>", styles['Normal']))
                elements.append(Paragraph(f"{check_status} - {check.get('details', '')}", styles['Normal']))
                elements.append(Spacer(1, 15))
            else:
                elements.append(Paragraph(f"<b>{check_type}</b>", styles['Normal']))
                elements.append(Paragraph(f"{check_status}", styles['Normal']))
                elements.append(Spacer(1, 15))
        
        # Add SSH Filesystem Snapshots for PDF
        ssh_fs = self.results.get("ssh_filesystem_data", [])
        if ssh_fs:
            for fs_entry in ssh_fs:
                server = fs_entry.get("server", "Unknown")
                data = fs_entry.get("data", [])
                if data:
                    elements.append(Paragraph(f"<b>OS Filesystem Snapshot (via SSH): {server}</b>", styles['Normal']))
                    elements.append(Spacer(1, 5))
                    
                    keys = list(data[0].keys())
                    table_data = [keys]
                    for item in data:
                        table_data.append([str(item.get(k, "")) for k in keys])
                    
                    t = Table(table_data)
                    t.setStyle(TableStyle([
                        ('BACKGROUND', (0,0), (-1,0), colors.HexColor('#2980B9')),
                        ('TEXTCOLOR', (0,0), (-1,0), colors.whitesmoke),
                        ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                        ('FONTNAME', (0,0), (-1,0), 'Helvetica-Bold'),
                        ('FONTSIZE', (0,0), (-1,0), 8),
                        ('FONTSIZE', (0,1), (-1,-1), 7),
                        ('BOTTOMPADDING', (0,0), (-1,0), 8),
                        ('BACKGROUND', (0,1), (-1,-1), colors.HexColor('#D6EAF8')),
                        ('ROWBACKGROUNDS', (0,1), (-1,-1), [colors.HexColor('#D6EAF8'), colors.white]),
                        ('GRID', (0,0), (-1,-1), 0.5, colors.HexColor('#3498DB'))
                    ]))
                    elements.append(t)
                    elements.append(Spacer(1, 10))
        
        elements.append(Spacer(1, 20))


        # Detailed Data
        elements.append(PageBreak())
        elements.append(Paragraph("3. Detailed Status", h1_style))
        for i, tcode_result in enumerate(self.results.get("tcodes", [])):
            if i > 0:
                elements.append(PageBreak())
            elements.append(Paragraph(f"{tcode_result['tcode']} - {tcode_result['name']}", h2_style))
            
            # Add Analysis Summary
            analysis = tcode_result.get("analysis_summary", "Analysis completed.")
            elements.append(Paragraph(f"<b>System Analysis:</b> {analysis}", styles['Normal']))
            elements.append(Spacer(1, 5))
            
            # SM21 special: embed all scroll-page screenshots
            sm21_pages = tcode_result.get("sm21_pages", [])
            if tcode_result['tcode'] == 'SM21' and sm21_pages:
                elements.append(Paragraph("Visual Evidence (SAP WebGUI - System Log Pages):", styles['Normal']))
                for pi, ss_path in enumerate(sm21_pages):
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            print(f"DEBUG PDF: SM21 page {pi+1} embedded ({file_size} bytes)")
                            elements.append(Paragraph(f"Page {pi+1}:", styles['Normal']))
                            try:
                                img = Image(ss_path, width=14.0*inch, height=7.5*inch)
                                elements.append(img)
                            except Exception as e:
                                print(f"DEBUG PDF: SM21 page {pi+1} error: {e}")
                            elements.append(Spacer(1, 10))
            
            # ST22 special: embed Today + Yesterday screenshots
            elif tcode_result['tcode'] == 'ST22' and tcode_result.get("st22_pages", []):
                st22_pages = tcode_result["st22_pages"]
                day_labels = ["Today", "Yesterday"]
                elements.append(Paragraph("Visual Evidence (SAP WebGUI - ABAP Dumps):", styles['Normal']))
                for pi, ss_path in enumerate(st22_pages):
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            label = day_labels[pi] if pi < len(day_labels) else f"Page {pi+1}"
                            print(f"DEBUG PDF: ST22 {label} embedded ({file_size} bytes)")
                            elements.append(Paragraph(f"{label}:", styles['Normal']))
                            try:
                                img = Image(ss_path, width=14.0*inch, height=7.5*inch)
                                elements.append(img)
                            except Exception as e:
                                print(f"DEBUG PDF: ST22 {label} error: {e}")
                            elements.append(Spacer(1, 10))
            else:
                # Standard screenshot embedding for other tcodes
                screenshot_path = tcode_result.get("screenshot")
                if screenshot_path and os.path.exists(screenshot_path):
                    file_size = os.path.getsize(screenshot_path)
                    if file_size > 5000:
                        print(f"DEBUG PDF: Embedding screenshot {screenshot_path} ({file_size} bytes)")
                        elements.append(Paragraph("Visual Evidence (SAP WebGUI):", styles['Normal']))
                        try:
                            img = Image(screenshot_path, width=14.0*inch, height=7.5*inch)
                            elements.append(img)
                        except Exception as e:
                            print(f"DEBUG PDF: Image error: {e}")
                            elements.append(Paragraph(f"[Image load error: {e}]", styles['Normal']))
                        elements.append(Spacer(1, 10))
                    else:
                        print(f"DEBUG PDF: Skipping blank screenshot {screenshot_path} ({file_size} bytes)")
                        elements.append(Paragraph("[Screenshot not available - WebGUI capture returned blank]", styles['Normal']))
                        elements.append(Spacer(1, 5))

            # DB02 special: embed additional performance/status screenshots
            db02_pages = tcode_result.get("db02_pages", [])
            if tcode_result['tcode'] == 'DB02' and db02_pages:
                db02_labels = ["Overview", "Performance Graph"]
                elements.append(Paragraph("Additional DB02 Views:", styles['Normal']))
                for pi, ss_path in enumerate(db02_pages):
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            label = db02_labels[pi] if pi < len(db02_labels) else f"Page {pi+1}"
                            print(f"DEBUG PDF: DB02 {label} embedded ({file_size} bytes)")
                            elements.append(Paragraph(f"{label}:", styles['Normal']))
                            try:
                                img = Image(ss_path, width=14.0*inch, height=7.5*inch)
                                elements.append(img)
                            except Exception as e:
                                print(f"DEBUG PDF: DB02 {label} error: {e}")
                            elements.append(Spacer(1, 10))

            # ST03N special
            st03n_pages = tcode_result.get("ST03N_pages", [])
            if tcode_result['tcode'] == 'ST03N' and st03n_pages:
                st03n_labels = ["Workload Overview", "Transaction Profile", "Time Profile", "Response Time Distribution"]
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

            # SCC4 special
            scc4_pages = tcode_result.get("SCC4_pages", [])
            if tcode_result['tcode'] == 'SCC4' and scc4_pages:
                elements.append(Paragraph("SCC4 Client Configurations:", styles['Normal']))
                for pi in range(1, len(scc4_pages)):
                    ss_path = scc4_pages[pi]
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            print(f"DEBUG PDF: SCC4 Client {pi} embedded ({file_size} bytes)")
                            elements.append(Paragraph(f"Client {pi}:", styles['Normal']))
                            try:
                                img = Image(ss_path, width=14.0*inch, height=7.5*inch)
                                elements.append(img)
                            except Exception as e:
                                print(f"DEBUG PDF: SCC4 error: {e}")
                            elements.append(Spacer(1, 10))

            # SMLG special
            smlg_pages = tcode_result.get("SMLG_pages", [])
            if tcode_result['tcode'] == 'SMLG' and len(smlg_pages) > 1:
                smlg_labels = ["Load Distribution"]
                elements.append(Paragraph("SMLG Load Distribution Views:", styles['Normal']))
                for pi in range(1, len(smlg_pages)):
                    ss_path = smlg_pages[pi]
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            label = smlg_labels[pi-1] if (pi-1) < len(smlg_labels) else f"Page {pi+1}"
                            print(f"DEBUG PDF: SMLG {label} embedded ({file_size} bytes)")
                            elements.append(Paragraph(f"{label}:", styles['Normal']))
                            try:
                                img = Image(ss_path, width=14.0*inch, height=7.5*inch)
                                elements.append(img)
                            except Exception as e:
                                print(f"DEBUG PDF: SMLG error: {e}")
                            elements.append(Spacer(1, 10))

            # SMGW special
            smgw_pages = tcode_result.get("SMGW_pages", [])
            if tcode_result['tcode'] == 'SMGW' and len(smgw_pages) > 1:
                smgw_labels = ["Logged On Clients"]
                elements.append(Paragraph("SMGW Logged-On Clients:", styles['Normal']))
                for pi in range(1, len(smgw_pages)):
                    ss_path = smgw_pages[pi]
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            label = smgw_labels[pi-1] if (pi-1) < len(smgw_labels) else f"Page {pi+1}"
                            print(f"DEBUG PDF: SMGW {label} embedded ({file_size} bytes)")
                            elements.append(Paragraph(f"{label}:", styles['Normal']))
                            try:
                                img = Image(ss_path, width=14.0*inch, height=7.5*inch)
                                elements.append(img)
                            except Exception as e:
                                print(f"DEBUG PDF: SMGW error: {e}")
                            elements.append(Spacer(1, 10))

            # SMICM special
            smicm_pages = tcode_result.get("SMICM_pages", [])
            if tcode_result['tcode'] == 'SMICM' and len(smicm_pages) > 1:
                smicm_labels = ["ICM Services List"]
                elements.append(Paragraph("SMICM ICM Services Views:", styles['Normal']))
                for pi in range(1, len(smicm_pages)):
                    ss_path = smicm_pages[pi]
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            label = smicm_labels[pi-1] if (pi-1) < len(smicm_labels) else f"Page {pi+1}"
                            print(f"DEBUG PDF: SMICM {label} embedded ({file_size} bytes)")
                            elements.append(Paragraph(f"{label}:", styles['Normal']))
                            try:
                                img = Image(ss_path, width=14.0*inch, height=7.5*inch)
                                elements.append(img)
                            except Exception as e:
                                print(f"DEBUG PDF: SMICM error: {e}")
                            elements.append(Spacer(1, 10))

            # STRUST special
            strust_pages = tcode_result.get("STRUST_pages", [])
            if tcode_result['tcode'] == 'STRUST' and len(strust_pages) > 1:
                elements.append(Paragraph("STRUST Expiring Certificates:", styles['Normal']))
                for pi in range(1, len(strust_pages)):
                    ss_path = strust_pages[pi]
                    if os.path.exists(ss_path):
                        file_size = os.path.getsize(ss_path)
                        if file_size > 5000:
                            print(f"DEBUG PDF: STRUST Page {pi} embedded ({file_size} bytes)")
                            elements.append(Paragraph(f"Anomaly Detail {pi}:", styles['Normal']))
                            try:
                                img = Image(ss_path, width=14.0*inch, height=7.5*inch)
                                elements.append(img)
                            except Exception as e:
                                print(f"DEBUG PDF: STRUST error: {e}")
                            elements.append(Spacer(1, 10))

            if tcode_result["anomalies"]:
                elements.append(Paragraph("Anomalies Detected:", styles['Normal']))
                for anom in tcode_result["anomalies"]:
                    elements.append(Paragraph(f"• {anom}", styles['Normal']))
            else:
                elements.append(Paragraph("Status: Normal", styles['Normal']))
                
            elements.append(Spacer(1, 10))

            data = tcode_result.get("data")
            # Skip tables for all monitored T-codes
            if False: # Keep original logic for future reference
                keys = list(data[0].keys()) # Restore all columns
                table_data = [keys]
                # Compact table if screenshot exists
                display_rows = 20 if screenshot_path else 100
                for item in data[:display_rows]:
                    table_data.append([str(item.get(k, "")) for k in keys])
                
                t = Table(table_data)
                t.setStyle(TableStyle([
                    ('BACKGROUND', (0,0), (-1,0), colors.lightgrey),
                    ('GRID', (0,0), (-1,-1), 0.5, colors.black),
                    ('FONTSIZE', (0,0), (-1,-1), 5), # Tiny font for many columns
                    ('ALIGN', (0,0), (-1,-1), 'LEFT'),
                ]))
                elements.append(t)
            else:
                pass # No specific RFC table data available.

            elements.append(Spacer(1, 20))

        doc.build(elements)
        return filepath

if __name__ == "__main__":
    # Test Report Generation
    mock_results = {
        "anomalies": ["SM37: Failed background jobs found.", "DB02: Missing indexes detected."],
        "external_checks": [
            {"server": "app_server_1", "type": "OS Filesystem", "status": "OK", "details": "All filesystems under 90%"}
        ],
        "tcodes": [
            {
                "tcode": "SM37",
                "name": "Background Jobs",
                "anomalies": ["SM37: Failed background jobs found."],
                "screenshot": ""
            }
        ]
    }
    generator = ReportGenerator(mock_results)
    word_path = generator.generate_word()
    pdf_path = generator.generate_pdf()
    print(f"Generated Word: {word_path}")
    print(f"Generated PDF: {pdf_path}")
