from src.rag.generators import FakeTextGenerator
from src.rag.pipeline import RagPipeline
from src.rag.search_models import SearchQuery, SearchResult


class FakeSearchService:
    def search(self, request: SearchQuery) -> list[SearchResult]:
        return [
            SearchResult(
                review_id="R1",
                text="가격이 비싸요",
                rank=1,
                mode="hybrid",
                fused_score=0.03,
                lexical_rank=2,
                vector_rank=1,
                match_source="both",
                metadata={"product_id": "P1", "category": "beverage"},
            )
        ]


def test_rag_pipeline_runs_deterministically_with_fakes() -> None:
    generator = FakeTextGenerator(response="가격 불만이 확인됩니다. [R1]")
    pipeline = RagPipeline(
        FakeSearchService(),
        generator,
        context_max_items=5,
        context_max_chars=1000,
    )
    answer = pipeline.run(SearchQuery(text="가격 불만은?", mode="hybrid"))
    assert answer.answer == "가격 불만이 확인됩니다. [R1]"
    assert answer.status == "success"
    assert answer.sources[0].review_id == "R1"
    assert answer.sources[0].match_source == "both"
    assert answer.retrieval.retrieved_count == 1
    assert answer.retrieval.context_count == 1
    assert answer.generator_model == "fake-v1"
    assert "review_id=R1" in generator.prompts[0]
