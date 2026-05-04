from __future__ import annotations

import src.llm as llm


def test_llm_package_does_not_eager_export_local_sentence_transformers_provider() -> None:
    assert not hasattr(llm, "LocalSentenceTransformersEmbeddingProvider")
