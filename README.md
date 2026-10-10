# WTQ Build Track - Utility Bill Decoder

Reads K-Electric / LESCO / IESCO electricity bill images and
1. **Level 1** - extracts the bill into a fixed JSON schema,
2. **Level 2** - answers customer questions about the bill in plain English.

Runtime: **Python 3.12** (3.11+ works).

## How it works

| Step | What happens | Where |
|------|--------------|-------|
| 1 | Image is auto-rotated (EXIF) and downscaled if huge | `bill_decoder/llm.py` |
| 2 | Vision LLM extracts the Level 1 JSON using the guide's rules + a worked example | `extract.py`, `prompts.py` |
| 3 | Output is normalised in code (numbers, `CR` credits, dates, enum types, zero/blank lines dropped, identifiers never kept) | `postprocess.py` |
| 4 | Consistency checks (charges sum = subtotal, taxes sum = subtotal, readings vs units). On failure the model gets **one** re-look at the image; the more self-consistent result is kept | `extract.py` |
| 5 | A second pass transcribes usage history, billing history, calculation lines, late-payment amounts, message board | `extract.py` |
| 6 | Level 2: LLM *plans* the arithmetic as small expressions -> **code computes them exactly** (safe AST evaluator, no `eval`) -> LLM writes answers using the computed numbers | `qa.py`, `calc.py` |
| 7 | CSVs are written with the `csv` module (correct quoting, one-line JSON) | `csv_io.py` |

Reliability: retries with backoff, per-bill JSON cache (`.cache/`, safe to resume after a crash), a failed bill degrades to
nulls / a "cannot determine" answer instead of crashing the run, bills are processed in parallel.

## Setup (Windows / PowerShell in VS Code - no virtual environment)

Default model: **Gemini 3.5 Flash-Lite** via a free Google AI Studio key (`gemini-3.1-flash-lite` also works).

```powershell
pip install -r requirements.txt
copy .env.example .env      # then edit .env and paste your API key
```
Packages are installed straight into your Python 3.11+ install (no venv needed).
(`requirements-optional.txt` is only for the Anthropic/OpenAI providers.)
macOS/Linux: `pip3 install -r requirements.txt && cp .env.example .env`.

`.env` variables: `MODEL_PROVIDER` (`anthropic|google|openai`), `MODEL_NAME`, `API_KEY`, plus optional
`REQUEST_DELAY_SECONDS` (set to `4.5` for the Gemini free tier, 15 requests/min), `MAX_WORKERS`, `CACHE_DIR`, `MAX_IMAGE_SIDE`.
Only the competition-approved models are accepted; anything else exits with an error.

## Run

Full test run (writes `output/level1.csv` and `output/level2.csv`):
```powershell
python main.py run --bills test/bills --level1 test/csv/level1.csv --level2 test/csv/level2.csv --out output
```
Score extraction on the training bills (compares with hand-checked `train/expected/*.json`; the guide only gives the answer for KESC_0008, add more files there as you check bills by hand):
```powershell
python main.py eval
```
One bill (development / demo):
```powershell
python main.py bill train/bills/KESC_0008.png --ask "How much of my bill is taxes?" --ask "How many months went above 200 units?"
```
Offline tests (no API key): `python -m tests.test_offline` and `python -m tests.test_pipeline_fake_llm`.

Build the submission ZIP (validates CSVs, scans for leaked keys, checks 15 MB): 
`python package_submission.py --output output --demo demo/demo.mp4`

## AI usage

- **Models used at runtime:** gemini-3.5-flash-lite (Google Gemini API, google-genai SDK) - *edit this line if you change MODEL_NAME*.
- **APIs / services:** Google Gemini API. Local libraries: Pillow (image handling). No OCR or invoice-extraction services.
- **AI tools used to write the code:** Claude (claude.ai chat).
- Everything the LLM does is verified or post-processed in code: schema normalisation, consistency checks, exact arithmetic.
