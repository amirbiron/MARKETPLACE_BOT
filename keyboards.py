"""
מקלדות Telegram (InlineKeyboard + ReplyKeyboard)
"""
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, ReplyKeyboardMarkup, KeyboardButton
from typing import List, Tuple
from models import UserRole
from services.coupon_service import CouponService


class Keyboards:
    """מחלקה למקלדות טלגרם"""
    
    @staticmethod
    def main_menu(user_role: UserRole) -> InlineKeyboardMarkup:
        """תפריט ראשי לפי תפקיד משתמש - כפתורי אינליין"""
        keyboard = []
        
        # כפתורים בסיסיים לכל המשתמשים
        keyboard.append([
            InlineKeyboardButton("🛒 קניית קופונים", callback_data="menu_buy_coupons"),
            InlineKeyboardButton("💰 יתרה והטענה", callback_data="menu_balance")
        ])
        keyboard.append([
            InlineKeyboardButton("📜 ההזמנות שלי", callback_data="menu_my_orders"),
            InlineKeyboardButton("⭐ המועדפים שלי", callback_data="menu_favorites")
        ])
        keyboard.append([
            InlineKeyboardButton("💳 ההפקדות שלי", callback_data="menu_my_deposits"),
            InlineKeyboardButton("📜 קופונים שנמכרו", callback_data="menu_sold_coupons")
        ])
        
        # כפתורי מוכר
        if user_role in [UserRole.SELLER_VERIFIED, UserRole.SELLER_UNVERIFIED]:
            keyboard.append([
                InlineKeyboardButton("📦 העלאת קופון", callback_data="menu_upload_coupon"),
                InlineKeyboardButton("📊 המכירות שלי", callback_data="menu_my_sales")
            ])
            keyboard.append([
                InlineKeyboardButton("💸 משיכת כספים", callback_data="menu_withdraw"),
                InlineKeyboardButton("📈 סטטיסטיקות", callback_data="menu_stats")
            ])
        else:
            # הצג כפתור "הפוך למוכר" רק למשתמשים שאינם מוכרים
            keyboard.append([
                InlineKeyboardButton("🏪 הפוך למוכר", callback_data="menu_become_seller")
            ])
        
        # כפתורי אדמין
        if user_role == UserRole.ADMIN:
            keyboard.append([
                InlineKeyboardButton("👨‍💼 פאנל אדמין", callback_data="menu_admin_panel"),
                InlineKeyboardButton("🔧 ניהול מערכת", callback_data="menu_system_management")
            ])
        
        # כפתורים נוספים
        keyboard.append([
            InlineKeyboardButton("💬 הצ'אטים שלי", callback_data="menu_my_chats"),
            InlineKeyboardButton("⚙️ הגדרות", callback_data="menu_settings")
        ])
        keyboard.append([
            InlineKeyboardButton("📋 תקנון", callback_data="menu_rules"),
            InlineKeyboardButton("📩 פנייה למערכת", callback_data="menu_support")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def categories_keyboard() -> InlineKeyboardMarkup:
        """מקלדת קטגוריות קופונים"""
        keyboard = []
        
        for category in CouponService.CATEGORIES:
            keyboard.append([
                InlineKeyboardButton(category, callback_data=f"cat_{category}")
            ])
        
        keyboard.append([
            InlineKeyboardButton("🔍 חיפוש חופשי", callback_data="search_free")
        ])
        keyboard.append([
            InlineKeyboardButton("🔥 קופונים חמים", callback_data="hot_coupons")
        ])
        keyboard.append([
            InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def coupon_details_keyboard(
        coupon_id: str,
        seller_id: int,
        current_user_id: int,
        is_favorite: bool = False
    ) -> InlineKeyboardMarkup:
        """מקלדת פרטי קופון"""
        keyboard = []
        
        if current_user_id != seller_id:
            keyboard.append([
                InlineKeyboardButton("💳 קנה עכשיו", callback_data=f"buy_{coupon_id}")
            ])
            
            if is_favorite:
                keyboard.append([
                    InlineKeyboardButton("💔 הסר ממועדפים", callback_data=f"unfav_{coupon_id}")
                ])
            else:
                keyboard.append([
                    InlineKeyboardButton("⭐ הוסף למועדפים", callback_data=f"fav_{coupon_id}")
                ])
        
        keyboard.append([
            InlineKeyboardButton("📊 צפה בדירוגים", callback_data=f"reviews_{seller_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("👤 פרופיל המוכר", callback_data=f"seller_{seller_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("🔙 חזרה", callback_data="back_to_category")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def confirm_purchase_keyboard(coupon_id: str, total_price: float) -> InlineKeyboardMarkup:
        """אישור קנייה"""
        keyboard = [
            [InlineKeyboardButton(f"✅ אשר קנייה ({total_price:.2f}₪)", callback_data=f"confirm_buy_{coupon_id}")],
            [InlineKeyboardButton("❌ ביטול", callback_data="cancel_purchase")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def order_actions_keyboard(order_id: str, can_report: bool) -> InlineKeyboardMarkup:
        """פעולות על הזמנה"""
        keyboard = []
        
        if can_report:
            keyboard.append([
                InlineKeyboardButton("✅ אשר קבלת הקופון", callback_data=f"confirm_order_{order_id}")
            ])
            keyboard.append([
                InlineKeyboardButton("🚨 דווח על בעיה", callback_data=f"report_issue_{order_id}")
            ])
        
        keyboard.append([
            InlineKeyboardButton("💬 פתח צ'אט עם המוכר", callback_data=f"chat_{order_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("📊 דרג את המוכר", callback_data=f"rate_{order_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("🔙 חזרה", callback_data="my_orders")
        ])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def rating_keyboard(order_id: str) -> InlineKeyboardMarkup:
        """דירוג מוכר"""
        keyboard = [
            [InlineKeyboardButton("⭐️ 1", callback_data=f"rating_1_{order_id}"),
             InlineKeyboardButton("⭐️⭐️ 2", callback_data=f"rating_2_{order_id}")],
            [InlineKeyboardButton("⭐️⭐️⭐️ 3", callback_data=f"rating_3_{order_id}")],
            [InlineKeyboardButton("⭐️⭐️⭐️⭐️ 4", callback_data=f"rating_4_{order_id}")],
            [InlineKeyboardButton("⭐️⭐️⭐️⭐️⭐️ 5", callback_data=f"rating_5_{order_id}")],
            [InlineKeyboardButton("❌ ביטול", callback_data="cancel_rating")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def pagination_keyboard(
        items: List[Tuple[str, str]],
        current_page: int,
        total_pages: int,
        prefix: str
    ) -> InlineKeyboardMarkup:
        """מקלדת עם פגינציה"""
        keyboard = []
        
        for text, callback_data in items:
            keyboard.append([InlineKeyboardButton(text, callback_data=callback_data)])
        
        if total_pages > 1:
            nav_row = []
            if current_page > 0:
                nav_row.append(InlineKeyboardButton("⬅️ הקודם", callback_data=f"{prefix}_page_{current_page-1}"))
            
            nav_row.append(InlineKeyboardButton(f"📄 {current_page+1}/{total_pages}", callback_data="ignore"))
            
            if current_page < total_pages - 1:
                nav_row.append(InlineKeyboardButton("הבא ➡️", callback_data=f"{prefix}_page_{current_page+1}"))
            
            keyboard.append(nav_row)
        
        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data=f"{prefix}_back")])
        
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def back_button() -> InlineKeyboardMarkup:
        """כפתור חזרה פשוט"""
        return InlineKeyboardMarkup([[InlineKeyboardButton("🔙 חזרה", callback_data="back")]])
    
    @staticmethod
    def admin_main_keyboard() -> InlineKeyboardMarkup:
        """מקלדת תפריט אדמין ראשי"""
        keyboard = [
            [InlineKeyboardButton("👥 בקשות מוכרים", callback_data="admin_seller_requests")],
            [InlineKeyboardButton("💸 בקשות משיכה", callback_data="admin_payout_requests")],
            [InlineKeyboardButton("💰 בקשות הפקדה", callback_data="admin_deposit_requests")],
            [InlineKeyboardButton("⚖️ מחלוקות פתוחות", callback_data="admin_disputes")],
            [InlineKeyboardButton("🔐 ניהול Escrow", callback_data="escrow_menu")],
            [InlineKeyboardButton("🛡️ ניהול הונאות", callback_data="fraud_menu")],
            [InlineKeyboardButton("📩 פניות תמיכה", callback_data="admin_support_tickets")],
            [InlineKeyboardButton("💵 הוספת יתרה", callback_data="admin_add_balance")],
            [InlineKeyboardButton("📊 סטטיסטיקות", callback_data="admin_stats")],
            [InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def admin_seller_request_keyboard(seller_id: int) -> InlineKeyboardMarkup:
        """מקלדת לטיפול בבקשת מוכר"""
        keyboard = [
            [
                InlineKeyboardButton("✅ אשר", callback_data=f"approve_seller_{seller_id}"),
                InlineKeyboardButton("❌ דחה", callback_data=f"reject_seller_{seller_id}")
            ],
            [InlineKeyboardButton("🔙 חזרה", callback_data="admin_seller_requests")]
        ]
        return InlineKeyboardMarkup(keyboard)
    
    @staticmethod
    def system_management_keyboard() -> InlineKeyboardMarkup:
        """מקלדת ניהול מערכת"""
        keyboard = [
            [InlineKeyboardButton("👥 ניהול משתמשים", callback_data="sys_manage_users")],
            [InlineKeyboardButton("🏪 ניהול מוכרים", callback_data="sys_manage_sellers")],
            [InlineKeyboardButton("🎫 ניהול קופונים", callback_data="sys_manage_coupons")],
            [InlineKeyboardButton("📢 שליחת הודעה לכולם", callback_data="sys_broadcast")],
            [InlineKeyboardButton("🔒 חסימת משתמש", callback_data="sys_block_user")],
            [InlineKeyboardButton("📋 לוגים אחרונים", callback_data="sys_view_logs")],
            [InlineKeyboardButton("⚙️ הגדרות מערכת", callback_data="sys_settings")],
            [InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def favorites_list_keyboard(
        items: List[Tuple[str, str]],
        current_page: int,
        total_pages: int
    ) -> InlineKeyboardMarkup:
        """מקלדת רשימת מועדפים עם פגינציה"""
        keyboard = []

        # הוספת כל הפריטים
        for text, callback_data in items:
            keyboard.append([InlineKeyboardButton(text, callback_data=callback_data)])

        # ניווט בין עמודים
        if total_pages > 1:
            nav_row = []
            if current_page > 0:
                nav_row.append(InlineKeyboardButton("⬅️ הקודם", callback_data=f"favorites_page_{current_page-1}"))

            nav_row.append(InlineKeyboardButton(f"📄 {current_page+1}/{total_pages}", callback_data="ignore"))

            if current_page < total_pages - 1:
                nav_row.append(InlineKeyboardButton("הבא ➡️", callback_data=f"favorites_page_{current_page+1}"))

            keyboard.append(nav_row)

        # כפתור חזרה
        keyboard.append([InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")])

        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def report_window_keyboard(order_id: str) -> InlineKeyboardMarkup:
        """מקלדת להתראת חלון דיווח - עם כפתורי אישור ודיווח"""
        keyboard = [
            [InlineKeyboardButton("✅ אשר קופון", callback_data=f"confirm_from_notif_{order_id}")],
            [InlineKeyboardButton("🚨 דווח על בעיה", callback_data=f"report_from_notif_{order_id}")],
            [InlineKeyboardButton("📦 צפה בהזמנה", callback_data=f"order_{order_id}")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def auction_ending_keyboard(auction_id: str) -> InlineKeyboardMarkup:
        """מקלדת להתראת סיום מכרז - עם כפתור להגדלת הצעה"""
        keyboard = [
            [InlineKeyboardButton("💸 הגדל הצעה", callback_data=f"auction_bid_{auction_id}")],
            [InlineKeyboardButton("👁️ צפה במכרז", callback_data=f"auction_view_{auction_id}")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def sold_coupons_keyboard(
        items: List[Tuple[str, str]],
        current_page: int,
        total_pages: int
    ) -> InlineKeyboardMarkup:
        """מקלדת היסטוריית קופונים שנמכרו עם פגינציה"""
        keyboard = []

        # הוספת כל הפריטים (כל אחד כטקסט בלבד, ללא callback)
        for text, _ in items:
            # פריטים הם טקסט בלבד לשקיפות, לא קליקביליים
            keyboard.append([InlineKeyboardButton(text, callback_data="sold_coupon_info")])

        # ניווט בין עמודים
        if total_pages > 1:
            nav_row = []
            if current_page > 0:
                nav_row.append(InlineKeyboardButton("⬅️ הקודם", callback_data=f"sold_page_{current_page-1}"))

            nav_row.append(InlineKeyboardButton(f"📄 {current_page+1}/{total_pages}", callback_data="ignore"))

            if current_page < total_pages - 1:
                nav_row.append(InlineKeyboardButton("הבא ➡️", callback_data=f"sold_page_{current_page+1}"))

            keyboard.append(nav_row)

        # כפתור חזרה
        keyboard.append([InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")])

        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def sold_coupons_pagination_keyboard(
        current_page: int,
        total_pages: int
    ) -> InlineKeyboardMarkup:
        """מקלדת פגינציה בלבד להיסטוריית קופונים שנמכרו"""
        keyboard = []

        # ניווט בין עמודים
        if total_pages > 1:
            nav_row = []
            if current_page > 0:
                nav_row.append(InlineKeyboardButton("⬅️ הקודם", callback_data=f"sold_page_{current_page-1}"))

            nav_row.append(InlineKeyboardButton(f"📄 {current_page+1}/{total_pages}", callback_data="ignore"))

            if current_page < total_pages - 1:
                nav_row.append(InlineKeyboardButton("הבא ➡️", callback_data=f"sold_page_{current_page+1}"))

            keyboard.append(nav_row)

        # כפתור חזרה
        keyboard.append([InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")])

        return InlineKeyboardMarkup(keyboard)

    # ==================== Anti-Fraud Keyboards ====================

    @staticmethod
    def fraud_management_keyboard() -> InlineKeyboardMarkup:
        """מקלדת ניהול הונאות"""
        keyboard = [
            [InlineKeyboardButton("🚨 אירועים ממתינים לבדיקה", callback_data="fraud_pending_events")],
            [InlineKeyboardButton("📊 סטטיסטיקות הונאה", callback_data="fraud_stats")],
            [InlineKeyboardButton("🚫 משתמשים חסומים", callback_data="fraud_blocked_users")],
            [InlineKeyboardButton("📋 היסטוריית אירועים", callback_data="fraud_history")],
            [InlineKeyboardButton("🔙 חזרה לפאנל אדמין", callback_data="admin_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def fraud_alert_keyboard(user_id: int) -> InlineKeyboardMarkup:
        """מקלדת התראת הונאה - לשימוש בהודעות לאדמינים"""
        keyboard = [
            [InlineKeyboardButton("👤 צפה בפרטי משתמש", callback_data=f"fraud_view_user_{user_id}")],
            [InlineKeyboardButton("📋 היסטוריית הונאה", callback_data=f"fraud_user_history_{user_id}")],
            [
                InlineKeyboardButton("✅ בטל חסימה", callback_data=f"fraud_unblock_{user_id}"),
                InlineKeyboardButton("🚫 החזק חסום", callback_data=f"fraud_keep_blocked_{user_id}")
            ],
            [InlineKeyboardButton("🔙 לפאנל הונאות", callback_data="fraud_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def fraud_event_keyboard(log_id: str, user_id: int) -> InlineKeyboardMarkup:
        """מקלדת לאירוע הונאה בודד"""
        keyboard = [
            [InlineKeyboardButton("👤 צפה במשתמש", callback_data=f"fraud_view_user_{user_id}")],
            [InlineKeyboardButton("✅ סמן כנבדק", callback_data=f"fraud_mark_reviewed_{log_id}")],
            [
                InlineKeyboardButton("🚫 חסום משתמש", callback_data=f"fraud_block_user_{user_id}"),
                InlineKeyboardButton("⚠️ שלח אזהרה", callback_data=f"fraud_warn_user_{user_id}")
            ],
            [InlineKeyboardButton("🔙 חזרה", callback_data="fraud_pending_events")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def fraud_user_actions_keyboard(user_id: int, is_blocked: bool = False) -> InlineKeyboardMarkup:
        """מקלדת פעולות על משתמש מפאנל הונאות"""
        keyboard = []
        
        if is_blocked:
            keyboard.append([InlineKeyboardButton("✅ בטל חסימה", callback_data=f"fraud_unblock_{user_id}")])
        else:
            keyboard.append([InlineKeyboardButton("🚫 חסום משתמש", callback_data=f"fraud_block_user_{user_id}")])
        
        keyboard.extend([
            [InlineKeyboardButton("📋 היסטוריית הונאה", callback_data=f"fraud_user_history_{user_id}")],
            [InlineKeyboardButton("📊 חשב ניקוד אמינות", callback_data=f"fraud_calc_trust_{user_id}")],
            [InlineKeyboardButton("🔙 חזרה", callback_data="fraud_menu")]
        ])
        
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def fraud_blocked_users_keyboard(
        users: List[Tuple[str, int]],
        current_page: int,
        total_pages: int
    ) -> InlineKeyboardMarkup:
        """מקלדת רשימת משתמשים חסומים"""
        keyboard = []
        
        # הוספת כל המשתמשים
        for name, user_id in users:
            keyboard.append([InlineKeyboardButton(
                f"🚫 {name}",
                callback_data=f"fraud_view_user_{user_id}"
            )])
        
        # ניווט בין עמודים
        if total_pages > 1:
            nav_row = []
            if current_page > 0:
                nav_row.append(InlineKeyboardButton("⬅️ הקודם", callback_data=f"fraud_blocked_page_{current_page-1}"))
            
            nav_row.append(InlineKeyboardButton(f"📄 {current_page+1}/{total_pages}", callback_data="ignore"))
            
            if current_page < total_pages - 1:
                nav_row.append(InlineKeyboardButton("הבא ➡️", callback_data=f"fraud_blocked_page_{current_page+1}"))
            
            keyboard.append(nav_row)
        
        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="fraud_menu")])
        
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def trust_score_display(score: int) -> str:
        """המרת ניקוד אמינות לתצוגה גרפית"""
        if score >= 80:
            emoji = "🏆"
            level = "מוכר אמין מאוד"
        elif score >= 60:
            emoji = "✅"
            level = "מוכר אמין"
        elif score >= 40:
            emoji = "⚠️"
            level = "מוכר סביר"
        elif score >= 20:
            emoji = "⚡"
            level = "מוכר חדש"
        else:
            emoji = "🔴"
            level = "דורש תשומת לב"
        
        # סרגל התקדמות
        filled = int(score / 10)
        empty = 10 - filled
        bar = "█" * filled + "░" * empty
        
        return f"{emoji} {score}/100 - {level}\n[{bar}]"

    # ==================== Escrow Keyboards ====================

    @staticmethod
    def escrow_management_keyboard() -> InlineKeyboardMarkup:
        """מקלדת ניהול Escrow"""
        keyboard = [
            [InlineKeyboardButton("💰 יתרת Escrow", callback_data="escrow_balance")],
            [InlineKeyboardButton("⏳ ממתינים לשחרור", callback_data="escrow_pending")],
            [InlineKeyboardButton("⚖️ במחלוקת", callback_data="escrow_disputed")],
            [InlineKeyboardButton("📊 סטטיסטיקות", callback_data="escrow_stats")],
            [InlineKeyboardButton("📋 דוח יומי", callback_data="escrow_daily_report")],
            [InlineKeyboardButton("🔙 חזרה לפאנל אדמין", callback_data="admin_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def escrow_transaction_keyboard(escrow_id: str, order_id: str, status: str) -> InlineKeyboardMarkup:
        """מקלדת לעסקת Escrow בודדת"""
        keyboard = []
        
        # פעולות תלויות סטטוס
        if status in ["held", "disputed"]:
            keyboard.append([
                InlineKeyboardButton("✅ שחרר למוכר", callback_data=f"escrow_release_{escrow_id}"),
                InlineKeyboardButton("↩️ החזר לקונה", callback_data=f"escrow_refund_{escrow_id}")
            ])
        
        keyboard.extend([
            [InlineKeyboardButton("📦 צפה בהזמנה", callback_data=f"order_{order_id}")],
            [InlineKeyboardButton("📋 לוג פעולות", callback_data=f"escrow_logs_{escrow_id}")],
            [InlineKeyboardButton("🔙 חזרה", callback_data="escrow_pending")]
        ])
        
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def escrow_confirm_action_keyboard(escrow_id: str, action: str) -> InlineKeyboardMarkup:
        """מקלדת אישור פעולת Escrow"""
        keyboard = [
            [
                InlineKeyboardButton("✅ אשר", callback_data=f"escrow_confirm_{action}_{escrow_id}"),
                InlineKeyboardButton("❌ ביטול", callback_data=f"escrow_view_{escrow_id}")
            ]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def escrow_list_keyboard(
        items: List[Tuple[str, str]],
        current_page: int,
        total_pages: int,
        prefix: str = "escrow"
    ) -> InlineKeyboardMarkup:
        """מקלדת רשימת Escrow עם פגינציה"""
        keyboard = []
        
        # הוספת כל הפריטים
        for text, callback_data in items:
            keyboard.append([InlineKeyboardButton(text, callback_data=callback_data)])
        
        # ניווט בין עמודים
        if total_pages > 1:
            nav_row = []
            if current_page > 0:
                nav_row.append(InlineKeyboardButton("⬅️ הקודם", callback_data=f"{prefix}_page_{current_page-1}"))
            
            nav_row.append(InlineKeyboardButton(f"📄 {current_page+1}/{total_pages}", callback_data="ignore"))
            
            if current_page < total_pages - 1:
                nav_row.append(InlineKeyboardButton("הבא ➡️", callback_data=f"{prefix}_page_{current_page+1}"))
            
            keyboard.append(nav_row)
        
        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="escrow_menu")])
        
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def escrow_status_display(status: str) -> str:
        """המרת סטטוס Escrow לתצוגה"""
        status_map = {
            "held": "⏳ מוחזק",
            "released": "✅ שוחרר למוכר",
            "refunded": "↩️ הוחזר לקונה",
            "disputed": "⚖️ במחלוקת",
            "cancelled": "❌ בוטל"
        }
        return status_map.get(status, status)

    # ==================== Payment Gateway Keyboards ====================

    @staticmethod
    def payment_methods_keyboard(gateway_enabled: bool = False) -> InlineKeyboardMarkup:
        """מקלדת בחירת אמצעי תשלום"""
        keyboard = []
        
        # תשלום בכרטיס אשראי (אם מופעל)
        if gateway_enabled:
            keyboard.append([
                InlineKeyboardButton("💳 כרטיס אשראי", callback_data="pay_credit_card")
            ])
        
        # שיטות ידניות
        keyboard.extend([
            [InlineKeyboardButton("📱 ביט / פייבוקס", callback_data="deposit_manual")],
            [InlineKeyboardButton("🏦 העברה בנקאית", callback_data="deposit_manual")],
            [InlineKeyboardButton("🔙 חזרה", callback_data="my_balance")]
        ])
        
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def credit_card_amounts_keyboard() -> InlineKeyboardMarkup:
        """מקלדת סכומים לתשלום בכרטיס"""
        keyboard = [
            [
                InlineKeyboardButton("50₪", callback_data="cc_amount_50"),
                InlineKeyboardButton("100₪", callback_data="cc_amount_100"),
            ],
            [
                InlineKeyboardButton("200₪", callback_data="cc_amount_200"),
                InlineKeyboardButton("500₪", callback_data="cc_amount_500"),
            ],
            [InlineKeyboardButton("💰 סכום אחר", callback_data="cc_custom_amount")],
            [InlineKeyboardButton("🔙 חזרה", callback_data="add_balance")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def saved_cards_keyboard(
        cards: List[Tuple[str, str, str, bool]],  # (card_id, brand, last4, is_default)
        show_new_card: bool = True
    ) -> InlineKeyboardMarkup:
        """מקלדת כרטיסים שמורים"""
        keyboard = []
        
        for card_id, brand, last4, is_default in cards:
            emoji = "⭐" if is_default else "💳"
            text = f"{emoji} {brand} ****{last4}"
            keyboard.append([
                InlineKeyboardButton(text, callback_data=f"cc_use_card_{card_id}")
            ])
        
        if show_new_card:
            keyboard.append([
                InlineKeyboardButton("💳 כרטיס חדש", callback_data="cc_new_card")
            ])
            keyboard.append([
                InlineKeyboardButton("💳➕ כרטיס חדש + שמירה", callback_data="cc_new_card_save")
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="pay_credit_card")])
        
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def payment_pending_keyboard(
        payment_url: str,
        transaction_id: str
    ) -> InlineKeyboardMarkup:
        """מקלדת תשלום ממתין"""
        keyboard = [
            [InlineKeyboardButton("💳 מעבר לתשלום", url=payment_url)],
            [InlineKeyboardButton("🔄 בדוק סטטוס", callback_data=f"cc_check_status_{transaction_id}")],
            [InlineKeyboardButton("❌ ביטול", callback_data="my_balance")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def card_management_keyboard(
        card_id: str,
        is_default: bool = False
    ) -> InlineKeyboardMarkup:
        """מקלדת ניהול כרטיס בודד"""
        keyboard = []
        
        if not is_default:
            keyboard.append([
                InlineKeyboardButton("⭐ הגדר כברירת מחדל", callback_data=f"cc_set_default_{card_id}")
            ])
        
        keyboard.append([
            InlineKeyboardButton("🗑️ מחק כרטיס", callback_data=f"cc_delete_card_{card_id}")
        ])
        keyboard.append([
            InlineKeyboardButton("🔙 חזרה", callback_data="cc_manage_cards")
        ])
        
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def payout_methods_keyboard(
        has_paypal: bool = False,
        has_payoneer: bool = False
    ) -> InlineKeyboardMarkup:
        """מקלדת שיטות משיכה"""
        keyboard = [
            [InlineKeyboardButton("🏦 העברה בנקאית", callback_data="payout_method_bank_transfer")],
            [InlineKeyboardButton("📱 ביט", callback_data="payout_method_bit")],
        ]
        
        if has_paypal:
            keyboard.append([
                InlineKeyboardButton("🅿️ PayPal", callback_data="payout_method_paypal")
            ])
        
        if has_payoneer:
            keyboard.append([
                InlineKeyboardButton("💳 Payoneer", callback_data="payout_method_payoneer")
            ])
        
        keyboard.append([InlineKeyboardButton("🔙 חזרה", callback_data="my_balance")])
        
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def payout_confirm_keyboard(
        use_saved: bool = False
    ) -> InlineKeyboardMarkup:
        """מקלדת אישור פרטי משיכה"""
        keyboard = []
        
        if use_saved:
            keyboard.append([
                InlineKeyboardButton("✅ השתמש בפרטים שמורים", callback_data="payout_use_saved")
            ])
        
        keyboard.append([
            InlineKeyboardButton("📝 הזן פרטים חדשים", callback_data="payout_new_details")
        ])
        keyboard.append([
            InlineKeyboardButton("🔙 חזרה", callback_data="automated_payout")
        ])
        
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def payment_gateway_status_display(status: str) -> str:
        """המרת סטטוס תשלום לתצוגה"""
        status_map = {
            "pending": "⏳ ממתין לתשלום",
            "processing": "🔄 בעיבוד",
            "completed": "✅ הושלם",
            "failed": "❌ נכשל",
            "cancelled": "🚫 בוטל",
            "expired": "⌛ פג תוקף",
            "refunded": "↩️ הוחזר"
        }
        return status_map.get(status, status)

    @staticmethod
    def payout_method_display(method: str) -> str:
        """המרת שיטת משיכה לתצוגה"""
        method_map = {
            "bank_transfer": "🏦 העברה בנקאית",
            "bit": "📱 ביט",
            "paypal": "🅿️ PayPal",
            "payoneer": "💳 Payoneer"
        }
        return method_map.get(method, method)

    @staticmethod
    def payout_status_display(status: str) -> str:
        """המרת סטטוס משיכה לתצוגה"""
        status_map = {
            "pending": "⏳ ממתין לאישור",
            "approved": "✅ אושר",
            "processing": "🔄 בעיבוד",
            "completed": "✅ הושלם",
            "failed": "❌ נכשל",
            "rejected": "🚫 נדחה"
        }
        return status_map.get(status, status)

    # ==================== Admin Payment Gateway Keyboards ====================

    @staticmethod
    def admin_payment_gateway_menu() -> InlineKeyboardMarkup:
        """מקלדת ניהול סליקה לאדמין"""
        keyboard = [
            [InlineKeyboardButton("📊 סטטיסטיקות תשלומים", callback_data="admin_pg_stats")],
            [InlineKeyboardButton("⏳ עסקאות ממתינות", callback_data="admin_pg_pending")],
            [InlineKeyboardButton("💸 משיכות ממתינות", callback_data="admin_payouts_pending")],
            [InlineKeyboardButton("📋 היסטוריית עסקאות", callback_data="admin_pg_history")],
            [InlineKeyboardButton("⚙️ הגדרות סליקה", callback_data="admin_pg_settings")],
            [InlineKeyboardButton("🔙 חזרה לפאנל אדמין", callback_data="admin_menu")]
        ]
        return InlineKeyboardMarkup(keyboard)

    @staticmethod
    def admin_payout_action_keyboard(payout_id: str) -> InlineKeyboardMarkup:
        """מקלדת פעולות על משיכה (אדמין)"""
        keyboard = [
            [
                InlineKeyboardButton("✅ אשר ועבד", callback_data=f"admin_process_payout_{payout_id}"),
                InlineKeyboardButton("❌ דחה", callback_data=f"admin_reject_payout_{payout_id}")
            ],
            [InlineKeyboardButton("👤 פרטי מוכר", callback_data=f"admin_payout_seller_{payout_id}")],
            [InlineKeyboardButton("🔙 חזרה", callback_data="admin_payouts_pending")]
        ]
        return InlineKeyboardMarkup(keyboard)
