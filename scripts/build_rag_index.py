"""Build (or dry-run estimate) the RAG FAISS index from rag_docs/.

This runs the (expensive) embedding step OUTSIDE the request path so the Flask
app only ever *loads* the persisted index at boot.

    python scripts/build_rag_index.py --dry-run   # count chunks + estimate cost, no embedding
    python scripts/build_rag_index.py             # build + persist rag_index/
"""
import sys
import os

sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), "..")))

from dotenv import load_dotenv

load_dotenv()

from backend.rag_system import RAGSystem  # noqa: E402

# text-embedding-ada-002 pricing (USD per 1K tokens) and a rough chars->tokens ratio.
PRICE_PER_1K_TOKENS = 0.0001
CHARS_PER_TOKEN = 4.0


def dry_run(rag: RAGSystem) -> None:
    total_chunks = 0
    total_chars = 0
    per_source = {}
    for root, _, files in os.walk(rag.docs_path):
        for fname in sorted(files):
            path = os.path.join(root, fname)
            try:
                docs = rag._documents_for_file(path)
            except Exception as e:  # noqa: BLE001
                print(f"  {fname}: ERROR {e}")
                continue
            if not docs:
                continue
            chars = sum(len(d.page_content) for d in docs)
            per_source[fname] = (len(docs), chars)
            total_chunks += len(docs)
            total_chars += chars

    print("\nPer-source chunk counts:")
    for fname, (n, chars) in per_source.items():
        print(f"  {fname:55s} {n:6d} chunks  {chars/1e6:5.2f}M chars")

    est_tokens = total_chars / CHARS_PER_TOKEN
    est_cost = (est_tokens / 1000) * PRICE_PER_1K_TOKENS
    print(f"\nTOTAL: {total_chunks} chunks, {total_chars/1e6:.2f}M chars")
    print(f"Estimated embedding tokens: ~{est_tokens/1e6:.2f}M")
    print(f"Estimated one-time cost (ada-002 @ ${PRICE_PER_1K_TOKENS}/1K tok): ~${est_cost:.2f}")


def main(argv) -> int:
    rag = RAGSystem(docs_path="rag_docs", index_path="rag_index")

    if "--dry-run" in argv:
        if rag.embeddings is None:
            print("(RAG embeddings unavailable — dry-run still counts chunks.)")
        dry_run(rag)
        return 0

    if rag.embeddings is None:
        print("Cannot build index: no embeddings backend (set OPENAI_API_KEY).")
        return 1

    rag.update_embeddings()  # force_rebuild + persist
    print("Done.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
