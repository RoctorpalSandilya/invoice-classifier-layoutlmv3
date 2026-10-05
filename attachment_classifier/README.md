# attachment_classifier

Fine-tunes `microsoft/layoutlmv3-base` to classify document attachments as **invoice** (1) vs
**not invoice** (0). Handles PDF, JPG/JPEG/PNG and DOCX. First page only.

```
attachment_classifier/
  config.py            all paths / hyper-params / seed (edit here, nowhere else)
  sources/             where attachments come from (filesystem now, Postgres+Blob later)
  extraction/          bytes -> words + boxes + page image  (+ on-disk cache)
  dataset/             AttachmentSource -> HF DatasetDict (train/test) + manifest.csv
  training/            Trainer fine-tuning + evaluation
  inference/           AttachmentClassifier: the only API the production system calls
  cli.py               train / evaluate / predict
  tests/               pytest smoke tests
```

## System dependencies

| Dependency | Why | Install |
|---|---|---|
| Tesseract 5 + `eng`, `fra` language packs | OCR for images and scanned PDFs | Windows: UB-Mannheim installer (per-user install lands in `%LOCALAPPDATA%\Programs\Tesseract-OCR`). Linux: `apt install tesseract-ocr tesseract-ocr-eng tesseract-ocr-fra`. Extra languages: drop `*.traineddata` from the `tessdata_fast` repo into the `tessdata` folder. |
| LibreOffice (`soffice`) | DOCX -> PDF conversion | Windows MSI or `apt install libreoffice-writer`. |
| Poppler | **not required**: pdfplumber renders pages through pypdfium2 | – |

`config.py` auto-detects `tesseract` and `soffice` on `PATH` and in the usual Windows install
folders. Override with `Config(tesseract_cmd=..., soffice_cmd=...)` if needed.

```
pip install -r requirements.txt
```

## Offline / proxy environments (model weights)

`config.py` uses `./models/layoutlmv3-base` when that folder exists, otherwise the Hub id
`microsoft/layoutlmv3-base`. On networks with TLS inspection, Python's `certifi` bundle may
reject huggingface.co while `curl` (Windows cert store) succeeds. In that case fetch the weights
once with curl and the pipeline runs fully offline afterwards:

```
mkdir models\layoutlmv3-base
for %f in (config.json merges.txt preprocessor_config.json tokenizer_config.json vocab.json model.safetensors) do ^
  curl -L -o models\layoutlmv3-base\%f https://huggingface.co/microsoft/layoutlmv3-base/resolve/main/%f
```

## Hardware expectations

Measured on a 12-core laptop CPU (i5-1245U), batch size 4, 512 tokens:

| Mode | per step | per epoch (1 120 train files) |
|---|---|---|
| full fine-tune | ~40 s | ~3 h |
| `--freeze-backbone` | ~16 s | ~1.2 h |

A CUDA GPU brings a full epoch down to a few minutes. The first extraction pass (OCR of ~1 150
images) takes 20–40 min and is cached afterwards.

## Data layout (current source)

```
Attachments/
  invoices/   -> label 1   (folder may be called "invoice" or "invoices")
  random/     -> label 0
```

## Run

From the folder that contains the `attachment_classifier` package:

```
# full fine-tune, 5 epochs
python -m attachment_classifier.cli train --source-root ./Attachments

# linear probe (frozen backbone) – faster, fine for small datasets / CPU
python -m attachment_classifier.cli train --source-root ./Attachments --freeze-backbone --epochs 3

# quick experiment on 50 files per class
python -m attachment_classifier.cli train --max-items 50 --epochs 1

# evaluate a saved model (same seed -> identical split)
python -m attachment_classifier.cli evaluate --model-dir ./artifacts/run_<ts>/model --source-root ./Attachments

# classify one file
python -m attachment_classifier.cli predict --model-dir ./artifacts/run_<ts>/model --file some.pdf
```

Artifacts land in `./artifacts/run_<timestamp>/`:
`model/` (model + processor), `metrics.json` (train/test metrics, confusion matrix, config,
dataset sizes, skipped files), `manifest.csv`, `test_predictions.csv`.

The first extraction pass is slow (OCR). Results are cached in `./.feature_cache` keyed by the
sha256 of the file bytes, so later runs are fast. Delete the folder to force re-extraction.

## Using the model from code

```python
from attachment_classifier.inference import AttachmentClassifier

clf = AttachmentClassifier("artifacts/run_.../model")
res = clf.predict(pdf_bytes, "application/pdf")
res.prob_invoice, res.is_invoice, res.has_text_layer, res.n_words
```

## Adding a new AttachmentSource (e.g. Postgres + Azure Blob)

1. Subclass `sources.base.AttachmentSource` and implement `iter_items()` yielding
   `AttachmentItem(id, filename, content_type, data: bytes, label)`.
   A stub with the intended design is in `sources/postgres_blob.py`.
2. Pass an instance to `dataset.build_dataset(source, processor, cfg, out_dir)`.
3. Nothing in `extraction/`, `training/` or `inference/` imports from `sources/`, so no other
   change is needed. For production scoring, call `AttachmentClassifier.predict(bytes, content_type)`
   directly with the blob bytes.

## Tests

```
pytest attachment_classifier/tests -q
```

The predict round-trip test is skipped automatically until a trained model exists under
`./artifacts/run_*/model` (or set `AC_MODEL_DIR`).
