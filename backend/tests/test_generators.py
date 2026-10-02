from src.rag.generators import FakeTextGenerator, TextGenerator


def use_generator(generator: TextGenerator, prompt: str) -> str:
    return generator.generate(prompt)


def test_fake_generator_is_deterministic_and_records_prompts() -> None:
    generator = FakeTextGenerator(model="test-model")
    first = use_generator(generator, "grounded prompt")
    second = use_generator(generator, "grounded prompt")
    assert first == second
    assert generator.model == "test-model"
    assert generator.prompts == ["grounded prompt", "grounded prompt"]


def test_fake_generator_can_return_fixed_response() -> None:
    generator = FakeTextGenerator(response="근거 기반 답변")
    assert generator.generate("any prompt") == "근거 기반 답변"
