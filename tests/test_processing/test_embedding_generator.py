"""Tests for EmbeddingGenerator."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from mysterial.processing.embedding_generator import EmbeddingGenerator


class TestEmbeddingGenerator:
    def test_build_symbol_text_all_fields(self) -> None:
        gen = EmbeddingGenerator()
        text = gen.build_symbol_text("greet", "Return a greeting.", "def greet(name: str):")
        assert "greet" in text
        assert "Return a greeting." in text
        assert "def greet(name: str):" in text

    def test_build_symbol_text_no_docstring(self) -> None:
        gen = EmbeddingGenerator()
        text = gen.build_symbol_text("foo", None, "def foo():")
        assert "foo" in text
        assert "def foo():" in text

    def test_build_symbol_text_minimal(self) -> None:
        gen = EmbeddingGenerator()
        text = gen.build_symbol_text("bar", None, None)
        assert text == "bar"

    def test_embed_delegates_to_model(self) -> None:
        gen = EmbeddingGenerator()
        fake_model = MagicMock()
        import numpy as np

        fake_model.encode.return_value = [np.array([0.1, 0.2, 0.3])]
        gen._model = fake_model

        result = gen.embed("hello world")
        assert result == pytest.approx([0.1, 0.2, 0.3])
        fake_model.encode.assert_called_once()

    def test_embed_batch_returns_list_of_lists(self) -> None:
        gen = EmbeddingGenerator()
        fake_model = MagicMock()
        import numpy as np

        fake_model.encode.return_value = [np.array([0.1] * 4), np.array([0.2] * 4)]
        gen._model = fake_model

        results = gen.embed_batch(["text1", "text2"])
        assert len(results) == 2
        assert all(isinstance(r, list) for r in results)

    def test_embed_raises_when_sentence_transformers_missing(self) -> None:
        gen = EmbeddingGenerator()
        # No model set, and we mock the import to fail
        with patch.dict("sys.modules", {"sentence_transformers": None}):
            with pytest.raises(RuntimeError, match="sentence-transformers"):
                gen.embed("test")

    def test_dimension_property(self) -> None:
        gen = EmbeddingGenerator()
        # Should return the value from settings (384 by default)
        assert gen.dimension == 384
