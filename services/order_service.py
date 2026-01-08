"""
שירות ניהול הזמנות - משולב עם Escrow
"""
from typing import List, Optional, Dict
from datetime import datetime, timedelta
from bson import ObjectId
import database
from models import Order, OrderStatus, Coupon, EscrowStatus
from config import Config
from services.user_service import UserService
from services.coupon_service import CouponService
from services.escrow_service import EscrowService
import logging

logger = logging.getLogger(__name__)


class OrderService:
    """שירות לניהול הזמנות"""
    
    @staticmethod
    async def create_order(buyer_id: int, coupon_id: ObjectId) -> Optional[Order]:
        """
        יצירת הזמנה חדשה עם Escrow
        
        תהליך:
        1. בדיקת קופון ויתרה
        2. ניכוי כסף מהקונה
        3. העברת כסף ל-Escrow (לא ישירות למוכר!)
        4. יצירת הזמנה
        5. סימון קופון כנמכר
        """
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
        
        # ========== ESCROW: העברת כסף ל-Escrow במקום למוכר ==========
        escrow = await EscrowService.hold_funds(
            order_id=order._id,
            buyer_id=buyer_id,
            seller_id=coupon.seller_id,
            amount=coupon.sale_price,
            buyer_commission=buyer_commission,
            seller_commission=seller_commission
        )
        
        if not escrow:
            # אם ה-Escrow נכשל, החזר כסף לקונה ומחק הזמנה
            await UserService.update_user_balance(buyer_id, total_price)
            await orders.delete_one({"_id": order._id})
            logger.error(f"Failed to create escrow for order {order._id}")
            return None
        
        # סימון הקופון כנמכר
        await CouponService.mark_as_sold(coupon_id)
        
        logger.info(f"Created order {order._id} with Escrow: buyer={buyer_id}, seller={coupon.seller_id}, price={total_price}₪")
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
        """
        אישור קבלת הקופון על ידי הקונה
        שחרור כספים מ-Escrow למוכר
        """
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
            # ========== ESCROW: שחרור כספים למוכר ==========
            escrow_released = await EscrowService.release_to_seller(
                order_id=order_id,
                notes="אושר ע\"י הקונה"
            )
            
            if not escrow_released:
                logger.warning(f"Order {order_id} confirmed but escrow release failed")
            
            logger.info(f"Order {order_id} confirmed by buyer, escrow released to seller")
            return True
        return False
    
    @staticmethod
    async def complete_order(order_id: ObjectId) -> bool:
        """
        השלמת הזמנה (אחרי 24 שעות ללא דיווח)
        שחרור אוטומטי מ-Escrow
        """
        order = await OrderService.get_order(order_id)
        if not order:
            return False
        
        orders = await database.get_orders_collection()
        
        result = await orders.update_one(
            {"_id": order_id},
            {"$set": {"status": OrderStatus.COMPLETED.value}}
        )
        
        if result.modified_count > 0:
            # ========== ESCROW: שחרור אוטומטי למוכר ==========
            # הערה: הלוגיקה של הזמן נמצאת ב-EscrowService.process_auto_releases
            # אבל אפשר גם לקרוא ישירות מכאן
            escrow_released = await EscrowService.release_to_seller(
                order_id=order_id,
                notes="שחרור אוטומטי - 24 שעות ללא דיווח"
            )
            
            if not escrow_released:
                logger.warning(f"Order {order_id} completed but escrow release failed")
            
            logger.info(f"Order {order_id} auto-completed after 24 hours, escrow released")
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
    
    @staticmethod
    async def report_issue(order_id: ObjectId, reason: str) -> bool:
        """
        דיווח על בעיה בהזמנה
        מעביר את ה-Escrow לסטטוס מחלוקת
        """
        order = await OrderService.get_order(order_id)
        if not order:
            return False
        
        if not await OrderService.can_report_issue(order_id):
            logger.warning(f"Cannot report issue for order {order_id} - window closed")
            return False
        
        orders = await database.get_orders_collection()
        
        result = await orders.update_one(
            {"_id": order_id},
            {
                "$set": {
                    "status": OrderStatus.DISPUTED.value,
                    "dispute_reason": reason,
                    "disputed_at": datetime.utcnow()
                }
            }
        )
        
        if result.modified_count > 0:
            # ========== ESCROW: סימון כמחלוקת ==========
            await EscrowService.mark_disputed(
                order_id=order_id,
                notes=f"דיווח מהקונה: {reason}"
            )
            
            logger.info(f"Order {order_id} marked as disputed: {reason}")
            return True
        return False
    
    @staticmethod
    async def refund_order(order_id: ObjectId, admin_id: int, notes: Optional[str] = None) -> bool:
        """
        החזר כספים לקונה (פעולת אדמין)
        """
        order = await OrderService.get_order(order_id)
        if not order:
            return False
        
        orders = await database.get_orders_collection()
        
        result = await orders.update_one(
            {"_id": order_id},
            {
                "$set": {
                    "status": OrderStatus.REFUNDED.value,
                    "refunded_at": datetime.utcnow(),
                    "refund_notes": notes,
                    "refunded_by": admin_id
                }
            }
        )
        
        if result.modified_count > 0:
            # ========== ESCROW: החזר כספים לקונה ==========
            escrow_refunded = await EscrowService.refund_to_buyer(
                order_id=order_id,
                admin_id=admin_id,
                notes=notes
            )
            
            if not escrow_refunded:
                logger.warning(f"Order {order_id} marked as refunded but escrow refund failed")
            
            logger.info(f"Order {order_id} refunded by admin {admin_id}")
            return True
        return False
    
    @staticmethod
    async def get_order_with_escrow(order_id: ObjectId) -> Optional[Dict]:
        """קבלת הזמנה עם פרטי Escrow"""
        order = await OrderService.get_order(order_id)
        if not order:
            return None
        
        escrow = await EscrowService.get_escrow(order_id)
        
        return {
            "order": order,
            "escrow": escrow
        }
