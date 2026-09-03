# Day 5 Vector Search

## PostgreSQL and pgvector setup

Install PostgreSQL with the pgvector extension available on the server. The Python
environment uses `psycopg` for connections and `pgvector` as the vector dependency.
Set the connection and embedding settings in `.env`:

```dotenv
POSTGRESQL_URL=postgresql://user:password@localhost:5432/fnb_voc
EMBEDDING_PROVIDER=fake
EMBEDDING_MODEL=fake-v1
EMBEDDING_DIMENSION=384
EMBEDDING_BATCH_SIZE=100
```

Schema initialization runs `CREATE EXTENSION IF NOT EXISTS vector` before table
creation, so repeated initialization is safe. The database user must have permission
to enable the extension. If extension creation is managed by an administrator, enable
`vector` once before running the CLI.

## Embedding and storage flow

`EmbeddingProvider` defines single-text and batch embedding operations. The bundled
`FakeEmbeddingProvider` produces deterministic normalized vectors for development and
tests without an external API call.

Validated `Review` records are read in stable `review_id` order. Indexing hashes the
exact review text with SHA-256, checks the stored model/hash/dimension, embeds only
changed content in configured batches, and upserts one vector per review and model.
The command reports `indexed`, `skipped`, and `failed` counts. Re-running it with
unchanged reviews is idempotent.

`review_embeddings` stores the review foreign key, model, dimension, vector, content
hash, and creation/update timestamps. Database constraints keep dimensions within the
supported range and ensure the recorded dimension matches the vector.

## CLI usage

Install the project and development dependencies, set `POSTGRESQL_URL`, then index
reviews already stored in PostgreSQL:

```bash
python -m pip install -e ".[dev]"
python -m src.rag.vector_cli index
python -m src.rag.vector_cli index --batch-size 50
```

Run cosine-similarity search with a deterministic top-k order:

```bash
python -m src.rag.vector_cli search "너무 달지 않은 음료" --top-k 5
```

Filters can be combined. `--product` accepts a product ID, `--category` a product
category, `--rating` an exact 1–5 rating, and `--pain-point` a taxonomy category ID:

```bash
python -m src.rag.vector_cli search "가격이 아쉬운 간식" \
  --top-k 10 \
  --product P001 \
  --category snack \
  --rating 2 \
  --pain-point price
```

The CLI emits one JSON object per search result with `review_id`, cosine `score`,
cosine `distance`, and `review_text`. All query values and filters are passed as bound
parameters.

## Limitations

- Only the deterministic `fake` provider is bundled. A production provider must
  implement `EmbeddingProvider` and be wired into the provider factory.
- Embedding dimensions are limited to 1–2000 for pgvector index compatibility.
- Search performs exact cosine ranking; approximate HNSW/IVFFlat indexes are not yet
  configured.
- Changing the embedding model or dimension requires re-indexing reviews for that
  model.
- Hybrid keyword/vector ranking, reranking, and external embedding APIs are outside
  Day 5 scope.

## Validation

```bash
ruff check .
pytest
```
