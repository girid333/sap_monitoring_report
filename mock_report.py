import os
from backend.report_generator import ReportGenerator

mock_results = {
    "start_time": "2026-05-24 15:00:00",
    "end_time": "2026-05-24 15:01:00",
    "anomalies": [
        "STRUST: Certificate Expired (System PSE)",
        "SMICM: Service SMTP port 26 is inactive",
        "ST22: Dump found TIME_OUT",
        "SM21: Database error in system log"
    ],
    "tcodes": [
        {
            "tcode": "SMICM",
            "name": "ICM Monitor",
            "pages": ["backend/screenshots/mock_smicm.png"],
            "anomalies": ["SMICM: Service SMTP port 26 is inactive"]
        },
        {
            "tcode": "STRUST",
            "name": "Trust Manager",
            "pages": ["backend/screenshots/mock_strust.png"],
            "anomalies": ["STRUST: Certificate Expired (System PSE)"]
        }
    ],
    "external_checks": [
        {
            "type": "SAP Web Dispatcher",
            "status": "UP",
            "method": "HTTP",
            "url": "https://example.com"
        }
    ]
}

# Create dummy images so generator doesn't fail
os.makedirs("backend/screenshots", exist_ok=True)
try:
    from PIL import Image
    Image.new('RGB', (100, 100), color='grey').save("backend/screenshots/mock_smicm.png")
    Image.new('RGB', (100, 100), color='grey').save("backend/screenshots/mock_strust.png")
except Exception:
    pass

generator = ReportGenerator(mock_results, output_dir="backend/reports_test")
print("Generating Word...")
try:
    word_file = generator.generate_word()
    print(f"Word done: {word_file}")
except Exception as e:
    print(f"Word error: {e}")

print("Generating PDF...")
try:
    pdf_file = generator.generate_pdf()
    print(f"PDF done: {pdf_file}")
except Exception as e:
    print(f"PDF error: {e}")
