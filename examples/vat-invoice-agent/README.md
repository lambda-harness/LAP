# VAT Invoice Extraction Agent

LAP Local 0.1 Agent for Chinese VAT invoice images and PDFs. The Host stages
one or more granted input artifacts. The Agent renders PDF pages, calls the
DeepSeek vision API, validates normalized invoice fields, and emits one XLSX
artifact.

Runtime requirements: Python 3.10+, `openpyxl`, `PyMuPDF`, and an explicitly
delegated `DEEPSEEK_API_KEY`. Optional environment settings are
`DEEPSEEK_VISION_BASE_URL` and `DEEPSEEK_VISION_MODEL`.

