"""
Document Chunker

Provides document chunking with page/section tracking for vector embeddings.
Supports PDF (page-aware), HTML (section-aware), and plain text.
"""

import re
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from io import BytesIO


@dataclass
class ChunkData:
    """Container for chunk data with metadata for citations."""
    text: str
    chunk_index: int
    page_number: Optional[int] = None      # For PDFs
    section_id: Optional[str] = None       # For HTML/DOCX (e.g., "## Methods")
    char_start: int = 0                    # Character offset in original
    char_end: int = 0                      # Character offset end


@dataclass
class PageContent:
    """Content from a single PDF page."""
    page_number: int
    text: str
    char_start: int
    char_end: int


class DocumentChunker:
    """
    Document chunking with page/section tracking for citations.

    Supports:
    - PDF: Page-aware chunking with page numbers
    - HTML: Section-aware chunking based on headings
    - Text: Character-offset chunking
    """

    def __init__(
        self,
        chunk_size: int = 512,
        chunk_overlap: int = 50,
        min_chunk_size: int = 100,
        verbose: bool = False
    ):
        """
        Initialize the chunker.

        Args:
            chunk_size: Target size for each chunk (in characters)
            chunk_overlap: Overlap between chunks for context preservation
            min_chunk_size: Minimum chunk size (smaller chunks are merged)
            verbose: Enable verbose logging
        """
        self.chunk_size = chunk_size
        self.chunk_overlap = chunk_overlap
        self.min_chunk_size = min_chunk_size
        self.verbose = verbose

    def _log(self, message: str):
        """Log message if verbose mode enabled."""
        if self.verbose:
            print(f"[Chunker] {message}")

    # =========================================================================
    # PDF Chunking with Page Tracking
    # =========================================================================

    def chunk_pdf(self, pdf_content: bytes) -> List[ChunkData]:
        """
        Chunk PDF with page number tracking.

        Extracts text page-by-page and creates chunks that track
        which page(s) they came from.

        Args:
            pdf_content: PDF file content as bytes

        Returns:
            List of ChunkData with page numbers
        """
        try:
            import fitz  # PyMuPDF
        except ImportError:
            raise ImportError("PyMuPDF (fitz) is required for PDF chunking")

        chunks: List[ChunkData] = []
        pdf_document = fitz.open(stream=pdf_content, filetype="pdf")

        # Extract text from each page with position tracking
        pages: List[PageContent] = []
        char_offset = 0

        for page_num in range(len(pdf_document)):
            page = pdf_document[page_num]
            text = page.get_text().strip()
            if text:
                pages.append(PageContent(
                    page_number=page_num + 1,  # 1-indexed
                    text=text,
                    char_start=char_offset,
                    char_end=char_offset + len(text)
                ))
                char_offset += len(text) + 2  # Account for separator

        pdf_document.close()

        if not pages:
            self._log("PDF contains no extractable text")
            return []

        self._log(f"Extracted {len(pages)} pages from PDF")

        # Create chunks respecting page boundaries when possible
        chunk_index = 0
        current_text = ""
        current_page = pages[0].page_number
        current_char_start = 0

        for page in pages:
            page_text = page.text

            # If adding this page would exceed chunk size, finalize current chunk
            if current_text and len(current_text) + len(page_text) > self.chunk_size:
                # Create chunk from current accumulated text
                if len(current_text) >= self.min_chunk_size:
                    chunks.append(ChunkData(
                        text=current_text.strip(),
                        chunk_index=chunk_index,
                        page_number=current_page,
                        char_start=current_char_start,
                        char_end=current_char_start + len(current_text)
                    ))
                    chunk_index += 1

                # Start new chunk with overlap
                overlap_text = current_text[-self.chunk_overlap:] if len(current_text) > self.chunk_overlap else ""
                current_text = overlap_text
                current_char_start = page.char_start - len(overlap_text)
                current_page = page.page_number

            # Add page text to current chunk
            if current_text:
                current_text += "\n\n" + page_text
            else:
                current_text = page_text
                current_char_start = page.char_start
                current_page = page.page_number

            # If current chunk is large enough on its own, split it
            while len(current_text) > self.chunk_size:
                # Find a good split point
                split_point = self._find_split_point(current_text, self.chunk_size)

                chunks.append(ChunkData(
                    text=current_text[:split_point].strip(),
                    chunk_index=chunk_index,
                    page_number=current_page,
                    char_start=current_char_start,
                    char_end=current_char_start + split_point
                ))
                chunk_index += 1

                # Keep overlap for next chunk
                overlap_start = max(0, split_point - self.chunk_overlap)
                current_text = current_text[overlap_start:]
                current_char_start += overlap_start

        # Don't forget the last chunk
        if current_text and len(current_text.strip()) >= self.min_chunk_size:
            chunks.append(ChunkData(
                text=current_text.strip(),
                chunk_index=chunk_index,
                page_number=current_page,
                char_start=current_char_start,
                char_end=current_char_start + len(current_text)
            ))

        self._log(f"Created {len(chunks)} chunks from PDF")
        return chunks

    # =========================================================================
    # HTML/Markdown Chunking with Section Tracking
    # =========================================================================

    def chunk_html(self, html_content: bytes, url: Optional[str] = None) -> List[ChunkData]:
        """
        Chunk HTML with section tracking based on headings.

        Uses Trafilatura to extract markdown, then chunks by sections.

        Args:
            html_content: HTML content as bytes
            url: Optional URL for fallback extraction

        Returns:
            List of ChunkData with section identifiers
        """
        try:
            import trafilatura
        except ImportError:
            raise ImportError("Trafilatura is required for HTML chunking")

        # Extract markdown from HTML
        html_string = html_content.decode('utf-8', errors='ignore')
        markdown = trafilatura.extract(
            html_string,
            output_format='markdown',
            include_links=True,
            include_images=False,
            include_tables=True
        )

        if not markdown:
            self._log("Failed to extract content from HTML")
            return []

        return self.chunk_markdown(markdown)

    def chunk_markdown(self, markdown_text: str) -> List[ChunkData]:
        """
        Chunk markdown text with section tracking.

        Identifies sections by headers and creates chunks that
        preserve section context.

        Args:
            markdown_text: Markdown-formatted text

        Returns:
            List of ChunkData with section identifiers
        """
        chunks: List[ChunkData] = []
        chunk_index = 0

        # Split by headers while preserving section info
        # Pattern matches markdown headers (# Header, ## Header, etc.)
        header_pattern = re.compile(r'^(#{1,6})\s+(.+)$', re.MULTILINE)

        # Find all headers and their positions
        headers: List[Tuple[int, str, str]] = []  # (position, level, text)
        for match in header_pattern.finditer(markdown_text):
            level = match.group(1)
            text = match.group(2).strip()
            headers.append((match.start(), level, text))

        if not headers:
            # No headers, chunk as plain text
            return self.chunk_text(markdown_text)

        # Process sections
        for i, (start_pos, level, header_text) in enumerate(headers):
            # Determine section end (start of next header or end of text)
            if i + 1 < len(headers):
                end_pos = headers[i + 1][0]
            else:
                end_pos = len(markdown_text)

            section_text = markdown_text[start_pos:end_pos].strip()
            section_id = f"{level} {header_text}"

            # If section is small enough, keep as single chunk
            if len(section_text) <= self.chunk_size:
                if len(section_text) >= self.min_chunk_size:
                    chunks.append(ChunkData(
                        text=section_text,
                        chunk_index=chunk_index,
                        section_id=section_id,
                        char_start=start_pos,
                        char_end=end_pos
                    ))
                    chunk_index += 1
            else:
                # Split large section into multiple chunks
                section_chunks = self._split_section(
                    section_text,
                    section_id,
                    start_pos,
                    chunk_index
                )
                chunks.extend(section_chunks)
                chunk_index += len(section_chunks)

        self._log(f"Created {len(chunks)} chunks from markdown")
        return chunks

    def _split_section(
        self,
        text: str,
        section_id: str,
        base_offset: int,
        start_chunk_index: int
    ) -> List[ChunkData]:
        """Split a large section into multiple chunks, preserving section ID."""
        chunks: List[ChunkData] = []
        chunk_index = start_chunk_index
        pos = 0

        while pos < len(text):
            # Determine end of this chunk
            end = min(pos + self.chunk_size, len(text))

            # Find a good split point if not at end
            if end < len(text):
                split_point = self._find_split_point(text[pos:end], self.chunk_size)
                end = pos + split_point

            chunk_text = text[pos:end].strip()
            if len(chunk_text) >= self.min_chunk_size:
                chunks.append(ChunkData(
                    text=chunk_text,
                    chunk_index=chunk_index,
                    section_id=section_id,
                    char_start=base_offset + pos,
                    char_end=base_offset + end
                ))
                chunk_index += 1

            # Move forward with overlap
            pos = end - self.chunk_overlap if end < len(text) else end

        return chunks

    # =========================================================================
    # Plain Text Chunking
    # =========================================================================

    def chunk_text(self, text: str, content_type: str = "text") -> List[ChunkData]:
        """
        Chunk plain text with character offsets.

        Args:
            text: Text to chunk
            content_type: Content type indicator

        Returns:
            List of ChunkData with character offsets
        """
        if not text or not text.strip():
            return []

        chunks: List[ChunkData] = []
        chunk_index = 0
        pos = 0

        while pos < len(text):
            # Determine end of this chunk
            end = min(pos + self.chunk_size, len(text))

            # Find a good split point if not at end
            if end < len(text):
                split_point = self._find_split_point(text[pos:end], self.chunk_size)
                end = pos + split_point

            chunk_text = text[pos:end].strip()
            if len(chunk_text) >= self.min_chunk_size:
                chunks.append(ChunkData(
                    text=chunk_text,
                    chunk_index=chunk_index,
                    char_start=pos,
                    char_end=end
                ))
                chunk_index += 1

            # Move forward with overlap
            pos = end - self.chunk_overlap if end < len(text) else end

        self._log(f"Created {len(chunks)} chunks from text")
        return chunks

    # =========================================================================
    # Helper Methods
    # =========================================================================

    def _find_split_point(self, text: str, target: int) -> int:
        """
        Find a good split point near the target position.

        Prefers splitting at:
        1. Paragraph breaks (double newline)
        2. Sentence endings (. ! ?)
        3. Other punctuation (, ; :)
        4. Word boundaries (space)

        Args:
            text: Text to find split point in
            target: Target split position

        Returns:
            Best split position
        """
        if len(text) <= target:
            return len(text)

        # Search window: look back from target
        search_start = max(0, target - 100)
        search_text = text[search_start:target]

        # Priority 1: Paragraph break
        last_para = search_text.rfind('\n\n')
        if last_para != -1:
            return search_start + last_para + 2

        # Priority 2: Sentence ending
        for pattern in ['. ', '! ', '? ', '.\n', '!\n', '?\n']:
            last_sent = search_text.rfind(pattern)
            if last_sent != -1:
                return search_start + last_sent + len(pattern)

        # Priority 3: Other punctuation
        for pattern in [', ', '; ', ': ', ',\n', ';\n', ':\n']:
            last_punct = search_text.rfind(pattern)
            if last_punct != -1:
                return search_start + last_punct + len(pattern)

        # Priority 4: Word boundary
        last_space = search_text.rfind(' ')
        if last_space != -1:
            return search_start + last_space + 1

        # Fallback: split at target
        return target


def get_chunker(
    chunk_size: int = 512,
    chunk_overlap: int = 50,
    min_chunk_size: int = 100,
    verbose: bool = False
) -> DocumentChunker:
    """
    Factory function to create a document chunker.

    Args:
        chunk_size: Target size for each chunk
        chunk_overlap: Overlap between chunks
        min_chunk_size: Minimum chunk size
        verbose: Enable verbose logging

    Returns:
        DocumentChunker instance
    """
    return DocumentChunker(
        chunk_size=chunk_size,
        chunk_overlap=chunk_overlap,
        min_chunk_size=min_chunk_size,
        verbose=verbose
    )
