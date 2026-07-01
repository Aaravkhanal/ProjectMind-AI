from abc import ABC, abstractmethod
from typing import Optional, List
from uuid import uuid4

import chromadb
from langchain_chroma import Chroma
from langchain_core.documents import Document
try:
    from langchain_huggingface import HuggingFaceEmbeddings
except ImportError:
    HuggingFaceEmbeddings = None  # type: ignore[assignment,misc]


class IVectorStore(ABC):
    @abstractmethod
    def load(
        self,
        path: str,
        collection_name: str,
        embedding: HuggingFaceEmbeddings,
        documents: Optional[List[Document]] = None,
    ) -> "IVectorStore":
        raise NotImplementedError

    @abstractmethod
    def add_documents(self, documents: List[Document]) -> None:
        raise NotImplementedError

    @abstractmethod
    def search(self, query: str, k: int) -> List[Document]:
        raise NotImplementedError

    @abstractmethod
    def as_retriever(self, query: str, embedding: HuggingFaceEmbeddings, k: int):
        raise NotImplementedError


class VectorStore(IVectorStore):
    def __init__(self, store: Optional[Chroma] = None):
        self._store = store

    def load(
        self,
        path: str,
        collection_name: str,
        embedding: HuggingFaceEmbeddings,
        documents: Optional[List[Document]] = None,
    ) -> "VectorStore":
        if documents:
            store = Chroma.from_documents(
                documents=documents,
                embedding=embedding,
                persist_directory=path,
                collection_name=collection_name,
            )
        else:
            store = Chroma(
                persist_directory=path,
                embedding_function=embedding,
                collection_name=collection_name,
            )
        return VectorStore(store)

    def add_documents(self, documents: List[Document]) -> None:
        if not self._store:
            raise RuntimeError("VectorStore not loaded. Call load() first.")
        uuids = [str(uuid4()) for _ in documents]
        self._store.add_documents(documents=documents, ids=uuids)

    def search(self, query: str, k: int = 4) -> List[Document]:
        if not self._store:
            raise RuntimeError("VectorStore not loaded. Call load() first.")
        results = self._store.similarity_search(query, k=k)
        chromadb.api.client.SharedSystemClient.clear_system_cache()
        return results

    def as_retriever(
        self, query: str, embedding: HuggingFaceEmbeddings, k: int = 4
    ):
        if not self._store:
            raise RuntimeError("VectorStore not loaded. Call load() first.")
        similar = self._store.similarity_search(query, k=k)
        chromadb.api.client.SharedSystemClient.clear_system_cache()
        temp = self._store.from_documents(documents=similar, embedding=embedding)
        return temp.as_retriever()
