-- 기존 VOC는 전역 데이터입니다. 명시적 조직/매장 연결이 없으면 조사에서 제외합니다.
CREATE TABLE IF NOT EXISTS serviq_history_sources (
    tenant_id TEXT NOT NULL,
    store TEXT NOT NULL,
    review_id TEXT NOT NULL,
    PRIMARY KEY(tenant_id,store,review_id)
);
CREATE INDEX IF NOT EXISTS serviq_history_sources_review ON serviq_history_sources(review_id,tenant_id,store);
