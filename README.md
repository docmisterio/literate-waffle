# Trivia Rubric Extractor

Generate quick-grading CSV rubrics from Geeks Who Drink-style trivia PDFs.

## Requirements

- Python 3.9+ (macOS ships with 3.9; any later version works)
- PDFs must be the standard export with embedded question text (not image-only scans)
- Optional: [`pdfminer.six`](https://github.com/pdfminer/pdfminer.six) for best text extraction accuracy (`python3 -m pip install pdfminer.six`)

The script automatically falls back to a lightweight built-in parser if `pdfminer.six` is unavailable, but complex modern exports generally require it to decode embedded fonts correctly.

## Usage

```bash
python3 trivia_rubric.py /path/to/Quiz.pdf
```

- The CSV name defaults to the PDF name (e.g., `Quiz.pdf` → `Quiz.csv`) in the same directory.
- Optionally pass a second argument to choose a different output path:

  ```bash
  python3 trivia_rubric.py /path/to/Quiz.pdf /desired/output/rubric.csv
  ```

### Working With iCloud or Read-Only Locations

If the PDF lives in iCloud Drive or another protected folder, you may not have write access next to the file. Either supply an output path you control, or copy the PDF into this repository before running the script.

Example:

```bash
python3 trivia_rubric.py "/Users/you/Desktop/localFolder/061323_Quiz1.pdf" ./rubrics/061323.csv
```

## Output Format

Each round becomes a block in the CSV:

```
Round 1: Hubba Hubba!
Question,Answer
1,ABBA
2,Caribbean Sea
...
```

Tiebreakers (when present) appear as a final section.

## Troubleshooting

- **“PDF not found”** – Double-check the path (quote it if there are spaces) and ensure the file is downloaded locally.
- **“Cannot write to …”** – Run the script from a writable folder or pass a different output path.
- **Blank/incorrect answers** – The script only works on PDFs containing embedded text. Image-only scans need OCR before parsing.
