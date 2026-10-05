"""기존 hybrid 검색에 조직/매장 출처 허용 목록을 적용합니다."""
import re

import psycopg

from src.rag.search_models import SearchFilters, SearchQuery
from src.rag.search_service import SearchService


class PostgresHistorySearch:
    def __init__(self, dsn, embedding_provider=None):
        self.dsn, self.embedding_provider = dsn, embedding_provider

    def search(self, tenant_id, store, query):
        with psycopg.connect(self.dsn) as connection:
            connection.execute("SET LOCAL statement_timeout='10s'")
            if not connection.execute("SELECT 1 FROM serviq_history_sources WHERE tenant_id=%s AND store=%s LIMIT 1", (tenant_id, store)).fetchone():
                return []
            results = SearchService(connection.cursor(), self.embedding_provider).search(
                SearchQuery(text=query, mode="hybrid", top_k=5, candidate_k=20,
                            filters=SearchFilters(tenant_id=tenant_id, store=store)))
        # 원문은 일시적인 검색 결과에만 존재합니다. Node에는 안전한 출처 ID/순위만 넘깁니다.
        return [("review:"+r.review_id, r.rank) for r in results
                if re.fullmatch(r"[A-Za-z0-9_.:-]{1,128}", r.review_id)]
