import arxiv
from urllib.parse import urlencode, quote_plus

class MyArxivClient(arxiv.Client):
    def __init__(self, **kwargs):
        print("kwargs", kwargs)
        super().__init__(**kwargs)

    def _format_url(self, search: arxiv.Search, start: int, page_size: int) -> str:
        url_args = search._url_args()
        url_args.update({
            "start": start,
            "max_results": page_size,
        })
        
        search_query = url_args.pop("search_query", None)
        encoded = urlencode(url_args)
        if search_query is not None:
            # Keep +, :, [, ], and space (as +) unencoded in search_query
            encoded_query = quote_plus(search_query, safe=':+[]')
            query_string = f"search_query={encoded_query}&{encoded}"
        else:
            query_string = encoded
        return self.query_url_format.format(query_string)