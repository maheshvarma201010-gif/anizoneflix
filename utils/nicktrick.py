import re
import logging
import asyncio
import aiohttp
from urllib.parse import urlparse, parse_qs, unquote, urljoin

logger = logging.getLogger("MZ_NICKTRICK")

USER_AGENT = "Mozilla/5.0 (Linux; Android 10; Mobile) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"

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

def resolve_nicktrick_url_sync(url: str) -> str:
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

async def resolve_nicktrick_url_async(url: str) -> str:
    """
    Port of node bypass.js script:
    1. Extracts domain before '=' as default/custom referer.
    2. Extracts target URL after '=' (or nicktrick param).
    3. Sends HTTP GET request with User-Agent and Referer headers.
    4. Follows up to 10 HTTP redirects and returns final destination URL.
    """
    try:
        parsed = urlparse(url)
        referer = f"{parsed.scheme}://{parsed.netloc}/" if parsed.scheme and parsed.netloc else "https://urllinkshort.in/"

        extracted = None
        params = parse_qs(parsed.query)
        if "nicktrick" in params and params["nicktrick"]:
            extracted = params["nicktrick"][0]
        elif "=" in url:
            extracted = url.split("=", 1)[1]

        target_url = unquote(extracted) if extracted else url
        if not (target_url.startswith("http://") or target_url.startswith("https://")):
            target_url = url

        current_url = target_url
        current_referer = referer

        async with aiohttp.ClientSession() as session:
            for depth in range(10):
                headers = {
                    "User-Agent": USER_AGENT,
                    "Referer": current_referer,
                    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
                }
                try:
                    async with session.get(current_url, headers=headers, allow_redirects=False, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                        if resp.status in [301, 302, 303, 307, 308] and "Location" in resp.headers:
                            redirect_target = urljoin(current_url, resp.headers["Location"])
                            current_referer = current_url
                            current_url = redirect_target
                        else:
                            return current_url
                except Exception as req_err:
                    logger.error(f"HTTP request error at depth {depth} for {current_url}: {req_err}")
                    return current_url

        return current_url
    except Exception as e:
        logger.error(f"Error resolving nicktrick URL async {url}: {e}")
        return url
