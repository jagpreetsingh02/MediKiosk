"""Generate the Module B document fixtures.

Three kinds, because the three exercise different code paths:

* **Digital PDF** — has a text layer. TextLayerOCR reads it exactly; Tesseract has to
  rasterise and recognise. This is the pair that makes the benchmark interesting.
* **Clean scan (PNG)** — no text layer. TextLayerOCR must fail honestly; Tesseract reads it.
* **Degraded scan (PNG)** — blurred, low contrast, rotated, noisy: a photograph of a creased
  prescription taken on a cheap phone in bad light, which is what actually arrives at a kiosk.
  Drives the handwriting / low-confidence lane.

Ground truth for every fixture is written alongside as `<name>.truth.json`, so the benchmark
scores against something rather than against a vibe.
"""
from __future__ import annotations

import json
import random
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont
from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

OUT = Path(__file__).resolve().parents[1] / "data" / "fixtures" / "documents"
OUT.mkdir(parents=True, exist_ok=True)
random.seed(20260823)

PRESCRIPTION = [
    "SHRI VENKATESHWARA POLYCLINIC",
    "Dr. R. Sharma, MBBS MD (Gen Med)    Reg No. TN/12345",
    "",
    "Patient: [synthetic]        Age: 64 / F",
    "Date: 14/03/2026",
    "",
    "Diagnosis: Type 2 diabetes mellitus with hypertension",
    "",
    "Rx",
    "TAB. METFORMIN 500MG 1-0-1 x 30 days",
    "TAB. AMLODIPINE 5MG OD x 30 days",
    "TAB. ATORVASTATIN 10MG HS x 30 days",
    "CAP. OMEPRAZOLE 20MG 1-0-0 x 14 days",
    "",
    "Advice: review after one month with fasting sugar",
]

LAB_REPORT = [
    "METRO DIAGNOSTICS - BIOCHEMISTRY REPORT",
    "Sample collected on 02/02/2026",
    "",
    "Haemoglobin 9.4 g/dL           (12.0 - 15.0)",
    "HbA1c 8.2 %                    (4.0 - 5.6)",
    "Fasting Blood Sugar 168 mg/dL  (70 - 99)",
    "Serum Creatinine 1.1 mg/dL     (0.6 - 1.1)",
    "TSH 6.8 uIU/mL                 (0.4 - 4.0)",
    "Total Cholesterol 214 mg/dL    (0 - 200)",
    "ESR 34 mm/hr                   (0 - 20)",
]

DISCHARGE = [
    "GOVERNMENT GENERAL HOSPITAL - DISCHARGE SUMMARY",
    "Admitted: 03/09/2024    Discharged: 09/09/2024",
    "",
    "Diagnosis: Community acquired pneumonia",
    "Procedure: Pleural tap done on 05/09/2024",
    "",
    "Discharge medication:",
    "TAB. AMOXICILLIN 625MG TDS x 7 days",
    "SYP. LACTULOSE 15ML HS",
]

TRUTH = {
    "prescription": {
        "medications": [
            {"name": "METFORMIN", "dose": "500MG", "frequency": "1-0-1"},
            {"name": "AMLODIPINE", "dose": "5MG", "frequency": "OD"},
            {"name": "ATORVASTATIN", "dose": "10MG", "frequency": "HS"},
            {"name": "OMEPRAZOLE", "dose": "20MG", "frequency": "1-0-0"},
        ],
        "diagnoses": ["Type 2 diabetes mellitus with hypertension"],
        "investigations": [],
        "documentDate": "2026-03-14",
    },
    "lab_report": {
        "medications": [],
        "diagnoses": [],
        "investigations": [
            {"analyte": "Haemoglobin", "value": 9.4, "flag": "low"},
            {"analyte": "HbA1c", "value": 8.2, "flag": "high"},
            {"analyte": "Fasting Blood Sugar", "value": 168.0, "flag": "high"},
            {"analyte": "Serum Creatinine", "value": 1.1, "flag": "in_range"},
            {"analyte": "TSH", "value": 6.8, "flag": "high"},
            {"analyte": "Total Cholesterol", "value": 214.0, "flag": "high"},
            {"analyte": "ESR", "value": 34.0, "flag": "high"},
        ],
        "documentDate": "2026-02-02",
    },
    "discharge": {
        "medications": [
            {"name": "AMOXICILLIN", "dose": "625MG", "frequency": "TDS"},
            {"name": "LACTULOSE", "dose": "15ML", "frequency": "HS"},
        ],
        "diagnoses": ["Community acquired pneumonia"],
        "investigations": [],
        "documentDate": "2024-09-03",
    },
}

DOCS = {"prescription": PRESCRIPTION, "lab_report": LAB_REPORT, "discharge": DISCHARGE}


def write_pdf(name: str, lines: list[str]) -> None:
    pdf = canvas.Canvas(str(OUT / f"{name}.pdf"), pagesize=A4)
    _, height = A4
    pdf.setFont("Helvetica", 11)
    y = height - 70
    for line in lines:
        pdf.drawString(56, y, line)
        y -= 18
    pdf.save()


def _font(size: int) -> ImageFont.FreeTypeFont:
    for candidate in (
        "/System/Library/Fonts/Supplemental/Courier New.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/Library/Fonts/Arial.ttf",
    ):
        if Path(candidate).exists():
            return ImageFont.truetype(candidate, size)
    return ImageFont.load_default(size)


def write_png(name: str, lines: list[str], *, degraded: bool) -> None:
    width, height = 1240, 1754  # A4 at 150 dpi
    image = Image.new("L", (width, height), 255)
    draw = ImageDraw.Draw(image)
    font = _font(26)
    y = 90
    for line in lines:
        draw.text((70, y), line, font=font, fill=30)
        y += 42

    if degraded:
        # A phone photo of a creased page under a ceiling tube light.
        #
        # Calibrated deliberately: the point of this fixture is to drive entities into the
        # VERIFICATION LANE, which means text that is recognisable but not confidently so.
        # An earlier, harsher version produced zero output — which tests nothing at all,
        # because "the OCR found nothing" and "the OCR found the wrong dose" are entirely
        # different failure modes and only the second one is dangerous.
        image = image.rotate(-0.9, resample=Image.BICUBIC, fillcolor=255)
        image = image.filter(ImageFilter.GaussianBlur(radius=0.8))
        pixels = image.load()
        assert pixels is not None
        for _ in range(int(width * height * 0.020)):
            x, ry = random.randrange(width), random.randrange(height)
            pixels[x, ry] = max(0, min(255, pixels[x, ry] + random.randint(-70, 70)))
        # Uneven illumination: bright at the top-left, falling off to the bottom-right.
        shade = Image.linear_gradient("L").resize((width, height))
        image = Image.blend(image, shade, 0.12)
        image = image.point(lambda v: int(60 + (v - 60) * 0.78))  # crush the contrast

    image.save(OUT / f"{name}{'_degraded' if degraded else '_scan'}.png")


def main() -> None:
    for name, lines in DOCS.items():
        write_pdf(name, lines)
        write_png(name, lines, degraded=False)
        write_png(name, lines, degraded=True)
        (OUT / f"{name}.truth.json").write_text(json.dumps(TRUTH[name], indent=2) + "\n")
        (OUT / f"{name}.txt").write_text("\n".join(lines) + "\n")

    (OUT / "README.md").write_text(
        "# Document fixtures\n\n"
        "Generated by `scripts/make_document_fixtures.py`. All synthetic: no real patient, no\n"
        "real doctor, no real registration number.\n\n"
        "| Suffix | What it is | Which backend it exercises |\n"
        "|---|---|---|\n"
        "| `.pdf` | digital PDF with a text layer | both — this is the benchmark pair |\n"
        "| `_scan.png` | clean 150 dpi render, no text layer | tesseract (textlayer must fail honestly) |\n"
        "| `_degraded.png` | rotated, blurred, noisy, low contrast | the low-confidence / verification lane |\n"
        "| `.truth.json` | ground truth | scoring for `eval/ocr_bench.py` |\n"
        "| `.txt` | plain text | fast unit tests |\n"
    )
    print(f"wrote {len(list(OUT.iterdir()))} files to {OUT}")


if __name__ == "__main__":
    main()
