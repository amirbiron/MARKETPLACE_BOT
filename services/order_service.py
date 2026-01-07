"""
שירות ניהול הזמנות
"""
from typing import List, Optional
from datetime import datetime, timedelta
from bson import ObjectId
import database
from models import Order, OrderStatus, Coupon
from config import Config
from services.user_service import UserService
from services.coupon_service import CouponService
import logging

logger = logging.getLogger(__name__)


class OrderService:
    """שירות לניהול הזמנות"""
    
    @staticmethod
    async def create_order(buyer_id: int, coupon_id: ObjectId) -> Optional[Order]:
        """יצירת הזמנה חדשה"""
        # בדיקת קופון
        coupon = await CouponService.get_coupon(coupon_id)
        if not coupon or coupon.status.value != "active":
            logger.warning(f"Coupon {coupon_id} not available")
            return None
        
        # בדיקת יתרה
        buyer = await UserService.get_user(buyer_id)
        if not buyer:
            logger.warning(f"Buyer {buyer_id} not found")
            return None
        
        # חישוב עמלות
        buyer_commission = coupon.sale_price * Config.BUYER_COMMISSION
        total_price = coupon.sale_price + buyer_commission
        
        if buyer.balance < total_price:
            logger.warning(f"Insufficient balance for buyer {buyer_id}: {buyer.balance}₪ < {total_price}₪")
            return None
        
        # בדיקה אם המוכר מאומת
        is_verified = await UserService.is_verified_seller(coupon.seller_id)
        seller_commission_rate = Config.VERIFIED_SELLER_COMMISSION if is_verified else Config.UNVERIFIED_SELLER_COMMISSION
        seller_commission = coupon.sale_price * seller_commission_rate
        
        # יצירת ההזמנה
        order = Order(
            buyer_id=buyer_id,
            seller_id=coupon.seller_id,
            coupon_id=coupon_id,
            price_paid=total_price,
            buyer_commission=buyer_commission,
            seller_commission=seller_commission,
            status=OrderStatus.PENDING
        )
        
        orders = await database.get_orders_collection()
        result = await orders.insert_one(order.to_dict())
        order._id = result.inserted_id
        
        # ניכוי כסף מהקונה
        await UserService.update_user_balance(buyer_id, -total_price)
        
        # הוספת כסף למוכר (אבל מוקפא למשך 24 שעות)
        seller_net = coupon.sale_price - seller_commission
        await UserService.update_user_balance(coupon.seller_id, seller_net)
        await UserService.freeze_balance(coupon.seller_id, seller_net)
        
        # סימון הקופון כנמכר
        await CouponService.mark_as_sold(coupon_id)
        
        logger.info(f"Created order {order._id}: buyer={buyer_id}, seller={coupon.seller_id}, price={total_price}₪")
        return order
    
    @staticmethod
    async def get_order(order_id: ObjectId) -> Optional[Order]:
        """קבלת הזמנה לפי ID"""
        orders = await database.get_orders_collection()
        order_data = await orders.find_one({"_id": order_id})
        
        if order_data:
            return Order.from_dict(order_data)
        return None
    
    @staticmethod
    async def get_buyer_orders(buyer_id: int) -> List[Order]:
        """קבלת כל ההזמנות של קונה"""
        orders = await database.get_orders_collection()
        cursor = orders.find({"buyer_id": buyer_id}).sort("created_at", -1)
        
        order_list = []
        async for order_data in cursor:
            order_list.append(Order.from_dict(order_data))
        
        return order_list
    
    @staticmethod
    async def get_seller_orders(seller_id: int) -> List[Order]:
        """קבלת כל ההזמנות של מוכר"""
        orders = await database.get_orders_collection()
        cursor = orders.find({"seller_id": seller_id}).sort("created_at", -1)
        
        order_list = []
        async for order_data in cursor:
            order_list.append(Order.from_dict(order_data))
        
        return order_list
    
    @staticmethod
    async def confirm_order(order_id: ObjectId) -> bool:
        """אישור קבלת הקופון על ידי הקונה"""
        order = await OrderService.get_order(order_id)
        if not order or order.status != OrderStatus.PENDING:
            return False
        
        orders = await database.get_orders_collection()
        
        result = await orders.update_one(
            {"_id": order_id},
            {
                "$set": {
                    "status": OrderStatus.CONFIRMED.value,
                    "confirmed_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count > 0:
            # שחרור כסף המוכר (לא מוקפא יותר)
            seller_net = order.price_paid - order.buyer_commission - order.seller_commission
            await UserService.unfreeze_balance(order.seller_id, seller_net)
            
            logger.info(f"Order {order_id} confirmed by buyer")
            return True
        return False
    
    @staticmethod
    async def complete_order(order_id: ObjectId) -> bool:
        """השלמת הזמנה (אחרי 24 שעות ללא דיווח)"""
        order = await OrderService.get_order(order_id)
        if not order:
            return False
        
        orders = await database.get_orders_collection()
        
        result = await orders.update_one(
            {"_id": order_id},
            {"$set": {"status": OrderStatus.COMPLETED.value}}
        )
        
        if result.modified_count > 0:
            # שחרור כסף המוכר אוטומטית
            seller_net = order.price_paid - order.buyer_commission - order.seller_commission
            await UserService.unfreeze_balance(order.seller_id, seller_net)
            
            logger.info(f"Order {order_id} auto-completed after 24 hours")
            return True
        return False
    
    @staticmethod
    async def check_and_complete_orders():
        """בדיקה והשלמה אוטומטית של הזמנות שעברו 24 שעות"""
        orders = await database.get_orders_collection()
        cutoff_time = datetime.utcnow() - timedelta(hours=Config.BALANCE_FREEZE_HOURS)
        
        cursor = orders.find({
            "status": OrderStatus.PENDING.value,
            "created_at": {"$lte": cutoff_time}
        })
        
        completed_count = 0
        async for order_data in cursor:
            order = Order.from_dict(order_data)
            if await OrderService.complete_order(order._id):
                completed_count += 1
        
        if completed_count > 0:
            logger.info(f"Auto-completed {completed_count} orders")
        
        return completed_count
    
    @staticmethod
    async def can_report_issue(order_id: ObjectId) -> bool:
        """בדיקה האם אפשר לדווח על בעיה (בתוך 12 שעות)"""
        order = await OrderService.get_order(order_id)
        if not order or order.status != OrderStatus.PENDING:
            return False
        
        time_passed = datetime.utcnow() - order.created_at
        return time_passed < timedelta(hours=Config.REPORT_WINDOW_HOURS)
