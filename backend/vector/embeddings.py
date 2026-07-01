from enum import Enum
from typing import Optional

try:
    from langchain_huggingface import HuggingFaceEmbeddings as _HFEmbeddings
    _HF_AVAILABLE = True
except ImportError:
    _HFEmbeddings = None  # type: ignore[assignment]
    _HF_AVAILABLE = False


class EmbeddingModel(Enum):
    HUGGINGFACE = "sentence-transformers/all-mpnet-base-v2"
    MINILM = "sentence-transformers/all-MiniLM-L6-v2"


class Embeddings:
    def __init__(self, model: EmbeddingModel = EmbeddingModel.HUGGINGFACE):
        if not _HF_AVAILABLE:
            raise ImportError(
                "langchain-huggingface is not installed. "
                "Install it with: pip install projectmind[huggingface]"
            )
        self.embedding = _HFEmbeddings(model_name=model.value)

    @classmethod
    def default(cls) -> "Embeddings":
        return cls(EmbeddingModel.HUGGINGFACE)

    @classmethod
    def fast(cls) -> "Embeddings":
        return cls(EmbeddingModel.MINILM)
