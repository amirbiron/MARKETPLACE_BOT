# 🛍️ Marketplace Bot - בוט מרקטפלייס לטלגרם

בוט טלגרם מתקדם לקניה ומכירת קופונים וכרטיסים עם מערכת תשלומים, דירוגים ומכרזים.

## 🎯 תכונות עיקריות

### 👥 משתמשים
- **קונים**: קניית קופונים, ניהול מועדפים, דירוג מוכרים
- **מוכרים**: העלאת קופונים/מכרזים, קבלת תשלומים, משיכת כספים
- **אדמינים**: ניהול מוכרים, טיפול במחלוקות, אישור משיכות

### 💰 מערכת כלכלית
- יתרה פנימית במערכת
- עמלות מותאמות (2% קונה, 3-5% מוכר)
- מנגנון הקפאה למשך 24 שעות
- משיכת כספים עם מינימום 200₪

### 🔐 אבטחה ואמון
- דירוגים והערות (1-5 כוכבים)
- מנגנון מחלוקות עם צ'אט
- אימות מוכרים (מאומת/לא מאומת)
- חלון דיווח 12 שעות

### 🎪 מכרזים
- מכרזים עם מחיר פתיחה וזמן סיום
- הצעות מחיר עם הקפאת יתרה
- זוכה אוטומטי בסיום

## 🚀 התקנה והרצה

### דרישות מקדימות
- Python 3.11+
- MongoDB
- Telegram Bot Token

### התקנה מקומית

```bash
# שכפול הפרויקט
git clone <repository-url>
cd marketplace_bot

# יצירת סביבה וירטואלית
python -m venv venv
source venv/bin/activate  # Linux/Mac
# או
venv\Scripts\activate  # Windows

# התקנת תלויות
pip install -r requirements.txt

# העתקת קובץ הגדרות
cp .env.example .env

# עריכת .env והוספת:
# - BOT_TOKEN
# - MONGODB_URI
# - ADMIN_IDS

# הרצת הבוט
python main.py
```

### Deploy ל-Render

1. דחוף את הקוד ל-GitHub
2. צור MongoDB Atlas חינמי
3. התחבר ל-Render והגדר Web Service
4. הגדר Environment Variables
5. הבוט יעלה אוטומטית!

## 📁 מבנה הפרויקט

```
marketplace_bot/
├── main.py              # נקודת כניסה
├── config.py            # הגדרות
├── database.py          # MongoDB
├── models.py            # מודלים
├── utils.py             # עזרים
├── services/            # לוגיקה עסקית
└── requirements.txt     # תלויות
```

## 📊 טכנולוגיות

- Python 3.11+
- python-telegram-bot 22.5
- PyMongo 4.15.5 (Async)
- MongoDB
- Render

---

**נוצר עם ❤️ על ידי Claude & אמיר חיים**
