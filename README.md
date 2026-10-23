# CT-200 traceable QA backend

`uvicorn app.main:app --reload` starts Swagger at `/docs`. Ingest both PDFs through `POST /documents/ingest` using multipart fields `document_name`, `version_label`, optional `document_id`, and `file`. Run `pytest -q`.

Run `python demo.py` for the verified direct v1→v2 ingestion/diff example. Suggested incremental commits: `docs: record PDF findings`, `feat: parse CT-200 hierarchy`, `feat: add versioned persistence and matching`, `feat: expose traceability API`, and `test: cover parser/version workflow`.

The project uses SQLite for immutable source/version/selection records and `generated_outputs.json` as the documented JSON alternative to MongoDB. The mock provider is deterministic and needs no key.
