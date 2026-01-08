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
        phone: Optional[str] = None,
        id_number: Optional[str] = None,
        is_verified: bool = False,
        rating_average: float = 0.0,
        rating_count: int = 0,
        created_at: Optional[datetime] = None,
        _id: Optional[ObjectId] = None,
    ):
        self._id = _id
        self.user_id = user_id
        self.username = username
        self.first_name = first_name
        self.role = role
        self.balance = balance
        self.frozen_balance = frozen_balance
        self.business_name = business_name
        self.phone = phone
        self.id_number = id_number
        self.is_verified = is_verified
        self.rating_average = rating_average
        self.rating_count = rating_count
        self.created_at = created_at or datetime.utcnow()
    
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
            "phone": self.phone,
            "id_number": self.id_number,
            "is_verified": self.is_verified,
            "rating_average": self.rating_average,
            "rating_count": self.rating_count,
            "created_at": self.created_at,
        }
        if self._id:
            data["_id"] = self._id
        return data
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "User":
        """יצירה מ-dict"""
        return cls(
            _id=data.get("_id"),
            user_id=data["user_id"],
            username=data.get("username"),
            first_name=data.get("first_name"),
            role=UserRole(data.get("role", "buyer")),
            balance=data.get("balance", 0.0),
            frozen_balance=data.get("frozen_balance", 0.0),
            business_name=data.get("business_name"),
            phone=data.get("phone"),
            id_number=data.get("id_number"),
            is_verified=data.get("is_verified", False),
            rating_average=data.get("rating_average", 0.0),
            rating_count=data.get("rating_count", 0),
            created_at=data.get("created_at"),
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
