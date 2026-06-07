"""
Tool schemas passed to the OpenAI API.
Each agent only receives the tools relevant to its job.
"""

WEB_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "web_search",
        "description": "Search the web for recent information on a topic using Tavily.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        },
    },
}

ARXIV_SEARCH_TOOL = {
    "type": "function",
    "function": {
        "name": "arxiv_search",
        "description": "Search Arxiv for academic papers related to a topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string"},
                "max_results": {"type": "integer", "default": 3},
            },
            "required": ["query"],
        },
    },
}

FETCH_URL_TOOL = {
    "type": "function",
    "function": {
        "name": "fetch_url",
        "description": "Fetch and extract the full text content of a URL (web page or PDF).",
        "parameters": {
            "type": "object",
            "properties": {
                "url": {"type": "string", "description": "The URL to fetch"},
            },
            "required": ["url"],
        },
    },
}

STORE_CLAIM_TOOL = {
    "type": "function",
    "function": {
        "name": "store_validated_claim",
        "description": "Store a validated claim with its supporting and contradicting sources.",
        "parameters": {
            "type": "object",
            "properties": {
                "claim": {"type": "string"},
                "supported_by": {"type": "array", "items": {"type": "string"}},
                "contradicted_by": {"type": "array", "items": {"type": "string"}},
                "confidence": {"type": "number", "minimum": 0, "maximum": 1},
            },
            "required": ["claim", "supported_by"],
        },
    },
}

RAG_RETRIEVE_TOOL = {
    "type": "function",
    "function": {
        "name": "rag_retrieve",
        "description": "Retrieve relevant document chunks from the vector store based on a query. "
                       "Returns past research context that may be relevant to the current topic.",
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The query to search the knowledge base for"},
                "n_results": {"type": "integer", "default": 8, "description": "Max results to return"},
            },
            "required": ["query"],
        },
    },
}

RAG_STORE_TOOL = {
    "type": "function",
    "function": {
        "name": "rag_store",
        "description": "Store document chunks into the vector store for future retrieval.",
        "parameters": {
            "type": "object",
            "properties": {
                "chunks": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "content": {"type": "string"},
                            "url": {"type": "string"},
                            "source_type": {"type": "string"},
                        },
                    },
                    "description": "Chunks to store in the knowledge base",
                },
                "job_id": {"type": "string", "description": "Job ID for metadata tracking"},
            },
            "required": ["chunks", "job_id"],
        },
    },
}
