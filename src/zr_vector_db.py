#!/usr/bin/env python3
"""
ZoteroResearcher Vector Database Module

Local vector database for semantic search over Zotero collections.
Supports RAG queries with citations and document discovery.
"""

import hashlib
from dataclasses import dataclass
from datetime import datetime
from typing import Optional, Dict, List, Any

# Handle both relative and absolute imports
try:
    from .zr_common import ZoteroResearcherBase
    from .zr_vector_embeddings import VectorEmbeddingModel, get_embedding_model
    from .zr_vector_chunker import DocumentChunker, ChunkData, get_chunker
except ImportError:
    from zr_common import ZoteroResearcherBase
    from zr_vector_embeddings import VectorEmbeddingModel, get_embedding_model
    from zr_vector_chunker import DocumentChunker, ChunkData, get_chunker


@dataclass
class SourceMatch:
    """Document discovery result."""
    item_key: str
    title: str
    authors: str
    date: str
    item_type: str
    doc_type: Optional[str]
    relevance_score: float
    justification: Optional[str]
    top_excerpts: List[str]
    zotero_link: str


@dataclass
class ChunkSearchResult:
    """Vector search result with source metadata."""
    chunk_id: int
    item_key: str
    chunk_text: str
    similarity: float
    page_number: Optional[int]
    section_id: Optional[str]
    item_type: Optional[str]
    doc_type: Optional[str]


class ZoteroVectorSearcher(ZoteroResearcherBase):
    """
    Local vector database RAG for Zotero collections.

    Provides:
    - Document indexing with page/section tracking
    - RAG queries with citations
    - Document discovery (find top N relevant sources)
    - Filtering by item type and document type
    """

    # Default configuration
    DEFAULT_EMBEDDING_MODEL = "all-MiniLM-L6-v2"
    DEFAULT_CHUNK_SIZE = 512
    DEFAULT_CHUNK_OVERLAP = 50
    DEFAULT_TOP_K = 20

    def __init__(
        self,
        library_id: str,
        library_type: str,
        api_key: str,
        anthropic_api_key: str,
        project_name: str = None,
        force_rebuild: bool = False,
        verbose: bool = False,
        enable_cache: bool = True,  # Cache required for vector operations
        cache_dir: str = None,
        offline: bool = False
    ):
        """
        Initialize the vector searcher.

        Note: enable_cache=True is required for vector operations.
        """
        super().__init__(
            library_id=library_id,
            library_type=library_type,
            api_key=api_key,
            anthropic_api_key=anthropic_api_key,
            project_name=project_name,
            force_rebuild=force_rebuild,
            verbose=verbose,
            enable_cache=enable_cache,
            cache_dir=cache_dir,
            offline=offline
        )

        # Vector configuration (can be overridden from project config)
        self.vector_embedding_model = self.DEFAULT_EMBEDDING_MODEL
        self.vector_chunk_size = self.DEFAULT_CHUNK_SIZE
        self.vector_chunk_overlap = self.DEFAULT_CHUNK_OVERLAP
        self.vector_top_k = self.DEFAULT_TOP_K

        # Lazy-initialized components
        self._embedding_model: Optional[VectorEmbeddingModel] = None
        self._chunker: Optional[DocumentChunker] = None

    def _get_embedding_model(self) -> VectorEmbeddingModel:
        """Get or create embedding model (lazy initialization)."""
        if self._embedding_model is None:
            self._embedding_model = get_embedding_model(
                model_name=self.vector_embedding_model,
                verbose=self.verbose
            )
        return self._embedding_model

    def _get_chunker(self) -> DocumentChunker:
        """Get or create document chunker (lazy initialization)."""
        if self._chunker is None:
            self._chunker = get_chunker(
                chunk_size=self.vector_chunk_size,
                chunk_overlap=self.vector_chunk_overlap,
                verbose=self.verbose
            )
        return self._chunker

    def _load_vector_config(self, collection_key: str):
        """Load vector configuration from project config note."""
        try:
            # Try to load project config
            config = self.load_project_config_from_zotero(collection_key)
            if config:
                if 'vector_embedding_model' in config:
                    self.vector_embedding_model = config['vector_embedding_model']
                if 'vector_chunk_size' in config:
                    self.vector_chunk_size = int(config['vector_chunk_size'])
                if 'vector_chunk_overlap' in config:
                    self.vector_chunk_overlap = int(config['vector_chunk_overlap'])
                if 'vector_top_k' in config:
                    self.vector_top_k = int(config['vector_top_k'])
        except Exception as e:
            if self.verbose:
                print(f"  Note: Could not load vector config: {e}")

    # =========================================================================
    # Indexing Operations
    # =========================================================================

    def index_collection(
        self,
        collection_key: str,
        subcollections: Optional[str] = None,
        include_main: bool = False
    ) -> Dict[str, Any]:
        """
        Index all documents in a collection to the vector database.

        Args:
            collection_key: Parent collection key
            subcollections: Comma-separated subcollection names to filter
            include_main: Include items from main collection (not just subcollections)

        Returns:
            Dictionary with indexing statistics
        """
        print(f"\n=== Indexing Collection for Vector Search ===")

        # Load configuration
        self._load_vector_config(collection_key)

        # Ensure cache is enabled
        cache = self._get_cache(collection_key)
        if not cache:
            raise RuntimeError(
                "Vector indexing requires local cache. "
                "Run with --enable-cache or --sync first."
            )

        # Get items from collection (with optional subcollection filtering)
        items = self.get_items_to_process(
            collection_key,
            subcollections=subcollections,
            include_main=include_main
        )

        if not items:
            print("No items found in collection.")
            return {'indexed': 0, 'skipped': 0, 'errors': 0}

        print(f"Found {len(items)} items to index")
        print(f"Using embedding model: {self.vector_embedding_model}")
        print(f"Chunk size: {self.vector_chunk_size}, overlap: {self.vector_chunk_overlap}")

        # Initialize components
        embedding_model = self._get_embedding_model()
        chunker = self._get_chunker()

        # Track statistics
        stats = {
            'indexed': 0,
            'skipped': 0,
            'errors': 0,
            'total_chunks': 0
        }

        # Process each item
        for i, item in enumerate(items, 1):
            item_key = item['key']
            item_data = item.get('data', {})
            item_type = item_data.get('itemType', '')
            title = item_data.get('title', 'Untitled')

            # Skip child items
            if item_type in ['attachment', 'note']:
                continue

            print(f"\n[{i}/{len(items)}] Processing: {title[:60]}...")

            try:
                # Check if already indexed (unless force rebuild)
                if not self.force_rebuild:
                    index_state = cache.get_index_state(item_key)
                    if index_state:
                        print(f"  Already indexed ({index_state['chunk_count']} chunks)")
                        stats['skipped'] += 1
                        continue

                # Get content
                content, content_type = self._get_item_content(item, collection_key)
                if not content:
                    print(f"  Skipped: No extractable content")
                    stats['skipped'] += 1
                    continue

                # Calculate content hash for change detection
                content_hash = hashlib.sha256(content.encode('utf-8')).hexdigest()[:16]

                # Chunk the content
                if content_type == 'pdf':
                    # For PDFs, we need the raw bytes
                    pdf_bytes = self._get_pdf_bytes(item, collection_key)
                    if pdf_bytes:
                        chunks = chunker.chunk_pdf(pdf_bytes)
                    else:
                        chunks = chunker.chunk_text(content)
                elif content_type == 'html':
                    chunks = chunker.chunk_markdown(content)
                else:
                    chunks = chunker.chunk_text(content)

                if not chunks:
                    print(f"  Skipped: No chunks created")
                    stats['skipped'] += 1
                    continue

                print(f"  Created {len(chunks)} chunks")

                # Generate embeddings
                chunk_texts = [c.text for c in chunks]
                embeddings = embedding_model.embed_documents(chunk_texts)

                # Serialize embeddings
                serialized_embeddings = [
                    VectorEmbeddingModel.serialize_embedding(emb)
                    for emb in embeddings
                ]

                # Prepare chunk data for storage
                chunk_dicts = [
                    {
                        'text': c.text,
                        'chunk_index': c.chunk_index,
                        'page_number': c.page_number,
                        'section_id': c.section_id,
                        'char_start': c.char_start,
                        'char_end': c.char_end
                    }
                    for c in chunks
                ]

                # Store in cache
                cache.store_chunks(
                    item_key=item_key,
                    chunks=chunk_dicts,
                    embeddings=serialized_embeddings,
                    item_type=item_type,
                    doc_type=None,  # Could load from Phase 1 summary if available
                    content_hash=content_hash,
                    embedding_model=self.vector_embedding_model
                )

                stats['indexed'] += 1
                stats['total_chunks'] += len(chunks)
                print(f"  Indexed successfully")

            except Exception as e:
                print(f"  Error: {e}")
                stats['errors'] += 1
                if self.verbose:
                    import traceback
                    traceback.print_exc()

        # Print summary
        print(f"\n=== Indexing Complete ===")
        print(f"Indexed: {stats['indexed']} items ({stats['total_chunks']} chunks)")
        print(f"Skipped: {stats['skipped']} items")
        print(f"Errors: {stats['errors']} items")

        # Print vector stats
        cache.print_vector_stats()

        return stats

    def _get_item_content(
        self,
        item: Dict,
        collection_key: str
    ) -> tuple[Optional[str], Optional[str]]:
        """
        Get text content from an item's attachment.

        Returns:
            Tuple of (content_text, content_type) or (None, None)
        """
        # get_source_content returns (content_text, content_type) tuple
        content_text, content_type = self.get_source_content(item)
        if not content_text:
            return None, None

        return content_text, content_type or 'text'

    def _get_pdf_bytes(self, item: Dict, collection_key: str) -> Optional[bytes]:
        """Get raw PDF bytes for an item if available."""
        try:
            children = self.get_item_attachments(item['key'])
            for child in children:
                child_data = child.get('data', {})
                if self.is_pdf_attachment(child_data):
                    return self.download_attachment(child['key'])
        except Exception as e:
            if self.verbose:
                print(f"  Could not get PDF bytes: {e}")
        return None

    # =========================================================================
    # RAG Query Operations
    # =========================================================================

    def run_vector_query(
        self,
        collection_key: str,
        subcollections: Optional[str] = None,
        include_main: bool = False,
        item_types: Optional[List[str]] = None,
        doc_types: Optional[List[str]] = None
    ) -> Optional[str]:
        """
        Run RAG query and generate report with citations.

        Args:
            collection_key: Parent collection key
            subcollections: Comma-separated subcollection names to filter
            include_main: Include items from main collection
            item_types: Filter by Zotero item types
            doc_types: Filter by document types

        Returns:
            Report key if successful, None otherwise
        """
        print(f"\n=== Running Vector Search Query ===")

        # Load configuration
        self._load_vector_config(collection_key)

        # Ensure cache exists with indexed data
        cache = self._get_cache(collection_key)
        if not cache:
            raise RuntimeError("Vector search requires local cache.")

        indexed_items = cache.get_indexed_items()
        if not indexed_items:
            raise RuntimeError(
                "No indexed items found. Run --index-vectors first."
            )

        print(f"Found {len(indexed_items)} indexed items")

        # Load query from Query Request note
        query = self.load_query_request_from_zotero(collection_key)
        if not query:
            raise RuntimeError(
                "No query found. Please add a query to the 【Query Request】 note."
            )

        print(f"Query: {query[:100]}...")

        # Embed query
        embedding_model = self._get_embedding_model()
        query_embedding = embedding_model.embed_query(query)
        query_embedding_bytes = VectorEmbeddingModel.serialize_embedding(query_embedding)

        # Search for relevant chunks
        results = cache.search_vectors(
            query_embedding=query_embedding_bytes,
            top_k=self.vector_top_k,
            item_types=item_types,
            doc_types=doc_types
        )

        if not results:
            print("No relevant chunks found.")
            return None

        print(f"Found {len(results)} relevant chunks")

        # Group chunks by source
        grouped = self._group_chunks_by_source(results)
        print(f"From {len(grouped)} unique sources")

        # Generate response with Claude
        response = self._generate_rag_response(query, grouped, collection_key)

        # Generate report title
        report_title = self._generate_report_title(query)

        # Create report
        report_content = self._format_vector_search_report(
            title=report_title,
            query=query,
            response=response,
            grouped_chunks=grouped,
            collection_key=collection_key
        )

        # Save to Zotero
        note_title = f"Vector Search Report: {report_title}"
        note_key = self.create_standalone_note(
            collection_key=self._get_project_subcollection_key(collection_key),
            title=note_title,
            content=report_content,
            convert_markdown=True
        )

        print(f"\nReport saved: {note_title}")
        return note_key

    def load_query_request_from_zotero(self, collection_key: str) -> Optional[str]:
        """Load query from Query Request note in project subcollection."""
        try:
            return self.load_note_from_subcollection(
                collection_key,
                self._get_query_request_note_title(),
                check_todo=True,
                remove_title_line=True,
                remove_footer=True,
                operation_name="vector search"
            )
        except Exception as e:
            if self.verbose:
                print(f"Could not load query: {e}")
            return None

    def _group_chunks_by_source(
        self,
        results: List[Dict]
    ) -> Dict[str, Dict]:
        """
        Group search results by source item.

        Returns dict keyed by item_key with:
        - item_key
        - chunks: list of chunk results
        - max_similarity: highest similarity score
        - metadata: item metadata (loaded later)
        """
        grouped = {}

        for result in results:
            item_key = result['item_key']
            if item_key not in grouped:
                grouped[item_key] = {
                    'item_key': item_key,
                    'chunks': [],
                    'max_similarity': 0.0,
                    'metadata': None
                }

            grouped[item_key]['chunks'].append(result)
            if result['similarity'] > grouped[item_key]['max_similarity']:
                grouped[item_key]['max_similarity'] = result['similarity']

        # Sort by max similarity
        sorted_groups = dict(sorted(
            grouped.items(),
            key=lambda x: x[1]['max_similarity'],
            reverse=True
        ))

        return sorted_groups

    def _generate_rag_response(
        self,
        query: str,
        grouped_chunks: Dict[str, Dict],
        collection_key: str
    ) -> str:
        """Generate RAG response using Claude with citations."""
        # Build context from chunks
        context_parts = []
        source_index = 1

        for item_key, group in grouped_chunks.items():
            # Load item metadata
            cache = self._get_cache(collection_key)
            item = cache.get_item(item_key) if cache else None
            item_data = item.get('data', {}) if item else {}
            title = item_data.get('title', 'Unknown Source')

            # Add source header
            context_parts.append(f"[Source {source_index}: {title}]")

            # Add top chunks for this source
            for chunk in group['chunks'][:3]:  # Limit chunks per source
                location = ""
                if chunk.get('page_number'):
                    location = f"Page {chunk['page_number']}"
                elif chunk.get('section_id'):
                    location = chunk['section_id']

                if location:
                    context_parts.append(f"[{location}]")
                context_parts.append(chunk['chunk_text'])
                context_parts.append("---")

            source_index += 1

        context = "\n".join(context_parts)

        # Load project overview for context
        project_overview = ""
        try:
            project_overview = self.load_project_overview_from_zotero(collection_key)
        except Exception:
            pass

        # Generate response
        prompt = self._build_rag_prompt(query, context, project_overview)

        response = self.llm_client.call(
            prompt=prompt,
            model=self.haiku_model,
            max_tokens=4096
        )

        return response

    def _build_rag_prompt(
        self,
        query: str,
        context: str,
        project_overview: str
    ) -> str:
        """Build prompt for RAG response generation."""
        return f"""You are a research assistant analyzing sources from a Zotero collection.
Answer the query based ONLY on the provided context. Cite sources using [N, p.X] format where N is the source number and X is the page number or section.

{f"Project Context: {project_overview}" if project_overview else ""}

Retrieved Context:
{context}

Query:
{query}

Instructions:
1. Answer based ONLY on the provided context
2. Cite every claim with [source_number, page/section] (e.g., [1, p.5] or [2, Methods])
3. If information is not in the context, say so explicitly
4. Organize your response clearly with headings if appropriate
5. Include specific quotes and statistics when available

Response:"""

    def _generate_report_title(self, query: str) -> str:
        """Generate a concise title for the report."""
        prompt = f"""Generate a concise title (3-7 words) for a research report answering this query:

Query: {query}

Respond with ONLY the title, no quotes or explanation:"""

        title = self.llm_client.call(
            prompt=prompt,
            model=self.haiku_model,
            max_tokens=50
        )

        return title.strip().strip('"')[:100]

    def _format_vector_search_report(
        self,
        title: str,
        query: str,
        response: str,
        grouped_chunks: Dict[str, Dict],
        collection_key: str
    ) -> str:
        """Format the vector search report as markdown."""
        cache = self._get_cache(collection_key)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        report_parts = [
            f"# Vector Search Report: {title}",
            "",
            f"**Project:** {self.project_name}",
            f"**Date:** {timestamp}",
            f"**Sources Retrieved:** {len(grouped_chunks)}",
            "",
            "---",
            "",
            "## Query",
            "",
            query,
            "",
            "---",
            "",
            "## Response",
            "",
            response,
            "",
            "---",
            "",
            "## Sources",
            ""
        ]

        # Add source details
        source_index = 1
        for item_key, group in grouped_chunks.items():
            # Load metadata
            item = cache.get_item(item_key) if cache else None
            item_data = item.get('data', {}) if item else {}

            title = item_data.get('title', 'Unknown')
            creators = item_data.get('creators', [])
            authors = self._format_authors(creators)
            date = item_data.get('date', 'N/A')
            item_type = item_data.get('itemType', 'N/A')

            report_parts.append(f"### {source_index}. {title}")
            report_parts.append(f"**Authors:** {authors}")
            report_parts.append(f"**Date:** {date}")
            report_parts.append(f"**Type:** {item_type}")
            report_parts.append(f"**Relevance:** {group['max_similarity']:.2f}")
            report_parts.append("")

            # Add excerpts
            report_parts.append("#### Excerpts:")
            for chunk in group['chunks'][:3]:
                location = ""
                if chunk.get('page_number'):
                    location = f"**Page {chunk['page_number']}:** "
                elif chunk.get('section_id'):
                    location = f"**{chunk['section_id']}:** "

                excerpt = chunk['chunk_text'][:300]
                if len(chunk['chunk_text']) > 300:
                    excerpt += "..."
                report_parts.append(f"- {location}\"{excerpt}\"")

            report_parts.append("")
            source_index += 1

        report_parts.extend([
            "---",
            "",
            "*Generated by ZoteroResearcher Vector Search*"
        ])

        return "\n".join(report_parts)

    def _format_authors(self, creators: List[Dict]) -> str:
        """Format creator list as author string."""
        if not creators:
            return "Unknown"

        authors = []
        for creator in creators:
            if 'lastName' in creator:
                name = creator['lastName']
                if 'firstName' in creator:
                    name = f"{creator['firstName']} {name}"
            elif 'name' in creator:
                name = creator['name']
            else:
                continue
            authors.append(name)

        return ", ".join(authors) if authors else "Unknown"

    def _get_project_subcollection_key(self, collection_key: str) -> str:
        """Get the project subcollection key."""
        subcollection_name = self._get_subcollection_name()
        subcoll = self.get_subcollection(collection_key, subcollection_name)
        if subcoll:
            return subcoll['key']
        return collection_key

    # =========================================================================
    # Document Discovery Operations
    # =========================================================================

    def discover_sources(
        self,
        collection_key: str,
        top_n: int = 10,
        subcollections: Optional[str] = None,
        include_main: bool = False,
        item_types: Optional[List[str]] = None,
        doc_types: Optional[List[str]] = None
    ) -> List[SourceMatch]:
        """
        Find top N most relevant documents for a query.

        Args:
            collection_key: Parent collection key
            top_n: Number of sources to return
            subcollections: Comma-separated subcollection names
            include_main: Include items from main collection
            item_types: Filter by Zotero item types
            doc_types: Filter by document types

        Returns:
            List of SourceMatch objects
        """
        print(f"\n=== Discovering Relevant Sources ===")

        # Load configuration
        self._load_vector_config(collection_key)

        # Ensure cache exists with indexed data
        cache = self._get_cache(collection_key)
        if not cache:
            raise RuntimeError("Source discovery requires local cache.")

        indexed_items = cache.get_indexed_items()
        if not indexed_items:
            raise RuntimeError(
                "No indexed items found. Run --index-vectors first."
            )

        # Load query
        query = self.load_query_request_from_zotero(collection_key)
        if not query:
            raise RuntimeError(
                "No query found. Please add a query to the 【Query Request】 note."
            )

        print(f"Query: {query[:100]}...")
        print(f"Searching for top {top_n} relevant sources...")

        # Embed query
        embedding_model = self._get_embedding_model()
        query_embedding = embedding_model.embed_query(query)
        query_embedding_bytes = VectorEmbeddingModel.serialize_embedding(query_embedding)

        # Search with more results than needed (to aggregate by source)
        results = cache.search_vectors(
            query_embedding=query_embedding_bytes,
            top_k=top_n * 5,  # Get more chunks to aggregate
            item_types=item_types,
            doc_types=doc_types
        )

        if not results:
            print("No relevant sources found.")
            return []

        # Aggregate scores by source
        source_scores: Dict[str, Dict] = {}
        for result in results:
            item_key = result['item_key']
            if item_key not in source_scores:
                source_scores[item_key] = {
                    'total_similarity': 0.0,
                    'chunk_count': 0,
                    'max_similarity': 0.0,
                    'top_excerpts': [],
                    'item_type': result.get('item_type'),
                    'doc_type': result.get('doc_type')
                }

            source_scores[item_key]['total_similarity'] += result['similarity']
            source_scores[item_key]['chunk_count'] += 1
            if result['similarity'] > source_scores[item_key]['max_similarity']:
                source_scores[item_key]['max_similarity'] = result['similarity']

            # Keep top excerpts
            if len(source_scores[item_key]['top_excerpts']) < 3:
                source_scores[item_key]['top_excerpts'].append(
                    result['chunk_text'][:200]
                )

        # Calculate average similarity and rank
        for item_key in source_scores:
            scores = source_scores[item_key]
            # Use a combination of max and average similarity
            avg_sim = scores['total_similarity'] / scores['chunk_count']
            scores['relevance_score'] = 0.7 * scores['max_similarity'] + 0.3 * avg_sim

        # Sort by relevance and take top N
        ranked_sources = sorted(
            source_scores.items(),
            key=lambda x: x[1]['relevance_score'],
            reverse=True
        )[:top_n]

        # Build SourceMatch objects with metadata
        matches = []
        for item_key, scores in ranked_sources:
            # Load item metadata
            item = cache.get_item(item_key)
            item_data = item.get('data', {}) if item else {}

            title = item_data.get('title', 'Unknown')
            creators = item_data.get('creators', [])
            authors = self._format_authors(creators)
            date = item_data.get('date', 'N/A')
            item_type = item_data.get('itemType', 'N/A')

            # Generate Zotero link
            library_type = 'groups' if self.zot.library_type == 'group' else 'library'
            zotero_link = f"zotero://select/{library_type}/{self.zot.library_id}/items/{item_key}"

            match = SourceMatch(
                item_key=item_key,
                title=title,
                authors=authors,
                date=date,
                item_type=item_type,
                doc_type=scores.get('doc_type'),
                relevance_score=scores['relevance_score'],
                justification=None,  # Generated below if needed
                top_excerpts=scores['top_excerpts'],
                zotero_link=zotero_link
            )
            matches.append(match)

        print(f"Found {len(matches)} relevant sources")

        # Generate justifications for top results
        for match in matches[:5]:  # Only top 5 get justifications
            match.justification = self._generate_justification(
                query, match.title, match.top_excerpts
            )

        # Create discovery report
        self._create_discovery_report(query, matches, collection_key)

        return matches

    def _generate_justification(
        self,
        query: str,
        title: str,
        excerpts: List[str]
    ) -> str:
        """Generate brief justification for why a source is relevant."""
        excerpts_text = "\n".join([f"- {e}" for e in excerpts[:2]])

        prompt = f"""Based on the query and excerpts, write a 1-2 sentence justification for why this source is relevant.

Query: {query}

Source: {title}

Key Excerpts:
{excerpts_text}

Respond with ONLY the justification (1-2 sentences), no other text:"""

        justification = self.llm_client.call(
            prompt=prompt,
            model=self.haiku_model,
            max_tokens=100
        )

        return justification.strip()

    def _create_discovery_report(
        self,
        query: str,
        matches: List[SourceMatch],
        collection_key: str
    ) -> str:
        """Create and save discovery report to Zotero."""
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

        report_parts = [
            "# Document Discovery Results",
            "",
            f"**Query:** {query}",
            f"**Date:** {timestamp}",
            f"**Project:** {self.project_name}",
            "",
            "---",
            "",
            f"## Top {len(matches)} Relevant Sources",
            ""
        ]

        for i, match in enumerate(matches, 1):
            report_parts.append(
                f"### {i}. {match.title} (Score: {match.relevance_score:.2f})"
            )
            report_parts.append(f"**Authors:** {match.authors}")
            report_parts.append(f"**Date:** {match.date}")
            report_parts.append(f"**Type:** {match.item_type}")
            report_parts.append("")

            if match.justification:
                report_parts.append(f"**Why Relevant:** {match.justification}")
                report_parts.append("")

            report_parts.append(f"[Open in Zotero]({match.zotero_link})")
            report_parts.append("")
            report_parts.append("---")
            report_parts.append("")

        report_parts.append("*Generated by ZoteroResearcher Document Discovery*")

        report_content = "\n".join(report_parts)

        # Save to Zotero
        note_title = f"Document Discovery: {timestamp}"
        note_key = self.create_standalone_note(
            collection_key=self._get_project_subcollection_key(collection_key),
            title=note_title,
            content=report_content,
            convert_markdown=True
        )

        print(f"\nDiscovery report saved: {note_title}")
        return note_key
