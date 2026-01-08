"""
שירות אנליטיקס - סטטיסטיקות מתקדמות למוכרים
Analytics Service - Advanced statistics for sellers
"""
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, timedelta
from bson import ObjectId
import database
from config import Config
import logging

logger = logging.getLogger(__name__)


class AnalyticsService:
    """שירות אנליטיקס למוכרים"""
    
    # ==================== Sales Analytics ====================
    
    @staticmethod
    async def get_sales_by_period(
        seller_id: int,
        period: str = "month"  # "day", "week", "month", "year"
    ) -> Dict[str, Any]:
        """
        קבלת נתוני מכירות לפי תקופה
        מחזיר: סה"כ מכירות, הכנסות, ממוצע ליום
        """
        orders = await database.get_orders_collection()
        
        # חישוב תאריך התחלה לפי תקופה
        now = datetime.utcnow()
        if period == "day":
            start_date = now.replace(hour=0, minute=0, second=0, microsecond=0)
        elif period == "week":
            start_date = now - timedelta(days=7)
        elif period == "month":
            start_date = now - timedelta(days=30)
        elif period == "year":
            start_date = now - timedelta(days=365)
        else:
            start_date = now - timedelta(days=30)
        
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
                    "_id": None,
                    "total_sales": {"$sum": 1},
                    "total_revenue": {"$sum": "$price_paid"},
                    "total_commission": {"$sum": "$seller_commission"},
                    "avg_sale_price": {"$avg": "$price_paid"}
                }
            }
        ]
        
        cursor = orders.aggregate(pipeline)
        result = await cursor.to_list(length=1)
        
        if result:
            data = result[0]
            days_in_period = (now - start_date).days or 1
            return {
                "total_sales": data.get("total_sales", 0),
                "total_revenue": data.get("total_revenue", 0) - data.get("total_commission", 0),
                "gross_revenue": data.get("total_revenue", 0),
                "total_commission": data.get("total_commission", 0),
                "avg_sale_price": data.get("avg_sale_price", 0),
                "avg_sales_per_day": data.get("total_sales", 0) / days_in_period,
                "period": period,
                "start_date": start_date,
                "end_date": now
            }
        
        return {
            "total_sales": 0,
            "total_revenue": 0,
            "gross_revenue": 0,
            "total_commission": 0,
            "avg_sale_price": 0,
            "avg_sales_per_day": 0,
            "period": period,
            "start_date": start_date,
            "end_date": now
        }
    
    @staticmethod
    async def get_sales_graph_data(
        seller_id: int,
        period: str = "month"  # "week", "month", "year"
    ) -> List[Dict[str, Any]]:
        """
        קבלת נתונים לגרף מכירות לפי זמן
        מחזיר רשימה של נקודות נתונים (תאריך, מכירות, הכנסות)
        """
        orders = await database.get_orders_collection()
        
        now = datetime.utcnow()
        if period == "week":
            start_date = now - timedelta(days=7)
            group_format = "%Y-%m-%d"
        elif period == "month":
            start_date = now - timedelta(days=30)
            group_format = "%Y-%m-%d"
        elif period == "year":
            start_date = now - timedelta(days=365)
            group_format = "%Y-%m"
        else:
            start_date = now - timedelta(days=30)
            group_format = "%Y-%m-%d"
        
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
                            "format": group_format,
                            "date": "$created_at"
                        }
                    },
                    "sales": {"$sum": 1},
                    "revenue": {"$sum": {"$subtract": ["$price_paid", "$seller_commission"]}}
                }
            },
            {"$sort": {"_id": 1}}
        ]
        
        cursor = orders.aggregate(pipeline)
        results = await cursor.to_list(length=None)
        
        return [
            {
                "date": r["_id"],
                "sales": r["sales"],
                "revenue": r["revenue"]
            }
            for r in results
        ]
    
    # ==================== Category Analytics ====================
    
    @staticmethod
    async def get_sales_by_category(seller_id: int) -> List[Dict[str, Any]]:
        """
        פילוח מכירות לפי קטגוריה
        """
        orders = await database.get_orders_collection()
        coupons = await database.get_coupons_collection()
        
        # Pipeline with lookup to get category from coupon
        pipeline = [
            {
                "$match": {
                    "seller_id": seller_id,
                    "status": {"$in": ["completed", "confirmed"]}
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
            {"$unwind": "$coupon"},
            {
                "$group": {
                    "_id": "$coupon.category",
                    "sales": {"$sum": 1},
                    "revenue": {"$sum": {"$subtract": ["$price_paid", "$seller_commission"]}}
                }
            },
            {"$sort": {"sales": -1}}
        ]
        
        cursor = orders.aggregate(pipeline)
        results = await cursor.to_list(length=None)
        
        return [
            {
                "category": r["_id"],
                "sales": r["sales"],
                "revenue": r["revenue"]
            }
            for r in results
        ]
    
    # ==================== Top Products ====================
    
    @staticmethod
    async def get_top_selling_products(
        seller_id: int,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        מוצרים הנמכרים ביותר
        """
        orders = await database.get_orders_collection()
        
        pipeline = [
            {
                "$match": {
                    "seller_id": seller_id,
                    "status": {"$in": ["completed", "confirmed"]}
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
            {"$unwind": "$coupon"},
            {
                "$group": {
                    "_id": "$coupon_id",
                    "title": {"$first": "$coupon.title"},
                    "category": {"$first": "$coupon.category"},
                    "sales": {"$sum": 1},
                    "revenue": {"$sum": {"$subtract": ["$price_paid", "$seller_commission"]}}
                }
            },
            {"$sort": {"sales": -1}},
            {"$limit": limit}
        ]
        
        cursor = orders.aggregate(pipeline)
        results = await cursor.to_list(length=None)
        
        return [
            {
                "coupon_id": str(r["_id"]),
                "title": r["title"],
                "category": r["category"],
                "sales": r["sales"],
                "revenue": r["revenue"]
            }
            for r in results
        ]
    
    # ==================== Peak Sales Times ====================
    
    @staticmethod
    async def get_peak_sales_times(seller_id: int) -> Dict[str, Any]:
        """
        זמני שיא למכירות - לפי שעה ויום בשבוע
        """
        orders = await database.get_orders_collection()
        
        # Sales by hour
        hour_pipeline = [
            {
                "$match": {
                    "seller_id": seller_id,
                    "status": {"$in": ["completed", "confirmed"]}
                }
            },
            {
                "$group": {
                    "_id": {"$hour": "$created_at"},
                    "sales": {"$sum": 1}
                }
            },
            {"$sort": {"sales": -1}}
        ]
        
        cursor = orders.aggregate(hour_pipeline)
        hours_results = await cursor.to_list(length=None)
        
        # Sales by day of week
        day_pipeline = [
            {
                "$match": {
                    "seller_id": seller_id,
                    "status": {"$in": ["completed", "confirmed"]}
                }
            },
            {
                "$group": {
                    "_id": {"$dayOfWeek": "$created_at"},
                    "sales": {"$sum": 1}
                }
            },
            {"$sort": {"sales": -1}}
        ]
        
        cursor = orders.aggregate(day_pipeline)
        days_results = await cursor.to_list(length=None)
        
        # Map day numbers to Hebrew names
        day_names = {
            1: "ראשון",
            2: "שני",
            3: "שלישי",
            4: "רביעי",
            5: "חמישי",
            6: "שישי",
            7: "שבת"
        }
        
        peak_hour = hours_results[0]["_id"] if hours_results else None
        peak_day = days_results[0]["_id"] if days_results else None
        
        return {
            "by_hour": [{"hour": r["_id"], "sales": r["sales"]} for r in hours_results],
            "by_day": [{"day": day_names.get(r["_id"], str(r["_id"])), "day_num": r["_id"], "sales": r["sales"]} for r in days_results],
            "peak_hour": peak_hour,
            "peak_day": day_names.get(peak_day, "") if peak_day else None,
            "peak_hour_display": f"{peak_hour:02d}:00-{(peak_hour+1) % 24:02d}:00" if peak_hour is not None else None
        }
    
    # ==================== Conversion Rate ====================
    
    @staticmethod
    async def get_conversion_rate(seller_id: int) -> Dict[str, Any]:
        """
        אחוז המרה (צפיות → מכירות)
        """
        coupons = await database.get_coupons_collection()
        
        pipeline = [
            {"$match": {"seller_id": seller_id}},
            {
                "$group": {
                    "_id": None,
                    "total_views": {"$sum": {"$ifNull": ["$views", 0]}},
                    "total_sold": {
                        "$sum": {
                            "$cond": [{"$eq": ["$status", "sold"]}, 1, 0]
                        }
                    },
                    "total_coupons": {"$sum": 1}
                }
            }
        ]
        
        cursor = coupons.aggregate(pipeline)
        result = await cursor.to_list(length=1)
        
        if result:
            data = result[0]
            total_views = data.get("total_views", 0)
            total_sold = data.get("total_sold", 0)
            conversion_rate = (total_sold / total_views * 100) if total_views > 0 else 0
            
            return {
                "total_views": total_views,
                "total_sold": total_sold,
                "total_coupons": data.get("total_coupons", 0),
                "conversion_rate": round(conversion_rate, 2)
            }
        
        return {
            "total_views": 0,
            "total_sold": 0,
            "total_coupons": 0,
            "conversion_rate": 0
        }
    
    # ==================== Commission Report ====================
    
    @staticmethod
    async def get_commission_report(
        seller_id: int,
        period: str = "month"
    ) -> Dict[str, Any]:
        """
        דוח עמלות
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
                    "_id": None,
                    "total_gross": {"$sum": "$price_paid"},
                    "total_commission": {"$sum": "$seller_commission"},
                    "total_buyer_commission": {"$sum": "$buyer_commission"},
                    "order_count": {"$sum": 1}
                }
            }
        ]
        
        cursor = orders.aggregate(pipeline)
        result = await cursor.to_list(length=1)
        
        if result:
            data = result[0]
            return {
                "gross_revenue": data.get("total_gross", 0),
                "seller_commission": data.get("total_commission", 0),
                "buyer_commission_collected": data.get("total_buyer_commission", 0),
                "net_revenue": data.get("total_gross", 0) - data.get("total_commission", 0),
                "order_count": data.get("order_count", 0),
                "avg_commission_per_order": data.get("total_commission", 0) / data.get("order_count", 1) if data.get("order_count") else 0,
                "period": period,
                "start_date": start_date,
                "end_date": now
            }
        
        return {
            "gross_revenue": 0,
            "seller_commission": 0,
            "buyer_commission_collected": 0,
            "net_revenue": 0,
            "order_count": 0,
            "avg_commission_per_order": 0,
            "period": period,
            "start_date": start_date,
            "end_date": now
        }
    
    # ==================== Disputes Report ====================
    
    @staticmethod
    async def get_disputes_report(seller_id: int) -> Dict[str, Any]:
        """
        דוח מחלוקות
        """
        orders = await database.get_orders_collection()
        disputes = await database.get_disputes_collection()
        
        # Total orders
        total_orders = await orders.count_documents({
            "seller_id": seller_id,
            "status": {"$in": ["completed", "confirmed", "disputed", "refunded"]}
        })
        
        # Disputed orders
        disputed_orders = await orders.count_documents({
            "seller_id": seller_id,
            "status": {"$in": ["disputed", "refunded"]}
        })
        
        # Get dispute details
        dispute_pipeline = [
            {"$match": {"seller_id": seller_id}},
            {
                "$group": {
                    "_id": "$status",
                    "count": {"$sum": 1}
                }
            }
        ]
        
        cursor = disputes.aggregate(dispute_pipeline)
        dispute_status = await cursor.to_list(length=None)
        
        status_counts = {r["_id"]: r["count"] for r in dispute_status}
        
        dispute_rate = (disputed_orders / total_orders * 100) if total_orders > 0 else 0
        
        return {
            "total_orders": total_orders,
            "disputed_orders": disputed_orders,
            "dispute_rate": round(dispute_rate, 2),
            "open_disputes": status_counts.get("open", 0),
            "resolved_disputes": status_counts.get("resolved_refund", 0) + status_counts.get("resolved_no_refund", 0),
            "refunds_given": status_counts.get("resolved_refund", 0),
            "status_breakdown": status_counts
        }
    
    # ==================== Dashboard Summary ====================
    
    @staticmethod
    async def get_dashboard_summary(seller_id: int) -> Dict[str, Any]:
        """
        סיכום דשבורד מלא
        """
        # Get all data in parallel (in a real async scenario)
        today_stats = await AnalyticsService.get_sales_by_period(seller_id, "day")
        week_stats = await AnalyticsService.get_sales_by_period(seller_id, "week")
        month_stats = await AnalyticsService.get_sales_by_period(seller_id, "month")
        conversion = await AnalyticsService.get_conversion_rate(seller_id)
        disputes = await AnalyticsService.get_disputes_report(seller_id)
        peak_times = await AnalyticsService.get_peak_sales_times(seller_id)
        top_products = await AnalyticsService.get_top_selling_products(seller_id, 5)
        categories = await AnalyticsService.get_sales_by_category(seller_id)
        
        return {
            "today": today_stats,
            "week": week_stats,
            "month": month_stats,
            "conversion": conversion,
            "disputes": disputes,
            "peak_times": peak_times,
            "top_products": top_products,
            "categories": categories
        }
    
    # ==================== Record Analytics ====================
    
    @staticmethod
    async def record_daily_analytics(seller_id: int) -> bool:
        """
        תיעוד אנליטיקס יומי (לשימוש ב-background scheduler)
        """
        try:
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # Get today's stats
            stats = await AnalyticsService.get_sales_by_period(seller_id, "day")
            conversion = await AnalyticsService.get_conversion_rate(seller_id)
            categories = await AnalyticsService.get_sales_by_category(seller_id)
            
            analytics_data = {
                "seller_id": seller_id,
                "date": today,
                "views": conversion.get("total_views", 0),
                "sales": stats.get("total_sales", 0),
                "revenue": stats.get("total_revenue", 0),
                "top_categories": [c["category"] for c in categories[:3]] if categories else [],
                "created_at": datetime.utcnow()
            }
            
            # Use upsert to avoid duplicates
            seller_analytics = await database.get_seller_analytics_collection()
            await seller_analytics.update_one(
                {"seller_id": seller_id, "date": today},
                {"$set": analytics_data},
                upsert=True
            )
            
            return True
        except Exception as e:
            logger.error(f"Failed to record daily analytics for seller {seller_id}: {e}")
            return False
    
    # ==================== Comparison Analytics ====================
    
    @staticmethod
    async def get_period_comparison(
        seller_id: int,
        period: str = "week"  # Compare current vs previous
    ) -> Dict[str, Any]:
        """
        השוואה בין תקופות (התקופה הנוכחית מול הקודמת)
        """
        now = datetime.utcnow()
        
        if period == "week":
            current_start = now - timedelta(days=7)
            previous_start = now - timedelta(days=14)
            previous_end = current_start
        elif period == "month":
            current_start = now - timedelta(days=30)
            previous_start = now - timedelta(days=60)
            previous_end = current_start
        else:
            current_start = now - timedelta(days=7)
            previous_start = now - timedelta(days=14)
            previous_end = current_start
        
        orders = await database.get_orders_collection()
        
        # Current period
        current_pipeline = [
            {
                "$match": {
                    "seller_id": seller_id,
                    "status": {"$in": ["completed", "confirmed"]},
                    "created_at": {"$gte": current_start, "$lte": now}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "sales": {"$sum": 1},
                    "revenue": {"$sum": {"$subtract": ["$price_paid", "$seller_commission"]}}
                }
            }
        ]
        
        cursor = orders.aggregate(current_pipeline)
        current_result = await cursor.to_list(length=1)
        current_data = current_result[0] if current_result else {"sales": 0, "revenue": 0}
        
        # Previous period
        previous_pipeline = [
            {
                "$match": {
                    "seller_id": seller_id,
                    "status": {"$in": ["completed", "confirmed"]},
                    "created_at": {"$gte": previous_start, "$lt": previous_end}
                }
            },
            {
                "$group": {
                    "_id": None,
                    "sales": {"$sum": 1},
                    "revenue": {"$sum": {"$subtract": ["$price_paid", "$seller_commission"]}}
                }
            }
        ]
        
        cursor = orders.aggregate(previous_pipeline)
        previous_result = await cursor.to_list(length=1)
        previous_data = previous_result[0] if previous_result else {"sales": 0, "revenue": 0}
        
        # Calculate changes
        sales_change = ((current_data["sales"] - previous_data["sales"]) / previous_data["sales"] * 100) if previous_data["sales"] > 0 else 0
        revenue_change = ((current_data["revenue"] - previous_data["revenue"]) / previous_data["revenue"] * 100) if previous_data["revenue"] > 0 else 0
        
        return {
            "current": {
                "sales": current_data["sales"],
                "revenue": current_data["revenue"]
            },
            "previous": {
                "sales": previous_data["sales"],
                "revenue": previous_data["revenue"]
            },
            "change": {
                "sales": round(sales_change, 1),
                "revenue": round(revenue_change, 1)
            },
            "period": period
        }
