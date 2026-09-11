# Day 7 RAG

## Architecture

The RAG pipeline follows one explicit flow:

```text
SearchQuery -> SearchService -> ranked results -> structured context
            -> context budget -> grounded prompt -> TextGenerator -> RagAnswer
```

Retrieval remains selectable as `lexical`, `vector`, or `hybrid`. `TextGenerator` is
provider-neutral; the bundled `FakeTextGenerator` is deterministic and makes no
external calls.

## Configuration

```dotenv
RAG_RETRIEVAL_MODE=hybrid
RAG_TOP_K=5
RAG_CONTEXT_MAX_ITEMS=5
RAG_CONTEXT_MAX_CHARS=6000
GENERATOR_PROVIDER=fake
GENERATOR_MODEL=fake-v1
RAG_MINIMUM_EVIDENCE=1
```

Modes and numeric bounds are validated at startup. Context and evidence limits must
be positive.

## Context contract and limits

Ranked search results become structured context items containing review ID, text,
product ID, category, Pain Points, lexical/vector ranks, match source, and retrieval
metadata. Items are ordered by retrieval rank with review ID as a deterministic
tie-breaker.

The context budget applies both a maximum item count and a total review-text character
count. Evidence is never truncated: an item that would exceed the remaining character
budget is excluded, while later items that fit may still be included. Included items
retain their original retrieval order.

## Grounded prompt contract

Prompt version `fnb-voc-rag-v1` contains the user query and structured evidence. It
requires Korean answers based only on supplied reviews, review-ID citations for major
claims, no unsupported completion from general knowledge, and the exact fallback:

```text
근거가 충분하지 않습니다.
```

Prompt construction is deterministic. Changing the contract requires a new prompt
version.

## Sources and evidence guard

Generated text is separate from `RagSource` records. Each source exposes its review ID,
final rank, lexical/vector ranks, match source, and retrieval metadata. The response
also records retrieval mode, requested top-k, retrieved count, context count, generator
model, and prompt version.

Generation is skipped when:

- retrieval returns no results (`no_results`), or
- context remaining after budget limits is below `RAG_MINIMUM_EVIDENCE`
  (`insufficient_evidence`).

Both states return the explicit insufficient-evidence text. Insufficient responses may
still expose the weak sources for diagnosis; no-result responses have no sources.

## CLI

Set `POSTGRESQL_URL`, index reviews, then run:

```bash
python -m src.rag.rag_cli "가격 불만의 주요 원인은?"
python -m src.rag.rag_cli "단맛 관련 의견은?" --mode lexical --top-k 5
python -m src.rag.rag_cli "가성비 좋은 제품은?" \
  --mode hybrid --top-k 5 --candidate-k 20 \
  --category beverage --rating 4 --pain-point price
```

The JSON response always contains `answer`, `status`, and source review IDs. Add
`--details` for source ranks/metadata, retrieval counts, generator model, and prompt
version:

```bash
python -m src.rag.rag_cli "맛 개선 기회는?" --details
```

Product, category, rating, and Pain Point filters use the same semantics as Day 6
search. Lexical mode does not initialize an embedding provider.

## Limitations

- Only deterministic fake embedding and generation providers are bundled.
- The fake generator demonstrates orchestration, not natural-language answer quality.
- Evidence citations are instructed by the prompt but are not post-validated against
  generated sentences.
- Context budgeting counts review-text characters, not tokenizer-specific tokens.
- RAG evaluation, production LLM integrations, reranking, and citation verification
  are outside Day 7 scope.

## Validation

```bash
ruff check .
pytest
```
