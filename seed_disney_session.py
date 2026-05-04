#!/usr/bin/env python3
"""Open the persistent Playwright profile so you can log in to Disney.

Run this once on the VPS whenever `/status` reports that the Disney browser
session needs attention. It uses the same profile directory as the worker.
"""

import os
import re

from dotenv import load_dotenv

load_dotenv()

TOKEN_COOKIE_NAME = "TPR-WDW-LBJS.WEB-PROD.token"


def _has_auth_cookie(context) -> bool:
    cookies = context.cookies(["https://disneyworld.disney.go.com", "https://disney.go.com"])
    return any(cookie.get("name") == TOKEN_COOKIE_NAME for cookie in cookies)


def _click_first(page, selectors) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() and locator.is_visible(timeout=1500):
                locator.click()
                return True
        except Exception:
            pass
    return False


def _fill_first(page, selectors, value) -> bool:
    for selector in selectors:
        locator = page.locator(selector).first
        try:
            if locator.count() and locator.is_visible(timeout=1500):
                locator.fill(value)
                return True
        except Exception:
            pass
    return False


def _attempt_credential_login(page) -> bool:
    email = os.environ.get("DISNEY_LOGIN_EMAIL", "").strip()
    password = os.environ.get("DISNEY_LOGIN_PASSWORD", "").strip()
    if not email or not password:
        return False

    print("Dedicated Disney credentials found in environment; attempting login.")
    page.wait_for_load_state("domcontentloaded")
    page.wait_for_timeout(2000)

    email_filled = _fill_first(page, [
        "input[type='email']",
        "input[name*='email' i]",
        "input[id*='email' i]",
        "input[name*='username' i]",
        "input[id*='username' i]",
        "input[type='text']",
    ], email)
    if not email_filled:
        print("Could not find a visible email field; manual login is required.")
        return False

    _click_first(page, [
        "button[type='submit']",
        "button:has-text('Continue')",
        "button:has-text('Next')",
        "button:has-text('Sign In')",
        "input[type='submit']",
    ])
    page.wait_for_timeout(3000)

    password_filled = _fill_first(page, [
        "input[type='password']",
        "input[name*='password' i]",
        "input[id*='password' i]",
    ], password)
    if not password_filled:
        print("Could not find a visible password field; manual login or challenge is required.")
        return False

    _click_first(page, [
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
    with sync_playwright() as p:
        context = p.chromium.launch_persistent_context(
            profile_dir,
            headless=False,
            args=["--no-sandbox"],
        )
        page = context.pages[0] if context.pages else context.new_page()
        page.goto("https://disneyworld.disney.go.com/login", wait_until="domcontentloaded")
        print("Disney login browser is open.")
        attempted_auto = _attempt_credential_login(page)
        if not attempted_auto or not _has_auth_cookie(context):
            print("Complete Disney login manually, then press Enter here to verify and save the browser profile.")
            input()
        page.goto("https://disneyworld.disney.go.com/dine-res/restaurant/space-220-lounge/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        if _has_auth_cookie(context):
            print("Disney auth cookie found. Browser profile is ready for the worker.")
        else:
            print("WARNING: Disney auth cookie was not found. The worker will still require login.")
        context.close()


if __name__ == "__main__":
    main()
