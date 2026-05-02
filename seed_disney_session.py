#!/usr/bin/env python3
"""Open the persistent Playwright profile so you can log in to Disney.

Run this once on the VPS whenever `/status` reports that the Disney browser
session needs attention. It uses the same profile directory as the worker.
"""

import os

from dotenv import load_dotenv

load_dotenv()


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
        print("Log in, then press Enter here to close and save the browser profile.")
        input()
        context.close()


if __name__ == "__main__":
    main()
