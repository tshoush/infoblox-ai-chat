import os
import re
from typing import List

from PyPDF2 import PdfReader
import yaml
from bs4 import BeautifulSoup

# RAG deps (langchain + FAISS) are optional and heavy — and FAISS has no wheel
# on some platforms (e.g. RHEL 7 / old glibc). Import them defensively so the
# backend still runs without them; RAG simply degrades to a no-op.
try:
    from langchain.text_splitter import RecursiveCharacterTextSplitter
    from langchain_community.embeddings import OpenAIEmbeddings
except Exception:  # noqa: BLE001
    RecursiveCharacterTextSplitter = None
    OpenAIEmbeddings = None
try:
    from langchain_community.vectorstores import FAISS
except Exception:  # noqa: BLE001
    FAISS = None

class RAGSystem:
    """Retrieval-Augmented Generation system for documentation context."""

    def __init__(self, docs_path: str = "rag_docs", embeddings_model: str = "text-embedding-ada-002",
                 index_path: str = "rag_index"):
        self.docs_path = docs_path
        self.index_path = index_path
        self.embeddings_model = embeddings_model
        self.vector_store = None
        self.embeddings = None
        # Text splitting only needs langchain (lightweight); keep it if available
        # so chunking/ingestion works even when the vector store (FAISS) does not.
        self.text_splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200, length_function=len,
        ) if RecursiveCharacterTextSplitter else None

        # Embeddings + FAISS are required to actually index/search. Any of:
        # missing deps, no OpenAI key, or no docs -> RAG degrades to a no-op
        # (retrieve_context returns []) instead of crashing the app at startup.
        try:
            if OpenAIEmbeddings is None or FAISS is None:
                raise ImportError("RAG vector deps (langchain/faiss) not installed")
            self.embeddings = OpenAIEmbeddings(model=self.embeddings_model)
            self.initialize_documents()
        except Exception as e:
            print(f"RAG disabled: {e}")
            self.embeddings = None

    def _load_persisted_index(self):
        """Loads a previously saved FAISS index to avoid re-embedding on boot."""
        if not os.path.isdir(self.index_path):
            return None
        try:
            # allow_dangerous_deserialization is required by newer langchain to
            # load a local pickle we created ourselves.
            try:
                store = FAISS.load_local(
                    self.index_path, self.embeddings, allow_dangerous_deserialization=True
                )
            except TypeError:  # older langchain has no such kwarg
                store = FAISS.load_local(self.index_path, self.embeddings)
            print(f"Loaded persisted RAG index from '{self.index_path}'.")
            return store
        except Exception as e:
            print(f"Could not load persisted RAG index ({e}); rebuilding.")
            return None

    # Minimum chunk length worth embedding (drops page numbers, lone headers, etc.).
    MIN_CHUNK_CHARS = 60

    @staticmethod
    def _clean_text(text: str) -> str:
        """Collapse runaway whitespace so chunks aren't padded with blank lines."""
        if not text:
            return ""
        # Normalize newlines, collapse 3+ blank lines, strip trailing spaces.
        text = re.sub(r"[ \t]+\n", "\n", text)
        text = re.sub(r"\n{3,}", "\n\n", text)
        return text.strip()

    def _iter_pdf_pages(self, file_path: str):
        """Yields (page_number, cleaned_text) for each non-empty PDF page.

        Splitting per page (rather than concatenating the whole document) keeps
        chunk boundaries aligned to the source and lets us record page numbers
        in metadata for citations.
        """
        with open(file_path, "rb") as f:
            reader = PdfReader(f)
            for page_num, page in enumerate(reader.pages, start=1):
                text = self._clean_text(page.extract_text() or "")
                if text:
                    yield page_num, text

    def _load_yaml_text(self, file_path: str) -> str:
        with open(file_path, "r") as f:
            data = yaml.safe_load(f)
        # Render as readable YAML (not a JSON dump) so chunks read as prose.
        return yaml.safe_dump(data, sort_keys=False, default_flow_style=False)

    def _load_html(self, file_path: str) -> str:
        with open(file_path, "r") as f:
            soup = BeautifulSoup(f, "html.parser")
        for tag in soup(["script", "style", "nav", "header", "footer"]):
            tag.decompose()
        # Prefer the main content region so we don't index repeated site
        # chrome (Sphinx sidebars/breadcrumbs appear on every page).
        main = (
            soup.find("div", attrs={"role": "main"})
            or soup.find("div", class_="body")
            or soup.find("div", class_="document")
            or soup.find("main")
            or soup
        )
        return self._clean_text(main.get_text(separator="\n"))

    def _documents_for_file(self, file_path: str):
        """Returns a list of chunked LangChain documents for one source file."""
        fname = os.path.basename(file_path)
        lower = fname.lower()
        chunks = []

        if lower.endswith(".pdf"):
            for page_num, page_text in self._iter_pdf_pages(file_path):
                for piece in self.text_splitter.split_text(page_text):
                    chunks.append(("pdf", {"source": fname, "page": page_num}, piece))
        elif lower.endswith((".yaml", ".yml")):
            text = self._load_yaml_text(file_path)
            for piece in self.text_splitter.split_text(text):
                chunks.append(("yaml", {"source": fname}, piece))
        elif lower.endswith((".html", ".htm")):
            text = self._load_html(file_path)
            for piece in self.text_splitter.split_text(text):
                chunks.append(("html", {"source": fname}, piece))
        else:
            return []

        # Build documents, filtering out trivially short / noise chunks.
        from langchain.schema import Document  # local import keeps top of file light
        docs = []
        for i, (_, meta, piece) in enumerate(chunks):
            piece = self._clean_text(piece)
            if len(piece) < self.MIN_CHUNK_CHARS:
                continue
            docs.append(Document(page_content=piece, metadata={**meta, "chunk_id": i}))
        return docs

    def initialize_documents(self, force_rebuild: bool = False, batch_size: int = 256) -> None:
        """Loads and indexes documentation from the docs_path.

        Reuses a persisted FAISS index when present (so we don't pay to
        re-embed every document on each startup); otherwise builds the index in
        batches (with progress) and saves it to ``index_path``.
        """
        if not force_rebuild:
            persisted = self._load_persisted_index()
            if persisted is not None:
                self.vector_store = persisted
                return

        documents = []
        for root, _, files in os.walk(self.docs_path):
            for file in sorted(files):
                file_path = os.path.join(root, file)
                try:
                    file_docs = self._documents_for_file(file_path)
                except Exception as e:
                    print(f"  Skipping '{file}' ({type(e).__name__}: {e}).")
                    continue
                if file_docs:
                    print(f"  {file}: {len(file_docs)} chunks")
                    documents.extend(file_docs)

        if not documents:
            print("No documents found to index.")
            return

        print(f"Embedding {len(documents)} chunks in batches of {batch_size}...")
        store = None
        for start in range(0, len(documents), batch_size):
            batch = documents[start:start + batch_size]
            if store is None:
                store = FAISS.from_documents(batch, self.embeddings)
            else:
                store.add_documents(batch)
            print(f"  embedded {min(start + batch_size, len(documents))}/{len(documents)}")

        self.vector_store = store
        try:
            self.vector_store.save_local(self.index_path)
            print(f"Indexed {len(documents)} chunks and saved index to '{self.index_path}'.")
        except Exception as e:
            print(f"Indexed {len(documents)} chunks (index not persisted: {e}).")

    def retrieve_context(self, query: str, k: int = 3) -> List[str]:
        """Finds relevant documentation snippets, each prefixed with its source."""
        if not self.vector_store:
            return []
        docs = self.vector_store.similarity_search(query, k=k)
        snippets = []
        for doc in docs:
            meta = doc.metadata or {}
            src = meta.get("source")
            page = meta.get("page")
            label = f"{src} p.{page}" if src and page else (src or "")
            snippets.append(f"[{label}]\n{doc.page_content}" if label else doc.page_content)
        return snippets

    def update_embeddings(self) -> None:
        """Re-indexes documents from disk, replacing any persisted index."""
        if not self.embeddings:
            print("Cannot update embeddings: RAG is disabled (no embeddings backend).")
            return
        self.initialize_documents(force_rebuild=True)