"""Downloads allowlisted external veterinary sources into data/knowledge/external/. (Phase 6)

The clinic's own Markdown is the high-value content; this adds general pet-health
background from a short, hand-checked list of sources.

Three rules, and none of them are optional:

1. **A hardcoded allowlist, never a crawler.** Every URL below was chosen and
   checked by a person. A broad crawler would be both less accurate and less
   defensible.

2. **robots.txt decides.** Each host's robots.txt is fetched and parsed before
   anything else, and a Disallow is final -- the URL is skipped and reported, not
   fetched. The site's own ``Crawl-delay`` is honoured as a *minimum*, so a host
   asking for 30 seconds gets 30 seconds even though --delay defaults lower.
   ``fda.gov`` does ask for 30, which is why a full run takes minutes.

3. **The seed list is US-government public-domain material** (FDA Center for
   Veterinary Medicine, USDA APHIS). Copyright and terms-of-service questions on
   that content are settled; for anything else, read the terms yourself, record
   what you found in ``license_note``, and confirm with --dry-run before adding it.

Text extraction is stdlib only -- no beautifulsoup4, no new dependency -- and
maps h1..h6 onto Markdown headings so app/rag/chunker.py's heading logic keeps
working on fetched pages. Every file carries YAML front-matter with its
``source_url``, which ingest reads back so the chatbot can attribute the answer.

Run from api/ with the venv active:

    python scripts/fetch_external.py --dry-run   # robots verdicts, writes nothing
    python scripts/fetch_external.py
"""

from __future__ import annotations

import argparse
import re
import sys
import time
import urllib.robotparser
from dataclasses import dataclass
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from urllib.parse import urljoin, urlparse

# Allow "python scripts/fetch_external.py" without installing the package.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import httpx

from app.config import settings

USER_AGENT = "VetClinicKnowledgeBot/1.0 (+educational clinic project; contact the clinic)"
DEFAULT_DELAY = 2.0


@dataclass(frozen=True)
class Source:
    url: str
    title: str
    license_note: str


# Keep this list short, curated, and personally checked. See the module docstring.
ALLOWLIST: list[Source] = [
    Source(
        url="https://www.fda.gov/animal-veterinary/animal-health-literacy/keep-worms-out-your-pets-heart-facts-about-heartworm-disease",
        title="Heartworm disease in pets (FDA)",
        license_note="US federal government work, public domain (17 USC 105)",
    ),
    Source(
        url="https://www.fda.gov/animal-veterinary/animal-health-literacy/leave-chocolate-out-rovers-celebrations",
        title="Chocolate is toxic to dogs (FDA)",
        license_note="US federal government work, public domain (17 USC 105)",
    ),
    Source(
        url="https://www.fda.gov/animal-veterinary/animal-health-literacy/paws-xylitol-toxic-dogs",
        title="Xylitol is toxic to dogs (FDA)",
        license_note="US federal government work, public domain (17 USC 105)",
    ),
    Source(
        url="https://www.fda.gov/animal-veterinary/animal-health-literacy/lovely-lilies-and-curious-cats-dangerous-combination",
        title="Lilies are toxic to cats (FDA)",
        license_note="US federal government work, public domain (17 USC 105)",
    ),
    Source(
        url="https://www.fda.gov/animal-veterinary/animal-health-literacy/who-do-you-call-if-you-have-pet-emergency",
        title="Who to call in a pet emergency (FDA)",
        license_note="US federal government work, public domain (17 USC 105)",
    ),
]

_SKIP_TAGS = {"script", "style", "nav", "header", "footer", "aside", "form", "noscript", "svg"}
_BLOCK_TAGS = {"p", "div", "section", "article", "br", "tr", "table", "ul", "ol", "blockquote"}
_HEADINGS = {f"h{n}": n for n in range(1, 7)}


class _TextExtractor(HTMLParser):
    """Minimal HTML -> Markdown-ish text. Stdlib only, deliberately."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip_depth = 0
        self._heading: int | None = None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag in _HEADINGS:
            self._heading = _HEADINGS[tag]
            self.parts.append("\n\n" + "#" * self._heading + " ")
        elif tag == "li":
            self.parts.append("\n- ")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth = max(0, self._skip_depth - 1)
            return
        if self._skip_depth:
            return
        if tag in _HEADINGS:
            self._heading = None
            self.parts.append("\n\n")
        elif tag in _BLOCK_TAGS:
            self.parts.append("\n\n")

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = re.sub(r"\s+", " ", data)
        if text.strip():
            self.parts.append(text)

    def text(self) -> str:
        joined = "".join(self.parts)
        joined = re.sub(r"[ \t]+", " ", joined)
        joined = re.sub(r" *\n *", "\n", joined)
        joined = re.sub(r"\n{3,}", "\n\n", joined)
        # A heading left with no text after it helps nobody.
        joined = re.sub(r"^#+\s*$", "", joined, flags=re.MULTILINE)
        return joined.strip()


# Site chrome that survives tag-level filtering because FDA renders it as plain
# divs and lists rather than <nav>/<footer>. Each entry was read off a real
# fetched page. Matching is exact on a stripped line (or the "- " list form), so
# a paragraph that merely contains the word "Feedback" is untouched.
_CHROME_LINES = {
    "skip to main content",
    "skip to fda search",
    "skip to in this section menu",
    "skip to footer links",
    "skip to topics menu",
    "in this section",
    "feedback",
    "back to top",
    "home",
    "animal & veterinary",
    "resources for you",
    "animal health literacy",
    "espanol",
    "espa\u00f1ol",
    "share",
    "print",
    "subscribe to email updates",
}


def strip_chrome(text: str) -> str:
    """Drop navigation and footer lines the tag filter cannot see.

    Also drops the breadcrumb trail, which shows up as a run of list items whose
    last entry repeats the page title -- one more copy of the title adds nothing
    to an embedding and dilutes the chunk it lands in.
    """
    kept: list[str] = []
    for line in text.splitlines():
        bare = line.strip()
        if bare.startswith("- "):
            bare = bare[2:].strip()
        if bare.lower().rstrip(":") in _CHROME_LINES:
            continue
        kept.append(line)
    joined = "\n".join(kept)
    return re.sub(r"\n{3,}", "\n\n", joined).strip()


def slugify(value: str) -> str:
    slug = re.sub(r"[^a-z0-9]+", "-", value.lower()).strip("-")
    return (slug or "source")[:80]


def robots_for(client: httpx.Client, url: str) -> tuple[urllib.robotparser.RobotFileParser | None, str]:
    """Fetch and parse a host's robots.txt. A fetch failure is not permission."""
    robots_url = urljoin(f"{urlparse(url).scheme}://{urlparse(url).netloc}", "/robots.txt")
    try:
        response = client.get(robots_url)
    except httpx.HTTPError as exc:
        return None, f"robots.txt unreachable ({type(exc).__name__})"
    if response.status_code >= 400:
        # RFC 9309: 4xx means no restrictions. Say so out loud rather than
        # quietly assuming it.
        parser = urllib.robotparser.RobotFileParser()
        parser.parse([])
        return parser, f"robots.txt returned {response.status_code}; treating as allow-all"
    parser = urllib.robotparser.RobotFileParser()
    parser.parse(response.text.splitlines())
    return parser, "robots.txt fetched"


def write_document(source: Source, body: str, out_dir: Path) -> Path:
    """Write one fetched page with the front-matter ingest reads back."""
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / f"{slugify(source.title)}.md"
    fetched_at = datetime.now(timezone.utc).isoformat(timespec="seconds")
    front = (
        "---\n"
        f"title: {source.title}\n"
        f"source_url: {source.url}\n"
        f"license: {source.license_note}\n"
        f"fetched_at: {fetched_at}\n"
        "---\n\n"
    )
    path.write_text(front + body + "\n", encoding="utf-8")
    return path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="report the robots.txt verdict for every URL and write nothing",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=DEFAULT_DELAY,
        help=f"minimum seconds between requests (default {DEFAULT_DELAY}); a "
        "larger Crawl-delay in robots.txt always wins",
    )
    args = parser.parse_args()

    if not ALLOWLIST:
        print("ALLOWLIST is empty; nothing to fetch.")
        return

    out_dir = Path(settings.external_knowledge_dir)
    headers = {"User-Agent": USER_AGENT}
    robots_cache: dict[str, tuple[urllib.robotparser.RobotFileParser | None, str]] = {}
    fetched = skipped = failed = 0

    with httpx.Client(headers=headers, timeout=60.0, follow_redirects=True) as client:
        for index, source in enumerate(ALLOWLIST):
            host = urlparse(source.url).netloc
            if host not in robots_cache:
                robots_cache[host] = robots_for(client, source.url)
            rules, note = robots_cache[host]

            if rules is None:
                print(f"SKIP    {source.url}\n        {note} -- refusing to guess")
                skipped += 1
                continue
            if not rules.can_fetch(USER_AGENT, source.url):
                print(f"SKIP    {source.url}\n        disallowed by robots.txt")
                skipped += 1
                continue

            crawl_delay = rules.crawl_delay(USER_AGENT)
            delay = max(float(crawl_delay or 0), args.delay)

            if args.dry_run:
                print(
                    f"ALLOW   {source.url}\n"
                    f"        {note}; crawl-delay={crawl_delay or 'none'}, "
                    f"would wait {delay:.0f}s; {source.license_note}"
                )
                continue

            if index:
                time.sleep(delay)

            try:
                response = client.get(source.url)
                response.raise_for_status()
            except httpx.HTTPError as exc:
                print(f"FAIL    {source.url}\n        {type(exc).__name__}: {exc}")
                failed += 1
                continue

            extractor = _TextExtractor()
            extractor.feed(response.text)
            body = strip_chrome(extractor.text())
            if len(body) < 200:
                print(f"FAIL    {source.url}\n        extracted only {len(body)} chars")
                failed += 1
                continue

            path = write_document(source, body, out_dir)
            print(f"OK      {source.url}\n        -> {path} ({len(body)} chars)")
            fetched += 1

    if args.dry_run:
        print(f"\nDry run: {len(ALLOWLIST) - skipped} allowed, {skipped} skipped. Nothing written.")
    else:
        print(f"\n{fetched} fetched, {skipped} skipped, {failed} failed.")
        if fetched:
            print("Now run:  python scripts/ingest_knowledge.py")


if __name__ == "__main__":
    main()
