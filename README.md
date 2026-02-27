# AI & Cyber Daily Monitor

מערכת אוטומטית יומית לאיסוף, תרגום וסיכום חדשות בתחומי בינה מלאכותית וסייבר.

## מה המערכת עושה?

1. **סורקת ~50 מקורות** RSS מתחומי AI וסייבר (כולל מקורות ישראליים)
2. **מסירה כפילויות** לפי URL ודמיון כותרות
3. **מתרגמת ומסכמת** לעברית באמצעות Gemini API (חינם)
4. **מציגה דשבורד** עברי RTL רספונסיבי ב-GitHub Pages
5. **שולחת אימייל יומי** עם 10-15 העדכונים החשובים

## התקנה מהירה

```bash
# 1. Clone the repo
git clone https://github.com/shaimccann/ai-cyber-monitor.git
cd ai-cyber-monitor

# 2. Install dependencies
pip install -r requirements.txt

# 3. Set environment variables
export GEMINI_API_KEY="your-api-key"
export EMAIL_ADDRESS="your-email@gmail.com"
export EMAIL_PASSWORD="your-app-password"

# 4. Run the pipeline
python scripts/scan.py
python scripts/deduplicate.py
python scripts/summarize.py
python scripts/send_email.py
```

## GitHub Actions

המערכת רצה אוטומטית כל יום ב-08:00 שעון ישראל.

### Secrets נדרשים:
| Secret | תיאור |
|---|---|
| `GEMINI_API_KEY` | מפתח API של Google Gemini |
| `EMAIL_ADDRESS` | כתובת Gmail |
| `EMAIL_PASSWORD` | App Password של Gmail |

## ניהול מקורות

עמוד אדמין נפרד (`docs/admin.html`) מאפשר ניהול מקורות דרך הדפדפן.
דורש GitHub Personal Access Token עם הרשאת `contents: write`.

## כלי עזר

### גילוי RSS
```bash
python scripts/discover_rss.py https://openai.com
```

## מבנה הפרויקט

```
├── .github/workflows/daily-scan.yml   # תזמון יומי
├── scripts/                           # סקריפטים
│   ├── scan.py                        # סריקת RSS
│   ├── deduplicate.py                 # דה-דופליקציה
│   ├── summarize.py                   # סיכום ותרגום
│   ├── send_email.py                  # אימייל יומי
│   ├── discover_rss.py                # גילוי RSS
│   └── llm_provider.py               # הפשטת LLM
├── config/
│   ├── sources.json                   # רשימת מקורות
│   └── config.yaml                    # הגדרות
├── data/articles/                     # נתונים יומיים
├── docs/                              # דשבורד (GitHub Pages)
│   ├── index.html                     # דשבורד ציבורי
│   ├── style.css
│   ├── app.js
│   └── admin.html                     # ניהול מקורות (מוגן)
└── requirements.txt
```
