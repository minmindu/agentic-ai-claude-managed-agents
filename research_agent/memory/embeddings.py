"""
memory/embeddings.py
---------------------
One place that turns text into a vector. Used on BOTH sides of every
vector search:

  - write time: embed the text we're storing (a summary, a KB entry)
                with input_type="document", then save the array on the doc.
  - read time:  embed the incoming query with input_type="query", then
                hand that array to $vectorSearch.

Both sides MUST use the same model, or the vectors land in incompatible
spaces and similarity scores are meaningless. Keeping the single model
choice here (via SETTINGS) is what guarantees that.

Voyage's input_type is a real retrieval-quality lever, not decoration:
documents and queries get embedded slightly differently so that a short
question lands near the longer passage that answers it. We expose it
rather than hide it.

The Voyage client is created lazily and cached, so importing this module
never requires a key — only actually embedding does. That keeps the
regex-fallback code paths (and the tests that use them) runnable with no
VOYAGE_API_KEY set.
"""

from functools import lru_cache

from config.settings import SETTINGS


@lru_cache(maxsize=1)
def _client():
    """Create the Voyage client once per process. Imported lazily so a
    missing key only bites when you actually embed, not on import."""
    import voyageai  # local import: optional dependency for the vector path

    api_key = SETTINGS["voyage_api_key"]
    if not api_key:
        raise RuntimeError(
            "VOYAGE_API_KEY is not set. Add it to your .env file to use the "
            "vector-search memory paths (or run those lookups with vector=False)."
        )
    return voyageai.Client(api_key=api_key)


def embed_text(text: str, input_type: str = "document") -> list[float]:
    """
    Embed a single string.

    Args:
        text:       The text to embed.
        input_type: "document" when embedding something you're storing,
                    "query" when embedding a user's search query. Voyage
                    uses this to optimize query↔document matching.

    Returns:
        A list[float] of length SETTINGS["voyage_embedding_dims"].
    """
    result = _client().embed(
        [text],
        model=SETTINGS["voyage_embedding_model"],
        input_type=input_type,
    )
    return result.embeddings[0]


def embed_texts(texts: list[str], input_type: str = "document") -> list[list[float]]:
    """Batch form of embed_text — one Voyage call for many strings.
    Prefer this when embedding a backlog (e.g. back-filling existing
    summaries) so you're not paying per-request overhead per document."""
    if not texts:
        return []
    result = _client().embed(
        texts,
        model=SETTINGS["voyage_embedding_model"],
        input_type=input_type,
    )
    return result.embeddings
