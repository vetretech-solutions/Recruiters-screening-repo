"""Optional LinkedIn browser posting fallback (OAuth API is preferred)."""

import json
import os
from dataclasses import dataclass

SESSION_PREFIX = "linkedin_session:"


@dataclass
class LinkedInLoginResult:
    success: bool
    message: str
    session_token: str | None = None
    account_name: str | None = None
    profile_url: str | None = None


def is_browser_session(access_token: str | None) -> bool:
    return bool(access_token and access_token.startswith(SESSION_PREFIX))


def pack_session(cookies: list) -> str:
    return SESSION_PREFIX + json.dumps(cookies)


def unpack_session(access_token: str) -> list:
    return json.loads(access_token[len(SESSION_PREFIX) :])


def _browser_context(playwright):
    headless = os.getenv("LINKEDIN_BROWSER_HEADLESS", "true").lower() != "false"
    browser = playwright.chromium.launch(
        headless=headless,
        args=["--disable-blink-features=AutomationControlled"],
    )
    context = browser.new_context(
        user_agent=(
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        ),
        viewport={"width": 1280, "height": 800},
    )
    return browser, context


def post_to_linkedin_feed(session_token: str, text: str) -> tuple[str | None, str]:
    """Browser fallback when OAuth API posting is unavailable."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        return None, "Playwright not installed on server."

    cookies = unpack_session(session_token)
    try:
        with sync_playwright() as playwright:
            browser, context = _browser_context(playwright)
            context.add_cookies(cookies)
            page = context.new_page()
            page.goto("https://www.linkedin.com/feed/", wait_until="networkidle", timeout=45000)

            if "login" in page.url.lower():
                browser.close()
                return None, "LinkedIn session expired. Disconnect and use Sign in with LinkedIn."

            share_selectors = [
                ".share-box-feed-entry__trigger",
                "button.share-box-feed-entry__trigger",
                "div.share-box-feed-entry__closed-share-box button",
                "button:has-text('Start a post')",
            ]
            for selector in share_selectors:
                try:
                    loc = page.locator(selector).first
                    if loc.count() and loc.is_visible(timeout=3000):
                        loc.click()
                        break
                except Exception:
                    continue
            else:
                browser.close()
                return None, "Could not open LinkedIn share box. Use Sign in with LinkedIn (OAuth) instead."

            page.wait_for_timeout(2000)
            editor = page.locator("div.ql-editor, div[contenteditable='true'][role='textbox']").first
            editor.click(timeout=10000)
            editor.fill(text)

            post_btn = page.locator(
                "button.share-actions__primary-action, button.artdeco-button--primary:has-text('Post')"
            ).first
            post_btn.click(timeout=10000)
            page.wait_for_timeout(4000)
            post_url = page.url
            browser.close()
            return post_url, "Job post published on your LinkedIn feed."
    except Exception as exc:
        return None, f"LinkedIn browser posting failed: {exc}. Use Sign in with LinkedIn (OAuth)."
