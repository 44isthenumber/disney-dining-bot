#!/usr/bin/env python3
"""Open the persistent Playwright profile so you can log in to Disney.

Run this once on the VPS whenever `/status` reports that the Disney browser
session needs attention. It uses the same profile directory as the worker.

Manual completion (MFA, CAPTCHA): run with a TTY so you can press Enter after
logging in, for example:

  ssh -t -i ~/.ssh/disney_dining_vps root@HOST \\
    'cd /opt/disney-dining-bot && . .venv/bin/activate && DISNEY_HEADLESS=false xvfb-run -a python3 seed_disney_session.py'
"""

import os
import re
import sys
from typing import Optional

from dotenv import load_dotenv

load_dotenv()

TOKEN_COOKIE_NAME = "TPR-WDW-LBJS.WEB-PROD.token"


def _goto_with_retries(
    page,
    url: str,
    *,
    attempts: int = 3,
    wait_until: str = "domcontentloaded",
    timeout: int = 90_000,
) -> None:
    """Disney occasionally fails with net::ERR_HTTP2_PROTOCOL_ERROR; retry quietly."""
    last_exc: Optional[BaseException] = None
    for attempt in range(1, attempts + 1):
        try:
            page.goto(url, wait_until=wait_until, timeout=timeout)
            return
        except Exception as exc:
            last_exc = exc
            if attempt >= attempts:
                raise
            delay_ms = 1500 * attempt
            print(f"[seed] Navigation attempt {attempt}/{attempts} failed ({exc!r}); waiting {delay_ms}ms…")
            page.wait_for_timeout(delay_ms)
    if last_exc:
        raise last_exc


def _has_auth_cookie(context) -> bool:
    cookies = context.cookies(["https://disneyworld.disney.go.com", "https://disney.go.com"])
    return any(cookie.get("name") == TOKEN_COOKIE_NAME for cookie in cookies)


def _fill_first_any_frame(page, selectors, value, timeout_ms: int = 12000) -> bool:
    """Disney often renders email/password inside cross-origin iframes."""
    for frame in page.frames:
        for selector in selectors:
            loc = frame.locator(selector).first
            try:
                loc.wait_for(state="visible", timeout=timeout_ms)
                loc.fill(value, timeout=timeout_ms)
                return True
            except Exception:
                continue
    return False


def _click_first_any_frame(page, selectors, timeout_ms: int = 4000) -> bool:
    for frame in page.frames:
        for selector in selectors:
            loc = frame.locator(selector).first
            try:
                loc.wait_for(state="visible", timeout=timeout_ms)
                loc.click(timeout=timeout_ms)
                return True
            except Exception:
                continue
    return False


def _dismiss_common_overlays(page) -> None:
    _click_first_any_frame(page, [
        "button:has-text('Accept All')",
        "button:has-text('Accept')",
        "button[id*='accept' i]",
        "#onetrust-accept-btn-handler",
        "button:has-text('Continue')",
    ])
    page.wait_for_timeout(800)


def _attempt_credential_login(page) -> bool:
    email = os.environ.get("DISNEY_LOGIN_EMAIL", "").strip()
    password = os.environ.get("DISNEY_LOGIN_PASSWORD", "").strip()
    if not email or not password:
        return False

    print("Dedicated Disney credentials found in environment; attempting login.")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2500)
    try:
        page.wait_for_selector("iframe", timeout=15000)
    except Exception:
        pass
    _dismiss_common_overlays(page)

    email_selectors = [
        "input[type='email']",
        "input[autocomplete='email']",
        "input[autocomplete='username']",
        "input[name*='email' i]",
        "input[id*='email' i]",
        "input[name*='username' i]",
        "input[id*='username' i]",
        "input[type='text']",
        "input[inputmode='email']",
    ]

    email_filled = _fill_first_any_frame(page, email_selectors, email)
    if not email_filled:
        _click_first_any_frame(page, [
            "a[href*='login' i]",
            "button:has-text('Sign In')",
            "text=Sign In",
            "[data-testid*='sign-in' i]",
        ])
        page.wait_for_timeout(4000)
        try:
            page.wait_for_selector("iframe", timeout=12000)
        except Exception:
            pass
        _dismiss_common_overlays(page)
        email_filled = _fill_first_any_frame(page, email_selectors, email)
    if not email_filled:
        print("Could not find a visible email field; manual login is required.")
        return False

    _click_first_any_frame(page, [
        "button[type='submit']",
        "button:has-text('Continue')",
        "button:has-text('Next')",
        "button:has-text('Sign In')",
        "input[type='submit']",
    ])
    page.wait_for_timeout(4000)

    password_filled = _fill_first_any_frame(page, [
        "input[type='password']",
        "input[name*='password' i]",
        "input[id*='password' i]",
    ], password)
    if not password_filled:
        print("Could not find a visible password field; manual login or challenge is required.")
        return False

    _click_first_any_frame(page, [
        "button[type='submit']",
        "button:has-text('Sign In')",
        "button:has-text('Log In')",
        "button:has-text('Continue')",
        "input[type='submit']",
    ])
    page.wait_for_timeout(8000)

    body_text = ""
    try:
        body_text = page.locator("body").inner_text(timeout=3000)
    except Exception:
        pass
    if re.search(r"(verification|captcha|passcode|security code|two-step|2-step)", body_text, re.I):
        print("Disney requested an additional verification step; manual completion is required.")
        return False
    return True


def main() -> None:
    from playwright.sync_api import sync_playwright

    profile_dir = os.environ.get("DISNEY_BROWSER_PROFILE_DIR", ".browser-profile")
    headless = os.environ.get("DISNEY_HEADLESS", "false").strip().lower() in (
        "1", "true", "yes", "on",
    )
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            profile_dir,
            headless=headless,
            args=["--no-sandbox"],
        )
        page = context.pages[0] if context.pages else context.new_page()

        # Navigate to login page with retries
        _goto_with_retries(
            page,
            "https://disneyworld.disney.go.com/login",
            wait_until="domcontentloaded",
            timeout=90000,
        )
        print("Disney login browser is open.")
        _dismiss_common_overlays(page)

        # === Step 1: Try automatic credential login ===
        auto_success = False
        for attempt in range(1, 4):
            if _attempt_credential_login(page) and _has_auth_cookie(context):
                auto_success = True
                break
            print(f"[seed] Auto-login attempt {attempt}/3 did not yield valid cookie.")
            if attempt < 3:
                delay = 8 * attempt
                print(f"[seed] Waiting {delay}s before retry...")
                page.wait_for_timeout(delay * 1000)

        if auto_success:
            print("[seed] Automatic login succeeded with valid cookie.")
        else:
            # === Step 2: Manual login fallback ===
            if not headless:
                print("Automatic login failed or additional verification required.")
                print("Complete Disney login manually, then press Enter here to verify and save the browser profile.")
                try:
                    input()
                except EOFError:
                    print("Non-interactive session (no TTY); skipping manual wait.")
            else:
                print("[seed] Headless mode and auto-login failed. Cannot proceed.")

        # === Step 3: Final validation ===
        _goto_with_retries(
            page,
            "https://disneyworld.disney.go.com/dine-res/restaurant/space-220-lounge/",
            wait_until="domcontentloaded",
            timeout=90000,
        )
        page.wait_for_timeout(3000)

        has_cookie = _has_auth_cookie(context)
        if has_cookie:
            print("SUCCESS: Disney auth cookie found. Browser profile is ready for the worker.")
            context.close()
            sys.exit(0)
        else:
            print("WARNING: Disney auth cookie was not found after login attempts.")
            context.close()
            sys.exit(1)


if __name__ == "__main__":
    main()
