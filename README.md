# 🛒 Marketplace Telegram Bot

מערכת מקיפה למסחר בקופונים וכרטיסים דיגיטליים דרך Telegram.

[![Version](https://img.shields.io/badge/version-1.1.0-blue.svg)](https://github.com/amirbiron/MARKETPLACE_BOT)
[![Python](https://img.shields.io/badge/python-3.9+-green.svg)](https://python.org)
[![MongoDB](https://img.shields.io/badge/MongoDB-5.0+-green.svg)](https://mongodb.com)
[![License](https://img.shields.io/badge/license-MIT-blue.svg)](LICENSE)

## 📋 תוכן עניינים

- [תכונות עיקריות](#-תכונות-עיקריות)
- [מה חדש בגרסה 1.1](#-מה-חדש-בגרסה-11)
- [מבנה הפרויקט](#-מבנה-הפרויקט)
- [התקנה והרצה](#-התקנה-והרצה)
- [הגדרות](#-הגדרות)
- [פקודות בוט](#-פקודות-בוט)
- [אבטחה](#-אבטחה)
- [Roadmap](#-roadmap)

---

## ✨ תכונות עיקריות

### 👥 לקונים
| תכונה | תיאור |
|--------|--------|
| 🛒 **קניית קופונים** | עיון בקטגוריות וקנייה מאובטחת |
| ⭐ **מערכת מועדפים** | שמירת קופונים + התראות על ירידת מחיר, קופונים דומים ופקיעת תוקף |
| ⭐ **דירוגים וביקורות** | דירוג מוכרים (1-5 ⭐) עם הערות |
| 💬 **צ'אט אנונימי** | תקשורת ישירה ומאובטחת עם מוכרים |
| ⚖️ **מחלוקות** | פתיחת תיקים ופתרון בעיות עם מנגנון 12 שעות |
| 📜 **היסטוריית רכישות** | מעקב אחר כל ההזמנות |
| 📜 **קופונים שנמכרו** | צפייה בעסקאות אחרונות לשקיפות מלאה |
| 🎪 **מכרזים** | השתתפות במכרזים והצבת הצעות מחיר |
| 🔍 **חיפוש מתקדם** | חיפוש חופשי + פילטרים (מחיר, הנחה, דירוג) |
| 🔥 **קופונים חמים** | צפייה בקופונים הנמכרים ביותר |

### 💼 למוכרים
| תכונה | תיאור |
|--------|--------|
| 📦 **העלאת קופונים** | תהליך פשוט ומהיר עם קטגוריות |
| 📊 **סטטיסטיקות** | קופונים פעילים, מכירות החודש, דירוג, אחוז מחלוקות |
| 💸 **משיכות** | בקשות משיכת כספים (מינימום 200₪, עמלה 1%) |
| 🎪 **מכרזים** | יצירת מכרזים לקופונים עם זמן סיום |
| 💬 **צ'אט** | תקשורת אנונימית עם לקוחות |
| ⭐ **בניית מוניטין** | דירוגים וביקורות מקונים |

### 👨‍💼 לאדמינים
| תכונה | תיאור |
|--------|--------|
| 👥 **ניהול מוכרים** | אישור/דחיית בקשות הרשמה |
| 💰 **ניהול תשלומים** | אישור הפקדות ומשיכות |
| ⚖️ **טיפול במחלוקות** | פתרון סכסוכים והחזרים |
| 📊 **סטטיסטיקות** | מעקב אחר ביצועי המערכת |
| 🔧 **ניהול מערכת** | חסימת משתמשים, שליחת הודעות |

---

## 🆕 מה חדש בגרסה 1.1

### ⭐ מערכת מועדפים מלאה
- שמירת קופון למועדפים עם כפתור ⭐
- הסרה ממועדפים עם כפתור 💔
- תפריט "המועדפים שלי" עם פגינציה
- 📉 התראה על ירידת מחיר
- 🔔 התראה על קופון דומה בקטגוריה
- ⏰ התראה יום לפני פקיעת תוקף

### 🔔 מערכת התראות מורחבת
- ⏰ התראה 2 שעות לפני סיום מכרז (לכל המשתתפים)
- ⏰ התראה 30 דקות לפני סיום מכרז
- ⚠️ התראה 2 שעות לפני סגירת חלון דיווח (12 שעות)
- ✅ כפתור "אשר קופון" בהתראה
- 🚨 כפתור "דווח על בעיה" בהתראה
- 📣 התראה למוכר 3 ימים לפני פקיעת קופון

### 📜 היסטוריית קופונים שנמכרו (שקיפות)
- כפתור "📜 קופונים שנמכרו" בתפריט הראשי
- תצוגת 100 עסקאות אחרונות
- פרטים: שם קונה (אנונימי), מוכר, קופון, מחיר מקורי, מחיר מכירה, תאריך
- פגינציה (10 עסקאות בעמוד)
- מטרה: שקיפות ובניית אמון

---

## 📁 מבנה הפרויקט

```
MARKETPLACE_BOT/
│
├── main.py                      # Entry point
├── config.py                    # הגדרות כלליות
├── database.py                  # MongoDB connection
├── models.py                    # Data models
├── keyboards.py                 # Telegram keyboards
├── utils.py                     # Utility functions
│
├── services/                    # Business logic
│   ├── user_service.py          # ניהול משתמשים
│   ├── coupon_service.py        # ניהול קופונים
│   ├── order_service.py         # ניהול הזמנות
│   ├── auction_service.py       # מערכת מכרזים
│   ├── review_service.py        # דירוגים וביקורות
│   ├── chat_service.py          # צ'אט אנונימי
│   ├── notification_service.py  # התראות
│   ├── favorites_service.py     # מועדפים והתראות
│   ├── dispute_service.py       # מחלוקות
│   ├── payment_service.py       # תשלומים
│   ├── payout_service.py        # משיכות
│   └── background_scheduler.py  # משימות רקע (10 tasks)
│
├── handlers/                    # Telegram handlers
│   ├── buyer_handlers.py        # Handlers לקונים
│   ├── seller_handlers.py       # Handlers למוכרים
│   ├── admin_handlers.py        # Handlers לאדמינים
│   ├── auction_handlers.py      # Handlers למכרזים
│   ├── chat_handlers.py         # Handlers לצ'אט
│   ├── dispute_handlers.py      # Handlers למחלוקות
│   ├── payment_handlers.py      # Handlers לתשלומים
│   └── support_handlers.py      # Handlers לתמיכה
│
├── requirements.txt             # Dependencies
├── .env.example                 # Environment variables template
├── Procfile                     # Render deployment
├── render.yaml                  # Render config
└── README.md                    # אתה כאן!
```

---

## 🚀 התקנה והרצה

### דרישות מערכת
- Python 3.9+
- MongoDB 5.0+
- Telegram Bot Token (מ-@BotFather)

### התקנה מקומית

```bash
# 1. שכפול הפרויקט
git clone https://github.com/amirbiron/MARKETPLACE_BOT.git
cd MARKETPLACE_BOT

# 2. יצירת סביבה וירטואלית
python -m venv venv
source venv/bin/activate  # Linux/Mac
# או: venv\Scripts\activate  # Windows

# 3. התקנת תלויות
pip install -r requirements.txt

# 4. הגדרות סביבה
cp .env.example .env
# ערוך את .env עם הפרטים שלך

# 5. הרצת הבוט
python main.py
```

### Deploy ל-Render

הפרויקט מוכן ל-deploy ב-Render:
1. צור חשבון ב-[render.com](https://render.com)
2. חבר את ה-GitHub repo
3. הגדר את משתני הסביבה
4. Deploy!

---

## ⚙️ הגדרות

### משתני סביבה (.env)

```bash
# Telegram Bot Token
BOT_TOKEN=your_bot_token_here

# MongoDB
MONGODB_URI=mongodb+srv://user:pass@cluster.mongodb.net/
MONGODB_DB_NAME=marketplace_bot

# Admin User IDs (comma-separated)
ADMIN_IDS=123456789,987654321

# Environment
ENVIRONMENT=production  # או development

# Payment Details (אופציונלי)
BIT_PHONE=050-1234567
PAYBOX_LINK=https://paybox.co.il/...
BANK_NAME=לאומי
BANK_BRANCH=123
BANK_ACCOUNT=1234567
BANK_OWNER=שם בעל החשבון
MIN_DEPOSIT_AMOUNT=50
```

### הגדרות עמלות (config.py)

| הגדרה | ערך | תיאור |
|--------|------|--------|
| `BUYER_COMMISSION` | 2% | עמלת קונה |
| `VERIFIED_SELLER_COMMISSION` | 3% | עמלת מוכר מאומת |
| `UNVERIFIED_SELLER_COMMISSION` | 5% | עמלת מוכר לא מאומת |
| `WITHDRAWAL_COMMISSION` | 1% | עמלת משיכה |
| `MIN_PAYOUT_AMOUNT` | 200₪ | מינימום למשיכה |
| `BALANCE_FREEZE_HOURS` | 24 | הקפאת כספים למוכר |
| `REPORT_WINDOW_HOURS` | 12 | חלון דיווח לקונה |
| `DAILY_COUPON_LIMIT_UNVERIFIED` | 10 | הגבלת קופונים יומית |
| `MIN_BID_INCREMENT` | 5₪ | תוספת מינימלית במכרז |

---

## 📱 פקודות בוט

### 👥 כל המשתמשים
| פקודה | תיאור |
|--------|--------|
| `/start` | התחלה + תפריט ראשי |
| `/menu` | תפריט ראשי |
| `/buy` | קניית קופונים |
| `/search` | חיפוש חופשי |
| `/filters` | חיפוש מתקדם עם פילטרים |
| `/hot_coupons` | קופונים חמים |
| `/myorders` | ההזמנות שלי |
| `/balance` | יתרה |
| `/my_deposits` | ההפקדות שלי |
| `/chats` | הצ'אטים שלי |
| `/my_disputes` | המחלוקות שלי |
| `/auctions` | מכרזים פעילים |
| `/my_bids` | ההצעות שלי במכרזים |
| `/rules` | תקנון |
| `/support` | פנייה למערכת |
| `/help` | עזרה |

### 💼 מוכרים
| פקודה | תיאור |
|--------|--------|
| `/register_seller` | הרשמה כמוכר |
| `/upload` | העלאת קופון |
| `/mysales` | המכירות שלי |
| `/stats` | סטטיסטיקות |
| `/create_auction` | יצירת מכרז |
| `/my_auctions` | המכרזים שלי |
| `/withdraw` | בקשת משיכה |

### 👨‍💼 אדמינים
| פקודה | תיאור |
|--------|--------|
| `/admin` | פאנל ניהול |

---

## 🔔 משימות רקע (Background Tasks)

המערכת מריצה 10 משימות רקע אוטומטיות:

| משימה | תדירות | תיאור |
|--------|---------|--------|
| `check_expired_auctions` | כל 5 דקות | סיום מכרזים שהסתיימו |
| `check_price_drops` | כל שעה | התראות על ירידת מחיר במועדפים |
| `notify_similar_coupons` | כל 6 שעות | התראות על קופונים דומים |
| `cleanup_old_notifications` | יומי | ניקוי התראות ישנות (30+ יום) |
| `check_dispute_deadlines` | כל 30 דקות | תזכורות 2 שעות לפני סגירת חלון דיווח |
| `cleanup_favorites` | יומי | ניקוי מועדפים של קופונים שנמחקו |
| `check_expired_coupons` | יומי | סימון קופונים שפגו תוקף |
| `notify_auction_ending` | כל 15 דקות | התראות 2 שעות + 30 דקות לפני סיום מכרז |
| `notify_expiring_coupons` | כל 12 שעות | התראה למוכר 3 ימים לפני פקיעת קופון |
| `notify_expiring_favorites` | כל 12 שעות | התראה למשתמש יום לפני פקיעת קופון במועדפים |

---

## 🔐 אבטחה

### מנגנוני אבטחה מובנים

| מנגנון | תיאור |
|--------|--------|
| 🔐 **אימות Telegram** | כל משתמש מזוהה לפי Telegram ID |
| 👥 **הפרדת הרשאות** | קונה / מוכר (מאומת/לא מאומת) / אדמין |
| 💬 **צ'אט אנונימי** | הסתרת מספרי טלפון ופרטים |
| 🔒 **הקפאת יתרה** | הקפאת כספים במכרזים עד סיום |
| ⏰ **חלון דיווח 12 שעות** | זמן לקונה לדווח על בעיה |
| 💰 **הקפאת כספים 24 שעות** | כספי מוכר מוקפאים עד אישור |
| 📊 **הגבלת קופונים** | 10 קופונים ביום למוכר לא מאומת |
| 📝 **Logging מלא** | תיעוד כל הפעולות במערכת |

### סוגי משתמשים

```
קונה (Buyer)
  ↓ הרשמה כמוכר
מוכר לא מאומת (Seller Unverified) - עמלה 5%, הגבלה 10 קופונים
  ↓ אימות ת.ז
מוכר מאומת (Seller Verified) - עמלה 3%, ללא הגבלה
  
אדמין (Admin) - גישה מלאה לניהול
```

---

## 🗺️ Roadmap

### ✅ גרסה 1.0 (MVP) - הושלם
- הרשמת מוכרים (מאומת/לא מאומת)
- קנייה רגילה דרך יתרה
- העלאת קופונים לפי קטגוריות
- דירוג בסיסי עם הערות
- ניהול יתרות (כולל עמלות + משיכה ידנית)
- צפייה בהיסטוריית רכישות
- פנייה למערכת / דיווח תקלות

### ✅ גרסה 1.1 - הושלם
- מכרזים מלאים עם יתרה
- צ'אט אנונימי עם מוכרים
- מערכת מועדפים מלאה
- התראות מתקדמות (מכרזים, מועדפים, חלון דיווח)
- היסטוריית קופונים שנמכרו (שקיפות)
- חיפוש מתקדם ופילטרים
- קופונים חמים

### 🔜 גרסה 1.2 - בתכנון
- [ ] Anti-Fraud אוטומטי
- [ ] Escrow אמיתי
- [ ] תמיכה בסליקה / אשראי
- [ ] דשבורד מתקדם למוכרים

---

## 📊 סטטיסטיקות פרויקט

| מדד | ערך |
|------|------|
| **שורות קוד** | ~8,500+ |
| **קבצי Services** | 14 |
| **קבצי Handlers** | 8 |
| **מודלים** | 10+ |
| **Background Tasks** | 10 |
| **Async/Await** | 100% |

---

## 🤝 תרומה לפרויקט

1. Fork את הפרויקט
2. צור branch חדש (`git checkout -b feature/amazing-feature`)
3. Commit השינויים (`git commit -m 'Add amazing feature'`)
4. Push ל-branch (`git push origin feature/amazing-feature`)
5. פתח Pull Request

---

## 📄 רישיון

MIT License - ראה [LICENSE](LICENSE) לפרטים.

---

## 📞 יצירת קשר

לשאלות ובעיות - פתח Issue ב-GitHub!

---

<div align="center">

**נוצר באהבה ❤️**

גרסה: 1.1.0 | עדכון אחרון: 08/01/2026

</div>
