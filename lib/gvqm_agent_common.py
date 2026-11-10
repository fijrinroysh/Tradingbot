import re
from typing import Tuple, List, Dict, Any

def clean_json_text(text: str) -> str:
    """
    Strips markdown code fences (```json ... ```) and isolates the outer JSON object.
    Robust against arbitrary markdown formatting, backticks, and whitespace.
    """
    if not text:
        return ""
    try:
        text = text.strip()
        text = re.sub(r'^```(?:json)?\s*', '', text, flags=re.IGNORECASE)
        text = re.sub(r'\s*```$', '', text, flags=re.IGNORECASE)
        start = text.find('{')
        end = text.rfind('}')
        if start != -1 and end != -1 and end >= start:
            return text[start : end + 1]
        return text
    except Exception:
        return text


def extract_and_format_citations(grounding_metadata: Dict[str, Any]) -> Tuple[List[str], List[Dict[str, str]]]:
    """
    Extracts search queries and deduplicated citation sources from Gemini groundingMetadata.
    Returns:
        tuple: (queries, citations) where citations is a list of dicts with 'title' and 'uri'.
    """
    if not grounding_metadata or not isinstance(grounding_metadata, dict):
        return [], []

    queries = grounding_metadata.get('webSearchQueries', [])
    chunks = grounding_metadata.get('groundingChunks', [])

    citations = []
    seen_uris = set()
    for chunk in chunks:
        if isinstance(chunk, dict):
            web = chunk.get('web', {})
            uri = web.get('uri')
            title = (web.get('title') or '').strip() or 'Web Source'
            if uri and uri not in seen_uris:
                seen_uris.add(uri)
                citations.append({'title': title, 'uri': uri})

    return queries, citations


# Backward-compatibility alias
_extract_and_format_citations = extract_and_format_citations
