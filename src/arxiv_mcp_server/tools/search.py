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
    """Process paper information with resource URI."""
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

def _build_query(arguments: Dict[str, Any]) -> str:
    # Build search query in arXiv API format: cat:quant-ph+AND+submittedDate:[200903192000+TO+200903232000]
    query_parts = []

    # Handle category (use first if multiple, or join with +OR+ if you want all)
    categories = arguments.get("categories")
    if categories:
        # If you want just one category, use the first:
        category_str = f"cat:{categories[0]}"
        # If you want all categories, join with +OR+:
        # category_str = '+OR+'.join(f"cat:{cat}" for cat in categories)
        query_parts.append(category_str)
    
    # Handle main query (plain text or with field)
    query = arguments["query"]
    if not any(field in query for field in ["all:", "ti:", "abs:", "au:", "cat:"]):
        if '"' in query:
            query_str = f"all:{query}"
        else:
            terms = query.split()
            if len(terms) > 1:
                query_str = '+AND+'.join(f"all:{term}" for term in terms)
            else:
                query_str = f"all:{query}"
    else:
        query_str = query.replace(' ', '+AND+')
    query_parts.append(query_str)

    # Handle date range
    date_from = '197001010000'
    date_to = datetime.now(timezone.utc).strftime('%Y%m%d%H%M')
    if arguments.get("date_from"):
        date_from = parser.parse(arguments["date_from"]).strftime('%Y%m%d%H%M')
    if arguments.get("date_to"):
        date_to = parser.parse(arguments["date_to"]).strftime('%Y%m%d%H%M')
    date_str = f"submittedDate:[{date_from}+TO+{date_to}]"
    query_parts.append(date_str)

    # Join all parts with +AND+
    return '+AND+'.join(query_parts)

    
    
    
async def handle_search(arguments: Dict[str, Any]) -> List[types.TextContent]:
    """Handle paper search requests.

    Automatically adds field specifiers to plain queries for better relevance.
    This fixes issue #33 where queries sorted by date returned irrelevant results.
    """
    try:
        # return [types.TextContent(type="text", text="I am good")]
        client = MyArxivClient()
        max_results = min(int(arguments.get("max_results", 10)), settings.MAX_RESULTS)

        # Set default sort criterion
        sort_by = arxiv.SortCriterion.Relevance
        if sort_by_method := arguments.get("sort_by_method"):
            if sort_by_method == "submitted":
                sort_by = arxiv.SortCriterion.SubmittedDate
            else:
                sort_by = arxiv.SortCriterion.Relevance

        search = arxiv.Search(
            query=_build_query(arguments),
            max_results=max_results,
            sort_by=sort_by,
        )

        # Process results with date filtering
        results = []
        for paper in client.results(search):
            results.append(_process_paper(paper))

            if len(results) >= max_results:
                break

        response_data = {"total_results": len(results), "papers": results}

        return [
            types.TextContent(type="text", text=json.dumps(response_data, indent=2))
        ]

    except Exception as e:
        return [types.TextContent(type="text", text=f"Error: {str(e)}")]
