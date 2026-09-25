import asyncio
import unittest
from playwright.async_api import async_playwright


class TestBrowserAutomation(unittest.IsolatedAsyncioTestCase):
    async def test_chrome_lifecycle(self):
        async with async_playwright() as p:
            browser = await p.chromium.launch(channel="chrome", headless=True)
            self.assertIsNotNone(browser)
            page = await browser.new_page()
            await page.set_content("<html><body><h1 id='title'>OpenHands Nexus</h1><input id='inp' type='text' /></body></html>")
            
            title_text = await page.inner_text("#title")
            self.assertEqual(title_text, "OpenHands Nexus")
            
            await page.fill("#inp", "Hello Colab")
            val = await page.input_value("#inp")
            self.assertEqual(val, "Hello Colab")
            
            eval_res = await page.evaluate("1 + 1")
            self.assertEqual(eval_res, 2)
            
            await browser.close()


if __name__ == "__main__":
    unittest.main()
