"""
פונקציות עזר כלליות
"""
from typing import List
from telegram import InlineKeyboardButton, InlineKeyboardMarkup
from datetime import datetime


def create_pagination_keyboard(
    items: List[tuple],  # [(text, callback_data), ...]
    current_page: int,
    total_pages: int,
    prefix: str = "page"
) -> InlineKeyboardMarkup:
    """יצירת מקלדת עם פגינציה"""
    keyboard = []
    
    # הוספת כפתורי פריטים
    for text, callback_data in items:
        keyboard.append([InlineKeyboardButton(text, callback_data=callback_data)])
    
    # הוספת כפתורי ניווט
    if total_pages > 1:
        nav_buttons = []
        
        if current_page > 0:
            nav_buttons.append(InlineKeyboardButton("⬅️ הקודם", callback_data=f"{prefix}_{current_page-1}"))
        
        nav_buttons.append(InlineKeyboardButton(
            f"📄 {current_page+1}/{total_pages}",
            callback_data="ignore"
        ))
        
        if current_page < total_pages - 1:
            nav_buttons.append(InlineKeyboardButton("הבא ➡️", callback_data=f"{prefix}_{current_page+1}"))
        
        keyboard.append(nav_buttons)
    
    # כפתור חזרה
    keyboard.append([InlineKeyboardButton("🔙 חזרה לתפריט", callback_data="main_menu")])
    
    return InlineKeyboardMarkup(keyboard)


def format_price(price: float) -> str:
    """עיצוב מחיר"""
    return f"{price:.2f}₪"


def format_datetime(dt: datetime) -> str:
    """עיצוב תאריך ושעה"""
    return dt.strftime("%d/%m/%Y %H:%M")


def format_date(dt: datetime) -> str:
    """עיצוב תאריך בלבד"""
    return dt.strftime("%d/%m/%Y")


def get_star_rating(rating: float) -> str:
    """המרת דירוג למספר כוכבים"""
    full_stars = int(rating)
    half_star = 1 if (rating - full_stars) >= 0.5 else 0
    empty_stars = 5 - full_stars - half_star
    
    return "⭐️" * full_stars + "✨" * half_star + "☆" * empty_stars


def truncate_text(text: str, max_length: int = 50) -> str:
    """קיצור טקסט"""
    if len(text) <= max_length:
        return text
    return text[:max_length-3] + "..."


def calculate_discount_percent(original_price: float, sale_price: float) -> int:
    """חישוב אחוז הנחה"""
    if original_price <= 0:
        return 0
    discount = ((original_price - sale_price) / original_price) * 100
    return int(discount)
