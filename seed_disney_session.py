#!/usr/bin/env python3
"""Open the persistent Playwright profile so you can log in to Disney.

Run this once on the VPS whenever `/status` reports that the Disney browser
session needs attention. It uses the same profile directory as the worker.
"""

import os

from dotenv import load_dotenv

load_dotenv()

TOKEN_COOKIE_NAME = "TPR-WDW-LBJS.WEB-PROD.token"


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
        print("Log in, then press Enter here to verify and save the browser profile.")
        input()
        page.goto("https://disneyworld.disney.go.com/dine-res/restaurant/space-220-lounge/", wait_until="domcontentloaded")
        page.wait_for_timeout(3000)
        cookies = context.cookies(["https://disneyworld.disney.go.com", "https://disney.go.com"])
        if any(cookie.get("name") == TOKEN_COOKIE_NAME for cookie in cookies):
            print("Disney auth cookie found. Browser profile is ready for the worker.")
        else:
            print("WARNING: Disney auth cookie was not found. The worker will still require login.")
        context.close()


if __name__ == "__main__":
    main()
