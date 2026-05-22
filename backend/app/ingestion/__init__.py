"""Ingestion pipeline: Router → typed workers → IngestResult.

Public entrypoints:
  router.route(file_path)             → (IngestType, confidence)
  orchestrator.ingest_all(project_id) → list[IngestResult]
"""
