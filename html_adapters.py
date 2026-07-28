import requests
import os
from bs4 import BeautifulSoup
from playwright.sync_api import sync_playwright

def scrape_successfactors(company):
    """
    סורק מערכות מבוססות SuccessFactors (כמו SAP, Elbit, Amdocs)
    """
    url = company.get("api_url")
    company_id = company.get("company_id")
    jobs = []
    
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
    }

    try:
        response = requests.get(url, headers=headers, timeout=15)
        response.raise_for_status()
        
        # הופך את טקסט האתר לאובייקט שאפשר לחפש בו
        soup = BeautifulSoup(response.text, 'lxml')
        
        # ב-SuccessFactors המשרות בדרך כלל יושבות בתוך טבלה, בשורות עם המחלקה 'data-row'
        job_rows = soup.find_all('tr', class_='data-row')
        
        # חילוץ כתובת הבסיס כדי לבנות לינקים תקינים (למשל https://jobs.sap.com)
        base_url = "/".join(url.split("/")[:3])
        
        for row in job_rows:
            # מציאת הכותרת והלינק
            title_tag = row.find('span', class_='jobTitle').find('a')
            if not title_tag:
                continue
                
            title = title_tag.text.strip()
            job_link = title_tag['href']
            
            if not job_link.startswith("http"):
                job_link = base_url + job_link
                
            # מציאת המיקום
            location_tag = row.find('span', class_='jobLocation')
            location = location_tag.text.strip() if location_tag else "Israel"
            
            # יצירת מזהה ייחודי (בדרך כלל נמצא בלינק)
            job_id = job_link.split("/")[-2] if "/" in job_link else title
            
            jobs.append({
                "id": f"{company_id}_{job_id}",
                "title": title,
                "location": location,
                "description": f"Full job description available at: {job_link}"
            })
            
        return jobs
        
    except Exception as e:
        print(f"❌ Error scraping HTML for {company_id}: {e}")
        return []

def scrape_microsoft(company):
    """
    סורק אתר המשרות של מיקרוסופט באמצעות Playwright
    """
    url = company.get("api_url")
    company_id = company.get("company_id")
    jobs = []
    
    print(f"🕵️ מפעיל סורק עומק (Playwright) עבור {company_id}...")

    try:
        with sync_playwright() as p:
            # headless=True אומר שהדפדפן ירוץ ברקע בלי להפריע לך במסך
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            page.goto(url)
            
            # המתנה שהמשרות ייטענו
            page.wait_for_timeout(8000)
            html_content = page.content()
            browser.close()

        soup = BeautifulSoup(html_content, 'lxml')
        
        # אסטרטגיה למיקרוסופט: כל משרה היא לינק שמכיל /job/ בכתובת שלו
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href']
            title = a_tag.text.strip()
            
            if '/job/' in href.lower() and len(title) > 3:
                # הרכבת הלינק המלא במידה וזה לינק יחסי
                full_link = href if href.startswith("http") else f"https://jobs.careers.microsoft.com{href}"
                job_id = href.split('/')[-1] if '/' in href else title
                
                jobs.append({
                    "id": f"{company_id}_{job_id}",
                    "title": title,
                    "location": "Israel", # מיקרוסופט מסננת לפי ישראל ב-URL במילא
                    "description": f"Full job description available at: {full_link}"
                })
                
        return jobs
        
    except Exception as e:
        print(f"❌ שגיאה בסריקת מיקרוסופט: {e}")
        return []

def scrape_universal_playwright(company):
    """
    סורק אוניברסלי שכולל יכולות דיאגנוסטיקה (צילומי מסך ושמירת HTML).
    """
    url = company.get("api_url")
    company_id = company.get("company_id")
    jobs = []
    
    print(f"🕵️ מפעיל סורק אוניברסלי (Playwright) עבור {company_id}...")

    # יצירת תיקיית דיאגנוסטיקה אם היא לא קיימת
    debug_dir = "debug_logs"
    if not os.path.exists(debug_dir):
        os.makedirs(debug_dir)

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=True)
            page = browser.new_page()
            
            page.goto(url)
            page.wait_for_timeout(8000)
            
            html_content = page.content()
            
            # 📸 קסם הדיאגנוסטיקה: מצלמים את המסך ושומרים את ה-HTML
            screenshot_path = os.path.join(debug_dir, f"{company_id}.png")
            html_path = os.path.join(debug_dir, f"{company_id}.html")
            
            page.screenshot(path=screenshot_path)
            with open(html_path, "w", encoding="utf-8") as f:
                f.write(html_content)
                
            browser.close()

        soup = BeautifulSoup(html_content, 'lxml')
        job_link_keywords = ['job', 'career', 'req', 'position', 'role', 'detail']
        seen_titles = set()
        
        for a_tag in soup.find_all('a', href=True):
            href = a_tag['href'].lower()
            title = a_tag.text.strip()
            
            if len(title) > 5 and any(keyword in href for keyword in job_link_keywords):
                if title not in seen_titles:
                    seen_titles.add(title)
                    
                    full_link = a_tag['href'] if a_tag['href'].startswith("http") else f"{url.split('.com')[0]}.com{a_tag['href']}"
                    
                    jobs.append({
                        "id": f"{company_id}_{hash(title)}",
                        "title": title,
                        "location": "Israel",
                        "description": f"Full job description available at: {full_link}"
                    })
        
        # אם מצאנו 0 משרות, נדפיס הודעה שמפנה אותך לבדוק את התמונה
        if not jobs:
            print(f"⚠️ {company_id} החזיר 0 משרות. מומלץ להציץ בתמונה: {screenshot_path}")
            
        return jobs
        
    except Exception as e:
        print(f"❌ שגיאה בסריקה אוניברסלית של {company_id}: {e}")
        return []