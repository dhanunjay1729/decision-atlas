"""Small document-only retriever; web retrieval must be explicitly integrated."""
import math
import re
from collections import Counter
from .models import Source

def tokens(text: str) -> list[str]:
    return re.findall(r'\w+', text.casefold())

def retrieve(question: str, sources: list[Source], limit: int = 12) -> list[Source]:
    chunks = []
    for s in sources:
        for offset in range(0, len(s.text), 1100):
            passage = s.text[offset:offset + 1300].strip()
            if passage:
                chunks.append(Source(id=f's{len(chunks)+1}', title=s.title, text=passage, page=s.page, kind=s.kind, url=s.url))
    if not chunks:
        return []
    counts = [Counter(tokens(c.text)) for c in chunks]
    avg_len = sum(sum(c.values()) for c in counts) / len(counts)
    query = set(tokens(question))
    frequencies = {t: sum(t in c for c in counts) for t in query}
    def score(i):
        c = counts[i]
        length = sum(c.values())
        result = 0.0
        for t in query:
            tf = c[t]
            if not tf:
                continue
            idf = math.log(1 + (len(counts) - frequencies[t] + .5) / (frequencies[t] + .5))
            result += idf * tf * 2.5 / (tf + 1.5 * (.25 + .75 * length / max(avg_len, 1)))
        return result
    order = sorted(range(len(chunks)), key=lambda i: (-score(i), i))
    return [chunks[i] for i in order[:limit]]
