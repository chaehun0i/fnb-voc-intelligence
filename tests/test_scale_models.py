import pytest

from src.rag.scale_models import ScaleJobConfig


def test_scale_config_validates() -> None:
    assert ScaleJobConfig(batch_size=2, workers=2).workers == 2
    with pytest.raises(ValueError):
        ScaleJobConfig(batch_size=0)
