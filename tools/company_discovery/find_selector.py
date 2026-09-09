"""One-off research helper: given a careers page and a real job title known
to appear on it, find a CSS selector whose matched elements look like job
cards (each containing a link and distinct title text), for use as this
project's existing `job_selector` config field. Not part of the shipped
application; never imported by src/.
"""
from __future__ import annotations

import sys

from playwright.sync_api import sync_playwright

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/152.0.0.0 Safari/537.36"
)


def inspect(url: str, needle: str | None) -> None:
    with sync_playwright() as pw:
        browser = pw.chromium.launch(headless=True)
        context = browser.new_context(user_agent=USER_AGENT)
        page = context.new_page()
        page.goto(url, wait_until="domcontentloaded", timeout=30000)
        page.wait_for_timeout(2500)

        if needle:
            locator = page.get_by_text(needle, exact=False)
            count = locator.count()
            print(f"text match count for {needle!r}: {count}", file=sys.stderr)
            if count == 0:
                print("not found on rendered page", file=sys.stderr)
            for i in range(min(count, 3)):
                el = locator.nth(i)
                info = el.evaluate(
                    """
                    (node) => {
                        const path = [];
                        let cur = node;
                        for (let depth = 0; depth < 6 && cur; depth++) {
                            const cls = cur.className && typeof cur.className === 'string'
                                ? '.' + cur.className.trim().split(/\\s+/).join('.')
                                : '';
                            path.push(cur.tagName.toLowerCase() + cls);
                            cur = cur.parentElement;
                        }
                        return path.join(' < ');
                    }
                    """
                )
                print(f"  match {i}: {info}", file=sys.stderr)

        # Also report repeated-structure candidates: any class used by >= 5
        # elements that each contain a link, as a generic signal.
        candidates = page.evaluate(
            """
            () => {
                const counts = {};
                document.querySelectorAll('[class]').forEach((el) => {
                    if (!el.querySelector('a[href]') && el.tagName !== 'A') return;
                    el.className.split(/\\s+/).forEach((cls) => {
                        if (!cls) return;
                        counts[cls] = (counts[cls] || 0) + 1;
                    });
                });
                return Object.entries(counts)
                    .filter(([, n]) => n >= 5 && n <= 500)
                    .sort((a, b) => b[1] - a[1])
                    .slice(0, 15);
            }
            """
        )
        print("repeated classnames wrapping a link (count):", file=sys.stderr)
        for cls, n in candidates:
            print(f"  .{cls}: {n}", file=sys.stderr)

        browser.close()


if __name__ == "__main__":
    inspect(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
