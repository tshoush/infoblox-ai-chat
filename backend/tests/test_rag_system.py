"""Hermetic tests for RAGSystem (no OpenAI key, no FAISS build required).

Covers graceful degradation when embeddings are unavailable and the
persisted-index lookup added on 2026-06-20.
"""
from backend import rag_system as rag_mod
from backend.rag_system import RAGSystem


def test_rag_degrades_when_embeddings_unavailable(monkeypatch, tmp_path):
    """No key / bad backend -> RAG disables itself instead of crashing import."""
    def boom(*a, **k):
        raise RuntimeError("no OpenAI key")

    monkeypatch.setattr(rag_mod, "OpenAIEmbeddings", boom)
    rag = RAGSystem(docs_path=str(tmp_path), index_path=str(tmp_path / "idx"))

    assert rag.embeddings is None
    assert rag.vector_store is None
    assert rag.retrieve_context("anything") == []  # never raises


def test_load_persisted_index_returns_none_when_absent(monkeypatch, tmp_path):
    monkeypatch.setattr(rag_mod, "OpenAIEmbeddings", lambda *a, **k: object())
    # Point at a non-existent index dir; walk over empty docs builds nothing.
    rag = RAGSystem(docs_path=str(tmp_path / "docs"), index_path=str(tmp_path / "missing"))
    assert rag._load_persisted_index() is None


def test_update_embeddings_noop_when_disabled(monkeypatch, tmp_path):
    def boom(*a, **k):
        raise RuntimeError("no key")

    monkeypatch.setattr(rag_mod, "OpenAIEmbeddings", boom)
    rag = RAGSystem(docs_path=str(tmp_path), index_path=str(tmp_path / "idx"))
    # Should not raise even though there is no embeddings backend.
    rag.update_embeddings()
    assert rag.vector_store is None


def _disabled_rag(monkeypatch, tmp_path):
    """A RAGSystem with no embeddings backend (so __init__ does no indexing)."""
    monkeypatch.setattr(rag_mod, "OpenAIEmbeddings", lambda *a, **k: (_ for _ in ()).throw(RuntimeError("no key")))
    return RAGSystem(docs_path=str(tmp_path / "docs"), index_path=str(tmp_path / "idx"))


def test_clean_text_collapses_whitespace(monkeypatch, tmp_path):
    rag = _disabled_rag(monkeypatch, tmp_path)
    # Trailing spaces/tabs before newlines are stripped and 3+ blank lines
    # collapse to one; leading indentation is preserved (matters for YAML).
    messy = "line one   \n\n\n\n   line two\t\t\n"
    assert rag._clean_text(messy) == "line one\n\n   line two"
    assert rag._clean_text("") == ""


def test_documents_for_yaml_are_readable_and_have_source(monkeypatch, tmp_path):
    rag = _disabled_rag(monkeypatch, tmp_path)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    y = docs_dir / "ref.yaml"
    y.write_text("title: Infoblox WAPI Reference\noverview: " + ("Networks are subnets. " * 20) + "\n")

    docs = rag._documents_for_file(str(y))
    assert docs, "expected at least one chunk"
    assert all(d.metadata.get("source") == "ref.yaml" for d in docs)
    # Readable YAML, not a JSON dump.
    assert "{" not in docs[0].page_content[:5]


def test_documents_filter_trivial_chunks(monkeypatch, tmp_path):
    rag = _disabled_rag(monkeypatch, tmp_path)
    docs_dir = tmp_path / "docs"
    docs_dir.mkdir(parents=True, exist_ok=True)
    tiny = docs_dir / "tiny.html"
    tiny.write_text("<html><body><p>42</p></body></html>")  # below MIN_CHUNK_CHARS
    assert rag._documents_for_file(str(tiny)) == []


def test_retrieve_context_prefixes_source_and_page(monkeypatch, tmp_path):
    from langchain.schema import Document

    rag = _disabled_rag(monkeypatch, tmp_path)

    class FakeStore:
        def similarity_search(self, query, k=3):
            return [Document(page_content="A records map names to IPv4.",
                             metadata={"source": "WAPI.pdf", "page": 1207})]

    rag.vector_store = FakeStore()
    out = rag.retrieve_context("a record", k=1)
    assert out == ["[WAPI.pdf p.1207]\nA records map names to IPv4."]
