"""Location validation for scraped job titles and URLs."""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Iterable
from urllib.parse import parse_qsl, unquote_plus, urlsplit

BLOCKED_LOCATIONS = frozenset({
    "Argentina",
    "Australia",
    "Barcelona",
    "Berlin",
    "Bogota",
    "Brazil",
    "Bucharest",
    "Budapest",
    "Buenos Aires",
    "Canada",
    "Chile",
    "China",
    "Copenhagen",
    "Dublin",
    "France",
    "Germany",
    "Hungary",
    "India",
    "Ireland",
    "Japan",
    "Krakow",
    "Lisbon",
    "London",
    "Madrid",
    "Manila",
    "Melbourne",
    "Mexico",
    "Mexico City",
    "Milan",
    "Munich",
    "Netherlands",
    "New York",
    "Paris",
    "PH",
    "Philippines",
    "Poland",
    "Prague",
    "Remote - US",
    "Romania",
    "San Francisco",
    "Santiago",
    "Sao Paulo",
    "Seattle",
    "Seoul",
    "Shanghai",
    "Singapore",
    "Spain",
    "Stockholm",
    "Sydney",
    "Taipei",
    "Tokyo",
    "Toronto",
    "UK",
    "United Kingdom",
    "United States",
    "US",
    "USA",
    "Vancouver",
    "Vienna",
    "Warsaw",
    "Zurich",
})

ALLOWED_LOCATIONS = frozenset({
    "Beer Sheva",
    "Beersheba",
    "Bnei Brak",
    "Caesarea",
    "Haifa",
    "Herzliya",
    "Hod Hasharon",
    "IL",
    "Israel",
    "Jerusalem",
    "Kfar Saba",
    "Lod",
    "Modiin",
    "Netanya",
    "Petah Tikva",
    "Ra'anana",
    "Raanana",
    "Ramat Hahayal",
    "Ramat Gan",
    "Rehovot",
    "Tel Aviv",
    "Tel-Aviv",
    "Yavne",
    "Yokneam",
})


@dataclass(frozen=True)
class LocationDecision:
    """Describe whether a job passed geographic validation."""

    allowed: bool
    reason: str = ""
    matched_location: str | None = None
    source: str | None = None


class LocationFilter:
    """Reject foreign jobs using safe title and URL location matching."""

    LOCATION_QUERY_KEYWORDS = (
        "country",
        "geo",
        "location",
        "office",
        "region",
    )
    SEPARATOR_PATTERN = re.compile(r"[-_/.,:;|?&=+()\[\]{}]+")
    WHITESPACE_PATTERN = re.compile(r"\s+")

    def __init__(
        self,
        blocked_locations: Iterable[str] = BLOCKED_LOCATIONS,
        allowed_locations: Iterable[str] = ALLOWED_LOCATIONS,
        strict_mode: bool = False,
    ) -> None:
        """Build reusable patterns and configure optional whitelist mode."""

        self.strict_mode = strict_mode
        self._blocked_patterns, self._blocked_acronyms = (
            self._compile_locations(blocked_locations)
        )
        self._allowed_patterns, self._allowed_acronyms = (
            self._compile_locations(allowed_locations)
        )

    def evaluate(self, job_title: str, job_url: str) -> LocationDecision:
        """Validate title and URL, returning a rejection reason when blocked."""

        sources = (("title", job_title), ("url", job_url))
        for source, value in sources:
            matched_location = self._find_match(
                value=value,
                source=source,
                patterns=self._blocked_patterns,
                acronyms=self._blocked_acronyms,
            )
            if matched_location is not None:
                return LocationDecision(
                    allowed=False,
                    reason="blocked foreign location",
                    matched_location=matched_location,
                    source=source,
                )

        if not self.strict_mode:
            return LocationDecision(allowed=True)

        for source, value in sources:
            matched_location = self._find_match(
                value=value,
                source=source,
                patterns=self._allowed_patterns,
                acronyms=self._allowed_acronyms,
            )
            if matched_location is not None:
                return LocationDecision(
                    allowed=True,
                    matched_location=matched_location,
                    source=source,
                )

        return LocationDecision(
            allowed=False,
            reason="strict mode requires a known Israeli location",
        )

    def _compile_locations(
        self,
        locations: Iterable[str],
    ) -> tuple[tuple[tuple[str, re.Pattern[str]], ...], frozenset[str]]:
        """Compile phrases and isolate two-letter location acronyms."""

        patterns: list[tuple[str, re.Pattern[str]]] = []
        acronyms: set[str] = set()
        unique_locations = {
            location.strip()
            for location in locations
            if isinstance(location, str) and location.strip()
        }

        for location in sorted(
            unique_locations,
            key=lambda value: (-len(value), value),
        ):
            if len(location) == 2 and location.isupper():
                acronyms.add(location)
                continue

            normalized = self._normalize(location)
            escaped = re.escape(normalized).replace(r"\ ", r"\s+")
            patterns.append(
                (
                    location,
                    re.compile(rf"(?<!\w){escaped}(?!\w)"),
                )
            )

        return tuple(patterns), frozenset(acronyms)

    def _find_match(
        self,
        value: str,
        source: str,
        patterns: tuple[tuple[str, re.Pattern[str]], ...],
        acronyms: frozenset[str],
    ) -> str | None:
        """Return the first safely matched location in one source value."""

        if not isinstance(value, str) or not value:
            return None

        normalized = self._normalize(value)
        for location, pattern in patterns:
            if pattern.search(normalized):
                return location

        for acronym in acronyms:
            if self._matches_acronym(value, source, acronym):
                return acronym
        return None

    def _normalize(self, value: str) -> str:
        """Decode URLs and normalize separators for phrase matching."""

        decoded = unquote_plus(value).casefold()
        separated = self.SEPARATOR_PATTERN.sub(" ", decoded)
        return self.WHITESPACE_PATTERN.sub(" ", separated).strip()

    @classmethod
    def _matches_acronym(
        cls,
        value: str,
        source: str,
        acronym: str,
    ) -> bool:
        """Match short codes without treating ordinary words as locations."""

        decoded = unquote_plus(value)
        if source == "title":
            pattern = rf"(?<![A-Za-z]){re.escape(acronym)}(?![A-Za-z])"
            return re.search(pattern, decoded) is not None

        url_parts = urlsplit(value)
        path_segments = {
            unquote_plus(segment).casefold()
            for segment in url_parts.path.split("/")
            if segment
        }
        if acronym.casefold() in path_segments:
            return True

        for key, query_value in parse_qsl(
            url_parts.query,
            keep_blank_values=True,
        ):
            is_location_key = any(
                keyword in key.casefold()
                for keyword in cls.LOCATION_QUERY_KEYWORDS
            )
            if (
                is_location_key
                and query_value.strip().casefold() == acronym.casefold()
            ):
                return True
        return False
