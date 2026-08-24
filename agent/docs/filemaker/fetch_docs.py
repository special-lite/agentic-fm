#!/usr/bin/env python3
"""
Fetch Claris FileMaker reference documentation as Markdown.

Claris publishes the entire help corpus in Markdown alongside the HTML,
indexed per the llms.txt convention:

    https://help.claris.com/llms.txt                      curated entry point
    https://help.claris.com/markdown/en/llms-full.txt      full page enumeration
    https://help.claris.com/markdown/en/<doc-set>/<slug>.md

This script reads that index and downloads the Markdown directly.  There is
no HTML scraping, no slug guessing, and no third-party dependency -- the
standard library is all that is required.

Usage
-----
    python3 fetch_docs.py                    # steps + functions + error codes
    python3 fetch_docs.py --steps            # script steps only
    python3 fetch_docs.py --functions        # functions only
    python3 fetch_docs.py --errors           # error codes only
    python3 fetch_docs.py --guides           # the default guide set (SQL, OData, APIs, ...)
    python3 fetch_docs.py --guides sql-reference odata-guide
    python3 fetch_docs.py --all              # everything above

    python3 fetch_docs.py --refresh          # re-fetch only pages Claris has changed
    python3 fetch_docs.py --force            # re-fetch everything
    python3 fetch_docs.py --prune            # drop pages Claris no longer lists
    python3 fetch_docs.py --keep-examples    # retain Example / Related topics sections
    python3 fetch_docs.py --locale ja        # non-English corpus
    python3 fetch_docs.py --guides --out ../other-repo/.claris-docs

Outputs
-------
    script-steps/<slug>.md
    functions/<category>/<slug>.md
    error-codes.md
    guides/<doc-set>/<slug>.md

Every saved file keeps a short provenance header (source URL, the Claris
``date_modified``, and ``topic_type``).  ``--refresh`` compares that stored
date against the index and re-downloads only what actually changed, so
keeping the corpus current costs a single index fetch plus the deltas.

Legal Notice
------------
The content fetched and stored by this script is sourced from the Claris
help site (https://help.claris.com) and is copyright (c) Claris International
Inc. All rights reserved.

The generated Markdown files are NOT part of this project's Apache 2.0
licensed source code and are intentionally excluded from version control
(see .gitignore).  You may run this script to generate a local copy for
your own personal, non-commercial use in accordance with the Claris
Website Terms of Use (https://claris.com/company/legal/terms).

Do not commit, redistribute, or publish the generated files.
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

# -- Constants ------------------------------------------------------------

HELP_HOST = "https://help.claris.com"
HERE = Path(__file__).resolve().parent

# Output roots, relative to HERE by default.  --out points them at another
# directory so a second repo can hold its own corpus without duplicating
# this script.
STEPS_OUT = HERE / "script-steps"
FUNCS_OUT = HERE / "functions"
GUIDES_OUT = HERE / "guides"
ERRORS_OUT = HERE / "error-codes.md"


def set_output_root(root: Path) -> None:
    """Re-point every output path at *root*."""
    global STEPS_OUT, FUNCS_OUT, GUIDES_OUT, ERRORS_OUT
    STEPS_OUT = root / "script-steps"
    FUNCS_OUT = root / "functions"
    GUIDES_OUT = root / "guides"
    ERRORS_OUT = root / "error-codes.md"

DELAY = 0.25  # seconds between HTTP requests
TIMEOUT = 30

# Category pages used to discover step and function reference topics.  These
# are only a *candidate* source -- the authoritative classification is the
# topic_type in each page's own front matter, so a conceptual page listed
# here (json-functions is prose, not a link table) still yields the right
# result and index pages filter themselves out.
STEP_CATS = [
    "control-script-steps",
    "navigation-script-steps",
    "editing-script-steps",
    "fields-script-steps",
    "records-script-steps",
    "found-sets-script-steps",
    "windows-script-steps",
    "files-script-steps",
    "accounts-script-steps",
    "artificial-intelligence-script-steps",
    "spelling-script-steps",
    "open-menu-item-script-steps",
    "miscellaneous-script-steps",
]

FUNC_CATS = [
    "text-functions",
    "text-formatting-functions",
    "number-functions",
    "date-functions",
    "time-functions",
    "timestamp-functions",
    "container-functions",
    "japanese-functions",
    "json-functions-category",
    "aggregate-functions",
    "repeating-functions",
    "financial-functions",
    "trigonometric-functions",
    "logical-functions",
    "artificial-intelligence-functions",
    "miscellaneous-functions",
    "get-functions",
    "design-functions",
    "mobile-functions",
]

# Guide doc-sets fetched by a bare --guides.  Any doc-set name that appears
# in the index may be passed explicitly instead.
DEFAULT_GUIDES = [
    "sql-reference",
    "odata-guide",
    "data-api-guide",
    "admin-api-guide",
    "security-guide",
    "pro-svg-grammar-for-button-icons",
    "developer-tool-guide",
    "app-upgrade-tool-guide",
]

# Folder name for category pages whose slug is not "<folder>-functions".
CAT_FOLDER = {"json-functions-category": "json"}

# topic_type values that mark an individual reference topic.
TYPE_STEP = "script-step-reference"
TYPE_FUNCTION = "function-reference"

# Section headings dropped unless --keep-examples (matched as prefix, folded).
SKIP_SECTIONS = ("example", "related topic", "see also")

# Front-matter keys carried through into the saved file.
KEEP_KEYS = ("title", "topic_type", "product", "version", "date_modified", "url")


# -- HTTP -----------------------------------------------------------------

def _get(url: str) -> str | None:
    """Fetch *url* as text.  Returns None on 404 / redirect-to-error."""
    time.sleep(DELAY)
    req = urllib.request.Request(url, headers={"User-Agent": "FileMaker-DocFetcher/2.0"})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        if exc.code == 404:
            return None
        raise
    # A missing Markdown page 302s to the marketing 404 page.
    if body.lstrip().startswith("<!DOCTYPE HTML") or body.lstrip().startswith("<html"):
        return None
    return body


# -- Index ----------------------------------------------------------------

_INDEX_LINE = re.compile(
    r"^- \[(?P<title>.*?)\]\("
    r"(?P<url>https://help\.claris\.com/markdown/(?P<locale>[a-z-]+)/"
    r"(?P<docset>[a-z0-9-]+)/(?P<slug>[a-z0-9._-]+)\.md)\)"
    r"(?:\s*\(modified:\s*(?P<modified>[^)]*)\))?"
)


def load_index(locale: str) -> dict[str, dict[str, dict]]:
    """Return {doc_set: {slug: {url, title, modified}}} from llms-full.txt."""
    url = f"{HELP_HOST}/markdown/{locale}/llms-full.txt"
    print(f"  Reading index {url} ... ", end="", flush=True)
    text = _get(url)
    if text is None:
        sys.exit(f"\nCould not read the documentation index at {url}")

    index: dict[str, dict[str, dict]] = {}
    for line in text.splitlines():
        m = _INDEX_LINE.match(line.strip())
        if not m:
            continue
        index.setdefault(m["docset"], {})[m["slug"]] = {
            "url": m["url"],
            "title": m["title"],
            "modified": (m["modified"] or "").strip(),
        }
    total = sum(len(v) for v in index.values())
    print(f"{total} pages across {len(index)} doc sets")
    return index


# -- Markdown handling ----------------------------------------------------

def split_front_matter(text: str) -> tuple[dict[str, str], str]:
    """Split a Claris Markdown page into (front-matter dict, body)."""
    if not text.startswith("---"):
        return {}, text
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    raw = text[3:end]
    body = text[end + 4:].lstrip("\n")
    front: dict[str, str] = {}
    for line in raw.splitlines():
        if ":" not in line:
            continue
        key, _, value = line.partition(":")
        front[key.strip()] = value.strip().strip('"')
    return front, body


def filter_sections(body: str, *, keep_examples: bool) -> str:
    """Drop Example / Related topics / See also sections from a page body."""
    if keep_examples:
        return body.strip()

    out: list[str] = []
    skipping = False
    for line in body.splitlines():
        heading = re.match(r"^(#{2,6})\s+(.*)$", line)
        if heading:
            name = heading.group(2).replace("\xa0", " ").strip().lower()
            name = re.sub(r"\s*\d+\s*$", "", name)  # "Example 2" -> "example"
            skipping = any(name.startswith(s) for s in SKIP_SECTIONS)
            if skipping:
                continue
        if not skipping:
            out.append(line)

    return re.sub(r"\n{3,}", "\n\n", "\n".join(out)).strip()


def render(front: dict[str, str], body: str, *, keep_examples: bool) -> str:
    """Rebuild a page with a trimmed provenance header."""
    header = [f"{k}: {front[k]}" for k in KEEP_KEYS if front.get(k)]
    text = filter_sections(body, keep_examples=keep_examples)
    if not header:
        return text + "\n"
    return "---\n" + "\n".join(header) + "\n---\n\n" + text + "\n"


def local_modified(path: Path) -> str | None:
    """Read the stored date_modified from an already-fetched page."""
    if not path.is_file():
        return None
    try:
        with path.open("r", encoding="utf-8") as fh:
            head = fh.read(1024)
    except OSError:
        return None
    m = re.search(r"^date_modified:\s*(.+)$", head, re.MULTILINE)
    return m.group(1).strip() if m else None


_ROW_LINK = re.compile(
    r"^\|\s*\[[^\]]+\]\(https://help\.claris\.com/[a-z-]+/pro-help/content/([a-z0-9._-]+)\.html"
)


def _table_row_slugs(body: str) -> list[str]:
    """Slugs listed as rows of a category page's link table, in order.

    Category pages present their members as a two-column Markdown table.
    Harvesting only those rows -- rather than every link on the page --
    keeps conceptual cross-references (the FileMaker Go help topics that
    older scrapes filed as "script steps") out of the corpus.
    """
    return [m.group(1) for line in body.splitlines() if (m := _ROW_LINK.match(line.strip()))]


def catalog_step_titles() -> set[str]:
    """Step names from the step catalog, used as a discovery safety net.

    A handful of real reference topics are absent from the category tables
    or carry a wrong topic_type in Claris's own front matter (Save Records
    as PDF, Set Dictionary).  Matching index *titles* against the catalog's
    step names catches them without guessing URL slugs.
    """
    catalog = HERE.parent.parent / "catalogs" / "step-catalog-en.json"
    if not catalog.is_file():
        return set()
    try:
        data = json.loads(catalog.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return set()
    steps = data.get("steps", data) if isinstance(data, dict) else data
    steps = steps.values() if isinstance(steps, dict) else steps
    return {normalize_title(s["name"]) for s in steps
            if isinstance(s, dict) and s.get("name")}


def normalize_title(name: str) -> str:
    """Fold a step name for comparison against a Claris page title.

    Claris titles differ from the catalog's step names in case ("Perform
    Script On Server"), in stray whitespace, and by a trailing platform
    suffix ("Speak (macOS)").  None of those should defeat a match.
    """
    return re.sub(r"\s*\([^)]*\)\s*$", "", name).strip().casefold()


# -- Fetch / save ---------------------------------------------------------

class Stats:
    def __init__(self) -> None:
        self.fetched = self.cached = 0
        self.missing: list[str] = []
        self.mislabelled: list[str] = []

    def line(self, label: str) -> str:
        out = f"  {label}: {self.fetched} fetched, {self.cached} unchanged"
        if self.mislabelled:
            out += f", {len(self.mislabelled)} with an unexpected topic_type"
        if self.missing:
            out += f", {len(self.missing)} unavailable"
        return out


def save_page(
    entry: dict,
    out_path: Path,
    stats: Stats,
    *,
    force: bool,
    refresh: bool,
    keep_examples: bool,
    expect_type: str | None = None,
) -> dict[str, str] | None:
    """Download one page and write it.  Returns its front matter, or None.

    Honours the cache: an existing file whose stored date_modified matches
    the index is left alone unless --force is given.
    """
    have = local_modified(out_path)
    if have is not None and not force:
        if not refresh or (entry["modified"] and have == entry["modified"]):
            stats.cached += 1
            return None

    text = _get(entry["url"])
    if text is None:
        stats.missing.append(entry["url"])
        return None

    front, body = split_front_matter(text)
    if expect_type and front.get("topic_type") != expect_type:
        # Claris's own front matter mislabels a few reference topics as
        # "conceptual".  Membership of a curated category table (or of the
        # step catalog) is the stronger signal, so note the mismatch and
        # keep the page rather than dropping it.
        stats.mislabelled.append(out_path.name)

    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(render(front, body, keep_examples=keep_examples), encoding="utf-8")
    stats.fetched += 1
    return front


def prune_dir(root: Path, keep: set[str]) -> None:
    """Delete generated pages under *root* that are no longer members.

    Earlier scrapes of the HTML help harvested every link on a category
    page, leaving unrelated topics behind in these folders.  The folders
    are generated and gitignored, so removing strays is safe.
    """
    if not root.is_dir():
        return
    removed = 0
    for path in sorted(root.rglob("*.md")):
        if str(path.relative_to(root)) not in keep:
            path.unlink()
            removed += 1
    for path in sorted(root.rglob("*"), reverse=True):
        if path.is_dir() and not any(path.iterdir()):
            path.rmdir()
    if removed:
        print(f"    pruned {removed} page(s) that are no longer listed")


def _discover(cats: list[str], pages: dict[str, dict]) -> dict[str, list[str]]:
    """Map each category slug to the reference slugs it links to."""
    found: dict[str, list[str]] = {}
    for cat in cats:
        entry = pages.get(cat)
        if entry is None:
            print(f"    {cat} -- not in index, skipped")
            continue
        text = _get(entry["url"])
        if text is None:
            print(f"    {cat} -- unavailable, skipped")
            continue
        _, body = split_front_matter(text)
        slugs = [s for s in dict.fromkeys(_table_row_slugs(body)) if s in pages and s not in cats]
        found[cat] = slugs
        print(f"    {cat}: {len(slugs)} candidates")
    return found


# -- Commands -------------------------------------------------------------

def fetch_steps(pages: dict[str, dict], stats: Stats, *, prune: bool = False, **kw) -> None:
    print("  Discovering script steps ...")
    discovered = _discover(STEP_CATS, pages)
    slugs = {s for v in discovered.values() for s in v}

    known = catalog_step_titles()
    if known:
        by_title = {slug: e for slug, e in pages.items()
                    if normalize_title(e["title"]) in known}
        extra = set(by_title) - slugs
        if extra:
            print(f"    step catalog: +{len(extra)} not listed on a category page")
        slugs |= set(by_title)

    print(f"\n  Checking {len(slugs)} candidate pages ...")
    for slug in sorted(slugs):
        save_page(pages[slug], STEPS_OUT / f"{slug}.md", stats,
                  expect_type=TYPE_STEP, **kw)
    if prune:
        prune_dir(STEPS_OUT, {f"{s}.md" for s in slugs})
    print(stats.line("Script steps"))


def fetch_functions(pages: dict[str, dict], stats: Stats, *, prune: bool = False, **kw) -> None:
    print("  Discovering functions ...")
    discovered = _discover(FUNC_CATS, pages)

    # First category to claim a slug owns its folder, so the ordering of
    # FUNC_CATS decides placement when a function is cross-linked.
    placement: dict[str, str] = {}
    for cat in FUNC_CATS:
        for slug in discovered.get(cat, []):
            placement.setdefault(slug, CAT_FOLDER.get(cat, cat.replace("-functions", "")))

    print(f"\n  Checking {len(placement)} candidate pages ...")
    for slug in sorted(placement):
        save_page(pages[slug], FUNCS_OUT / placement[slug] / f"{slug}.md", stats,
                  expect_type=TYPE_FUNCTION, **kw)
    if prune:
        prune_dir(FUNCS_OUT, {f"{placement[s]}/{s}.md" for s in placement})
    print(stats.line("Functions"))


def fetch_errors(pages: dict[str, dict], stats: Stats, **kw) -> None:
    entry = pages.get("error-codes")
    if entry is None:
        print("  error-codes not found in index")
        return
    kw = dict(kw, keep_examples=True)  # the page is one big table; keep it whole
    save_page(entry, ERRORS_OUT, stats, **kw)
    print(stats.line("Error codes"))


def fetch_guides(index: dict, doc_sets: list[str], stats: Stats, **kw) -> None:
    for doc_set in doc_sets:
        pages = index.get(doc_set)
        if not pages:
            print(f"  {doc_set} -- not in index, skipped")
            continue
        sub = Stats()
        print(f"  {doc_set}: {len(pages)} pages")
        for slug in sorted(pages):
            save_page(pages[slug], GUIDES_OUT / doc_set / f"{slug}.md", sub, **kw)
        print(sub.line(f"    {doc_set}"))
        stats.fetched += sub.fetched
        stats.cached += sub.cached
        stats.missing.extend(sub.missing)
    print(stats.line("Guides"))


# -- Main -----------------------------------------------------------------

def main() -> None:
    ap = argparse.ArgumentParser(
        description="Fetch Claris FileMaker reference documentation as Markdown",
    )
    ap.add_argument("--steps", action="store_true", help="Fetch script steps")
    ap.add_argument("--functions", action="store_true", help="Fetch functions")
    ap.add_argument("--errors", action="store_true", help="Fetch error codes")
    ap.add_argument(
        "--guides", nargs="*", metavar="DOC_SET",
        help=f"Fetch guide doc-sets (default: {', '.join(DEFAULT_GUIDES)})",
    )
    ap.add_argument("--all", action="store_true", help="Fetch everything, guides included")
    ap.add_argument("--locale", default="en", help="Documentation locale (default: en)")
    ap.add_argument("--out", metavar="DIR", type=Path,
                    help="Write the corpus under DIR instead of next to this script. "
                         "Use for a second repo that wants its own copy; make sure DIR "
                         "is gitignored there (the pages are copyright Claris).")
    ap.add_argument("--refresh", action="store_true",
                    help="Re-fetch pages whose Claris date_modified has changed")
    ap.add_argument("--force", action="store_true",
                    help="Re-download every page, changed or not")
    ap.add_argument("--prune", action="store_true",
                    help="Delete generated pages that are no longer listed by Claris")
    ap.add_argument("--keep-examples", action="store_true",
                    help="Keep Example / Related topics / See also sections")
    args = ap.parse_args()

    want_guides = args.all or args.guides is not None
    if not (args.steps or args.functions or args.errors or want_guides):
        args.steps = args.functions = args.errors = True

    if args.out:
        set_output_root(args.out.expanduser().resolve())
        print(f"  Output root: {STEPS_OUT.parent}")

    kw = dict(force=args.force, refresh=args.refresh, keep_examples=args.keep_examples)

    print("== Index ==")
    index = load_index(args.locale)
    pro_help = index.get("pro-help", {})
    if not pro_help and (args.all or args.steps or args.functions or args.errors):
        sys.exit("The index contains no pro-help pages; nothing to do.")
    print()

    if args.all or args.steps:
        print("== Script Steps ==")
        fetch_steps(pro_help, Stats(), prune=args.prune, **kw)
        print()

    if args.all or args.functions:
        print("== Functions ==")
        fetch_functions(pro_help, Stats(), prune=args.prune, **kw)
        print()

    if args.all or args.errors:
        print("== Error Codes ==")
        fetch_errors(pro_help, Stats(), **kw)
        print()

    if want_guides:
        doc_sets = args.guides if args.guides else DEFAULT_GUIDES
        print("== Guides ==")
        fetch_guides(index, doc_sets, Stats(), **kw)
        print()

    print("Done.")


if __name__ == "__main__":
    main()
