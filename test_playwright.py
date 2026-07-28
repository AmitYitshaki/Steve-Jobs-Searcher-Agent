from playwright.sync_api import sync_playwright
from bs4 import BeautifulSoup
import time

def test_microsoft_scraping():
    url = "https://jobs.careers.microsoft.com/global/en/search?q=Student&lc=Israel"
    
    print("🚀 מתניע דפדפן אוטומטי...")
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        page = browser.new_page()
        
        print("🌐 מנווט לאתר המשרות של מיקרוסופט...")
        page.goto(url)
        
        print("⏳ נותן לאתר 8 שניות לטעון את כל המשרות בנחת...")
        page.wait_for_timeout(8000) # המתנה "עיוורת" ובטוחה
        
        html_content = page.content()
        browser.close()
        
    print("✅ ה-HTML נשאב בהצלחה. מחפש את המשרות...")
    
    # שומרים עותק של הקוד למקרה שנצטרך לנתח אותו ידנית
    with open("debug_microsoft.html", "w", encoding="utf-8") as f:
        f.write(html_content)
    
    soup = BeautifulSoup(html_content, 'lxml')
    
    # אסטרטגיה חכמה: מחפשים כל כותרת (h2/h3) או לינק (a) שיש בהם טקסט הגיוני
    found_jobs = []
    
    # נסרוק את כל האלמנטים מסוג div, a, h2, h3
    for tag in soup.find_all(['div', 'a', 'h2', 'h3']):
        text = tag.text.strip()
        # אם הטקסט באורך הגיוני למשרה ויש בו מילות מפתח
        if 10 < len(text) < 100 and ("Student" in text or "Intern" in text or "Engineer" in text):
            if text not in found_jobs:
                found_jobs.append(text)
    
    if not found_jobs:
        print("❌ לא הצלחנו לשלוף טקסט באופן אוטומטי. נצטרך להסתכל בקובץ debug_microsoft.html")
    else:
        print(f"\n🎉 בינגו! מצאנו {len(found_jobs)} משרות פוטנציאליות:")
        for idx, job in enumerate(found_jobs, 1):
            print(f"{idx}. {job}")

if __name__ == "__main__":
    test_microsoft_scraping()