"""
ZoteroResearcher LLM Client

Centralized interface for all LLM interactions in the researcher module.
Handles both single and batch API calls with consistent error handling,
rate limiting, and progress tracking.
"""

import time
from typing import Optional, Dict, List, Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from anthropic import Anthropic


class ZRLLMClient:
    """
    Centralized LLM client for ZoteroResearcher.

    Provides consistent interface for single and batch LLM calls with:
    - Unified error handling
    - Automatic response parsing
    - Rate limiting
    - Progress tracking
    - Model selection
    """

    def __init__(
        self,
        anthropic_client: Anthropic,
        default_model: str = 'claude-haiku-4-5-20251001',
        verbose: bool = False
    ):
        """
        Initialize the LLM client.

        Args:
            anthropic_client: Initialized Anthropic client
            default_model: Default model to use if not specified per call
            verbose: If True, show detailed debug information
        """
        self.client = anthropic_client
        self.default_model = default_model
        self.verbose = verbose

    def call(
        self,
        prompt: str,
        max_tokens: int = 1000,
        model: Optional[str] = None,
        temperature: float = 1.0
    ) -> Optional[str]:
        """
        Make a single synchronous LLM API call.

        Args:
            prompt: The prompt to send
            max_tokens: Maximum tokens in response
            model: Model to use (overrides default)
            temperature: Temperature for sampling (0.0-1.0)

        Returns:
            Response text, or None if call fails
        """
        try:
            response = self.client.messages.create(
                model=model or self.default_model,
                max_tokens=max_tokens,
                temperature=temperature,
                messages=[
                    {"role": "user", "content": prompt}
                ]
            )

            if response.content and len(response.content) > 0:
                return response.content[0].text.strip()
            else:
                if self.verbose:
                    print(f"  ⚠️  Empty response from LLM")
                return None

        except Exception as e:
            if self.verbose:
                print(f"  ❌ LLM call error: {e}")
            return None

    def call_batch(
        self,
        requests: List[Dict],
        max_workers: int = 10,
        rate_limit_delay: float = 0.1,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Optional[str]]:
        """
        Make multiple LLM API calls in parallel using ThreadPoolExecutor.

        Args:
            requests: List of request dicts with keys:
                - 'id': Unique identifier for this request
                - 'prompt': The prompt to send
                - 'max_tokens': Maximum tokens in response (default: 1000)
                - 'model': Model to use (optional, uses default if not specified)
                - 'temperature': Temperature (optional, default: 1.0)
            max_workers: Number of concurrent threads (default: 10)
            rate_limit_delay: Delay in seconds between request submissions (default: 0.1)
            progress_callback: Optional callback(completed, total) called after each completion

        Returns:
            Dict mapping request IDs to responses: {id: response_text or None}
        """
        results = {}
        total = len(requests)
        completed = 0

        # Submit all requests to thread pool with rate limiting
        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            # Map futures to request IDs
            future_to_id = {}

            for request in requests:
                future = executor.submit(
                    self.call,
                    prompt=request['prompt'],
                    max_tokens=request.get('max_tokens', 1000),
                    model=request.get('model'),
                    temperature=request.get('temperature', 1.0)
                )
                future_to_id[future] = request['id']

                # Rate limiting between submissions
                if rate_limit_delay > 0:
                    time.sleep(rate_limit_delay)

            # Collect results as they complete
            for future in as_completed(future_to_id):
                request_id = future_to_id[future]
                try:
                    result = future.result()
                    results[request_id] = result
                except Exception as e:
                    if self.verbose:
                        print(f"  ❌ Error processing request {request_id}: {e}")
                    results[request_id] = None

                # Progress tracking
                completed += 1
                if progress_callback:
                    progress_callback(completed, total)

        return results

    def call_batch_with_parsing(
        self,
        requests: List[Dict],
        parser: Callable[[str], Optional[Dict]],
        max_workers: int = 10,
        rate_limit_delay: float = 0.1,
        progress_callback: Optional[Callable] = None
    ) -> Dict[str, Optional[Dict]]:
        """
        Make batch calls and parse responses with a custom parser function.

        Args:
            requests: List of request dicts (same format as call_batch)
            parser: Function to parse response text: parser(text) -> Dict or None
            max_workers: Number of concurrent threads
            rate_limit_delay: Delay between request submissions
            progress_callback: Optional callback(completed, total)

        Returns:
            Dict mapping request IDs to parsed results: {id: parsed_dict or None}
        """
        # Get raw responses
        raw_results = self.call_batch(
            requests,
            max_workers=max_workers,
            rate_limit_delay=rate_limit_delay,
            progress_callback=progress_callback
        )

        # Parse each response
        parsed_results = {}
        for request_id, response_text in raw_results.items():
            if response_text:
                try:
                    parsed_results[request_id] = parser(response_text)
                except Exception as e:
                    if self.verbose:
                        print(f"  ⚠️  Error parsing response for {request_id}: {e}")
                    parsed_results[request_id] = None
            else:
                parsed_results[request_id] = None

        return parsed_results
