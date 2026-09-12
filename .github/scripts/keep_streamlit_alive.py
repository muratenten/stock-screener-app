"""
Streamlit Community Cloud Auto Wake-Up & Keep-Alive Script
Uses Playwright to:
1. Open the Streamlit web application.
2. Check if the "This app has gone to sleep due to inactivity" screen is shown.
3. Automatically find and click "Yes, get this app back up!" button.
4. Wait for the app container to boot and establish active session.
"""

import sys
import time
from playwright.sync_api import sync_playwright

STREAMLIT_URL = "https://stock-screener-app-crrzltcyekqdt7uulhgpaa.streamlit.app/"

def main():
    print(f"🚀 [Streamlit Keep-Alive] Launching headless browser to check: {STREAMLIT_URL}")
    with sync_playwright() as p:
        # Launch browser with realistic user-agent
        browser = p.chromium.launch(
            headless=True,
            args=[
                "--no-sandbox",
                "--disable-setuid-sandbox",
                "--disable-dev-shm-usage",
                "--disable-gpu"
            ]
        )
        context = browser.new_context(
            user_agent="Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 800}
        )
        page = context.new_page()

        try:
            print(f"🌐 Navigating to {STREAMLIT_URL}...")
            response = page.goto(STREAMLIT_URL, wait_until="domcontentloaded", timeout=60000)
            status_code = response.status if response else "unknown"
            print(f"📡 Response status: {status_code}")

            # Wait a few seconds for Streamlit's React frontend to initialize
            time.sleep(8)

            page_content = page.content()
            page_title = page.title()
            print(f"📄 Page title: '{page_title}'")

            # Detect sleeping indicators
            is_sleeping = (
                "gone to sleep" in page_content
                or "sleeping" in page_content
                or "inactivity" in page_content
                or "back up" in page_content
            )

            wake_button = None
            candidate_selectors = [
                'button:has-text("Yes, get this app back up!")',
                'button:has-text("get this app back up")',
                'button:has-text("back up")',
                'button:has-text("Wake up")',
                'button:has-text("Yes,")',
            ]

            for sel in candidate_selectors:
                btn = page.locator(sel)
                if btn.count() > 0 and btn.first.is_visible():
                    wake_button = btn.first
                    break

            if wake_button:
                print("😴 [SLEEP DETECTED] App has gone to sleep. Wake-up button found!")
                btn_text = wake_button.inner_text()
                print(f"👉 Clicking wake-up button: '{btn_text}'...")
                wake_button.click()
                print("⏳ Clicked! Waiting 20 seconds for the app to wake up and rebuild...")
                time.sleep(20)
                print("🎉 Wake-up signal dispatched successfully!")
            elif is_sleeping:
                print("⚠️ Sleep text detected in page content, searching for clickable buttons...")
                buttons = page.locator("button").all()
                clicked = False
                for b in buttons:
                    text = b.inner_text().strip()
                    if any(w in text.lower() for w in ["yes", "wake", "back up", "get this"]):
                        print(f"👉 Clicking candidate button: '{text}'")
                        b.click()
                        clicked = True
                        time.sleep(15)
                        break
                if not clicked:
                    print("ℹ️ Could not find specific button, but page visited.")
            else:
                print("⚡ [ACTIVE] App is already awake, running, and active! No wake-up needed.")

            # Keep page open for another 10 seconds to maintain WebSocket connection
            time.sleep(10)
            print("✅ Keep-alive ping completed successfully.")

        except Exception as e:
            print(f"❌ Error during keep-alive execution: {e}")
            sys.exit(1)
        finally:
            context.close()
            browser.close()

if __name__ == "__main__":
    main()
