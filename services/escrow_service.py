"""
שירות Escrow - ניהול כספים מוחזקים בין קונה למוכר
"""
from typing import Optional, List, Dict, Any
from datetime import datetime, timedelta
from bson import ObjectId
import database
from models import EscrowTransaction, EscrowLog, EscrowStatus
from config import Config
from services.user_service import UserService
import logging

logger = logging.getLogger(__name__)


class EscrowService:
    """שירות לניהול Escrow"""
    
    # ==================== Core Escrow Operations ====================
    
    @staticmethod
    async def hold_funds(
        order_id: ObjectId,
        buyer_id: int,
        seller_id: int,
        amount: float,
        buyer_commission: float = 0.0,
        seller_commission: float = 0.0
    ) -> Optional[EscrowTransaction]:
        """
        הקפאת כספים ב-Escrow
        
        Args:
            order_id: מזהה ההזמנה
            buyer_id: מזהה הקונה
            seller_id: מזהה המוכר
            amount: סכום העסקה (ללא עמלות)
            buyer_commission: עמלת קונה
            seller_commission: עמלת מוכר
        
        Returns:
            EscrowTransaction אם הצליח, None אם נכשל
        """
        try:
            # בדיקה שאין כבר escrow לאותה הזמנה
            escrow_col = await database.get_escrow_transactions_collection()
            existing = await escrow_col.find_one({"order_id": order_id})
            
            if existing:
                logger.warning(f"Escrow already exists for order {order_id}")
                return EscrowTransaction.from_dict(existing)
            
            # חישוב זמן שחרור מתוכנן
            release_scheduled_at = datetime.utcnow() + timedelta(hours=Config.ESCROW_RELEASE_HOURS)
            
            # יצירת עסקת Escrow
            escrow = EscrowTransaction(
                order_id=order_id,
                buyer_id=buyer_id,
                seller_id=seller_id,
                amount=amount,
                buyer_commission=buyer_commission,
                seller_commission=seller_commission,
                status=EscrowStatus.HELD,
                held_at=datetime.utcnow(),
                release_scheduled_at=release_scheduled_at
            )
            
            result = await escrow_col.insert_one(escrow.to_dict())
            escrow._id = result.inserted_id
            
            # לוג הפעולה
            await EscrowService._log_action(
                escrow_id=escrow._id,
                action="hold",
                amount=amount + buyer_commission,
                from_account="buyer",
                to_account="escrow",
                performed_by=buyer_id,
                notes=f"הקפאת כספים להזמנה {order_id}"
            )
            
            logger.info(f"Escrow created: {escrow._id} for order {order_id}, amount={amount}₪")
            return escrow
            
        except Exception as e:
            logger.error(f"Failed to create escrow for order {order_id}: {e}")
            return None
    
    @staticmethod
    async def release_to_seller(
        order_id: ObjectId,
        admin_id: Optional[int] = None,
        notes: Optional[str] = None
    ) -> bool:
        """
        שחרור כספים למוכר
        
        Args:
            order_id: מזהה ההזמנה
            admin_id: מזהה אדמין (אם ידני)
            notes: הערות
        
        Returns:
            True אם הצליח
        """
        try:
            escrow_col = await database.get_escrow_transactions_collection()
            escrow_data = await escrow_col.find_one({"order_id": order_id})
            
            if not escrow_data:
                logger.warning(f"No escrow found for order {order_id}")
                return False
            
            escrow = EscrowTransaction.from_dict(escrow_data)
            
            if escrow.status != EscrowStatus.HELD:
                logger.warning(f"Escrow {escrow._id} not in HELD status: {escrow.status}")
                return False
            
            # העברת כספים למוכר
            seller_net = escrow.net_seller_amount
            success = await UserService.update_user_balance(escrow.seller_id, seller_net)
            
            if not success:
                logger.error(f"Failed to transfer {seller_net}₪ to seller {escrow.seller_id}")
                return False
            
            # עדכון הסטטוס
            action_type = "admin_release" if admin_id else "release"
            
            result = await escrow_col.update_one(
                {"_id": escrow._id},
                {
                    "$set": {
                        "status": EscrowStatus.RELEASED.value,
                        "released_at": datetime.utcnow(),
                        "released_to": "seller",
                        "notes": notes,
                        "admin_id": admin_id
                    }
                }
            )
            
            if result.modified_count > 0:
                # לוג הפעולה
                await EscrowService._log_action(
                    escrow_id=escrow._id,
                    action=action_type,
                    amount=seller_net,
                    from_account="escrow",
                    to_account="seller",
                    performed_by=admin_id or 0,
                    notes=notes or f"שחרור כספים למוכר {escrow.seller_id}"
                )
                
                logger.info(f"Released {seller_net}₪ to seller {escrow.seller_id} from escrow {escrow._id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to release escrow for order {order_id}: {e}")
            return False
    
    @staticmethod
    async def refund_to_buyer(
        order_id: ObjectId,
        admin_id: Optional[int] = None,
        notes: Optional[str] = None,
        partial_amount: Optional[float] = None
    ) -> bool:
        """
        החזר כספים לקונה
        
        Args:
            order_id: מזהה ההזמנה
            admin_id: מזהה אדמין
            notes: הערות
            partial_amount: סכום חלקי להחזר (None = החזר מלא)
        
        Returns:
            True אם הצליח
        """
        try:
            escrow_col = await database.get_escrow_transactions_collection()
            escrow_data = await escrow_col.find_one({"order_id": order_id})
            
            if not escrow_data:
                logger.warning(f"No escrow found for order {order_id}")
                return False
            
            escrow = EscrowTransaction.from_dict(escrow_data)
            
            if escrow.status not in [EscrowStatus.HELD, EscrowStatus.DISPUTED]:
                logger.warning(f"Escrow {escrow._id} cannot be refunded: status={escrow.status}")
                return False
            
            # חישוב סכום ההחזר
            refund_amount = partial_amount or escrow.total_buyer_paid
            
            # החזר כספים לקונה
            success = await UserService.update_user_balance(escrow.buyer_id, refund_amount)
            
            if not success:
                logger.error(f"Failed to refund {refund_amount}₪ to buyer {escrow.buyer_id}")
                return False
            
            # עדכון הסטטוס
            action_type = "admin_refund" if admin_id else "refund"
            
            result = await escrow_col.update_one(
                {"_id": escrow._id},
                {
                    "$set": {
                        "status": EscrowStatus.REFUNDED.value,
                        "released_at": datetime.utcnow(),
                        "released_to": "buyer",
                        "notes": notes,
                        "admin_id": admin_id
                    }
                }
            )
            
            if result.modified_count > 0:
                # לוג הפעולה
                await EscrowService._log_action(
                    escrow_id=escrow._id,
                    action=action_type,
                    amount=refund_amount,
                    from_account="escrow",
                    to_account="buyer",
                    performed_by=admin_id or 0,
                    notes=notes or f"החזר כספים לקונה {escrow.buyer_id}"
                )
                
                logger.info(f"Refunded {refund_amount}₪ to buyer {escrow.buyer_id} from escrow {escrow._id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to refund escrow for order {order_id}: {e}")
            return False
    
    @staticmethod
    async def mark_disputed(order_id: ObjectId, notes: Optional[str] = None) -> bool:
        """
        סימון Escrow כמחלוקת
        
        Args:
            order_id: מזהה ההזמנה
            notes: הערות
        
        Returns:
            True אם הצליח
        """
        try:
            escrow_col = await database.get_escrow_transactions_collection()
            
            # הארכת זמן השחרור המתוכנן
            new_release_time = datetime.utcnow() + timedelta(hours=Config.ESCROW_DISPUTE_EXTENSION_HOURS)
            
            result = await escrow_col.update_one(
                {"order_id": order_id, "status": EscrowStatus.HELD.value},
                {
                    "$set": {
                        "status": EscrowStatus.DISPUTED.value,
                        "release_scheduled_at": new_release_time,
                        "notes": notes
                    }
                }
            )
            
            if result.modified_count > 0:
                # קבלת פרטי ה-escrow
                escrow_data = await escrow_col.find_one({"order_id": order_id})
                if escrow_data:
                    await EscrowService._log_action(
                        escrow_id=escrow_data["_id"],
                        action="dispute",
                        amount=escrow_data["amount"],
                        from_account="escrow",
                        to_account="escrow",
                        notes=notes or "הזמנה נכנסה למחלוקת"
                    )
                
                logger.info(f"Marked escrow for order {order_id} as disputed")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to mark escrow as disputed for order {order_id}: {e}")
            return False
    
    # ==================== Query Methods ====================
    
    @staticmethod
    async def get_escrow(order_id: ObjectId) -> Optional[EscrowTransaction]:
        """קבלת Escrow לפי מזהה הזמנה"""
        escrow_col = await database.get_escrow_transactions_collection()
        escrow_data = await escrow_col.find_one({"order_id": order_id})
        
        if escrow_data:
            return EscrowTransaction.from_dict(escrow_data)
        return None
    
    @staticmethod
    async def get_escrow_by_id(escrow_id: ObjectId) -> Optional[EscrowTransaction]:
        """קבלת Escrow לפי מזהה"""
        escrow_col = await database.get_escrow_transactions_collection()
        escrow_data = await escrow_col.find_one({"_id": escrow_id})
        
        if escrow_data:
            return EscrowTransaction.from_dict(escrow_data)
        return None
    
    @staticmethod
    async def get_user_escrows(
        user_id: int,
        as_buyer: bool = True,
        status: Optional[EscrowStatus] = None,
        limit: int = 50
    ) -> List[EscrowTransaction]:
        """קבלת עסקאות Escrow של משתמש"""
        escrow_col = await database.get_escrow_transactions_collection()
        
        field = "buyer_id" if as_buyer else "seller_id"
        query = {field: user_id}
        
        if status:
            query["status"] = status.value
        
        cursor = escrow_col.find(query).sort("held_at", -1).limit(limit)
        
        escrows = []
        async for escrow_data in cursor:
            escrows.append(EscrowTransaction.from_dict(escrow_data))
        
        return escrows
    
    @staticmethod
    async def get_pending_releases() -> List[EscrowTransaction]:
        """קבלת עסקאות Escrow שממתינות לשחרור"""
        escrow_col = await database.get_escrow_transactions_collection()
        
        cursor = escrow_col.find({
            "status": EscrowStatus.HELD.value,
            "release_scheduled_at": {"$lte": datetime.utcnow()}
        }).sort("release_scheduled_at", 1)
        
        escrows = []
        async for escrow_data in cursor:
            escrows.append(EscrowTransaction.from_dict(escrow_data))
        
        return escrows
    
    @staticmethod
    async def get_all_held_escrows(limit: int = 100) -> List[EscrowTransaction]:
        """קבלת כל ה-Escrow המוחזקים"""
        escrow_col = await database.get_escrow_transactions_collection()
        
        cursor = escrow_col.find({
            "status": EscrowStatus.HELD.value
        }).sort("held_at", -1).limit(limit)
        
        escrows = []
        async for escrow_data in cursor:
            escrows.append(EscrowTransaction.from_dict(escrow_data))
        
        return escrows
    
    @staticmethod
    async def get_disputed_escrows(limit: int = 100) -> List[EscrowTransaction]:
        """קבלת כל ה-Escrow במחלוקת"""
        escrow_col = await database.get_escrow_transactions_collection()
        
        cursor = escrow_col.find({
            "status": EscrowStatus.DISPUTED.value
        }).sort("held_at", 1).limit(limit)
        
        escrows = []
        async for escrow_data in cursor:
            escrows.append(EscrowTransaction.from_dict(escrow_data))
        
        return escrows
    
    # ==================== Statistics & Reports ====================
    
    @staticmethod
    async def get_escrow_balance() -> float:
        """קבלת סה"כ כספים מוחזקים ב-Escrow"""
        escrow_col = await database.get_escrow_transactions_collection()
        
        pipeline = [
            {"$match": {"status": {"$in": [EscrowStatus.HELD.value, EscrowStatus.DISPUTED.value]}}},
            {"$group": {
                "_id": None,
                "total": {"$sum": "$amount"},
                "total_with_commission": {
                    "$sum": {"$add": ["$amount", "$buyer_commission"]}
                }
            }}
        ]
        
        cursor = escrow_col.aggregate(pipeline)
        results = await cursor.to_list(1)
        
        if results:
            return results[0].get("total_with_commission", 0)
        return 0.0
    
    @staticmethod
    async def get_escrow_stats() -> Dict[str, Any]:
        """קבלת סטטיסטיקות Escrow"""
        escrow_col = await database.get_escrow_transactions_collection()
        
        # סטטיסטיקות כלליות
        total_held = await escrow_col.count_documents({"status": EscrowStatus.HELD.value})
        total_disputed = await escrow_col.count_documents({"status": EscrowStatus.DISPUTED.value})
        total_released = await escrow_col.count_documents({"status": EscrowStatus.RELEASED.value})
        total_refunded = await escrow_col.count_documents({"status": EscrowStatus.REFUNDED.value})
        
        # סכומים
        pipeline = [
            {"$group": {
                "_id": "$status",
                "total_amount": {"$sum": "$amount"},
                "count": {"$sum": 1}
            }}
        ]
        
        cursor = escrow_col.aggregate(pipeline)
        by_status = await cursor.to_list(None)
        
        amounts_by_status = {}
        for item in by_status:
            amounts_by_status[item["_id"]] = item["total_amount"]
        
        # עסקאות ב-24 שעות אחרונות
        last_24h = datetime.utcnow() - timedelta(hours=24)
        recent_held = await escrow_col.count_documents({
            "held_at": {"$gte": last_24h}
        })
        recent_released = await escrow_col.count_documents({
            "released_at": {"$gte": last_24h},
            "status": EscrowStatus.RELEASED.value
        })
        
        # יתרת escrow נוכחית
        escrow_balance = await EscrowService.get_escrow_balance()
        
        return {
            "total_held": total_held,
            "total_disputed": total_disputed,
            "total_released": total_released,
            "total_refunded": total_refunded,
            "escrow_balance": escrow_balance,
            "amounts_by_status": amounts_by_status,
            "recent_24h_held": recent_held,
            "recent_24h_released": recent_released
        }
    
    @staticmethod
    async def get_daily_reconciliation_report() -> Dict[str, Any]:
        """דוח התאמה יומי"""
        escrow_col = await database.get_escrow_transactions_collection()
        
        today_start = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        yesterday_start = today_start - timedelta(days=1)
        
        # כספים שנכנסו היום
        pipeline_in = [
            {"$match": {"held_at": {"$gte": today_start}}},
            {"$group": {
                "_id": None,
                "total_in": {"$sum": {"$add": ["$amount", "$buyer_commission"]}},
                "count_in": {"$sum": 1}
            }}
        ]
        
        # כספים ששוחררו היום
        pipeline_out = [
            {"$match": {
                "released_at": {"$gte": today_start},
                "status": {"$in": [EscrowStatus.RELEASED.value, EscrowStatus.REFUNDED.value]}
            }},
            {"$group": {
                "_id": "$status",
                "total_out": {"$sum": "$amount"},
                "count_out": {"$sum": 1}
            }}
        ]
        
        cursor_in = escrow_col.aggregate(pipeline_in)
        results_in = await cursor_in.to_list(1)
        
        cursor_out = escrow_col.aggregate(pipeline_out)
        results_out = await cursor_out.to_list(None)
        
        total_in = results_in[0].get("total_in", 0) if results_in else 0
        count_in = results_in[0].get("count_in", 0) if results_in else 0
        
        total_released = 0
        total_refunded = 0
        count_released = 0
        count_refunded = 0
        
        for item in results_out:
            if item["_id"] == EscrowStatus.RELEASED.value:
                total_released = item.get("total_out", 0)
                count_released = item.get("count_out", 0)
            elif item["_id"] == EscrowStatus.REFUNDED.value:
                total_refunded = item.get("total_out", 0)
                count_refunded = item.get("count_out", 0)
        
        # יתרה נוכחית
        current_balance = await EscrowService.get_escrow_balance()
        
        return {
            "date": today_start.strftime("%Y-%m-%d"),
            "funds_in": {
                "total": total_in,
                "count": count_in
            },
            "funds_released": {
                "total": total_released,
                "count": count_released
            },
            "funds_refunded": {
                "total": total_refunded,
                "count": count_refunded
            },
            "current_balance": current_balance,
            "total_out": total_released + total_refunded,
            "net_change": total_in - (total_released + total_refunded)
        }
    
    @staticmethod
    async def get_escrow_logs(escrow_id: ObjectId, limit: int = 50) -> List[EscrowLog]:
        """קבלת לוגים של עסקת Escrow"""
        logs_col = await database.get_escrow_logs_collection()
        
        cursor = logs_col.find({"escrow_id": escrow_id}).sort("created_at", -1).limit(limit)
        
        logs = []
        async for log_data in cursor:
            logs.append(EscrowLog.from_dict(log_data))
        
        return logs
    
    # ==================== Auto-Release ====================
    
    @staticmethod
    async def process_auto_releases() -> int:
        """
        עיבוד שחרור אוטומטי של כספים
        מופעל ע"י background scheduler
        
        Returns:
            מספר העסקאות ששוחררו
        """
        if not Config.ESCROW_AUTO_RELEASE_ENABLED:
            return 0
        
        pending = await EscrowService.get_pending_releases()
        released_count = 0
        
        for escrow in pending:
            try:
                success = await EscrowService.release_to_seller(
                    order_id=escrow.order_id,
                    notes="שחרור אוטומטי אחרי 24 שעות"
                )
                
                if success:
                    released_count += 1
                    logger.info(f"Auto-released escrow {escrow._id} to seller {escrow.seller_id}")
                    
            except Exception as e:
                logger.error(f"Failed to auto-release escrow {escrow._id}: {e}")
        
        return released_count
    
    # ==================== Helper Methods ====================
    
    @staticmethod
    async def _log_action(
        escrow_id: ObjectId,
        action: str,
        amount: float,
        from_account: str,
        to_account: str,
        performed_by: Optional[int] = None,
        notes: Optional[str] = None
    ) -> None:
        """יצירת לוג פעולה"""
        try:
            logs_col = await database.get_escrow_logs_collection()
            
            log = EscrowLog(
                escrow_id=escrow_id,
                action=action,
                amount=amount,
                from_account=from_account,
                to_account=to_account,
                performed_by=performed_by,
                notes=notes
            )
            
            await logs_col.insert_one(log.to_dict())
            
        except Exception as e:
            logger.error(f"Failed to create escrow log: {e}")
    
    @staticmethod
    async def cancel_escrow(order_id: ObjectId, notes: Optional[str] = None) -> bool:
        """
        ביטול Escrow (ללא העברת כספים - למקרים מיוחדים)
        
        Args:
            order_id: מזהה ההזמנה
            notes: הערות
        
        Returns:
            True אם הצליח
        """
        try:
            escrow_col = await database.get_escrow_transactions_collection()
            
            result = await escrow_col.update_one(
                {"order_id": order_id, "status": EscrowStatus.HELD.value},
                {
                    "$set": {
                        "status": EscrowStatus.CANCELLED.value,
                        "released_at": datetime.utcnow(),
                        "notes": notes
                    }
                }
            )
            
            if result.modified_count > 0:
                logger.info(f"Cancelled escrow for order {order_id}")
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Failed to cancel escrow for order {order_id}: {e}")
            return False
