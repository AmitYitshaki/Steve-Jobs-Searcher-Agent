"""Tests for the reusable company-discovery relevance gate."""
from __future__ import annotations

import unittest

from tools.company_discovery.relevance_gate import CatalogRelevanceGate


class CatalogRelevanceGateTests(unittest.TestCase):
    """Keep future catalog expansion tied to objective role evidence."""

    def setUp(self) -> None:
        """Create one reusable gate per test."""

        self.gate = CatalogRelevanceGate()

    def test_passes_on_target_role_regardless_of_seniority(self) -> None:
        """Treat a senior target role as proof that the employer is relevant."""

        result = self.gate.evaluate([
            {"title": "Bookkeeper"},
            {"title": "Principal Security Researcher"},
        ])

        self.assertTrue(result.passed)
        self.assertEqual(
            result.matching_titles,
            ("Principal Security Researcher",),
        )

    def test_holds_company_with_only_non_target_roles(self) -> None:
        """Reject a clean ATS feed that contains no target-domain work."""

        result = self.gate.evaluate([
            {"title": "Bookkeeper"},
            {"title": "Jewelry Designer"},
            {"title": "Purchasing Buyer"},
        ])

        self.assertFalse(result.passed)
        self.assertEqual(result.matching_titles, ())


if __name__ == "__main__":
    unittest.main()
