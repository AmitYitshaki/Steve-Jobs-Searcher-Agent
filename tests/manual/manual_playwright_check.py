"""Manual interactive Playwright check; excluded from test discovery."""

from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright


def run_microsoft_scraping_check() -> None:
    """Open a real browser and save diagnostic Microsoft careers HTML."""

    url = "https://jobs.careers.microsoft.com/global/en/search?q=Student&lc=Israel"
    
    print("🚀 Launching an automated browser...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print("🌐 Navigating to the Microsoft careers site...")
        page.goto(url)
        
        print("⏳ Giving the site 8 seconds to load all jobs...")
        page.wait_for_timeout(8000) # Fixed, conservative wait.
        
        html_content = page.content()
        browser.close()
        
    print("✅ HTML captured. Looking for jobs...")
    
    # Save a copy of the HTML in case it needs manual inspection.
    with open("debug_microsoft.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    
    soup = BeautifulSoup(html_content, 'lxml')
    
    # Heuristic: collect any heading (h2/h3) or link (a) with job-like text.
    found_jobs = []
    
    # Scan every div, a, h2 and h3 element.
    for tag in soup.find_all(['div', 'a', 'h2', 'h3']):
        text = tag.text.strip()
        # Keep text of plausible job-title length that contains a keyword.
        if 10 < len(text) < 100 and ("Student" in text or "Intern" in text or "Engineer" in text):
            if text not in found_jobs:
                found_jobs.append(text)
    
    if not found_jobs:
        print("❌ Could not extract job text automatically. Inspect debug_microsoft.html.")
    else:
        print(f"\n🎉 Found {len(found_jobs)} potential jobs:")
        for idx, job in enumerate(found_jobs, 1):
            print(f"{idx}. {job}")

if __name__ == "__main__":
    run_microsoft_scraping_check()
