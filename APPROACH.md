# Approach and findings

Native PyMuPDF extraction is high quality; OCR is unnecessary. Both PDFs have no metadata. v1 has 6 pages and v2 has 7. Observed structure includes `2.1.1.1`, out-of-order `3.4` then `3.3`, duplicate "Error Codes" headings, page continuations, and text-extracted tables. v2 changes battery cycles 300→250 and low battery 15%→10%, inflation steps 40→30 mmHg, E3 2→1.5 seconds, adds E6, and adds §5.3.

Matching first uses normalized numbered headings, preserving duplicates and marking ambiguous matches. This is deliberately conservative: renamed or duplicated headings can be ambiguous. Staleness compares immutable snapshots to the newest unique logical match; numeric/unit/timing/negation changes are `potentially_high` heuristic signals, not clinical risk assessment.

## Decision log

* PDF reading order is the most likely silent failure; warnings, parser tests, and source snapshots expose it.
* Heading matching favors simplicity; major heading renames would be ambiguous first.
* Image-only/scanned tables are unsupported without Tesseract configured; they remain absent/low-confidence.
