import re
import logging
from urllib.parse import urlparse, parse_qs, unquote

logger = logging.getLogger("MZ_NICKTRICK")

def extract_nicktrick_urls(text: str, entities=None) -> list:
    urls = []
    if not text:
        text = ""

    # 1. Extract from plain text
    found_in_text = re.findall(r'https?://[^\s>"]+', text)
    urls.extend(found_in_text)

    # 2. Extract from message entities (hyperlinks)
    if entities:
        for entity in entities:
            if getattr(entity, "url", None):
                urls.append(entity.url)

    nicktrick_urls = []
    for url in urls:
        if "nicktrick=" in url or "urllinkshort.in" in url:
            nicktrick_urls.append(url)

    return list(set(nicktrick_urls))

def resolve_nicktrick_url(url: str) -> str:
    try:
        parsed = urlparse(url)
        params = parse_qs(parsed.query)
        if "nicktrick" in params and params["nicktrick"]:
            redirect_url = params["nicktrick"][0]
            redirect_url = unquote(redirect_url)
            if redirect_url.startswith("http://") or redirect_url.startswith("https://"):
                return redirect_url
    except Exception as e:
        logger.error(f"Error resolving nicktrick URL {url}: {e}")
    return url
