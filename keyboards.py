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
    def main_menu(user_role: UserRole) -> ReplyKeyboardMarkup:
        """תפריט ראשי לפי תפקיד משתמש"""
        keyboard = []
        
        keyboard.append([
            KeyboardButton("🛒 קניית קופונים"),
            KeyboardButton("💰 יתרה והטענה")
        ])
        keyboard.append([
            KeyboardButton("📜 ההזמנות שלי"),
            KeyboardButton("⭐ המועדפים שלי")
        ])
        
        if user_role in [UserRole.SELLER_VERIFIED, UserRole.SELLER_UNVERIFIED]:
            keyboard.append([
                KeyboardButton("📦 העלאת קופון"),
                KeyboardButton("📊 המכירות שלי")
            ])
            keyboard.append([
                KeyboardButton("💸 משיכת כספים"),
                KeyboardButton("📈 סטטיסטיקות")
            ])
        
        if user_role == UserRole.ADMIN:
            keyboard.append([
                KeyboardButton("👨‍💼 פאנל אדמין"),
                KeyboardButton("🔧 ניהול מערכת")
            ])
        
        keyboard.append([
            KeyboardButton("💬 הצ'אטים שלי"),
            KeyboardButton("⚙️ הגדרות")
        ])
        keyboard.append([
            KeyboardButton("📋 תקנון"),
            KeyboardButton("📩 פנייה למערכת")
        ])
        
        return ReplyKeyboardMarkup(keyboard, resize_keyboard=True)
    
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
