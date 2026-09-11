# Day 6 Hybrid Search

## Retrieval modes

The search service exposes one validated `SearchQuery` contract with three modes:

- `lexical` uses PostgreSQL full-text search over review text.
- `vector` embeds the query and uses pgvector cosine distance.
- `hybrid` retrieves candidates from both paths and combines their ranks with
  Reciprocal Rank Fusion (RRF).

Every result uses the shared `SearchResult` contract with a review ID, review text,
final rank, retrieval mode, explicit score fields, and metadata. Vector cosine score,
lexical rank score, and fused RRF score remain separate because they have different
meanings.

## Lexical retrieval

Lexical search builds a query with `plainto_tsquery('simple', ...)` and matches it
against `to_tsvector('simple', review_text)`. PostgreSQL `ts_rank_cd` orders matching
reviews, followed by `review_id` as a stable tie-breaker. Query text, filters, and
limits are bound parameters.

The `simple` configuration is language-neutral and does not provide Korean stemming,
synonym expansion, or typo tolerance. It is intended as a deterministic keyword
baseline.

## Filters

All three modes share the same optional filter contract:

- `product_id`: exact review product ID
- `category`: exact product category
- `rating`: exact integer rating from 1 through 5
- `pain_point`: exact taxonomy category ID assigned to the review

Filters are composable. Hybrid mode passes the same filter instance to both candidate
retrievers, so RRF only combines results from the same constrained review set.

## Reciprocal Rank Fusion

For each review, RRF adds a contribution from every retrieval path in which it
appears:

```text
fused_score(review) = sum(1 / (fusion_constant + source_rank))
```

The default fusion constant is `60` and can be changed when calling
`reciprocal_rank_fusion` or constructing the search service. Duplicate review IDs in
one source count only once at their best rank. Final ties are resolved by best source
rank and then `review_id`, making the output reproducible.

Hybrid results expose:

- `lexical_rank` and `vector_rank` when present
- the raw `lexical_score` and cosine `vector_score`
- `fused_score`, which is the RRF value rather than a normalized similarity
- `match_source`: `lexical`, `vector`, or `both`

## Hybrid flow and fallback

The hybrid service retrieves `candidate_k` results from each available path, fuses
them, and returns `top_k` results. `candidate_k` must be at least `top_k`.

Fallback behavior is explicit:

- An empty or whitespace-only query returns an empty list without database or
  embedding calls.
- Lexical mode never requires an embedding provider.
- Hybrid mode with no embedding provider runs lexical-only retrieval and still emits
  hybrid results with lexical provenance.
- An explicit `EmbeddingUnavailableError` falls back to lexical candidates.
- Unexpected provider errors and database/search errors propagate to the caller; they
  are not silently converted into empty results.
- Vector mode requires an embedding provider and reports its absence as an error.

## CLI usage

Set `POSTGRESQL_URL` and the embedding settings described in
[Vector Search](vector_search.md). Index stored reviews before vector or hybrid
retrieval:

```bash
python -m src.rag.vector_cli index --batch-size 50
```

Choose a retrieval mode with `--mode`:

```bash
python -m src.rag.vector_cli search "가격이 비싸요" --mode lexical --top-k 5
python -m src.rag.vector_cli search "가성비 좋은 음료" --mode vector --top-k 5
python -m src.rag.vector_cli search "너무 단 음료" \
  --mode hybrid --top-k 5 --candidate-k 20
```

The default mode is `hybrid`. Filters work identically in every mode:

```bash
python -m src.rag.vector_cli search "가격" \
  --mode hybrid \
  --product P001 \
  --category beverage \
  --rating 2 \
  --pain-point price
```

By default, each JSON line contains only `review_id`, `text`, `rank`, and `mode`. Add
`--details` to include source scores, source ranks, fused score, match source, and
other metadata:

```bash
python -m src.rag.vector_cli search "맛있는 간식" --mode hybrid --details
```

## Limitations

- The bundled fake embedding provider remains for deterministic local workflows and
  tests; production embeddings require a provider implementation.
- Lexical search uses exact full-text token matching without language-specific
  morphology.
- RRF combines rank positions and does not calibrate source scores.
- Approximate vector indexes, reranking, answer generation, and RAG are outside Day 6
  scope.

## Validation

```bash
ruff check .
pytest
```
