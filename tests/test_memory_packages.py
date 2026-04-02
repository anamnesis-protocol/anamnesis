"""
Tests for memory_packages.py — metadata extraction, keyword scoring, relevance query.

Pure Python — no Hedera network calls.
"""

import pytest
from pathlib import Path
from unittest.mock import patch, MagicMock

from src.memory_packages import (
extract_date_from_name,
extract_keywords,
extract_description,
build_metadata,
query_packages,
PackageMetadata,
)


# ---------------------------------------------------------------------------
# extract_date_from_name
# ---------------------------------------------------------------------------

class TestExtractDateFromName:
def test_extracts_iso_date(self):
assert extract_date_from_name("session_2026-03-16_vault_build") == "2026-03-16"

def test_extracts_date_from_research_filename(self):
assert extract_date_from_name("2026-03-11_patent-application") == "2026-03-11"

def test_no_date_returns_today(self):
from datetime import date
result = extract_date_from_name("Anygrations")
assert result == str(date.today())

def test_multiple_dates_returns_first(self):
result = extract_date_from_name("2026-01-01_to_2026-03-16_report")
assert result == "2026-01-01"


# ---------------------------------------------------------------------------
# extract_keywords
# ---------------------------------------------------------------------------

class TestExtractKeywords:
def test_returns_list(self):
result = extract_keywords("session_2026-03-16_vault", "# Vault Build\n\nContent here.")
assert isinstance(result, list)

def test_max_keywords_respected(self):
result = extract_keywords("a_b_c_d_e_f_g_h", "# Head\n\nword " * 50, max_keywords=5)
assert len(result) <= 5

def test_extracts_from_filename(self):
result = extract_keywords("anygrations_business_proposal", "# Doc\n\nContent.")
assert "anygrations" in result or "business" in result

def test_filters_short_words(self):
result = extract_keywords("a_bc_def", "# Title\n\n")
# 'a', 'bc' are too short; 'def' is exactly 3 chars — filtered
assert "a" not in result
assert "bc" not in result

def test_deduplicates(self):
result = extract_keywords(
"patent_patent_patent",
"# Patent Application\n\nPatent details patent.",
)
assert result.count("patent") <= 1

def test_extracts_from_heading(self):
content = "# Sovereign AI Context\n\nSome body text."
result = extract_keywords("filename", content)
assert "sovereign" in result or "context" in result


# ---------------------------------------------------------------------------
# extract_description
# ---------------------------------------------------------------------------

class TestExtractDescription:
def test_returns_first_non_heading_line(self):
content = "# Title\n\nThis is the description.\n\nMore content."
result = extract_description("filename", content)
assert result == "This is the description."

def test_skips_heading_lines(self):
content = "# H1\n## H2\n\nActual description here.\n"
result = extract_description("filename", content)
assert result == "Actual description here."

def test_skips_horizontal_rules(self):
content = "---\n# Title\n---\n\nReal description.\n"
result = extract_description("filename", content)
assert result == "Real description."

def test_truncates_to_120_chars(self):
long_line = "A" * 200
content = f"# Title\n\n{long_line}\n"
result = extract_description("filename", content)
assert len(result) <= 120

def test_fallback_to_filename(self):
content = "# \n\n \n\n"
result = extract_description("my_project_name", content)
assert "my" in result.lower() or "project" in result.lower() or "name" in result.lower()


# ---------------------------------------------------------------------------
# query_packages — relevance scoring
# ---------------------------------------------------------------------------

def _make_pkg(name, category, keywords, description="", date="2026-03-16", size=1000):
return PackageMetadata(
name=name,
category=category,
description=description,
keywords=keywords,
date=date,
size=size,
file_id=f"0.0.9{abs(hash(name)) % 99999:05d}",
)


class TestQueryPackages:
def setup_method(self):
self.packages = [
_make_pkg(
"session_2026-03-16_sovereign_patent",
"sessions",
["sovereign", "patent", "hedera", "poc"],
"Session: Sovereign AI patent PoC complete",
),
_make_pkg(
"Anygrations",
"projects",
["anygrations", "edtech", "integration", "mulesoft"],
"EdTech integration service for SMBs",
),
_make_pkg(
"Market_Research",
"research",
["market", "research", "edtech", "analysis"],
"Market research for EdTech integration tools",
),
_make_pkg(
"Comic_Arbitrage_Tool",
"projects",
["comic", "arbitrage", "grading", "cgc"],
"Comic book arbitrage and grading tool",
),
]

def test_returns_most_relevant_first(self):
results = query_packages("hedera patent", self.packages)
assert results[0][1].name == "session_2026-03-16_sovereign_patent"

def test_score_is_between_0_and_1(self):
results = query_packages("anygrations integration", self.packages)
for score, _ in results:
assert 0.0 <= score <= 1.0

def test_top_n_limits_results(self):
results = query_packages("edtech", self.packages, top_n=2)
assert len(results) <= 2

def test_no_match_returns_empty(self):
results = query_packages("xyzzy quantum blockchain llm", self.packages)
assert results == []

def test_threshold_filters_low_scores(self):
# High threshold — only perfect matches pass
results = query_packages("patent", self.packages, threshold=0.99)
# "patent" is one of two query tokens? No, it's one token. Score = overlap/len(query)
# Single-word query: score is 1.0 if matched, else 0
for score, _ in results:
assert score >= 0.99

def test_empty_query_returns_empty(self):
results = query_packages("", self.packages)
assert results == []

def test_numeric_only_query_returns_empty(self):
results = query_packages("123 456", self.packages)
assert results == []

def test_category_isolation(self):
"""Sessions query should score higher on session packages."""
session_results = query_packages(
"sovereign patent hedera poc",
[p for p in self.packages if p.category == "sessions"],
)
assert len(session_results) > 0
assert session_results[0][1].category == "sessions"

def test_full_match_scores_1(self):
"""If all query terms match, score should be 1.0."""
pkg = _make_pkg("test", "projects", ["hedera", "patent"], "Hedera patent project")
results = query_packages("hedera patent", [pkg])
assert len(results) == 1
assert results[0][0] == 1.0

def test_partial_match_scores_less_than_1(self):
pkg = _make_pkg("test", "projects", ["hedera"], "Hedera project")
results = query_packages("hedera patent", [pkg])
assert len(results) == 1
assert results[0][0] < 1.0

def test_results_sorted_descending(self):
results = query_packages("edtech integration market research", self.packages)
scores = [s for s, _ in results]
assert scores == sorted(scores, reverse=True)
