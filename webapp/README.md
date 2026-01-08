# שוק הקופונים - Web App

Telegram Mini App לשוק קופונים - ממשק משתמש מודרני ונוח.

## 📁 מבנה הפרויקט

```
webapp/
├── index.html          # עמוד קטלוג הקופונים
├── chat.html           # עמוד צ'אט מוכר-קונה
├── manifest.json       # PWA manifest
├── css/
│   └── styles.css      # עיצוב מלא
├── js/
│   ├── app.js          # לוגיקת עמוד הקופונים
│   └── chat.js         # לוגיקת עמוד הצ'אט
└── assets/             # תמונות ואייקונים
```

## 🎨 צבעי העיצוב

### עמוד קופונים
| אלמנט | צבע |
|--------|------|
| רקע ראשי | `#183018` |
| רקע כרטיסיות | `#1E3728` |
| טקסט ראשי (מחירים, כפתורים) | `#30F078` |
| טקסט שם עסק | `#91C8A5` |
| כפתור ירידת מחירים | `#F04860` |
| מחיר ישן (מחוק) | `#787878` |

### עמוד צ'אט
| אלמנט | צבע |
|--------|------|
| רקע עמוד | `#0F2314` |
| בועת מוכר | `#2D5037` |
| בועת קונה | `#2DF06E` |
| הודעת מערכת | `#142D4B` |
| בועת אדמין | `#1E2832` |
| כפתור שליחה | `#2DF06E` |

## 🚀 הרצה מקומית

### אפשרות 1: מצב Demo (ללא API)
```bash
cd webapp
python3 -m http.server 8000
```
ואז פתח: http://localhost:8000

> ⚠️ במצב זה מוצגים נתוני דוגמה בלבד

### אפשרות 2: עם API Server (מסונכרן עם הבוט)
```bash
# התקנת dependencies
pip install -r requirements.txt

# הרצת ה-API server
python webapp_api.py
```
ואז פתח: http://localhost:8080

> ✅ במצב זה הנתונים מגיעים מ-MongoDB

### אפשרות 3: Live Server (VS Code Extension)
פתח את `index.html` ולחץ "Go Live" (מצב Demo)

## 📱 Telegram Mini App Integration

ה-Web App מוכן לשימוש כ-Telegram Mini App:

1. צור בוט דרך [@BotFather](https://t.me/BotFather)
2. הגדר Web App URL:
   ```
   /setmenubutton
   ```
3. הוסף את ה-URL של ה-Web App שלך

ה-SDK של Telegram כבר מוטען:
```javascript
const tg = window.Telegram?.WebApp;
tg.ready();
tg.expand();
```

## ✨ תכונות

- ✅ עיצוב RTL מלא (עברית)
- ✅ רספונסיבי (מובייל first)
- ✅ אנימציות חלקות
- ✅ Dark mode מובנה
- ✅ תמיכה ב-Telegram Mini Apps
- ✅ PWA ready
- ✅ Loading states
- ✅ Empty states
- ✅ Haptic feedback

## 🔧 התאמות עתידיות

- [ ] חיבור ל-API אמיתי
- [ ] עמוד חיפוש
- [ ] עמוד ארנק
- [ ] עמוד פרופיל
- [ ] התראות Push
- [ ] אופליין support
