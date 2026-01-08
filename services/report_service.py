"""
שירות דוחות - יצירת דוחות PDF ו-CSV למוכרים
Report Service - PDF and CSV report generation for sellers
"""
from typing import List, Optional, Dict, Any
from datetime import datetime, timedelta
from io import BytesIO, StringIO
import csv
import database
from services.analytics_service import AnalyticsService
from config import Config
import logging

logger = logging.getLogger(__name__)


class ReportService:
    """שירות יצירת דוחות למוכרים"""
    
    # ==================== CSV Reports ====================
    
    @staticmethod
    async def generate_sales_csv(
        seller_id: int,
        period: str = "month"
    ) -> BytesIO:
        """
        יצירת דוח מכירות בפורמט CSV
        """
        orders = await database.get_orders_collection()
        coupons = await database.get_coupons_collection()
        
        now = datetime.utcnow()
        if period == "week":
            start_date = now - timedelta(days=7)
        elif period == "month":
            start_date = now - timedelta(days=30)
        elif period == "year":
            start_date = now - timedelta(days=365)
        else:
            start_date = now - timedelta(days=30)
        
        # Get orders with coupon details
        pipeline = [
            {
                "$match": {
                    "seller_id": seller_id,
                    "status": {"$in": ["completed", "confirmed"]},
                    "created_at": {"$gte": start_date}
                }
            },
            {
                "$lookup": {
                    "from": "coupons",
                    "localField": "coupon_id",
                    "foreignField": "_id",
                    "as": "coupon"
                }
            },
            {"$unwind": {"path": "$coupon", "preserveNullAndEmptyArrays": True}},
            {"$sort": {"created_at": -1}}
        ]
        
        cursor = orders.aggregate(pipeline)
        results = await cursor.to_list(length=None)
        
        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "תאריך",
            "מזהה הזמנה",
            "שם קופון",
            "קטגוריה",
            "מחיר מכירה",
            "עמלה",
            "נטו",
            "סטטוס"
        ])
        
        # Data rows
        for order in results:
            coupon = order.get("coupon", {})
            net = order.get("price_paid", 0) - order.get("seller_commission", 0)
            
            writer.writerow([
                order.get("created_at", datetime.utcnow()).strftime("%d/%m/%Y %H:%M"),
                str(order.get("_id", "")),
                coupon.get("title", "לא זמין"),
                coupon.get("category", "לא זמין"),
                f"{order.get('price_paid', 0):.2f}",
                f"{order.get('seller_commission', 0):.2f}",
                f"{net:.2f}",
                order.get("status", "")
            ])
        
        # Convert to bytes
        output.seek(0)
        bytes_output = BytesIO(output.getvalue().encode('utf-8-sig'))
        bytes_output.seek(0)
        
        return bytes_output
    
    @staticmethod
    async def generate_commission_csv(
        seller_id: int,
        period: str = "month"
    ) -> BytesIO:
        """
        יצירת דוח עמלות בפורמט CSV
        """
        orders = await database.get_orders_collection()
        
        now = datetime.utcnow()
        if period == "week":
            start_date = now - timedelta(days=7)
        elif period == "month":
            start_date = now - timedelta(days=30)
        elif period == "year":
            start_date = now - timedelta(days=365)
        else:
            start_date = now - timedelta(days=30)
        
        # Group by date
        pipeline = [
            {
                "$match": {
                    "seller_id": seller_id,
                    "status": {"$in": ["completed", "confirmed"]},
                    "created_at": {"$gte": start_date}
                }
            },
            {
                "$group": {
                    "_id": {
                        "$dateToString": {
                            "format": "%Y-%m-%d",
                            "date": "$created_at"
                        }
                    },
                    "sales_count": {"$sum": 1},
                    "gross_revenue": {"$sum": "$price_paid"},
                    "total_commission": {"$sum": "$seller_commission"}
                }
            },
            {"$sort": {"_id": -1}}
        ]
        
        cursor = orders.aggregate(pipeline)
        results = await cursor.to_list(length=None)
        
        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "תאריך",
            "מספר מכירות",
            "הכנסות ברוטו",
            "עמלות",
            "הכנסות נטו"
        ])
        
        # Data rows
        total_gross = 0
        total_commission = 0
        
        for row in results:
            net = row.get("gross_revenue", 0) - row.get("total_commission", 0)
            total_gross += row.get("gross_revenue", 0)
            total_commission += row.get("total_commission", 0)
            
            writer.writerow([
                row.get("_id", ""),
                row.get("sales_count", 0),
                f"{row.get('gross_revenue', 0):.2f}",
                f"{row.get('total_commission', 0):.2f}",
                f"{net:.2f}"
            ])
        
        # Summary row
        writer.writerow([])
        writer.writerow([
            "סה\"כ",
            "",
            f"{total_gross:.2f}",
            f"{total_commission:.2f}",
            f"{total_gross - total_commission:.2f}"
        ])
        
        # Convert to bytes
        output.seek(0)
        bytes_output = BytesIO(output.getvalue().encode('utf-8-sig'))
        bytes_output.seek(0)
        
        return bytes_output
    
    @staticmethod
    async def generate_products_csv(seller_id: int) -> BytesIO:
        """
        יצירת דוח מוצרים בפורמט CSV
        """
        coupons = await database.get_coupons_collection()
        
        cursor = coupons.find({"seller_id": seller_id}).sort("created_at", -1)
        results = await cursor.to_list(length=None)
        
        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "מזהה",
            "שם קופון",
            "קטגוריה",
            "מחיר מקורי",
            "מחיר מכירה",
            "הנחה %",
            "צפיות",
            "סטטוס",
            "תאריך יצירה",
            "תאריך תפוגה"
        ])
        
        # Data rows
        for coupon in results:
            original = coupon.get("original_price", 0)
            sale = coupon.get("sale_price", 0)
            discount = ((original - sale) / original * 100) if original > 0 else 0
            
            writer.writerow([
                str(coupon.get("_id", "")),
                coupon.get("title", ""),
                coupon.get("category", ""),
                f"{original:.2f}",
                f"{sale:.2f}",
                f"{discount:.1f}%",
                coupon.get("views", 0),
                coupon.get("status", ""),
                coupon.get("created_at", datetime.utcnow()).strftime("%d/%m/%Y"),
                coupon.get("expires_at", "").strftime("%d/%m/%Y") if coupon.get("expires_at") else "ללא"
            ])
        
        # Convert to bytes
        output.seek(0)
        bytes_output = BytesIO(output.getvalue().encode('utf-8-sig'))
        bytes_output.seek(0)
        
        return bytes_output
    
    @staticmethod
    async def generate_disputes_csv(seller_id: int) -> BytesIO:
        """
        יצירת דוח מחלוקות בפורמט CSV
        """
        disputes = await database.get_disputes_collection()
        
        cursor = disputes.find({"seller_id": seller_id}).sort("created_at", -1)
        results = await cursor.to_list(length=None)
        
        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Header
        writer.writerow([
            "מזהה",
            "מזהה הזמנה",
            "סיבה",
            "סטטוס",
            "תאריך פתיחה",
            "תאריך סגירה",
            "החלטה"
        ])
        
        # Data rows
        for dispute in results:
            writer.writerow([
                str(dispute.get("_id", "")),
                str(dispute.get("order_id", "")),
                dispute.get("reason", ""),
                dispute.get("status", ""),
                dispute.get("created_at", datetime.utcnow()).strftime("%d/%m/%Y %H:%M"),
                dispute.get("resolved_at", "").strftime("%d/%m/%Y %H:%M") if dispute.get("resolved_at") else "פתוח",
                dispute.get("resolution", "")
            ])
        
        # Convert to bytes
        output.seek(0)
        bytes_output = BytesIO(output.getvalue().encode('utf-8-sig'))
        bytes_output.seek(0)
        
        return bytes_output
    
    # ==================== Text Report (Simple PDF Alternative) ====================
    
    @staticmethod
    async def generate_monthly_report_text(
        seller_id: int,
        month: Optional[datetime] = None
    ) -> str:
        """
        יצירת דוח חודשי בפורמט טקסט
        (חלופה פשוטה ל-PDF - אפשר לשלוח כקובץ או להציג בטלגרם)
        """
        if month is None:
            month = datetime.utcnow().replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        
        # Get user info
        users = await database.get_users_collection()
        user = await users.find_one({"user_id": seller_id})
        business_name = user.get("business_name", "מוכר") if user else "מוכר"
        
        # Get stats
        stats = await AnalyticsService.get_sales_by_period(seller_id, "month")
        categories = await AnalyticsService.get_sales_by_category(seller_id)
        top_products = await AnalyticsService.get_top_selling_products(seller_id, 5)
        commission = await AnalyticsService.get_commission_report(seller_id, "month")
        disputes = await AnalyticsService.get_disputes_report(seller_id)
        comparison = await AnalyticsService.get_period_comparison(seller_id, "month")
        
        # Build report
        report = f"""
╔════════════════════════════════════════╗
║       📊 דוח מכירות חודשי              ║
╚════════════════════════════════════════╝

👤 מוכר: {business_name}
📅 תקופה: {month.strftime('%B %Y')}
🕐 נוצר: {datetime.utcnow().strftime('%d/%m/%Y %H:%M')}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📈 סיכום מכירות
────────────────
• סה"כ מכירות: {stats.get('total_sales', 0)}
• הכנסות ברוטו: {stats.get('gross_revenue', 0):.2f}₪
• עמלות ששולמו: {commission.get('seller_commission', 0):.2f}₪
• הכנסות נטו: {stats.get('total_revenue', 0):.2f}₪
• ממוצע למכירה: {stats.get('avg_sale_price', 0):.2f}₪

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📊 השוואה לחודש קודם
────────────────────
• מכירות: {comparison.get('current', {}).get('sales', 0)} ({comparison.get('change', {}).get('sales', 0):+.1f}%)
• הכנסות: {comparison.get('current', {}).get('revenue', 0):.2f}₪ ({comparison.get('change', {}).get('revenue', 0):+.1f}%)

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

🏆 מוצרים מובילים
─────────────────
"""
        for i, product in enumerate(top_products[:5], 1):
            report += f"{i}. {product.get('title', 'לא זמין')[:30]}\n"
            report += f"   מכירות: {product.get('sales', 0)} | הכנסות: {product.get('revenue', 0):.2f}₪\n"
        
        if not top_products:
            report += "   אין מוצרים להצגה\n"
        
        report += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📁 פילוח לפי קטגוריה
───────────────────
"""
        for cat in categories[:5]:
            report += f"• {cat.get('category', 'לא זמין')}: {cat.get('sales', 0)} מכירות ({cat.get('revenue', 0):.2f}₪)\n"
        
        if not categories:
            report += "   אין נתונים להצגה\n"
        
        report += f"""
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

⚖️ מחלוקות
──────────
• סה"כ הזמנות: {disputes.get('total_orders', 0)}
• מחלוקות: {disputes.get('disputed_orders', 0)}
• אחוז מחלוקות: {disputes.get('dispute_rate', 0):.1f}%
• מחלוקות פתוחות: {disputes.get('open_disputes', 0)}

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

💡 המלצות לשיפור
───────────────
"""
        # Generate recommendations
        recommendations = []
        
        if disputes.get('dispute_rate', 0) > 10:
            recommendations.append("• שים לב לאחוז מחלוקות גבוה - ודא שהקופונים תקינים")
        
        if comparison.get('change', {}).get('sales', 0) < -20:
            recommendations.append("• ירידה במכירות - שקול לעדכן מחירים או להוסיף קופונים חדשים")
        
        if stats.get('total_sales', 0) == 0:
            recommendations.append("• אין מכירות החודש - העלה קופונים חדשים!")
        
        if not recommendations:
            recommendations.append("• כל הכבוד! הביצועים שלך טובים!")
        
        for rec in recommendations:
            report += f"{rec}\n"
        
        report += """
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

📧 דוח זה נוצר אוטומטית על ידי מערכת Marketplace
"""
        
        return report
    
    # ==================== Export All Data ====================
    
    @staticmethod
    async def generate_full_export_csv(seller_id: int) -> BytesIO:
        """
        ייצוא כל הנתונים של המוכר בקובץ CSV אחד
        """
        orders = await database.get_orders_collection()
        coupons = await database.get_coupons_collection()
        reviews = await database.db.reviews if hasattr(database.db, 'reviews') else None
        
        # Get all orders
        order_cursor = orders.find({"seller_id": seller_id}).sort("created_at", -1)
        all_orders = await order_cursor.to_list(length=None)
        
        # Get all coupons
        coupon_cursor = coupons.find({"seller_id": seller_id}).sort("created_at", -1)
        all_coupons = await coupon_cursor.to_list(length=None)
        
        # Create CSV
        output = StringIO()
        writer = csv.writer(output)
        
        # Orders section
        writer.writerow(["=== הזמנות ==="])
        writer.writerow(["מזהה", "קונה ID", "סכום", "עמלה", "נטו", "סטטוס", "תאריך"])
        
        for order in all_orders:
            net = order.get("price_paid", 0) - order.get("seller_commission", 0)
            writer.writerow([
                str(order.get("_id", "")),
                order.get("buyer_id", ""),
                f"{order.get('price_paid', 0):.2f}",
                f"{order.get('seller_commission', 0):.2f}",
                f"{net:.2f}",
                order.get("status", ""),
                order.get("created_at", datetime.utcnow()).strftime("%d/%m/%Y %H:%M")
            ])
        
        writer.writerow([])
        writer.writerow([])
        
        # Coupons section
        writer.writerow(["=== קופונים ==="])
        writer.writerow(["מזהה", "שם", "קטגוריה", "מחיר מקורי", "מחיר מכירה", "צפיות", "סטטוס", "תאריך"])
        
        for coupon in all_coupons:
            writer.writerow([
                str(coupon.get("_id", "")),
                coupon.get("title", ""),
                coupon.get("category", ""),
                f"{coupon.get('original_price', 0):.2f}",
                f"{coupon.get('sale_price', 0):.2f}",
                coupon.get("views", 0),
                coupon.get("status", ""),
                coupon.get("created_at", datetime.utcnow()).strftime("%d/%m/%Y")
            ])
        
        # Convert to bytes
        output.seek(0)
        bytes_output = BytesIO(output.getvalue().encode('utf-8-sig'))
        bytes_output.seek(0)
        
        return bytes_output
