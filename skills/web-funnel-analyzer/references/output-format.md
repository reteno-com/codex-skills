# Output Format

This skill writes all artifacts under:
- `./output/funnels/screens/<run_name>/`
- `./output/funnels/texts/<run_name>/`

## Per-step screenshot

Pattern:
- `step-001.png`, `step-002.png`, ...

## Per-step text file

Pattern:
- `step-001.md`, `step-002.md`, ...

Sections:
1. Header metadata: URL, step number, step marker (`X of Y`), detected title/question.
2. `## DOM text`
3. `## OCR text` (present if OCR was attempted)
4. `## Merged text`

## Manifest

File:
- `manifest.json`

Key fields:
- `run_name`
- `url`
- `started_at`
- `ended_at`
- `stop_reason`
- `total_steps`
- `steps` (array of step records with screenshot/text paths and metadata)
- `warnings`

## Summary

File:
- `summary.md`

Includes:
1. Funnel overview (entry URL, captured screens, stop reason)
2. Step-by-step table
3. Key messaging themes and psychological hooks
4. CTA progression notes
5. Email-writing implications (subject angles, body themes, objections)
