# PDF Digital Sign (Django)

Place your signature on PDFs with **different position per page**.

## Features

1. **Upload signature** (or enter a local signature file path)
2. **Upload a sample PDF** (to preview pages and set positions)
3. **Main PDF path** — single PDF file, or a folder of PDFs
4. **Output path** — where signed files are saved
5. **Per-page placement** — click each page preview (or type X/Y) to put the signature where you want

## Setup

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver
```

Open: http://127.0.0.1:8000/

## How to use

### Step 1 — Setup
- Upload your signature **or** paste its path (e.g. `E:\signs\sign.png`)
- Upload a **sample PDF** (used for page preview / positions)
- Optional: set **Main PDF path** to a file or folder  
  - If folder: all PDFs in that folder are signed with the same page positions  
  - If empty: only the uploaded sample is signed
- Set **Output folder path** (e.g. `E:\pdfs\signed`)

### Step 2 — Position per page
- Select each page from the left list
- **Click** on the preview where you want the signature (bottom-left of the sign)
- Or type **X / Y / Width** in points
- Uncheck “Place signature on this page” to skip a page
- Click **Sign PDFs & save**

### Step 3 — Done
Signed files appear in your output folder with the **same original filename**.

## Notes

- Coordinates use PDF space: origin is **bottom-left**, units are points (72 pt ≈ 1 inch).
- This places a **signature image** on the PDF (not a cryptographic certificate signature).
- After signing, files are saved to your output folder and also copied to S3 automatically (no S3 UI).
