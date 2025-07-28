"""
RAG (Retrieval-Augmented Generation) system for documentation processing.
Handles PDF, YAML, and HTML document parsing and context retrieval.
"""

import os
import json
import logging
import hashlib
from typing import Dict, List, Any, Optional, Tuple
from pathlib import Path
from dataclasses import dataclass
import re

try:
    import PyPDF2
    PDF_AVAILABLE = True
except ImportError:
    PDF_AVAILABLE = False

try:
    import yaml
    YAML_AVAILABLE = True
except ImportError:
    YAML_AVAILABLE = False

try:
    from bs4 import BeautifulSoup
    HTML_AVAILABLE = True
except ImportError:
    HTML_AVAILABLE = False

try:
    import numpy as np
    from sklearn.feature_extraction.text import TfidfVectorizer
    from sklearn.metrics.pairwise import cosine_similarity
    SKLEARN_AVAILABLE = True
except ImportError:
    SKLEARN_AVAILABLE = False

from cache import cache_manager

logger = logging.getLogger(__name__)


@dataclass
class DocumentChunk:
    """Represents a chunk of document content."""
    id: str
    content: str
    source: str
    metadata: Dict[str, Any]
    embedding: Optional[List[float]] = None


@dataclass
class RetrievalResult:
    """Represents a retrieval result with relevance score."""
    chunk: DocumentChunk
    score: float
    rank: int


class DocumentProcessor:
    """Processes different document types into searchable chunks."""
    
    def __init__(self, chunk_size: int = 1000, chunk_overlap: int = 200):
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
    
    def process_pdf(self, file_path: str) -> List[DocumentChunk]:
        """Process PDF document into chunks."""
        if not PDF_AVAILABLE:
            logger.warning("PyPDF2 not available, skipping PDF processing")
            return []
        
        chunks = []
        try:
            with open(file_path, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                text_content = ""
                
                for page_num, page in enumerate(pdf_reader.pages):
                    try:
                        page_text = page.extract_text()
                        text_content += f"\n--- Page {page_num + 1} ---\n{page_text}"
                    except Exception as e:
                        logger.warning(f"Failed to extract text from page {page_num + 1}: {e}")
                
                # Split into chunks
                chunks = self._split_text_into_chunks(
                    text_content,
                    source=file_path,
                    doc_type="pdf"
                )
                
                logger.info(f"Processed PDF {file_path} into {len(chunks)} chunks")
                
        except Exception as e:
            logger.error(f"Failed to process PDF {file_path}: {e}")
        
        return chunks
    
    def process_yaml(self, file_path: str) -> List[DocumentChunk]:
        """Process YAML document into chunks."""
        if not YAML_AVAILABLE:
            logger.warning("PyYAML not available, skipping YAML processing")
            return []
        
        chunks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                yaml_content = yaml.safe_load(file)
                
                # Convert YAML to searchable text
                text_content = self._yaml_to_text(yaml_content)
                
                # Split into chunks
                chunks = self._split_text_into_chunks(
                    text_content,
                    source=file_path,
                    doc_type="yaml"
                )
                
                logger.info(f"Processed YAML {file_path} into {len(chunks)} chunks")
                
        except Exception as e:
            logger.error(f"Failed to process YAML {file_path}: {e}")
        
        return chunks
    
    def process_html(self, file_path: str) -> List[DocumentChunk]:
        """Process HTML document into chunks."""
        if not HTML_AVAILABLE:
            logger.warning("BeautifulSoup not available, skipping HTML processing")
            return []
        
        chunks = []
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                html_content = file.read()
                
                soup = BeautifulSoup(html_content, 'html.parser')
                
                # Remove script and style elements
                for script in soup(["script", "style"]):
                    script.decompose()
                
                # Extract text content
                text_content = soup.get_text()
                
                # Clean up whitespace
                text_content = re.sub(r'\s+', ' ', text_content).strip()
                
                # Split into chunks
                chunks = self._split_text_into_chunks(
                    text_content,
                    source=file_path,
                    doc_type="html"
                )
                
                logger.info(f"Processed HTML {file_path} into {len(chunks)} chunks")
                
        except Exception as e:
            logger.error(f"Failed to process HTML {file_path}: {e}")
        
        return chunks
    
    def _yaml_to_text(self, yaml_obj: Any, prefix: str = "") -> str:
        """Convert YAML object to searchable text."""
        if isinstance(yaml_obj, dict):
            text_parts = []
            for key, value in yaml_obj.items():
                current_prefix = f"{prefix}.{key}" if prefix else key
                text_parts.append(f"{current_prefix}: {self._yaml_to_text(value, current_prefix)}")
            return "\n".join(text_parts)
        
        elif isinstance(yaml_obj, list):
            text_parts = []
            for i, item in enumerate(yaml_obj):
                current_prefix = f"{prefix}[{i}]" if prefix else f"[{i}]"
                text_parts.append(self._yaml_to_text(item, current_prefix))
            return "\n".join(text_parts)
        
        else:
            return str(yaml_obj)
    
    def _split_text_into_chunks(self, text: str, source: str, doc_type: str) -> List[DocumentChunk]:
        """Split text into overlapping chunks."""
        chunks = []
        text_length = len(text)
        
        start = 0
        chunk_id = 0
        
        while start < text_length:
            end = min(start + self.chunk_size, text_length)
            
            # Try to break at sentence boundaries
            if end < text_length:
                # Look for sentence endings within the overlap region
                sentence_end = text.rfind('.', start, end)
                if sentence_end > start + self.chunk_size // 2:
                    end = sentence_end + 1
            
            chunk_text = text[start:end].strip()
            
            if chunk_text:
                chunk = DocumentChunk(
                    id=f"{hashlib.md5(f'{source}_{chunk_id}'.encode()).hexdigest()}",
                    content=chunk_text,
                    source=source,
                    metadata={
                        'doc_type': doc_type,
                        'chunk_index': chunk_id,
                        'start_pos': start,
                        'end_pos': end,
                        'length': len(chunk_text)
                    }
                )
                chunks.append(chunk)
                chunk_id += 1
            
            # Move start position with overlap
            start = max(start + self.chunk_size - self.chunk_overlap, end)
        
        return chunks


class EmbeddingSystem:
    """Handles document embeddings for similarity search."""
    
    def __init__(self):
        self.vectorizer = None
        self.document_vectors = None
        self.chunks: List[DocumentChunk] = []
        
        if SKLEARN_AVAILABLE:
            self.vectorizer = TfidfVectorizer(
                max_features=5000,
                stop_words='english',
                ngram_range=(1, 2),
                min_df=1,
                max_df=0.95
            )
        else:
            logger.warning("scikit-learn not available, using basic text matching")
    
    def build_embeddings(self, chunks: List[DocumentChunk]) -> None:
        """Build embeddings for document chunks."""
        self.chunks = chunks
        
        if not chunks:
            logger.warning("No chunks provided for embedding")
            return
        
        if SKLEARN_AVAILABLE and self.vectorizer:
            try:
                # Extract text content
                texts = [chunk.content for chunk in chunks]
                
                # Build TF-IDF vectors
                self.document_vectors = self.vectorizer.fit_transform(texts)
                
                logger.info(f"Built embeddings for {len(chunks)} chunks")
                
            except Exception as e:
                logger.error(f"Failed to build embeddings: {e}")
                self.document_vectors = None
        else:
            logger.info("Using basic text matching (no embeddings)")
    
    def search_similar(self, query: str, top_k: int = 5) -> List[RetrievalResult]:
        """Search for similar chunks to the query."""
        if not self.chunks:
            return []
        
        if SKLEARN_AVAILABLE and self.vectorizer and self.document_vectors is not None:
            return self._search_with_embeddings(query, top_k)
        else:
            return self._search_with_keywords(query, top_k)
    
    def _search_with_embeddings(self, query: str, top_k: int) -> List[RetrievalResult]:
        """Search using TF-IDF embeddings."""
        try:
            # Vectorize query
            query_vector = self.vectorizer.transform([query])
            
            # Calculate similarities
            similarities = cosine_similarity(query_vector, self.document_vectors).flatten()
            
            # Get top-k results
            top_indices = np.argsort(similarities)[::-1][:top_k]
            
            results = []
            for rank, idx in enumerate(top_indices):
                if similarities[idx] > 0:  # Only include non-zero similarities
                    results.append(RetrievalResult(
                        chunk=self.chunks[idx],
                        score=float(similarities[idx]),
                        rank=rank + 1
                    ))
            
            return results
            
        except Exception as e:
            logger.error(f"Embedding search failed: {e}")
            return self._search_with_keywords(query, top_k)
    
    def _search_with_keywords(self, query: str, top_k: int) -> List[RetrievalResult]:
        """Fallback search using keyword matching."""
        query_words = set(query.lower().split())
        
        scored_chunks = []
        for chunk in self.chunks:
            chunk_words = set(chunk.content.lower().split())
            
            # Calculate simple word overlap score
            overlap = len(query_words.intersection(chunk_words))
            if overlap > 0:
                score = overlap / len(query_words.union(chunk_words))
                scored_chunks.append((chunk, score))
        
        # Sort by score and return top-k
        scored_chunks.sort(key=lambda x: x[1], reverse=True)
        
        results = []
        for rank, (chunk, score) in enumerate(scored_chunks[:top_k]):
            results.append(RetrievalResult(
                chunk=chunk,
                score=score,
                rank=rank + 1
            ))
        
        return results


class RAGSystem:
    """Main RAG system for document retrieval and context generation."""
    
    def __init__(self, docs_directory: str = "rag_docs"):
        self.docs_directory = Path(docs_directory)
        self.processor = DocumentProcessor()
        self.embedding_system = EmbeddingSystem()
        self.chunks: List[DocumentChunk] = []
        self.initialized = False
    
    def initialize_documents(self) -> bool:
        """Load and index all documents in the docs directory."""
        try:
            if not self.docs_directory.exists():
                logger.warning(f"Documents directory {self.docs_directory} does not exist")
                return False
            
            # Check cache first
            cache_key = f"rag_chunks_{self._get_docs_hash()}"
            cached_chunks = cache_manager.get(cache_key)
            
            if cached_chunks:
                logger.info("Loading document chunks from cache")
                self.chunks = [DocumentChunk(**chunk_data) for chunk_data in cached_chunks]
            else:
                logger.info("Processing documents from scratch")
                self.chunks = self._process_all_documents()
                
                # Cache the chunks
                chunks_data = [
                    {
                        'id': chunk.id,
                        'content': chunk.content,
                        'source': chunk.source,
                        'metadata': chunk.metadata
                    }
                    for chunk in self.chunks
                ]
                cache_manager.set(cache_key, chunks_data, ttl=86400)  # Cache for 24 hours
            
            # Build embeddings
            self.embedding_system.build_embeddings(self.chunks)
            
            self.initialized = True
            logger.info(f"RAG system initialized with {len(self.chunks)} document chunks")
            return True
            
        except Exception as e:
            logger.error(f"Failed to initialize RAG system: {e}")
            return False
    
    def retrieve_context(self, query: str, max_chunks: int = 3) -> List[RetrievalResult]:
        """Retrieve relevant document chunks for a query."""
        if not self.initialized:
            logger.warning("RAG system not initialized")
            return []
        
        return self.embedding_system.search_similar(query, max_chunks)
    
    def build_context_string(self, query: str, max_chunks: int = 3, max_length: int = 2000) -> str:
        """Build a context string from retrieved documents."""
        results = self.retrieve_context(query, max_chunks)
        
        if not results:
            return "No relevant documentation found."
        
        context_parts = []
        current_length = 0
        
        for result in results:
            chunk_text = f"[Source: {Path(result.chunk.source).name}]\n{result.chunk.content}\n"
            
            if current_length + len(chunk_text) > max_length:
                # Truncate if needed
                remaining_space = max_length - current_length
                if remaining_space > 100:  # Only add if there's meaningful space
                    chunk_text = chunk_text[:remaining_space] + "...\n"
                    context_parts.append(chunk_text)
                break
            
            context_parts.append(chunk_text)
            current_length += len(chunk_text)
        
        return "\n".join(context_parts)
    
    def _process_all_documents(self) -> List[DocumentChunk]:
        """Process all documents in the docs directory."""
        all_chunks = []
        
        for file_path in self.docs_directory.rglob('*'):
            if file_path.is_file():
                file_extension = file_path.suffix.lower()
                
                try:
                    if file_extension == '.pdf':
                        chunks = self.processor.process_pdf(str(file_path))
                    elif file_extension in ['.yaml', '.yml']:
                        chunks = self.processor.process_yaml(str(file_path))
                    elif file_extension in ['.html', '.htm']:
                        chunks = self.processor.process_html(str(file_path))
                    else:
                        logger.debug(f"Skipping unsupported file type: {file_path}")
                        continue
                    
                    all_chunks.extend(chunks)
                    
                except Exception as e:
                    logger.error(f"Failed to process {file_path}: {e}")
        
        return all_chunks
    
    def _get_docs_hash(self) -> str:
        """Generate hash of all document files for cache invalidation."""
        file_info = []
        
        for file_path in self.docs_directory.rglob('*'):
            if file_path.is_file():
                stat = file_path.stat()
                file_info.append(f"{file_path.name}:{stat.st_mtime}:{stat.st_size}")
        
        combined_info = "|".join(sorted(file_info))
        return hashlib.md5(combined_info.encode()).hexdigest()
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get RAG system statistics."""
        if not self.initialized:
            return {'initialized': False}
        
        doc_types = {}
        sources = set()
        
        for chunk in self.chunks:
            doc_type = chunk.metadata.get('doc_type', 'unknown')
            doc_types[doc_type] = doc_types.get(doc_type, 0) + 1
            sources.add(chunk.source)
        
        return {
            'initialized': True,
            'total_chunks': len(self.chunks),
            'total_sources': len(sources),
            'document_types': doc_types,
            'embedding_system': 'TF-IDF' if SKLEARN_AVAILABLE else 'keyword_matching',
            'sources': list(sources)
        }


# Global RAG system instance
rag_system = RAGSystem()


def initialize_rag_system() -> bool:
    """Initialize the global RAG system."""
    return rag_system.initialize_documents()


def get_context_for_query(query: str, max_chunks: int = 3) -> str:
    """Get context string for a query."""
    return rag_system.build_context_string(query, max_chunks)