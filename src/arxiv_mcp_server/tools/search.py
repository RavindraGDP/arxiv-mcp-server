"""Search functionality for the arXiv MCP server."""

import arxiv
import json
from .arxiv_modified import MyArxivClient
from typing import Dict, Any, List
from datetime import datetime, timezone
from dateutil import parser
import mcp.types as types
from ..config import Settings

settings = Settings()

search_tool = types.Tool(
    name="search_papers",
    description="Search for papers on arXiv with advanced filtering",
    inputSchema={
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "max_results": {"type": "integer"},
            "date_from": {"type": "string"},
            "date_to": {"type": "string"},
            "categories": {"type": "array", "items": {"type": "string"}},
            "sort_by_method": {"type": "string", "enum": ["submitted", "relevance"]},
        },
        "required": ["query"],
    },
)

def _process_paper(paper: arxiv.Result) -> Dict[str, Any]:
    """Process arXiv paper result into standardized dictionary format.
    
    Args:
        paper: arXiv search result object
        
    Returns:
        Dictionary containing standardized paper information with:
        - id: Short arXiv ID
        - title: Paper title
        - authors: List of author names
        - abstract: Paper abstract/summary
        - categories: List of arXiv categories
        - published: ISO formatted publication date
        - url: PDF URL
        - resource_uri: Custom URI scheme for MCP resource access
    """
    return {
        "id": paper.get_short_id(),
        "title": paper.title,
        "authors": [author.name for author in paper.authors],
        "abstract": paper.summary,
        "categories": paper.categories,
        "published": paper.published.isoformat(),
        "url": paper.pdf_url,
        "resource_uri": f"arxiv://{paper.get_short_id()}",
    }

def _build_category_filter(categories: List[str]) -> str:
    """Build category filter for arXiv API query.
    
    Args:
        categories: List of arXiv category codes (e.g., ['cs.AI', 'cs.LG'])
        
    Returns:
        Category filter string in arXiv API format
    """
    return '+OR+'.join(f"cat:{cat}" for cat in categories)


def _build_text_query(query: str) -> str:
    """Build text search query with proper field specifiers.
    
    Handles plain text queries by adding field specifiers for better relevance,
    and preserves existing field-specific queries.
    
    Args:
        query: Raw search query string
        
    Returns:
        Formatted query string with appropriate field specifiers
    """
    # Check if query already has field specifiers
    has_field_specifier = any(field in query for field in ["all:", "ti:", "abs:", "au:", "cat:"])
    
    if has_field_specifier:
        # Preserve existing field specifiers, replace spaces with +AND+
        return query.replace(' ', '+AND+')
    
    # Add field specifiers for plain text queries
    if '"' in query:
        # Keep quoted phrases intact
        return f"all:{query}"
    
    terms = query.split()
    if len(terms) > 1:
        return '+AND+'.join(f"all:{term}" for term in terms)
    return f"all:{query}"


def _build_date_range_filter(date_from: str | None, date_to: str | None) -> str:
    """Build date range filter for arXiv API query.
    
    Args:
        date_from: Start date string (ISO format or any parsable format)
        date_to: End date string (ISO format or any parsable format)
        
    Returns:
        Date range filter string in arXiv API format
    """
    date_from_formated = '197001010000'
    date_to_formated = datetime.now(timezone.utc).strftime('%Y%m%d%H%M')
    
    try:
        if date_from:
            date_from_formated = parser.parse(date_from).strftime('%Y%m%d%H%M')
        
        if date_to:
            date_to_formated = parser.parse(date_to).strftime('%Y%m%d%H%M')
        
        return f"submittedDate:[{date_from_formated}+TO+{date_to_formated}]"
    except (ValueError, TypeError) as e:
        raise ValueError(f"Invalid date format: {e}")


def _build_query(arguments: Dict[str, Any]) -> str:
    """Build complete arXiv API query from search arguments.
    
    Constructs a query string in arXiv API format by combining:
    - Category filters (OR'd together)
    - Text search with field specifiers
    - Date range filters
    
    Args:
        arguments: Dictionary containing search parameters:
            - query: Text search query
            - categories: List of arXiv category codes (optional)
            - date_from: Start date for filtering (optional)
            - date_to: End date for filtering (optional)
            
    Returns:
        Complete query string ready for arXiv API
        
    Example:
        >>> arguments = {
        ...     "query": "machine learning",
        ...     "categories": ["cs.AI", "cs.LG"],
        ...     "date_from": "2023-01-01"
        ... }
        >>> _build_query(arguments)
        'cat:cs.AI+OR+cat:cs.LG+AND+all:machine+AND+submittedDate:[202301010000+TO+202412240839]'
    """
    query_parts = []

    # Add category filter if provided
    if categories := arguments.get("categories"):
        query_parts.append(_build_category_filter(categories))
    
    # Add text search query
    query_parts.append(_build_text_query(arguments["query"]))

    # Add date range filter
    query_parts.append(_build_date_range_filter(
        arguments.get("date_from"),
        arguments.get("date_to")
    ))

    # Combine all parts with AND
    return '+AND+'.join(query_parts)


async def handle_search(arguments: Dict[str, Any]) -> List[types.TextContent]:
    """Handle paper search requests via the arXiv MCP server.
    
    Searches arXiv for papers based on provided criteria including text query,
    categories, date ranges, and sorting preferences. Returns formatted results
    with paper metadata and resource URIs.
    
    Args:
        arguments: Search parameters dictionary containing:
            - query (str, required): Text search query
            - max_results (int, optional): Maximum results to return (default: 10)
            - categories (List[str], optional): arXiv category codes to filter by
            - date_from (str, optional): Start date for filtering (ISO format)
            - date_to (str, optional): End date for filtering (ISO format)
            - sort_by_method (str, optional): "relevance" (default) or "submitted"
            
    Returns:
        List containing a single TextContent with JSON-formatted search results.
        Results include total count and array of papers with metadata.
        
    Raises:
        ValueError: If date parsing fails
        Exception: For other search-related errors
        
    Example:
        >>> arguments = {
        ...     "query": "machine learning transformers",
        ...     "categories": ["cs.AI", "cs.LG"],
        ...     "max_results": 5,
        ...     "date_from": "2023-01-01",
        ...     "sort_by_method": "relevance"
        ... }
        >>> await handle_search(arguments)
    """
    try:
        client = MyArxivClient()
        max_results = min(int(arguments.get("max_results", 10)), settings.MAX_RESULTS)

        # Set default sort criterion to relevance for better user experience
        sort_by = arxiv.SortCriterion.Relevance
        if sort_by_method := arguments.get("sort_by_method"):
            if sort_by_method == "submitted":
                sort_by = arxiv.SortCriterion.SubmittedDate
            else:
                sort_by = arxiv.SortCriterion.Relevance

        # Build and execute search
        search = arxiv.Search(
            query=_build_query(arguments),
            max_results=max_results,
            sort_by=sort_by,
        )

        # Process and format results
        results = []
        for paper in client.results(search):
            results.append(_process_paper(paper))

            if len(results) >= max_results:
                break

        response_data = {
            "total_results": len(results), 
            "papers": results
        }

        return [
            types.TextContent(type="text", text=json.dumps(response_data, indent=2))
        ]

    except ValueError as e:
        return [
            types.TextContent(
                type="text", 
                text=json.dumps({"error": str(e), "type": "validation_error"}, indent=2)
            )
        ]
    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]
