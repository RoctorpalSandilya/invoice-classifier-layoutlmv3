# Invoice vs not-invoice attachment classifier (LayoutLMv3)

Classifies email attachments (PDF, JPG/JPEG/PNG, DOCX) as **invoice** or **not invoice** using
[`microsoft/layoutlmv3-base`](https://huggingface.co/microsoft/layoutlmv3-base), a document model
that reads the words, their positions on the page and the page image together.

## Results

Test set of 280 documents (stratified 20% hold-out, seed 42), frozen backbone, 3 epochs, CPU:

| Accuracy | Precision | Recall | F1 |
|---|---|---|---|
| 98.6% | 97.8% | 100% | 98.9% |

| | Predicted not invoice | Predicted invoice |
|---|---|---|
| **Actually not invoice** | 96 | 4 |
| **Actually invoice** | 0 | 180 |

Every invoice was caught. Three of the four false positives are plain-prose PDFs
(lorem ipsum, a page of text), which points to too few general-document negatives in the data.

## How it works

1. **Extraction** (first page only)
   - PDF with a text layer: words and boxes from `pdfplumber`, page rendered at 150 DPI.
   - Scanned PDF or image: OCR with Tesseract (`eng+fra`).
   - DOCX: converted to PDF with LibreOffice headless, then the PDF path.
   - Boxes are normalised to the 0–1000 scale LayoutLMv3 expects. Results are cached by file hash.
2. **Encoding**: `LayoutLMv3Processor(apply_ocr=False)` turns words, boxes and image into 512 tokens.
3. **Model**: `LayoutLMv3ForSequenceClassification`. The encoder's first-token (`<s>`, CLS-style)
   vector goes through the built-in `LayoutLMv3ClassificationHead`:
   `dropout → Linear 768→768 → tanh → dropout → Linear 768→2 → softmax`.
4. **Training**: Hugging Face `Trainer`, class-weighted cross-entropy, best epoch kept by F1.
   With `--freeze-backbone` only the head's 592,130 parameters train (0.47% of 126 M);
   without it the whole model is fine-tuned.

## Repository layout

```
attachment_classifier/   the pipeline package (see its own README for module details)
  config.py              all paths, hyper-parameters, thresholds, seed
  sources/               where attachments come from (filesystem now; Postgres + Azure Blob stub)
  extraction/            bytes -> words + boxes + page image, with on-disk cache
  dataset/               source -> train/test DatasetDict + manifest.csv
  training/              fine-tuning and evaluation
  inference/             AttachmentClassifier: the only API production code needs
  cli.py                 train / evaluate / predict
  tests/                 pytest smoke tests
demo.py                  interactive demo: paste a file path, get the verdict and confidence
email_classifier/        zero-shot email (header + body) classification with Laya
scripts/                 data generators (lookalike documents, matching email header/body text)
Email/                   generated email header/body .txt files, one pair per attachment
artifacts/               trained model, metrics.json, manifest.csv, test_predictions.csv
```

## Quick start: run the demo on the trained model

The trained model (480 MB) is stored with [Git LFS](https://git-lfs.com), so install Git LFS
before cloning, otherwise you get a small pointer file instead of the weights.

```
git lfs install
git clone <this repo URL>
cd <repo folder>
pip install -r attachment_classifier/requirements.txt
python demo.py
```

Then paste the path of any PDF, JPG/PNG or DOCX at the `path>` prompt. Try the samples in
`Attachments/invoices/` and `Attachments/random/`. Images and scanned PDFs also need
**Tesseract** installed (see below); text PDFs work without it.

If you cloned without LFS, run `git lfs pull` inside the repo to fetch the weights.

## Setup

```
pip install -r attachment_classifier/requirements.txt
```

System dependencies: **Tesseract 5** with `eng` and `fra` language packs, and **LibreOffice**
(only needed for DOCX). Both are auto-detected on `PATH` and in the usual Windows install folders.

The demo and inference only need the trained model in `artifacts/run_frozen_3ep/model`. To
**train again**, the pretrained base weights are expected in `models/layoutlmv3-base`; they are
not committed, and the code falls back to the Hugging Face Hub if the folder is missing. On
networks where Python cannot reach the Hub, fetch them with curl:

```
mkdir models\layoutlmv3-base
for %f in (config.json merges.txt preprocessor_config.json tokenizer_config.json vocab.json model.safetensors) do ^
  curl -L -o models\layoutlmv3-base\%f https://huggingface.co/microsoft/layoutlmv3-base/resolve/main/%f
```

## Usage

```
# demo: paste paths at the prompt, or pass them as arguments
python demo.py
python demo.py path\to\file.pdf

# train (full fine-tune, 5 epochs) or a faster linear probe
python -m attachment_classifier.cli train --source-root ./Attachments
python -m attachment_classifier.cli train --source-root ./Attachments --freeze-backbone --epochs 3

# evaluate a saved model, or classify one file
python -m attachment_classifier.cli evaluate --model-dir artifacts/run_frozen_3ep/model
python -m attachment_classifier.cli predict  --model-dir artifacts/run_frozen_3ep/model --file some.pdf

# tests
pytest attachment_classifier/tests -q
```

On a 12-core laptop CPU a frozen-backbone epoch takes about 1.5 hours and a full fine-tune epoch
about 3 hours. A GPU brings either down to minutes.

## Data

The `Attachments/` folder (1,400 files, 315 MB) is included. It was assembled as follows:

| Folder | Count | Source |
|---|---|---|
| `invoices/` (label 1) | 900 .jpg | `images/` folders of [mouadhamri/invoice_dataset](https://github.com/mouadhamri/invoice_dataset) |
| `random/receipt_*` (label 0) | 250 .jpg | [ICDAR 2019 SROIE](https://github.com/zzzDavid/ICDAR-2019-SROIE) receipts, random sample, seed 42 |
| `random/lookalike_*` (label 0) | 157 .pdf + 58 .docx | Generated: `python scripts/gen_lookalikes.py Attachments/random 215` |
| `random/doc_*` (label 0) | 35 .pdf | [py-pdf/sample-files](https://github.com/py-pdf/sample-files) |

The lookalikes are purchase orders, quotations, delivery notes, payslips, bank statements, expense
reports, remittance advices, timesheets and credit applications, filled with fictional data from
Faker. `python scripts/gen_emails.py .` regenerates the `Email/` header and body files.

## Email header + body classification (Laya, zero-shot)

`email_classifier/` classifies the **email** rather than the attachment, using
[Laya](https://huggingface.co/convaiinnovations/laya) (`convaiinnovations/laya`, English checkpoint,
ModernBERT-large, 421 M parameters). Laya answers typed questions about an email in one forward pass,
so it can be used zero-shot, without training.

Zero-shot results on all 1,400 generated emails (900 invoice / 500 not), threshold 0.5:

| Input | Question | Accuracy | Precision | Recall | F1 |
|---|---|---|---|---|---|
| body | document type (invoice / receipt / PO / quote / statement / other) | **1.000** | 1.000 | 1.000 | **1.000** |
| header + body | document type | 0.999 | 0.999 | 1.000 | 0.999 |
| body | yes/no as a two-option choice | 0.975 | 0.963 | 1.000 | 0.981 |
| header + body | `noul` (true/false) | 0.962 | 0.953 | 0.990 | 0.971 |
| body | `noul` (true/false) | 0.957 | 0.938 | 1.000 | 0.968 |
| header + body | yes/no as a two-option choice | 0.956 | 0.937 | 1.000 | 0.967 |

Yes/no questions mostly misfire on purchase orders, remittance advices and receipts. **These numbers are
optimistic**: the emails are template-generated, every invoice email contains the word "invoice" (only 9
of 500 others do), and the document-type options mirror the generated negative categories. Validate on
real emails before relying on it. The attachment filename is excluded from the header input because in
this data it encodes the label (`--include-attachment-name` adds it back).

Setup: the Laya files are not committed (about 800 MB). Fetch them with curl:

```
mkdir models\laya\encoder models\laya\tokenizer
for %f in (model.safetensors rl_agent_api.py rl_common.py email_utils.py rl_agent_config.json encoder/config.json tokenizer/tokenizer.json tokenizer/tokenizer_config.json) do ^
  curl -L -o models\laya\%f https://huggingface.co/convaiinnovations/laya/resolve/main/%f
```

Run (about 1.5 s per email per question on a laptop CPU):

```
python -m email_classifier.zero_shot_eval                                    # all emails, both modes, 3 questions
python -m email_classifier.zero_shot_eval --modes body --questions doc_type  # best setup only
python -m email_classifier.zero_shot_eval --limit 20                         # quick check
```

Outputs go to `artifacts/laya_zero_shot/<run>/`: `metrics.json` (all metrics plus accuracy per
document subgroup) and `predictions.csv` (P(invoice) and the answer for every email and question).

## Limitations and next steps

- Plain-prose documents can be misread as invoices; add more letters, reports and articles as negatives.
- Only the classification head has been trained so far; a full fine-tune should be run on a GPU.
- Only the first page is used.
- The email classifier has only been tested zero-shot on generated emails; test it on real email traffic.
