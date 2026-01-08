# 🛒 Marketplace Telegram Bot

מערכת מקיפה למסחר בקופונים וכרטיסים דיגיטליים דרך Telegram.

## 📋 תוכן עניינים

- [תכונות עיקריות](#-תכונות-עיקריות)
- [מבנה הפרויקט](#-מבנה-הפרויקט)
- [התקנה והרצה](#-התקנה-והרצה)
- [הגדרות](#-הגדרות)
- [תיעוד API](#-תיעוד-api)
- [סטטיסטיקות](#-סטטיסטיקות)

## ✨ תכונות עיקריות

### 👥 לקונים
- 🛒 **קניית קופונים** - עיון בקטגוריות וקנייה מאובטחת
- ⭐ **מערכת דירוגים** - דירוג מוכרים וביקורות
- 💬 **צ'אט אנונימי** - תקשורת ישירה עם מוכרים
- ⚖️ **מחלוקות** - פתיחת תיקים ופתרון בעיות
- 📜 **היסטוריה** - מעקב אחר כל ההזמנות
- ⭐ **מועדפים** - שמירת קופונים והתראות על ירידת מחיר
- 🎪 **מכרזים** - השתתפות במכרזים והצבת הצעות מחיר

### 💼 למוכרים
- 📦 **העלאת קופונים** - תהליך פשוט ומהיר
- 📊 **סטטיסטיקות** - מעקב אחר מכירות ודירוגים
- 💸 **משיכות** - בקשות משיכת כספים קלות
- 🎪 **מכרזים** - יצירת מכרזים לקופונים
- 💬 **צ'אט** - תקשורת עם לקוחות
- ⭐ **דירוגים** - בניית מוניטין

### 👨‍💼 לאדמינים
- 👥 **ניהול מוכרים** - אישור/דחיית מוכרים
- 💰 **ניהול תשלומים** - אישור משיכות והוספת יתרות
- ⚖️ **טיפול במחלוקות** - פתרון סכסוכים
- 📊 **סטטיסטיקות** - מעקב אחר ביצועי המערכת
- 💬 **ניהול צ'אטים** - צפייה וחסימה

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
│   ├── favorites_service.py     # מועדפים
│   ├── dispute_service.py       # מחלוקות
│   ├── payment_service.py       # תשלומים
│   ├── payout_service.py        # משיכות
│   └── background_scheduler.py  # משימות רקע
│
├── handlers/                    # Telegram handlers
│   ├── buyer_handlers.py        # Handlers לקונים
│   ├── seller_handlers.py       # Handlers למוכרים
│   ├── admin_handlers.py        # Handlers לאדמינים
│   ├── auction_handlers.py      # Handlers למכרזים
│   ├── chat_handlers.py         # Handlers לצ'אט
│   ├── dispute_handlers.py      # Handlers למחלוקות
│   └── payment_handlers.py      # Handlers לתשלומים
│
├── requirements.txt             # Dependencies
├── .env.example                 # Environment variables template
└── README.md                    # זה הקובץ!
```

## 🚀 התקנה והרצה

### דרישות מערכת
- Python 3.9+
- MongoDB 5.0+
- Telegram Bot Token

### התקנה

1. **שכפול הפרויקט**
```bash
git clone https://github.com/yourusername/MARKETPLACE_BOT.git
cd MARKETPLACE_BOT
```

2. **יצירת סביבה וירטואלית**
```bash
python -m venv venv
source venv/bin/activate  # Linux/Mac
# או
venv\Scripts\activate  # Windows
```

3. **התקנת תלויות**
```bash
pip install -r requirements.txt
```

4. **הגדרות סביבה**
```bash
cp .env.example .env
# ערוך את .env עם הפרטים שלך
```

5. **הרצת הבוט**
```bash
python main.py
```

## ⚙️ הגדרות

### משתני סביבה (.env)

```bash
# Telegram Bot Token
BOT_TOKEN=your_bot_token_here

# MongoDB
MONGODB_URI=mongodb://localhost:27017
MONGODB_DB_NAME=marketplace_bot

# Admin User IDs (comma-separated)
ADMIN_IDS=123456789,987654321

# Environment
ENVIRONMENT=development  # או production
```

### הגדרות כלליות (config.py)

```python
# עמלות
BUYER_COMMISSION_RATE = 0.02          # 2%
SELLER_COMMISSION_RATE = 0.04         # 4%

# משיכות
MIN_PAYOUT_AMOUNT = 200               # מינימום 200₪

# מכרזים
MIN_BID_INCREMENT = 5.0               # תוספת מינימלית 5₪

# מחלוקות
DISPUTE_WINDOW_HOURS = 12             # 12 שעות לדיווח

# פגינציה
ITEMS_PER_PAGE = 5                    # 5 פריטים לעמוד
```

## 📊 סטטיסטיקות

### סה"כ קוד
- **~7,900 שורות Python**
- **12 קבצי services**
- **7 קבצי handlers**
- **10+ מודלים**

### תכונות מרכזיות
- ✅ 100% Async/Await
- ✅ MongoDB with async driver
- ✅ Error handling מלא
- ✅ Logging מובנה
- ✅ Background tasks
- ✅ Real-time notifications
- ✅ Pagination
- ✅ Search & Filters

## 🔧 תיעוד API

### Services

#### UserService
```python
# יצירת משתמש
user = await UserService.create_user(user_id, username, first_name)

# קבלת משתמש
user = await UserService.get_user(user_id)

# עדכון יתרה
await UserService.update_balance(user_id, amount)
```

#### AuctionService
```python
# יצירת מכרז
auction_id, error = await AuctionService.create_auction(
    seller_id, coupon_id, starting_price, duration_hours=24
)

# הצבת הצעה
error = await AuctionService.place_bid(auction_id, bidder_id, amount)

# סיום מכרז
has_winner, msg = await AuctionService.end_auction(auction_id)
```

#### ChatService
```python
# יצירת שיחה
chat_id = await ChatService.create_chat(buyer_id, seller_id)

# שליחת הודעה
message_id = await ChatService.send_message(chat_id, sender_id, text)

# קבלת הודעות
messages = await ChatService.get_chat_messages(chat_id, user_id)
```

### Background Tasks

המערכת מריצה 8 משימות רקע אוטומטיות:

1. ✅ **Expired Auctions** - סיום מכרזים (כל 5 דקות)
2. 💰 **Price Drops** - התראות על ירידת מחיר (כל שעה)
3. ✨ **Similar Coupons** - התראות על קופונים דומים (כל 6 שעות)
4. 🗑️ **Cleanup Notifications** - ניקוי התראות ישנות (יומי)
5. ⚠️ **Dispute Deadlines** - תזכורות (כל שעתיים)
6. 🧹 **Cleanup Favorites** - ניקוי מועדפים (יומי)
7. 📅 **Expired Coupons** - סימון קופונים שפגו (יומי)
8. ⏰ **Auction Ending** - התראות על סיום מכרזים (כל שעה)

## 📱 פקודות בוט

### כל המשתמשים
- `/start` - התחלה
- `/buy` - קניית קופונים
- `/myorders` - ההזמנות שלי
- `/balance` - יתרה
- `/chats` - הצ'אטים שלי
- `/my_disputes` - המחלוקות שלי
- `/rules` - תקנון
- `/my_deposits` - צפייה בהיסטוריית ההפקדות

### מוכרים
- `/upload` - העלאת קופון
- `/mysales` - המכירות שלי
- `/stats` - סטטיסטיקות
- `/create_auction` - יצירת מכרז
- `/my_auctions` - המכרזים שלי
- `/my_payouts` - המשיכות שלי

### אדמינים
- `/admin` - פאנל ניהול

## 🔐 אבטחה

- ✅ אימות משתמשים דרך Telegram
- ✅ הפרדת הרשאות (קונה/מוכר/אדמין)
- ✅ צ'אט אנונימי (הסתרת מספרי טלפון)
- ✅ הקפאת יתרה במכרזים
- ✅ חלון זמן למחלוקות
- ✅ Logging מלא לכל פעולה

## 🤝 תרומה לפרויקט

אנא פתח Issue או Pull Request!

## 📄 רישיון

MIT License

## 📞 יצירת קשר

לשאלות ובעיות - פתח Issue ב-GitHub

---

נוצר בתאריך: 07/01/2026  
גרסה: 1.0.0  
סה"כ שורות: ~7,900 🎉
