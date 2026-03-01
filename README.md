# `scrix`

Weekly BOGO Publix deals

## Gemini setup (for `test.py`)

- Set your API key in an environment variable:
  - `GOOGLE_API_KEY` (recommended) or `GEMINI_API_KEY`
- Optional: override the model with `GEMINI_MODEL`.
  - Default is `gemini-1.5-pro-latest` (this avoids the common `models/gemini-1.5-pro` 404).

## Publix deal data sanitizer

This repo includes a small helper script, `sanitizer.py`, for cleaning/normalizing the scraped `publix.json` output.

### What it does

- Adds structured fields for easier downstream analysis:
  - `savings_parsed` (normalizes things like `Save Up To $5.55 Lb`)
  - `offer_parsed` (normalizes things like `Buy 1 Get 1 Free`, `2 for $10.00`, `$8.99 lb`, `Sale Price $29.99`)
- Preserves the original values in `savings_raw` / `offer_raw`.
- Writes JSON as UTF-8 with `ensure_ascii=false` so accented characters render properly.
- Emits a simple report (`*.report.json`) with counts of parsed deal types and any warnings.
- If the input file appears truncated at EOF, it will attempt a best-effort repair by appending missing closing brackets/braces.

### Usage

Run it against a scraped file:

```bash
python3 sanitizer.py publix.json --pretty
```

By default it writes:

- `publix.json.sanitized.json`
- `publix.json.report.json`

You can override output locations:

```bash
python3 sanitizer.py publix.json \
  --out cleaned.json \
  --report cleaned.report.json \
  --pretty
```
