# Day 8 RAG Evaluation

Evaluation datasets are JSON arrays or JSONL records. Each versioned case has `case_id`, `version`, `query`, optional `expected_pain_points`, `relevant_review_ids`, `answer_requirements`, and `expected_no_answer`. Case IDs and list values must be unique.

The deterministic runner computes Recall@K, Precision@K, MRR, nDCG@K, citation precision/recall, and no-answer accuracy. Citation reports also identify missing expected IDs and unsupported cited IDs. No-answer evaluation distinguishes false answers from false refusals.

Configure `EVALUATION_DATASET_PATH`, `EVALUATION_RETRIEVAL_K`, recall/precision/citation thresholds, and deterministic evaluator mode. The runner emits per-case results and averages. Threshold checks are a concise regression signal, not a claim of production answer quality.

Run programmatically with an application-configured RAG pipeline, or use the CLI entry point with an injected application pipeline:

```bash
python -m src.rag.evaluation_cli --dataset tests/fixtures/sample_rag_evaluation.jsonl --k 5
```

The command prints JSON containing averages, thresholds, and pass/fail, followed by a human-readable summary. `--json-only` suppresses that summary.

Limits: current relevance is binary ID matching; Pain Point and free-form answer requirements are schema fields but not semantic LLM judging; fake providers only validate deterministic orchestration. Dashboard work is outside Day 8 scope.

```bash
ruff check .
pytest
```
