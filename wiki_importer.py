#!/usr/bin/env python3
"""
Fetch selected Wikipedia pages, preserve their structure in a Markdown‑friendly
format, and concatenate everything into a single Markdown document.

Changes vs. previous version
----------------------------
* Each article now begins with an H1 heading (`# <Page Title>`), providing a
clear top‑level title before the article contents.
* Horizontal rule separator (`---`) still delimits articles visually.

Dependencies
------------
  pip install wikipedia

Configuration
-------------
  PAGES : list[str]
      Wikipedia page titles to download.
  OUTPUT_FILE : str
      Destination Markdown file name.
  SEPARATOR : str
      Markdown fragment placed between pages (default: horizontal rule).

Conversion rules
----------------
* Article title becomes `# <Title>` (heading level 1).
* Section headings like ``== History ==`` become Markdown ``## History``.
* Deeper headings (``===`` or ``====``) map to ``###``/``####`` …
* Unordered list markers ``*`` → ``-``  ; ordered list markers ``#`` → ``1.``.
* Reference brackets ``[12]`` and ``[citation needed]`` are dropped.
* Excess blank lines are collapsed to a maximum of one.
"""

from __future__ import annotations

import re
from pathlib import Path
from typing import List

import wikipedia  # third‑party

# ---------------------------------------------------------------------------
# Configuration — edit these constants if you want different pages/filename
# ---------------------------------------------------------------------------
PAGES: List[str] = [
  "Whisky",
  "Scotch Whisky",
]

OUTPUT_FILE: str = "background_knowledge.md"

# Markdown horizontal rule with surrounding spacing
SEPARATOR: str = "\n\n---\n\n"

# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------

def _convert_headings(text: str) -> str:
  """Convert MediaWiki section headings to Markdown (#)."""

  def repl(match: re.Match[str]) -> str:
      equals = match.group(1)
      level = len(equals) // 2  # '==' → 1, '====' → 2 …
      title = match.group(2).strip()
      # Markdown levels start at #; offset +1 so '==' becomes '##'
      return f"{'#' * (level + 1)} {title}"

  return re.sub(r"^(={2,6})\s*(.+?)\s*\1$", repl, text, flags=re.MULTILINE)


def _convert_lists(text: str) -> str:
  """Convert wiki list bullets to Markdown style."""
  text = re.sub(r"^\*\s+", "- ", text, flags=re.MULTILINE)
  text = re.sub(r"^#\s+", "1. ", text, flags=re.MULTILINE)
  return text


def sanitize(text: str) -> str:
  """Return article text with minimal cleaning but preserved structure."""
  # Drop citation/reference brackets entirely
  text = re.sub(r"\[[^\]]+\]", "", text)
  # Headings and lists → Markdown
  text = _convert_headings(text)
  text = _convert_lists(text)
  # Trim trailing whitespace on each line
  text = re.sub(r"[ \t]+$", "", text, flags=re.MULTILINE)
  # Collapse runs of >2 blank lines to exactly one
  text = re.sub(r"\n{3,}", "\n\n", text)
  return text.strip()


def fetch_page(title: str) -> str:
  """Download *title* from Wikipedia and return its sanitized Markdown."""
  try:
      page = wikipedia.page(title, auto_suggest=False)
      raw = page.content
  except wikipedia.DisambiguationError as err:
      alt = err.options[0]
      print(f"[warn] '{title}' ambiguous; falling back to '{alt}'.")
      raw = wikipedia.page(alt, auto_suggest=False).content
  except wikipedia.PageError:
      print(f"[warn] Page '{title}' not found — skipping.")
      return ""
  return sanitize(raw)


# ---------------------------------------------------------------------------
# Main routine
# ---------------------------------------------------------------------------

def main() -> None:
  wikipedia.set_lang("en")  # guarantee English content

  parts: List[str] = []
  for title in PAGES:
      print(f"Fetching '{title}' …")
      cleaned = fetch_page(title)
      if cleaned:
          # prepend H1 heading for the article title
          article_block = f"# {title}\n\n{cleaned}"
          parts.append(article_block)

  combined = SEPARATOR.join(parts)
  Path(OUTPUT_FILE).write_text(combined, encoding="utf-8")

  print(
      f"Saved {len(parts)} article(s) — {len(combined):,} characters → '{OUTPUT_FILE}'",
  )


if __name__ == "__main__":
  main()
