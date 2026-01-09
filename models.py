"""
מודלים לישויות המערכת (Users, Coupons, Orders, etc.)
"""
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Any
from enum import Enum
from bson import ObjectId


class UserRole(str, Enum):
    """סוגי משתמשים"""
    BUYER = "buyer"
    SELLER_UNVERIFIED = "seller_unverified"
    SELLER_VERIFIED = "seller_verified"
    ADMIN = "admin"


class CouponStatus(str, Enum):
    """סטטוסי קופונים"""
    ACTIVE = "active"
    SOLD = "sold"
    EXPIRED = "expired"
    DELETED = "deleted"


class OrderStatus(str, Enum):
    """סטטוסי הזמנות"""
    PENDING = "pending"
    COMPLETED = "completed"
    DISPUTED = "disputed"
    REFUNDED = "refunded"
    CONFIRMED = "confirmed"  # קונה אישר קבלת קופון


class P2POrderStatus(str, Enum):
    """סטטוסי הזמנות P2P - מודל לוח מודעות"""
    PENDING_BUYER_PAYMENT = "pending_buyer_payment"  # ממתין לתשלום הקונה
    PENDING_SELLER_CONFIRMATION = "pending_seller_confirmation"  # ממתין לאישור המוכר
    AUTO_DISPUTE = "auto_dispute"  # נכנס למחלוקת אוטומטית (timeout 12 שעות)
    MANUAL_DISPUTE = "manual_dispute"  # מחלוקת שנפתחה ידנית
    COMPLETED = "completed"  # הושלם בהצלחה
    CANCELLED = "cancelled"  # בוטל
    REFUNDED = "refunded"  # הוחזר (לא רלוונטי ל-P2P אבל נשמר לתאימות)


class TopupPaymentMethod(str, Enum):
    """אמצעי תשלום לטעינת קרדיט שירות"""
    TELEGRAM_STARS = "telegram_stars"
    EXTERNAL_LINK = "external_link"  # משולם/Upay
    CRYPTO = "crypto"
    BANK_TRANSFER = "bank_transfer"


class AuctionStatus(str, Enum):
    """סטטוסי מכרזים"""
    ACTIVE = "active"
    ENDED = "ended"
    CANCELLED = "cancelled"


class DisputeStatus(str, Enum):
    """סטטוסי מחלוקות"""
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED_REFUND = "resolved_refund"
    RESOLVED_NO_REFUND = "resolved_no_refund"
    CLOSED = "closed"


class PayoutStatus(str, Enum):
    """סטטוסי משיכות"""
    PENDING = "pending"
    APPROVED = "approved"
    REJECTED = "rejected"
    COMPLETED = "completed"


class EscrowStatus(str, Enum):
    """סטטוסי Escrow"""
    HELD = "held"  # כספים מוחזקים ב-Escrow
    RELEASED = "released"  # שוחררו למוכר
    REFUNDED = "refunded"  # הוחזרו לקונה
    DISPUTED = "disputed"  # במחלוקת
    CANCELLED = "cancelled"  # בוטל


class FraudEventType(str, Enum):
    """סוגי אירועי הונאה"""
    DUPLICATE_COUPON = "duplicate_coupon"  # קופון כפול
    HIGH_DISPUTE_RATE = "high_dispute_rate"  # אחוז מחלוקות גבוה
    HIGH_REFUND_RATE = "high_refund_rate"  # אחוז החזרים חריג
    SUSPICIOUS_PRICING = "suspicious_pricing"  # מחיר חשוד
    RAPID_ACTIVITY = "rapid_activity"  # פעילות מהירה מדי
    AUTO_BLOCK = "auto_block"  # חסימה אוטומטית
    MANUAL_REVIEW = "manual_review"  # סימון לבדיקה ידנית
    LARGE_TRANSACTION = "large_transaction"  # עסקה גדולה
    NEW_SELLER_LIMIT = "new_seller_limit"  # הגבלת מוכר חדש
    LOW_TRUST_SCORE = "low_trust_score"  # ניקוד אמינות נמוך
    SUSPICIOUS_PATTERN = "suspicious_pattern"  # דפוס חשוד כללי


class FraudRiskLevel(str, Enum):
    """רמות סיכון הונאה"""
    LOW = "low"  # נמוך
    MEDIUM = "medium"  # בינוני
    HIGH = "high"  # גבוה
    CRITICAL = "critical"  # קריטי


class SellerStatus(str, Enum):
    """סטטוסי אישור מוכר"""
    PENDING = "pending"  # ממתין לאישור אדמין
    APPROVED = "approved"  # אושר
    BLOCKED = "blocked"  # חסום


class User:
    """מודל משתמש"""
    
    def __init__(
        self,
        user_id: int,
        username: Optional[str] = None,
        first_name: Optional[str] = None,
        role: UserRole = UserRole.BUYER,
        balance: float = 0.0,
        frozen_balance: float = 0.0,
        business_name: Optional[str] = None,
        commercial_name: Optional[str] = None,  # שם מסחרי - מוצג בקופונים ובצ'אטים
        phone: Optional[str] = None,
        id_number: Optional[str] = None,
        is_verified: bool = False,
        seller_status: Optional[SellerStatus] = None,  # סטטוס אישור מוכר
        rating_average: float = 0.0,
        rating_count: int = 0,
        created_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
        # === שדות חדשים למודל לוח מודעות (Classifieds) ===
        service_credit_balance: float = 0.0,  # קרדיט שירות למוכרים (Non-Refundable)
        payment_methods: Optional[Dict[str, str]] = None,  # {bit: "050...", paybox: "https://..."}
        total_earned_real_money: float = 0.0,  # סה"כ כסף אמיתי שהמוכר קיבל מקונים (P2P)
        total_commissions_paid: float = 0.0,  # סה"כ עמלות שנוכו מהקרדיט
        timeout_violations: int = 0,  # כמה פעמים לא ענה בזמן (12 שעות)
        sales_count: int = 0,  # מספר מכירות מוצלחות
    ):
        self._id = _id
        self.user_id = user_id
        self.username = username
        self.first_name = first_name
        self.role = role
        self.balance = balance
        self.frozen_balance = frozen_balance
        self.business_name = business_name
        self.commercial_name = commercial_name
        self.phone = phone
        self.id_number = id_number
        self.is_verified = is_verified
        self.seller_status = seller_status
        self.rating_average = rating_average
        self.rating_count = rating_count
        self.created_at = created_at or datetime.utcnow()
        # === שדות חדשים ===
        self.service_credit_balance = service_credit_balance
        self.payment_methods = payment_methods or {}
        self.total_earned_real_money = total_earned_real_money
        self.total_commissions_paid = total_commissions_paid
        self.timeout_violations = timeout_violations
        self.sales_count = sales_count
    
    @property
    def display_name(self) -> str:
        """שם התצוגה - שם מסחרי אם קיים, אחרת שם עסק או שם פרטי"""
        return self.commercial_name or self.business_name or self.first_name or "משתמש"
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict עבור MongoDB"""
        data = {
            "user_id": self.user_id,
            "username": self.username,
            "first_name": self.first_name,
            "role": self.role.value if isinstance(self.role, Enum) else self.role,
            "balance": self.balance,
            "frozen_balance": self.frozen_balance,
            "business_name": self.business_name,
            "commercial_name": self.commercial_name,
            "phone": self.phone,
            "id_number": self.id_number,
            "is_verified": self.is_verified,
            "seller_status": self.seller_status.value if isinstance(self.seller_status, Enum) else self.seller_status,
            "rating_average": self.rating_average,
            "rating_count": self.rating_count,
            "created_at": self.created_at,
            # === שדות חדשים למודל לוח מודעות ===
            "service_credit_balance": self.service_credit_balance,
            "payment_methods": self.payment_methods,
            "total_earned_real_money": self.total_earned_real_money,
            "total_commissions_paid": self.total_commissions_paid,
            "timeout_violations": self.timeout_violations,
            "sales_count": self.sales_count,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "User":
        """יצירה מ-dict"""
        # Be resilient to legacy/unknown values (backward compatibility).
        seller_status_val = data.get("seller_status")
        try:
            seller_status = SellerStatus(seller_status_val) if seller_status_val else None
        except Exception:
            seller_status = None

        role_val = data.get("role", "buyer")
        try:
            role = UserRole(role_val)
        except Exception:
            # Legacy role mapping
            if role_val == "seller":
                is_verified = bool(data.get("is_verified")) or bool(data.get("verified")) or bool(data.get("id_number"))
                role = UserRole.SELLER_VERIFIED if is_verified else UserRole.SELLER_UNVERIFIED
            elif str(role_val).lower() in {"admin", "administrator"}:
                role = UserRole.ADMIN
            else:
                role = UserRole.BUYER
        
        return cls(
            _id=data.get("_id"),
            # Some legacy docs may still store the Telegram ID under `telegram_id`.
            user_id=data.get("user_id") or data.get("telegram_id"),
            username=data.get("username"),
            first_name=data.get("first_name"),
            role=role,
            balance=data.get("balance", 0.0),
            frozen_balance=data.get("frozen_balance", 0.0),
            business_name=data.get("business_name"),
            commercial_name=data.get("commercial_name"),
            phone=data.get("phone"),
            id_number=data.get("id_number"),
            is_verified=data.get("is_verified", data.get("verified", False)),
            seller_status=seller_status,
            rating_average=data.get("rating_average", 0.0),
            rating_count=data.get("rating_count", 0),
            created_at=data.get("created_at"),
            # === שדות חדשים למודל לוח מודעות ===
            service_credit_balance=data.get("service_credit_balance", 0.0),
            payment_methods=data.get("payment_methods", {}),
            total_earned_real_money=data.get("total_earned_real_money", 0.0),
            total_commissions_paid=data.get("total_commissions_paid", 0.0),
            timeout_violations=data.get("timeout_violations", 0),
            sales_count=data.get("sales_count", 0),
        )


class Coupon:
    """מודל קופון"""
    
    def __init__(
        self,
        seller_id: int,
        title: str,
        category: str,
        original_price: float,
        sale_price: float,
        description: Optional[str] = None,
        digital_code: Optional[str] = None,
        status: CouponStatus = CouponStatus.ACTIVE,
        created_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.seller_id = seller_id
        self.title = title
        self.category = category
        self.original_price = original_price
        self.sale_price = sale_price
        self.description = description
        self.digital_code = digital_code
        self.status = status
        self.created_at = created_at or datetime.utcnow()
        self.expires_at = expires_at
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict"""
        data = {
            "seller_id": self.seller_id,
            "title": self.title,
            "category": self.category,
            "original_price": self.original_price,
            "sale_price": self.sale_price,
            "description": self.description,
            "digital_code": self.digital_code,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "created_at": self.created_at,
            "expires_at": self.expires_at,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Coupon":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            seller_id=data["seller_id"],
            title=data["title"],
            category=data["category"],
            original_price=data["original_price"],
            sale_price=data["sale_price"],
            description=data.get("description"),
            digital_code=data.get("digital_code"),
            status=CouponStatus(data.get("status", "active")),
            created_at=data.get("created_at"),
            expires_at=data.get("expires_at"),
        )


class Order:
    """מודל הזמנה"""
    
    def __init__(
        self,
        buyer_id: int,
        seller_id: int,
        coupon_id: ObjectId,
        price_paid: float,
        buyer_commission: float,
        seller_commission: float,
        status: OrderStatus = OrderStatus.PENDING,
        created_at: Optional[datetime] = None,
        confirmed_at: Optional[datetime] = None,
        dispute_deadline: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.buyer_id = buyer_id
        self.seller_id = seller_id
        self.coupon_id = coupon_id
        self.price_paid = price_paid
        self.buyer_commission = buyer_commission
        self.seller_commission = seller_commission
        self.status = status
        self.created_at = created_at or datetime.utcnow()
        self.confirmed_at = confirmed_at
        self.dispute_deadline = dispute_deadline or (datetime.utcnow() + timedelta(hours=12))
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict"""
        data = {
            "buyer_id": self.buyer_id,
            "seller_id": self.seller_id,
            "coupon_id": self.coupon_id,
            "price_paid": self.price_paid,
            "buyer_commission": self.buyer_commission,
            "seller_commission": self.seller_commission,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "created_at": self.created_at,
            "confirmed_at": self.confirmed_at,
            "dispute_deadline": self.dispute_deadline,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Order":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            buyer_id=data["buyer_id"],
            seller_id=data["seller_id"],
            coupon_id=data["coupon_id"],
            price_paid=data["price_paid"],
            buyer_commission=data.get("buyer_commission", 0.0),
            seller_commission=data.get("seller_commission", 0.0),
            status=OrderStatus(data.get("status", "pending")),
            created_at=data.get("created_at"),
            confirmed_at=data.get("confirmed_at"),
            dispute_deadline=data.get("dispute_deadline"),
        )


class P2POrder:
    """מודל הזמנה P2P - מודל לוח מודעות"""
    
    def __init__(
        self,
        buyer_id: int,
        seller_id: int,
        coupon_id: ObjectId,
        price: float,  # מחיר המכירה (לא כולל עמלות - עמלות רק למוכר)
        status: P2POrderStatus = P2POrderStatus.PENDING_BUYER_PAYMENT,
        payment_method_used: Optional[str] = None,  # bit/paybox
        payment_proof_image: Optional[str] = None,  # file_id של צילום מסך
        seller_confirmation_deadline: Optional[datetime] = None,  # 12 שעות מהעלאת צילום
        seller_confirmed_at: Optional[datetime] = None,
        dispute_opened_at: Optional[datetime] = None,
        dispute_reason: Optional[str] = None,
        admin_notes: Optional[str] = None,
        commission_amount: float = 0.0,  # עמלה שנוכתה מהמוכר
        created_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.buyer_id = buyer_id
        self.seller_id = seller_id
        self.coupon_id = coupon_id
        self.price = price
        self.status = status
        self.payment_method_used = payment_method_used
        self.payment_proof_image = payment_proof_image
        self.seller_confirmation_deadline = seller_confirmation_deadline
        self.seller_confirmed_at = seller_confirmed_at
        self.dispute_opened_at = dispute_opened_at
        self.dispute_reason = dispute_reason
        self.admin_notes = admin_notes
        self.commission_amount = commission_amount
        self.created_at = created_at or datetime.utcnow()
        self.completed_at = completed_at
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict"""
        data = {
            "buyer_id": self.buyer_id,
            "seller_id": self.seller_id,
            "coupon_id": self.coupon_id,
            "price": self.price,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "payment_method_used": self.payment_method_used,
            "payment_proof_image": self.payment_proof_image,
            "seller_confirmation_deadline": self.seller_confirmation_deadline,
            "seller_confirmed_at": self.seller_confirmed_at,
            "dispute_opened_at": self.dispute_opened_at,
            "dispute_reason": self.dispute_reason,
            "admin_notes": self.admin_notes,
            "commission_amount": self.commission_amount,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "P2POrder":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            buyer_id=data["buyer_id"],
            seller_id=data["seller_id"],
            coupon_id=data["coupon_id"],
            price=data["price"],
            status=P2POrderStatus(data.get("status", "pending_buyer_payment")),
            payment_method_used=data.get("payment_method_used"),
            payment_proof_image=data.get("payment_proof_image"),
            seller_confirmation_deadline=data.get("seller_confirmation_deadline"),
            seller_confirmed_at=data.get("seller_confirmed_at"),
            dispute_opened_at=data.get("dispute_opened_at"),
            dispute_reason=data.get("dispute_reason"),
            admin_notes=data.get("admin_notes"),
            commission_amount=data.get("commission_amount", 0.0),
            created_at=data.get("created_at"),
            completed_at=data.get("completed_at"),
        )


class ServiceCreditTopup:
    """מודל טעינת קרדיט שירות למוכרים"""
    
    def __init__(
        self,
        seller_id: int,
        amount_paid_ils: float,  # כמה שילם באמת בשקלים
        credit_received: float,  # כמה קרדיט קיבל (כולל בונוס)
        payment_method: TopupPaymentMethod,
        platform_fee: float = 0.0,  # כמה הפלטפורמה (טלגרם/משולם) לקחה
        our_net_revenue: float = 0.0,  # כמה באמת נכנס לנו
        reference_code: Optional[str] = None,
        payment_proof_image: Optional[str] = None,
        status: str = "pending",  # pending, approved, rejected
        approved_by: Optional[int] = None,
        created_at: Optional[datetime] = None,
        processed_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.seller_id = seller_id
        self.amount_paid_ils = amount_paid_ils
        self.credit_received = credit_received
        self.payment_method = payment_method
        self.platform_fee = platform_fee
        self.our_net_revenue = our_net_revenue
        self.reference_code = reference_code
        self.payment_proof_image = payment_proof_image
        self.status = status
        self.approved_by = approved_by
        self.created_at = created_at or datetime.utcnow()
        self.processed_at = processed_at
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict"""
        data = {
            "seller_id": self.seller_id,
            "amount_paid_ils": self.amount_paid_ils,
            "credit_received": self.credit_received,
            "payment_method": self.payment_method.value if isinstance(self.payment_method, Enum) else self.payment_method,
            "platform_fee": self.platform_fee,
            "our_net_revenue": self.our_net_revenue,
            "reference_code": self.reference_code,
            "payment_proof_image": self.payment_proof_image,
            "status": self.status,
            "approved_by": self.approved_by,
            "created_at": self.created_at,
            "processed_at": self.processed_at,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ServiceCreditTopup":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            seller_id=data["seller_id"],
            amount_paid_ils=data["amount_paid_ils"],
            credit_received=data["credit_received"],
            payment_method=TopupPaymentMethod(data.get("payment_method", "external_link")),
            platform_fee=data.get("platform_fee", 0.0),
            our_net_revenue=data.get("our_net_revenue", 0.0),
            reference_code=data.get("reference_code"),
            payment_proof_image=data.get("payment_proof_image"),
            status=data.get("status", "pending"),
            approved_by=data.get("approved_by"),
            created_at=data.get("created_at"),
            processed_at=data.get("processed_at"),
        )


class Auction:
    """מודל מכרז"""
    
    def __init__(
        self,
        seller_id: int,
        coupon_id: ObjectId,
        starting_price: float,
        current_price: Optional[float] = None,
        current_bidder_id: Optional[int] = None,
        end_time: Optional[datetime] = None,
        status: AuctionStatus = AuctionStatus.ACTIVE,
        created_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.seller_id = seller_id
        self.coupon_id = coupon_id
        self.starting_price = starting_price
        self.current_price = current_price or starting_price
        self.current_bidder_id = current_bidder_id
        self.end_time = end_time or (datetime.utcnow() + timedelta(days=1))
        self.status = status
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict"""
        data = {
            "seller_id": self.seller_id,
            "coupon_id": self.coupon_id,
            "starting_price": self.starting_price,
            "current_price": self.current_price,
            "current_bidder_id": self.current_bidder_id,
            "end_time": self.end_time,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "created_at": self.created_at,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Auction":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            seller_id=data["seller_id"],
            coupon_id=data["coupon_id"],
            starting_price=data["starting_price"],
            current_price=data.get("current_price"),
            current_bidder_id=data.get("current_bidder_id"),
            end_time=data.get("end_time"),
            status=AuctionStatus(data.get("status", "active")),
            created_at=data.get("created_at"),
        )


class Review:
    """מודל ביקורת"""
    
    def __init__(
        self,
        seller_id: int,
        buyer_id: int,
        order_id: ObjectId,
        rating: int,  # 1-5
        comment: Optional[str] = None,
        created_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.seller_id = seller_id
        self.buyer_id = buyer_id
        self.order_id = order_id
        self.rating = max(1, min(5, rating))  # מוודא שהדירוג בין 1-5
        self.comment = comment[:15] if comment else None  # הגבלה ל-15 תווים
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict"""
        data = {
            "seller_id": self.seller_id,
            "buyer_id": self.buyer_id,
            "order_id": self.order_id,
            "rating": self.rating,
            "comment": self.comment,
            "created_at": self.created_at,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Review":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            seller_id=data["seller_id"],
            buyer_id=data["buyer_id"],
            order_id=data["order_id"],
            rating=data["rating"],
            comment=data.get("comment"),
            created_at=data.get("created_at"),
        )


class Dispute:
    """מודל מחלוקת"""
    
    def __init__(
        self,
        order_id: ObjectId,
        buyer_id: int,
        seller_id: int,
        reason: str,
        status: DisputeStatus = DisputeStatus.OPEN,
        admin_notes: Optional[str] = None,
        resolution: Optional[str] = None,
        created_at: Optional[datetime] = None,
        resolved_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.order_id = order_id
        self.buyer_id = buyer_id
        self.seller_id = seller_id
        self.reason = reason
        self.status = status
        self.admin_notes = admin_notes
        self.resolution = resolution
        self.created_at = created_at or datetime.utcnow()
        self.resolved_at = resolved_at
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict"""
        data = {
            "order_id": self.order_id,
            "buyer_id": self.buyer_id,
            "seller_id": self.seller_id,
            "reason": self.reason,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "admin_notes": self.admin_notes,
            "resolution": self.resolution,
            "created_at": self.created_at,
            "resolved_at": self.resolved_at,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Dispute":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            order_id=data["order_id"],
            buyer_id=data["buyer_id"],
            seller_id=data["seller_id"],
            reason=data["reason"],
            status=DisputeStatus(data.get("status", "open")),
            admin_notes=data.get("admin_notes"),
            resolution=data.get("resolution"),
            created_at=data.get("created_at"),
            resolved_at=data.get("resolved_at"),
        )


class Payout:
    """מודל משיכת כספים"""
    
    def __init__(
        self,
        seller_id: int,
        amount: float,
        commission: float,
        net_amount: float,
        status: PayoutStatus = PayoutStatus.PENDING,
        created_at: Optional[datetime] = None,
        processed_at: Optional[datetime] = None,
        admin_notes: Optional[str] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.seller_id = seller_id
        self.amount = amount
        self.commission = commission
        self.net_amount = net_amount
        self.status = status
        self.created_at = created_at or datetime.utcnow()
        self.processed_at = processed_at
        self.admin_notes = admin_notes
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict"""
        data = {
            "seller_id": self.seller_id,
            "amount": self.amount,
            "commission": self.commission,
            "net_amount": self.net_amount,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "created_at": self.created_at,
            "processed_at": self.processed_at,
            "admin_notes": self.admin_notes,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "Payout":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            seller_id=data["seller_id"],
            amount=data["amount"],
            commission=data.get("commission", 0.0),
            net_amount=data.get("net_amount", 0.0),
            status=PayoutStatus(data.get("status", "pending")),
            created_at=data.get("created_at"),
            processed_at=data.get("processed_at"),
            admin_notes=data.get("admin_notes"),
        )


class FraudLog:
    """מודל לוג אירועי הונאה"""
    
    def __init__(
        self,
        user_id: int,
        event_type: FraudEventType,
        risk_level: FraudRiskLevel = FraudRiskLevel.LOW,
        details: Optional[Dict[str, Any]] = None,
        reviewed: bool = False,
        reviewed_by: Optional[int] = None,
        reviewed_at: Optional[datetime] = None,
        review_notes: Optional[str] = None,
        created_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.user_id = user_id
        self.event_type = event_type
        self.risk_level = risk_level
        self.details = details or {}
        self.reviewed = reviewed
        self.reviewed_by = reviewed_by
        self.reviewed_at = reviewed_at
        self.review_notes = review_notes
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict עבור MongoDB"""
        data = {
            "user_id": self.user_id,
            "event_type": self.event_type.value if isinstance(self.event_type, Enum) else self.event_type,
            "risk_level": self.risk_level.value if isinstance(self.risk_level, Enum) else self.risk_level,
            "details": self.details,
            "reviewed": self.reviewed,
            "reviewed_by": self.reviewed_by,
            "reviewed_at": self.reviewed_at,
            "review_notes": self.review_notes,
            "created_at": self.created_at,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "FraudLog":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            user_id=data["user_id"],
            event_type=FraudEventType(data.get("event_type", "suspicious_pattern")),
            risk_level=FraudRiskLevel(data.get("risk_level", "low")),
            details=data.get("details", {}),
            reviewed=data.get("reviewed", False),
            reviewed_by=data.get("reviewed_by"),
            reviewed_at=data.get("reviewed_at"),
            review_notes=data.get("review_notes"),
            created_at=data.get("created_at"),
        )


class EscrowTransaction:
    """מודל עסקת Escrow"""
    
    def __init__(
        self,
        order_id: ObjectId,
        buyer_id: int,
        seller_id: int,
        amount: float,
        buyer_commission: float = 0.0,
        seller_commission: float = 0.0,
        status: EscrowStatus = EscrowStatus.HELD,
        held_at: Optional[datetime] = None,
        released_at: Optional[datetime] = None,
        released_to: Optional[str] = None,  # "buyer" or "seller"
        release_scheduled_at: Optional[datetime] = None,  # זמן שחרור מתוכנן
        notes: Optional[str] = None,
        admin_id: Optional[int] = None,  # אדמין שביצע פעולה ידנית
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.order_id = order_id
        self.buyer_id = buyer_id
        self.seller_id = seller_id
        self.amount = amount
        self.buyer_commission = buyer_commission
        self.seller_commission = seller_commission
        self.status = status
        self.held_at = held_at or datetime.utcnow()
        self.released_at = released_at
        self.released_to = released_to
        self.release_scheduled_at = release_scheduled_at or (datetime.utcnow() + timedelta(hours=24))
        self.notes = notes
        self.admin_id = admin_id
    
    @property
    def net_seller_amount(self) -> float:
        """סכום נטו שהמוכר מקבל"""
        return self.amount - self.seller_commission
    
    @property
    def total_buyer_paid(self) -> float:
        """סכום כולל ששילם הקונה"""
        return self.amount + self.buyer_commission
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict עבור MongoDB"""
        data = {
            "order_id": self.order_id,
            "buyer_id": self.buyer_id,
            "seller_id": self.seller_id,
            "amount": self.amount,
            "buyer_commission": self.buyer_commission,
            "seller_commission": self.seller_commission,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "held_at": self.held_at,
            "released_at": self.released_at,
            "released_to": self.released_to,
            "release_scheduled_at": self.release_scheduled_at,
            "notes": self.notes,
            "admin_id": self.admin_id,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EscrowTransaction":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            order_id=data["order_id"],
            buyer_id=data["buyer_id"],
            seller_id=data["seller_id"],
            amount=data["amount"],
            buyer_commission=data.get("buyer_commission", 0.0),
            seller_commission=data.get("seller_commission", 0.0),
            status=EscrowStatus(data.get("status", "held")),
            held_at=data.get("held_at"),
            released_at=data.get("released_at"),
            released_to=data.get("released_to"),
            release_scheduled_at=data.get("release_scheduled_at"),
            notes=data.get("notes"),
            admin_id=data.get("admin_id"),
        )


class EscrowLog:
    """מודל לוג פעולות Escrow - לשקיפות ומעקב"""
    
    def __init__(
        self,
        escrow_id: ObjectId,
        action: str,  # "hold", "release", "refund", "dispute", "admin_release", "admin_refund"
        amount: float,
        from_account: str,  # "buyer", "escrow", "system"
        to_account: str,  # "escrow", "seller", "buyer"
        performed_by: Optional[int] = None,  # user_id או admin_id
        notes: Optional[str] = None,
        created_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.escrow_id = escrow_id
        self.action = action
        self.amount = amount
        self.from_account = from_account
        self.to_account = to_account
        self.performed_by = performed_by
        self.notes = notes
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict עבור MongoDB"""
        data = {
            "escrow_id": self.escrow_id,
            "action": self.action,
            "amount": self.amount,
            "from_account": self.from_account,
            "to_account": self.to_account,
            "performed_by": self.performed_by,
            "notes": self.notes,
            "created_at": self.created_at,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "EscrowLog":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            escrow_id=data["escrow_id"],
            action=data["action"],
            amount=data["amount"],
            from_account=data["from_account"],
            to_account=data["to_account"],
            performed_by=data.get("performed_by"),
            notes=data.get("notes"),
            created_at=data.get("created_at"),
        )


# ==================== Payment Gateway Models ====================


class PaymentGateway(str, Enum):
    """ספקי סליקה נתמכים"""
    TRANZILA = "tranzila"
    CARDCOM = "cardcom"
    PAYPLUS = "payplus"
    MESHULAM = "meshulam"
    STRIPE = "stripe"  # אופציונלי לעתיד
    PAYPAL = "paypal"  # אופציונלי לעתיד


class PaymentTransactionStatus(str, Enum):
    """סטטוסי עסקאות תשלום"""
    PENDING = "pending"  # ממתין לתשלום
    PROCESSING = "processing"  # בעיבוד
    COMPLETED = "completed"  # הושלם בהצלחה
    FAILED = "failed"  # נכשל
    CANCELLED = "cancelled"  # בוטל
    REFUNDED = "refunded"  # הוחזר
    EXPIRED = "expired"  # פג תוקף


class PaymentTransactionType(str, Enum):
    """סוגי עסקאות תשלום"""
    DEPOSIT = "deposit"  # טעינת יתרה
    DIRECT_PURCHASE = "direct_purchase"  # קניה ישירה
    RECURRING = "recurring"  # תשלום חוזר
    PAYOUT = "payout"  # משיכה לבנק/פייפאל


class PayoutMethod(str, Enum):
    """שיטות משיכה למוכרים"""
    BANK_TRANSFER = "bank_transfer"  # העברה בנקאית
    PAYPAL = "paypal"  # PayPal
    PAYONEER = "payoneer"  # Payoneer
    BIT = "bit"  # ביט


class PayoutTransactionStatus(str, Enum):
    """סטטוסי משיכות"""
    PENDING = "pending"  # ממתין לאישור
    APPROVED = "approved"  # אושר
    PROCESSING = "processing"  # בעיבוד
    COMPLETED = "completed"  # הושלם
    FAILED = "failed"  # נכשל
    REJECTED = "rejected"  # נדחה


class PaymentTransaction:
    """מודל עסקת תשלום בכרטיס אשראי"""
    
    def __init__(
        self,
        user_id: int,
        gateway: PaymentGateway,
        transaction_type: PaymentTransactionType,
        amount: float,
        currency: str = "ILS",
        status: PaymentTransactionStatus = PaymentTransactionStatus.PENDING,
        gateway_transaction_id: Optional[str] = None,
        card_last4: Optional[str] = None,
        card_brand: Optional[str] = None,
        card_token: Optional[str] = None,  # טוקן לשמירת כרטיס
        description: Optional[str] = None,
        order_id: Optional[ObjectId] = None,  # אם זו קניה ישירה
        payment_url: Optional[str] = None,  # URL לדף תשלום
        webhook_received: bool = False,
        metadata: Optional[Dict[str, Any]] = None,
        error_message: Optional[str] = None,
        created_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        expires_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.user_id = user_id
        self.gateway = gateway
        self.transaction_type = transaction_type
        self.amount = amount
        self.currency = currency
        self.status = status
        self.gateway_transaction_id = gateway_transaction_id
        self.card_last4 = card_last4
        self.card_brand = card_brand
        self.card_token = card_token
        self.description = description
        self.order_id = order_id
        self.payment_url = payment_url
        self.webhook_received = webhook_received
        self.metadata = metadata or {}
        self.error_message = error_message
        self.created_at = created_at or datetime.utcnow()
        self.completed_at = completed_at
        self.expires_at = expires_at or (datetime.utcnow() + timedelta(minutes=30))
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict עבור MongoDB"""
        data = {
            "user_id": self.user_id,
            "gateway": self.gateway.value if isinstance(self.gateway, Enum) else self.gateway,
            "transaction_type": self.transaction_type.value if isinstance(self.transaction_type, Enum) else self.transaction_type,
            "amount": self.amount,
            "currency": self.currency,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "gateway_transaction_id": self.gateway_transaction_id,
            "card_last4": self.card_last4,
            "card_brand": self.card_brand,
            "card_token": self.card_token,
            "description": self.description,
            "order_id": self.order_id,
            "payment_url": self.payment_url,
            "webhook_received": self.webhook_received,
            "metadata": self.metadata,
            "error_message": self.error_message,
            "created_at": self.created_at,
            "completed_at": self.completed_at,
            "expires_at": self.expires_at,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PaymentTransaction":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            user_id=data["user_id"],
            gateway=PaymentGateway(data.get("gateway", "tranzila")),
            transaction_type=PaymentTransactionType(data.get("transaction_type", "deposit")),
            amount=data["amount"],
            currency=data.get("currency", "ILS"),
            status=PaymentTransactionStatus(data.get("status", "pending")),
            gateway_transaction_id=data.get("gateway_transaction_id"),
            card_last4=data.get("card_last4"),
            card_brand=data.get("card_brand"),
            card_token=data.get("card_token"),
            description=data.get("description"),
            order_id=data.get("order_id"),
            payment_url=data.get("payment_url"),
            webhook_received=data.get("webhook_received", False),
            metadata=data.get("metadata", {}),
            error_message=data.get("error_message"),
            created_at=data.get("created_at"),
            completed_at=data.get("completed_at"),
            expires_at=data.get("expires_at"),
        )


class SavedCard:
    """מודל כרטיס שמור"""
    
    def __init__(
        self,
        user_id: int,
        gateway: PaymentGateway,
        card_token: str,
        card_last4: str,
        card_brand: str,  # Visa, Mastercard, etc.
        card_expiry: Optional[str] = None,  # MM/YY
        is_default: bool = False,
        nickname: Optional[str] = None,
        created_at: Optional[datetime] = None,
        last_used_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.user_id = user_id
        self.gateway = gateway
        self.card_token = card_token
        self.card_last4 = card_last4
        self.card_brand = card_brand
        self.card_expiry = card_expiry
        self.is_default = is_default
        self.nickname = nickname
        self.created_at = created_at or datetime.utcnow()
        self.last_used_at = last_used_at
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict עבור MongoDB"""
        data = {
            "user_id": self.user_id,
            "gateway": self.gateway.value if isinstance(self.gateway, Enum) else self.gateway,
            "card_token": self.card_token,
            "card_last4": self.card_last4,
            "card_brand": self.card_brand,
            "card_expiry": self.card_expiry,
            "is_default": self.is_default,
            "nickname": self.nickname,
            "created_at": self.created_at,
            "last_used_at": self.last_used_at,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SavedCard":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            user_id=data["user_id"],
            gateway=PaymentGateway(data.get("gateway", "tranzila")),
            card_token=data["card_token"],
            card_last4=data["card_last4"],
            card_brand=data["card_brand"],
            card_expiry=data.get("card_expiry"),
            is_default=data.get("is_default", False),
            nickname=data.get("nickname"),
            created_at=data.get("created_at"),
            last_used_at=data.get("last_used_at"),
        )


class PayoutTransaction:
    """מודל עסקת משיכה למוכר"""
    
    def __init__(
        self,
        seller_id: int,
        amount: float,
        fee: float,
        net_amount: float,
        method: PayoutMethod,
        status: PayoutTransactionStatus = PayoutTransactionStatus.PENDING,
        payout_details: Optional[Dict[str, Any]] = None,  # פרטי בנק/פייפאל
        gateway_reference: Optional[str] = None,
        processed_by: Optional[int] = None,  # admin_id
        notes: Optional[str] = None,
        created_at: Optional[datetime] = None,
        processed_at: Optional[datetime] = None,
        completed_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.seller_id = seller_id
        self.amount = amount
        self.fee = fee
        self.net_amount = net_amount
        self.method = method
        self.status = status
        self.payout_details = payout_details or {}
        self.gateway_reference = gateway_reference
        self.processed_by = processed_by
        self.notes = notes
        self.created_at = created_at or datetime.utcnow()
        self.processed_at = processed_at
        self.completed_at = completed_at
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict עבור MongoDB"""
        data = {
            "seller_id": self.seller_id,
            "amount": self.amount,
            "fee": self.fee,
            "net_amount": self.net_amount,
            "method": self.method.value if isinstance(self.method, Enum) else self.method,
            "status": self.status.value if isinstance(self.status, Enum) else self.status,
            "payout_details": self.payout_details,
            "gateway_reference": self.gateway_reference,
            "processed_by": self.processed_by,
            "notes": self.notes,
            "created_at": self.created_at,
            "processed_at": self.processed_at,
            "completed_at": self.completed_at,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "PayoutTransaction":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            seller_id=data["seller_id"],
            amount=data["amount"],
            fee=data.get("fee", 0),
            net_amount=data.get("net_amount", data["amount"]),
            method=PayoutMethod(data.get("method", "bank_transfer")),
            status=PayoutTransactionStatus(data.get("status", "pending")),
            payout_details=data.get("payout_details", {}),
            gateway_reference=data.get("gateway_reference"),
            processed_by=data.get("processed_by"),
            notes=data.get("notes"),
            created_at=data.get("created_at"),
            processed_at=data.get("processed_at"),
            completed_at=data.get("completed_at"),
        )


class DailyCardLimit:
    """מודל הגבלת סכום יומי לכרטיס"""
    
    def __init__(
        self,
        user_id: int,
        date: datetime,
        total_amount: float = 0.0,
        transaction_count: int = 0,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.user_id = user_id
        self.date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        self.total_amount = total_amount
        self.transaction_count = transaction_count
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict עבור MongoDB"""
        data = {
            "user_id": self.user_id,
            "date": self.date,
            "total_amount": self.total_amount,
            "transaction_count": self.transaction_count,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "DailyCardLimit":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            user_id=data["user_id"],
            date=data["date"],
            total_amount=data.get("total_amount", 0.0),
            transaction_count=data.get("transaction_count", 0),
        )


# ==================== Seller Dashboard Models ====================


class SellerAnalytics:
    """מודל אנליטיקס יומי למוכר - לשמירת סטטיסטיקות היסטוריות"""
    
    def __init__(
        self,
        seller_id: int,
        date: datetime,
        views: int = 0,
        sales: int = 0,
        revenue: float = 0.0,
        top_categories: Optional[List[str]] = None,
        created_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.seller_id = seller_id
        self.date = date.replace(hour=0, minute=0, second=0, microsecond=0)
        self.views = views
        self.sales = sales
        self.revenue = revenue
        self.top_categories = top_categories or []
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict עבור MongoDB"""
        data = {
            "seller_id": self.seller_id,
            "date": self.date,
            "views": self.views,
            "sales": self.sales,
            "revenue": self.revenue,
            "top_categories": self.top_categories,
            "created_at": self.created_at,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SellerAnalytics":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            seller_id=data["seller_id"],
            date=data["date"],
            views=data.get("views", 0),
            sales=data.get("sales", 0),
            revenue=data.get("revenue", 0.0),
            top_categories=data.get("top_categories", []),
            created_at=data.get("created_at"),
        )


class AlertType(str, Enum):
    """סוגי התראות"""
    SALE_THRESHOLD = "sale_threshold"  # סף מכירות
    NEGATIVE_REVIEW = "negative_review"  # ביקורת שלילית
    DAILY_SUMMARY = "daily_summary"  # סיכום יומי
    WEEKLY_SUMMARY = "weekly_summary"  # סיכום שבועי
    DISPUTE_OPENED = "dispute_opened"  # מחלוקת נפתחה
    LOW_STOCK = "low_stock"  # מלאי נמוך (לעתיד)


class SellerAlertSettings:
    """מודל הגדרות התראות למוכר"""
    
    def __init__(
        self,
        seller_id: int,
        sales_threshold_enabled: bool = False,
        sales_threshold_amount: int = 10,  # התראה אחרי X מכירות
        negative_review_alert: bool = True,  # התראה על ביקורת שלילית
        daily_summary: bool = False,  # סיכום יומי
        weekly_summary: bool = False,  # סיכום שבועי
        dispute_alert: bool = True,  # התראה על מחלוקת
        low_trust_score_alert: bool = True,  # התראה על ניקוד אמינות נמוך
        email: Optional[str] = None,  # אימייל לסיכומים (אופציונלי)
        created_at: Optional[datetime] = None,
        updated_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.seller_id = seller_id
        self.sales_threshold_enabled = sales_threshold_enabled
        self.sales_threshold_amount = sales_threshold_amount
        self.negative_review_alert = negative_review_alert
        self.daily_summary = daily_summary
        self.weekly_summary = weekly_summary
        self.dispute_alert = dispute_alert
        self.low_trust_score_alert = low_trust_score_alert
        self.email = email
        self.created_at = created_at or datetime.utcnow()
        self.updated_at = updated_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict עבור MongoDB"""
        data = {
            "seller_id": self.seller_id,
            "sales_threshold_enabled": self.sales_threshold_enabled,
            "sales_threshold_amount": self.sales_threshold_amount,
            "negative_review_alert": self.negative_review_alert,
            "daily_summary": self.daily_summary,
            "weekly_summary": self.weekly_summary,
            "dispute_alert": self.dispute_alert,
            "low_trust_score_alert": self.low_trust_score_alert,
            "email": self.email,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "SellerAlertSettings":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            seller_id=data["seller_id"],
            sales_threshold_enabled=data.get("sales_threshold_enabled", False),
            sales_threshold_amount=data.get("sales_threshold_amount", 10),
            negative_review_alert=data.get("negative_review_alert", True),
            daily_summary=data.get("daily_summary", False),
            weekly_summary=data.get("weekly_summary", False),
            dispute_alert=data.get("dispute_alert", True),
            low_trust_score_alert=data.get("low_trust_score_alert", True),
            email=data.get("email"),
            created_at=data.get("created_at"),
            updated_at=data.get("updated_at"),
        )


class ScheduledCoupon:
    """מודל קופון מתוזמן לפרסום"""
    
    def __init__(
        self,
        seller_id: int,
        coupon_data: Dict[str, Any],  # נתוני הקופון לפרסום
        scheduled_at: datetime,  # זמן פרסום מתוכנן
        status: str = "pending",  # pending, published, cancelled
        published_coupon_id: Optional[ObjectId] = None,
        created_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.seller_id = seller_id
        self.coupon_data = coupon_data
        self.scheduled_at = scheduled_at
        self.status = status
        self.published_coupon_id = published_coupon_id
        self.created_at = created_at or datetime.utcnow()
    
    def to_dict(self) -> Dict[str, Any]:
        """המרה ל-dict עבור MongoDB"""
        data = {
            "seller_id": self.seller_id,
            "coupon_data": self.coupon_data,
            "scheduled_at": self.scheduled_at,
            "status": self.status,
            "published_coupon_id": self.published_coupon_id,
            "created_at": self.created_at,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "ScheduledCoupon":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            seller_id=data["seller_id"],
            coupon_data=data["coupon_data"],
            scheduled_at=data["scheduled_at"],
            status=data.get("status", "pending"),
            published_coupon_id=data.get("published_coupon_id"),
            created_at=data.get("created_at"),
        )
