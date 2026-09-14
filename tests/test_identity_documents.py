"""Structural checks for the split Agent Identity documents."""

from __future__ import annotations

import re
import unittest
from collections import Counter
from pathlib import Path
from urllib.parse import urldefrag, urlparse

REPO_ROOT = Path(__file__).resolve().parents[1]
SPEC_FILES = (
    "protocol.html",
    "agent-identity.html",
    "did-method-profiles.html",
    "did-wba.html",
)
SECTION_TOKEN_RE = re.compile(r"<section\b[^>]*>|</section\s*>", re.IGNORECASE)
ID_RE = re.compile(r'\sid=["\']([^"\']+)["\']', re.IGNORECASE)
HREF_RE = re.compile(r'href=["\']([^"\']+)["\']', re.IGNORECASE)
REQUIRED_PROTOCOL_ANCHORS = (
    "agent-identity",
    "agent-identity-overview",
    "agent-identity-design-principles",
    "did-wba-did-method-specification",
    "did-method-compatibility",
    "did-webvh-validation",
    "did-wba-cross-platform-http-authentication",
    "did-resolution",
    "native-did-web-compatibility",
)


def read_spec(name: str) -> str:
    return (REPO_ROOT / name).read_text(encoding="utf-8")


def collect_ids(html: str) -> list[str]:
    return ID_RE.findall(html)


def section_balance(html: str) -> int:
    depth = 0
    for token in SECTION_TOKEN_RE.finditer(html):
        raw = token.group(0).lower()
        depth += 1 if raw.startswith("<section") else -1
        if depth < 0:
            return depth
    return depth


class IdentityDocumentStructureTest(unittest.TestCase):
    def test_section_tags_are_balanced(self):
        for name in SPEC_FILES:
            with self.subTest(name=name):
                self.assertEqual(section_balance(read_spec(name)), 0)

    def test_html_ids_are_unique_within_each_file(self):
        for name in SPEC_FILES:
            with self.subTest(name=name):
                counts = Counter(collect_ids(read_spec(name)))
                duplicates = sorted(item for item, count in counts.items() if count > 1)
                self.assertEqual(duplicates, [])

    def test_local_links_resolve(self):
        for name in SPEC_FILES:
            html = read_spec(name)
            ids = set(collect_ids(html))
            for href in HREF_RE.findall(html):
                parsed = urlparse(href)
                if parsed.scheme in {"http", "https", "mailto"}:
                    continue
                path, fragment = urldefrag(href)
                with self.subTest(file=name, href=href):
                    if path:
                        target = (REPO_ROOT / path).resolve()
                        self.assertTrue(target.is_file(), f"missing file for {href}")
                        if fragment:
                            target_ids = set(collect_ids(target.read_text(encoding="utf-8")))
                            self.assertIn(fragment, target_ids)
                    elif fragment:
                        self.assertIn(fragment, ids)

    def test_protocol_keeps_migration_anchors(self):
        ids = set(collect_ids(read_spec("protocol.html")))
        missing = [anchor for anchor in REQUIRED_PROTOCOL_ANCHORS if anchor not in ids]
        self.assertEqual(missing, [])

    def test_companion_specs_are_complete_html_documents(self):
        for name in ("agent-identity.html", "did-method-profiles.html", "did-wba.html"):
            html = read_spec(name)
            with self.subTest(name=name):
                self.assertIn("<!doctype html>", html.lower())
                self.assertIn("respec-w3c", html)
                self.assertIn('<section id="abstract">', html)
                self.assertIn('<section id="sotd">', html)


if __name__ == "__main__":
    unittest.main()
