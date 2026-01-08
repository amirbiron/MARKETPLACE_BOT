"""
שירות סליקה - אינטגרציה עם ספקי תשלום
Payment Gateway Service - Integration with payment providers
"""
from typing import Optional, List, Dict, Any, Tuple
from datetime import datetime, timedelta
from bson import ObjectId
import aiohttp
import hashlib
import hmac
import json
import logging
import urllib.parse

import database
from models import (
    PaymentTransaction, PaymentTransactionStatus, PaymentTransactionType,
    PaymentGateway, SavedCard, DailyCardLimit
)
from config import Config
from services.user_service import UserService
from services.notification_service import NotificationService

logger = logging.getLogger(__name__)


class PaymentGatewayService:
    """
    שירות אינטגרציה עם ספקי סליקה
    
    תומך ב:
    - Tranzila
    - CardCom
    - PayPlus
    - Meshulam
    """
    
    # ==================== Transaction Creation ====================
    
    @staticmethod
    async def create_payment(
        user_id: int,
        amount: float,
        transaction_type: PaymentTransactionType = PaymentTransactionType.DEPOSIT,
        description: Optional[str] = None,
        order_id: Optional[ObjectId] = None,
        save_card: bool = False,
        use_saved_card_id: Optional[str] = None
    ) -> Tuple[Optional[PaymentTransaction], Optional[str]]:
        """
        יצירת תשלום חדש
        
        Args:
            user_id: מזהה המשתמש
            amount: סכום התשלום
            transaction_type: סוג העסקה
            description: תיאור העסקה
            order_id: מזהה הזמנה (לקניה ישירה)
            save_card: האם לשמור את הכרטיס
            use_saved_card_id: מזהה כרטיס שמור לשימוש
        
        Returns:
            Tuple[PaymentTransaction, error_message]
        """
        try:
            # בדיקת הגבלות
            error = await PaymentGatewayService._validate_payment(user_id, amount)
            if error:
                return None, error
            
            gateway = PaymentGateway(Config.PAYMENT_GATEWAY)
            
            # יצירת עסקה
            txn_col = await database.get_payment_gateway_transactions_collection()
            
            transaction = PaymentTransaction(
                user_id=user_id,
                gateway=gateway,
                transaction_type=transaction_type,
                amount=amount,
                description=description or f"טעינת יתרה {amount}₪",
                order_id=order_id,
                metadata={
                    "save_card": save_card,
                    "saved_card_id": use_saved_card_id
                }
            )
            
            result = await txn_col.insert_one(transaction.to_dict())
            transaction._id = result.inserted_id
            
            # אם משתמשים בכרטיס שמור
            if use_saved_card_id:
                payment_result = await PaymentGatewayService._charge_saved_card(
                    transaction, use_saved_card_id
                )
                if payment_result.get("success"):
                    return transaction, None
                else:
                    return None, payment_result.get("error", "שגיאה בחיוב הכרטיס")
            
            # יצירת URL לתשלום
            payment_url = await PaymentGatewayService._create_payment_url(transaction, save_card)
            
            if payment_url:
                # עדכון ה-URL בעסקה
                await txn_col.update_one(
                    {"_id": transaction._id},
                    {"$set": {"payment_url": payment_url}}
                )
                transaction.payment_url = payment_url
                return transaction, None
            else:
                return None, "שגיאה ביצירת קישור תשלום"
                
        except Exception as e:
            logger.error(f"Error creating payment: {e}")
            return None, f"שגיאה ביצירת תשלום: {str(e)}"
    
    @staticmethod
    async def _validate_payment(user_id: int, amount: float) -> Optional[str]:
        """בדיקת תקינות התשלום"""
        
        # בדיקה שסליקה מופעלת
        if not Config.PAYMENT_GATEWAY_ENABLED:
            return "סליקה אינה מופעלת במערכת"
        
        # בדיקת סכום מינימלי
        if amount < Config.MIN_CARD_PAYMENT:
            return f"סכום מינימלי לתשלום: {Config.MIN_CARD_PAYMENT}₪"
        
        # בדיקת סכום מקסימלי לעסקה
        if amount > Config.MAX_TRANSACTION_AMOUNT:
            return f"סכום מקסימלי לעסקה: {Config.MAX_TRANSACTION_AMOUNT}₪"
        
        # בדיקת הגבלה יומית
        limit_col = await database.get_daily_card_limits_collection()
        today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
        
        daily_usage = await limit_col.find_one({
            "user_id": user_id,
            "date": today
        })
        
        current_total = daily_usage.get("total_amount", 0) if daily_usage else 0
        
        if current_total + amount > Config.DAILY_CARD_LIMIT:
            remaining = Config.DAILY_CARD_LIMIT - current_total
            return f"חרגת מהמגבלה היומית. נותר: {remaining:.2f}₪ מתוך {Config.DAILY_CARD_LIMIT}₪"
        
        return None
    
    @staticmethod
    async def _create_payment_url(
        transaction: PaymentTransaction,
        save_card: bool = False
    ) -> Optional[str]:
        """יצירת URL לדף תשלום"""
        
        gateway = transaction.gateway
        
        if gateway == PaymentGateway.TRANZILA:
            return await PaymentGatewayService._create_tranzila_url(transaction, save_card)
        elif gateway == PaymentGateway.CARDCOM:
            return await PaymentGatewayService._create_cardcom_url(transaction, save_card)
        elif gateway == PaymentGateway.PAYPLUS:
            return await PaymentGatewayService._create_payplus_url(transaction, save_card)
        elif gateway == PaymentGateway.MESHULAM:
            return await PaymentGatewayService._create_meshulam_url(transaction, save_card)
        else:
            logger.error(f"Unsupported gateway: {gateway}")
            return None
    
    # ==================== Tranzila Integration ====================
    
    @staticmethod
    async def _create_tranzila_url(
        transaction: PaymentTransaction,
        save_card: bool = False
    ) -> Optional[str]:
        """יצירת קישור תשלום ב-Tranzila"""
        try:
            params = {
                "supplier": Config.TRANZILA_TERMINAL,
                "sum": str(transaction.amount),
                "currency": "1",  # ILS
                "tranmode": "VK",  # Internet transaction
                "cred_type": "1",  # Regular credit
                "TranzilaPW": Config.TRANZILA_PASSWORD,
                "pdesc": transaction.description or f"טעינת יתרה",
                "contact": str(transaction.user_id),
                "myid": str(transaction._id),
                "notify_url_address": f"{Config.WEBHOOK_BASE_URL}/webhook/tranzila",
                "success_url_address": f"{Config.WEBHOOK_BASE_URL}/payment/success",
                "fail_url_address": f"{Config.WEBHOOK_BASE_URL}/payment/fail",
            }
            
            # 3D Secure
            if Config.PAYMENT_3D_SECURE_ENABLED:
                params["eci"] = "7"  # 3D Secure
            
            # Token for card saving
            if save_card and Config.ALLOW_SAVE_CARD:
                params["TranzilaTK"] = "1"
            
            # Build URL
            query_string = urllib.parse.urlencode(params)
            payment_url = f"https://direct.tranzila.com/{Config.TRANZILA_TERMINAL}/iframe.php?{query_string}"
            
            return payment_url
            
        except Exception as e:
            logger.error(f"Error creating Tranzila URL: {e}")
            return None
    
    @staticmethod
    async def process_tranzila_webhook(data: Dict[str, Any]) -> bool:
        """עיבוד webhook מ-Tranzila"""
        try:
            transaction_id = data.get("myid")
            response_code = data.get("Response")
            
            if not transaction_id:
                logger.warning("Missing myid in Tranzila webhook")
                return False
            
            txn_col = await database.get_payment_gateway_transactions_collection()
            transaction = await txn_col.find_one({"_id": ObjectId(transaction_id)})
            
            if not transaction:
                logger.warning(f"Transaction not found: {transaction_id}")
                return False
            
            # Success response
            if response_code == "000":
                # Update transaction
                await txn_col.update_one(
                    {"_id": ObjectId(transaction_id)},
                    {
                        "$set": {
                            "status": PaymentTransactionStatus.COMPLETED.value,
                            "gateway_transaction_id": data.get("ConfirmationCode"),
                            "card_last4": data.get("ccno", "")[-4:] if data.get("ccno") else None,
                            "card_brand": data.get("cardtype"),
                            "webhook_received": True,
                            "completed_at": datetime.utcnow()
                        }
                    }
                )
                
                # Save card token if requested
                if data.get("TranzilaTK") and transaction.get("metadata", {}).get("save_card"):
                    await PaymentGatewayService._save_card(
                        user_id=transaction["user_id"],
                        gateway=PaymentGateway.TRANZILA,
                        card_token=data["TranzilaTK"],
                        card_last4=data.get("ccno", "")[-4:] if data.get("ccno") else "****",
                        card_brand=data.get("cardtype", "Unknown"),
                        card_expiry=data.get("expdate")
                    )
                
                # Add balance to user
                await PaymentGatewayService._complete_payment(
                    transaction["user_id"],
                    transaction["amount"],
                    str(transaction_id)
                )
                
                return True
            else:
                # Failed
                await txn_col.update_one(
                    {"_id": ObjectId(transaction_id)},
                    {
                        "$set": {
                            "status": PaymentTransactionStatus.FAILED.value,
                            "error_message": data.get("ErrorMessage", f"Error code: {response_code}"),
                            "webhook_received": True
                        }
                    }
                )
                return False
                
        except Exception as e:
            logger.error(f"Error processing Tranzila webhook: {e}")
            return False
    
    # ==================== CardCom Integration ====================
    
    @staticmethod
    async def _create_cardcom_url(
        transaction: PaymentTransaction,
        save_card: bool = False
    ) -> Optional[str]:
        """יצירת קישור תשלום ב-CardCom"""
        try:
            params = {
                "TerminalNumber": Config.CARDCOM_TERMINAL,
                "UserName": Config.CARDCOM_USERNAME,
                "APILevel": "10",
                "codepage": "65001",  # UTF-8
                "Operation": "1",  # Create LowProfile page
                "Language": "he",
                "CoinID": "1",  # ILS
                "SumToBill": str(transaction.amount),
                "ProductName": transaction.description or "טעינת יתרה",
                "SuccessRedirectUrl": f"{Config.WEBHOOK_BASE_URL}/payment/success",
                "FailedRedirectUrl": f"{Config.WEBHOOK_BASE_URL}/payment/fail",
                "WebHookUrl": f"{Config.WEBHOOK_BASE_URL}/webhook/cardcom",
                "ReturnValue": str(transaction._id),
            }
            
            if save_card and Config.ALLOW_SAVE_CARD:
                params["CreateToken"] = "true"
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    "https://secure.cardcom.solutions/Interface/LowProfile.aspx",
                    data=params
                ) as response:
                    result = await response.text()
                    
                    # Parse response
                    result_dict = dict(x.split("=") for x in result.split("&") if "=" in x)
                    
                    if result_dict.get("ResponseCode") == "0":
                        return result_dict.get("url")
                    else:
                        logger.error(f"CardCom error: {result_dict}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error creating CardCom URL: {e}")
            return None
    
    @staticmethod
    async def process_cardcom_webhook(data: Dict[str, Any]) -> bool:
        """עיבוד webhook מ-CardCom"""
        try:
            transaction_id = data.get("ReturnValue")
            response_code = data.get("ResponseCode")
            
            if not transaction_id:
                return False
            
            txn_col = await database.get_payment_gateway_transactions_collection()
            transaction = await txn_col.find_one({"_id": ObjectId(transaction_id)})
            
            if not transaction:
                return False
            
            if response_code == "0":
                await txn_col.update_one(
                    {"_id": ObjectId(transaction_id)},
                    {
                        "$set": {
                            "status": PaymentTransactionStatus.COMPLETED.value,
                            "gateway_transaction_id": data.get("InternalDealNumber"),
                            "card_last4": data.get("Last4Digits"),
                            "card_brand": data.get("CardBrand"),
                            "webhook_received": True,
                            "completed_at": datetime.utcnow()
                        }
                    }
                )
                
                # Save token if available
                if data.get("Token") and transaction.get("metadata", {}).get("save_card"):
                    await PaymentGatewayService._save_card(
                        user_id=transaction["user_id"],
                        gateway=PaymentGateway.CARDCOM,
                        card_token=data["Token"],
                        card_last4=data.get("Last4Digits", "****"),
                        card_brand=data.get("CardBrand", "Unknown"),
                        card_expiry=data.get("CardExpDate")
                    )
                
                await PaymentGatewayService._complete_payment(
                    transaction["user_id"],
                    transaction["amount"],
                    str(transaction_id)
                )
                
                return True
            else:
                await txn_col.update_one(
                    {"_id": ObjectId(transaction_id)},
                    {
                        "$set": {
                            "status": PaymentTransactionStatus.FAILED.value,
                            "error_message": data.get("Description", f"Error: {response_code}"),
                            "webhook_received": True
                        }
                    }
                )
                return False
                
        except Exception as e:
            logger.error(f"Error processing CardCom webhook: {e}")
            return False
    
    # ==================== PayPlus Integration ====================
    
    @staticmethod
    async def _create_payplus_url(
        transaction: PaymentTransaction,
        save_card: bool = False
    ) -> Optional[str]:
        """יצירת קישור תשלום ב-PayPlus"""
        try:
            headers = {
                "Authorization": json.dumps({
                    "api_key": Config.PAYPLUS_API_KEY,
                    "secret_key": Config.PAYPLUS_SECRET_KEY
                }),
                "Content-Type": "application/json"
            }
            
            payload = {
                "payment_page_uid": Config.PAYPLUS_TERMINAL_UID,
                "charge_method": 1,  # Credit card
                "amount": int(transaction.amount * 100),  # In agorot
                "currency_code": "ILS",
                "sendEmailApproval": False,
                "sendEmailFailure": False,
                "more_info": str(transaction._id),
                "customer": {
                    "customer_uid": str(transaction.user_id)
                },
                "items": [{
                    "name": transaction.description or "טעינת יתרה",
                    "quantity": 1,
                    "price": int(transaction.amount * 100),
                    "vat_type": 0
                }],
                "success_url": f"{Config.WEBHOOK_BASE_URL}/payment/success",
                "failure_url": f"{Config.WEBHOOK_BASE_URL}/payment/fail",
                "callback_url": f"{Config.WEBHOOK_BASE_URL}/webhook/payplus"
            }
            
            if save_card and Config.ALLOW_SAVE_CARD:
                payload["create_token"] = True
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{Config.PAYPLUS_API_URL}/PaymentPages/generateLink",
                    headers=headers,
                    json=payload
                ) as response:
                    result = await response.json()
                    
                    if result.get("results", {}).get("status") == "success":
                        return result["data"]["payment_page_link"]
                    else:
                        logger.error(f"PayPlus error: {result}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error creating PayPlus URL: {e}")
            return None
    
    @staticmethod
    async def process_payplus_webhook(data: Dict[str, Any]) -> bool:
        """עיבוד webhook מ-PayPlus"""
        try:
            transaction_id = data.get("more_info") or data.get("transaction", {}).get("more_info")
            status = data.get("transaction", {}).get("status_code")
            
            if not transaction_id:
                return False
            
            txn_col = await database.get_payment_gateway_transactions_collection()
            transaction = await txn_col.find_one({"_id": ObjectId(transaction_id)})
            
            if not transaction:
                return False
            
            if status == "000":
                txn_data = data.get("transaction", {})
                
                await txn_col.update_one(
                    {"_id": ObjectId(transaction_id)},
                    {
                        "$set": {
                            "status": PaymentTransactionStatus.COMPLETED.value,
                            "gateway_transaction_id": txn_data.get("uid"),
                            "card_last4": txn_data.get("four_digits"),
                            "card_brand": txn_data.get("brand_name"),
                            "webhook_received": True,
                            "completed_at": datetime.utcnow()
                        }
                    }
                )
                
                # Save token
                if txn_data.get("token_uid") and transaction.get("metadata", {}).get("save_card"):
                    await PaymentGatewayService._save_card(
                        user_id=transaction["user_id"],
                        gateway=PaymentGateway.PAYPLUS,
                        card_token=txn_data["token_uid"],
                        card_last4=txn_data.get("four_digits", "****"),
                        card_brand=txn_data.get("brand_name", "Unknown"),
                        card_expiry=txn_data.get("expiry_month", "") + "/" + txn_data.get("expiry_year", "")
                    )
                
                await PaymentGatewayService._complete_payment(
                    transaction["user_id"],
                    transaction["amount"],
                    str(transaction_id)
                )
                
                return True
            else:
                await txn_col.update_one(
                    {"_id": ObjectId(transaction_id)},
                    {
                        "$set": {
                            "status": PaymentTransactionStatus.FAILED.value,
                            "error_message": data.get("transaction", {}).get("status_description"),
                            "webhook_received": True
                        }
                    }
                )
                return False
                
        except Exception as e:
            logger.error(f"Error processing PayPlus webhook: {e}")
            return False
    
    # ==================== Meshulam Integration ====================
    
    @staticmethod
    async def _create_meshulam_url(
        transaction: PaymentTransaction,
        save_card: bool = False
    ) -> Optional[str]:
        """יצירת קישור תשלום ב-Meshulam"""
        try:
            params = {
                "pageCode": Config.MESHULAM_PAGE_CODE,
                "userId": Config.MESHULAM_USER_ID,
                "sum": str(transaction.amount),
                "description": transaction.description or "טעינת יתרה",
                "pageField[paymentNum]": "1",
                "successUrl": f"{Config.WEBHOOK_BASE_URL}/payment/success",
                "cancelUrl": f"{Config.WEBHOOK_BASE_URL}/payment/fail",
                "cField1": str(transaction._id),
                "cField2": str(transaction.user_id),
            }
            
            # Sign request
            sign_string = Config.MESHULAM_API_KEY + Config.MESHULAM_PAGE_CODE + str(transaction.amount)
            signature = hashlib.md5(sign_string.encode()).hexdigest()
            params["cs"] = signature
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{Config.MESHULAM_API_URL}/createPaymentProcess",
                    data=params
                ) as response:
                    result = await response.json()
                    
                    if result.get("status") == 1:
                        return result.get("data", {}).get("url")
                    else:
                        logger.error(f"Meshulam error: {result}")
                        return None
                        
        except Exception as e:
            logger.error(f"Error creating Meshulam URL: {e}")
            return None
    
    @staticmethod
    async def process_meshulam_webhook(data: Dict[str, Any]) -> bool:
        """עיבוד webhook מ-Meshulam"""
        try:
            transaction_id = data.get("cField1")
            status = data.get("status")
            
            if not transaction_id:
                return False
            
            txn_col = await database.get_payment_gateway_transactions_collection()
            transaction = await txn_col.find_one({"_id": ObjectId(transaction_id)})
            
            if not transaction:
                return False
            
            if status == "1":  # Success
                await txn_col.update_one(
                    {"_id": ObjectId(transaction_id)},
                    {
                        "$set": {
                            "status": PaymentTransactionStatus.COMPLETED.value,
                            "gateway_transaction_id": data.get("transactionId"),
                            "card_last4": data.get("cardSuffix"),
                            "card_brand": data.get("cardType"),
                            "webhook_received": True,
                            "completed_at": datetime.utcnow()
                        }
                    }
                )
                
                await PaymentGatewayService._complete_payment(
                    transaction["user_id"],
                    transaction["amount"],
                    str(transaction_id)
                )
                
                return True
            else:
                await txn_col.update_one(
                    {"_id": ObjectId(transaction_id)},
                    {
                        "$set": {
                            "status": PaymentTransactionStatus.FAILED.value,
                            "error_message": data.get("errorMessage", "Payment failed"),
                            "webhook_received": True
                        }
                    }
                )
                return False
                
        except Exception as e:
            logger.error(f"Error processing Meshulam webhook: {e}")
            return False
    
    # ==================== Saved Cards ====================
    
    @staticmethod
    async def _save_card(
        user_id: int,
        gateway: PaymentGateway,
        card_token: str,
        card_last4: str,
        card_brand: str,
        card_expiry: Optional[str] = None
    ) -> Optional[SavedCard]:
        """שמירת כרטיס"""
        try:
            if not Config.ALLOW_SAVE_CARD:
                return None
            
            cards_col = await database.get_saved_cards_collection()
            
            # בדיקה שלא חרגנו ממגבלת הכרטיסים
            user_cards = await cards_col.count_documents({"user_id": user_id})
            if user_cards >= Config.MAX_SAVED_CARDS_PER_USER:
                logger.info(f"User {user_id} reached max saved cards limit")
                return None
            
            # בדיקה שהכרטיס לא שמור כבר
            existing = await cards_col.find_one({"card_token": card_token})
            if existing:
                return SavedCard.from_dict(existing)
            
            # קביעה אם זה הכרטיס הראשון (יהיה ברירת מחדל)
            is_default = user_cards == 0
            
            saved_card = SavedCard(
                user_id=user_id,
                gateway=gateway,
                card_token=card_token,
                card_last4=card_last4,
                card_brand=card_brand,
                card_expiry=card_expiry,
                is_default=is_default
            )
            
            result = await cards_col.insert_one(saved_card.to_dict())
            saved_card._id = result.inserted_id
            
            logger.info(f"Saved card for user {user_id}: **** **** **** {card_last4}")
            return saved_card
            
        except Exception as e:
            logger.error(f"Error saving card: {e}")
            return None
    
    @staticmethod
    async def get_user_saved_cards(user_id: int) -> List[SavedCard]:
        """קבלת כרטיסים שמורים של משתמש"""
        try:
            cards_col = await database.get_saved_cards_collection()
            cursor = cards_col.find({"user_id": user_id}).sort("is_default", -1)
            
            cards = []
            async for card_data in cursor:
                cards.append(SavedCard.from_dict(card_data))
            
            return cards
            
        except Exception as e:
            logger.error(f"Error getting saved cards: {e}")
            return []
    
    @staticmethod
    async def delete_saved_card(user_id: int, card_id: str) -> bool:
        """מחיקת כרטיס שמור"""
        try:
            cards_col = await database.get_saved_cards_collection()
            
            result = await cards_col.delete_one({
                "_id": ObjectId(card_id),
                "user_id": user_id
            })
            
            return result.deleted_count > 0
            
        except Exception as e:
            logger.error(f"Error deleting saved card: {e}")
            return False
    
    @staticmethod
    async def set_default_card(user_id: int, card_id: str) -> bool:
        """הגדרת כרטיס כברירת מחדל"""
        try:
            cards_col = await database.get_saved_cards_collection()
            
            # הסרת ברירת מחדל מכל הכרטיסים
            await cards_col.update_many(
                {"user_id": user_id},
                {"$set": {"is_default": False}}
            )
            
            # הגדרת הכרטיס החדש כברירת מחדל
            result = await cards_col.update_one(
                {"_id": ObjectId(card_id), "user_id": user_id},
                {"$set": {"is_default": True}}
            )
            
            return result.modified_count > 0
            
        except Exception as e:
            logger.error(f"Error setting default card: {e}")
            return False
    
    @staticmethod
    async def _charge_saved_card(
        transaction: PaymentTransaction,
        card_id: str
    ) -> Dict[str, Any]:
        """חיוב כרטיס שמור"""
        try:
            cards_col = await database.get_saved_cards_collection()
            card_data = await cards_col.find_one({
                "_id": ObjectId(card_id),
                "user_id": transaction.user_id
            })
            
            if not card_data:
                return {"success": False, "error": "כרטיס לא נמצא"}
            
            card = SavedCard.from_dict(card_data)
            gateway = card.gateway
            
            # חיוב לפי ספק
            if gateway == PaymentGateway.TRANZILA:
                result = await PaymentGatewayService._charge_tranzila_token(
                    transaction, card.card_token
                )
            elif gateway == PaymentGateway.CARDCOM:
                result = await PaymentGatewayService._charge_cardcom_token(
                    transaction, card.card_token
                )
            elif gateway == PaymentGateway.PAYPLUS:
                result = await PaymentGatewayService._charge_payplus_token(
                    transaction, card.card_token
                )
            else:
                return {"success": False, "error": "ספק לא נתמך לחיוב טוקן"}
            
            # עדכון זמן שימוש אחרון
            if result.get("success"):
                await cards_col.update_one(
                    {"_id": ObjectId(card_id)},
                    {"$set": {"last_used_at": datetime.utcnow()}}
                )
            
            return result
            
        except Exception as e:
            logger.error(f"Error charging saved card: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def _charge_tranzila_token(
        transaction: PaymentTransaction,
        token: str
    ) -> Dict[str, Any]:
        """חיוב טוקן ב-Tranzila"""
        try:
            params = {
                "supplier": Config.TRANZILA_TERMINAL,
                "TranzilaPW": Config.TRANZILA_PASSWORD,
                "TranzilaTK": token,
                "sum": str(transaction.amount),
                "currency": "1",
                "tranmode": "VK",
                "myid": str(transaction._id),
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(Config.TRANZILA_API_URL, data=params) as response:
                    result_text = await response.text()
                    
                    # Parse response
                    result = dict(x.split("=") for x in result_text.split("&") if "=" in x)
                    
                    if result.get("Response") == "000":
                        txn_col = await database.get_payment_gateway_transactions_collection()
                        await txn_col.update_one(
                            {"_id": transaction._id},
                            {
                                "$set": {
                                    "status": PaymentTransactionStatus.COMPLETED.value,
                                    "gateway_transaction_id": result.get("ConfirmationCode"),
                                    "completed_at": datetime.utcnow()
                                }
                            }
                        )
                        
                        await PaymentGatewayService._complete_payment(
                            transaction.user_id,
                            transaction.amount,
                            str(transaction._id)
                        )
                        
                        return {"success": True}
                    else:
                        return {"success": False, "error": result.get("ErrorMessage", "חיוב נכשל")}
                        
        except Exception as e:
            logger.error(f"Error charging Tranzila token: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def _charge_cardcom_token(
        transaction: PaymentTransaction,
        token: str
    ) -> Dict[str, Any]:
        """חיוב טוקן ב-CardCom"""
        try:
            params = {
                "TerminalNumber": Config.CARDCOM_TERMINAL,
                "UserName": Config.CARDCOM_USERNAME,
                "Token": token,
                "SumToBill": str(transaction.amount),
                "CoinID": "1",
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(Config.CARDCOM_API_URL, data=params) as response:
                    result_text = await response.text()
                    result = dict(x.split("=") for x in result_text.split("&") if "=" in x)
                    
                    if result.get("ResponseCode") == "0":
                        txn_col = await database.get_payment_gateway_transactions_collection()
                        await txn_col.update_one(
                            {"_id": transaction._id},
                            {
                                "$set": {
                                    "status": PaymentTransactionStatus.COMPLETED.value,
                                    "gateway_transaction_id": result.get("InternalDealNumber"),
                                    "completed_at": datetime.utcnow()
                                }
                            }
                        )
                        
                        await PaymentGatewayService._complete_payment(
                            transaction.user_id,
                            transaction.amount,
                            str(transaction._id)
                        )
                        
                        return {"success": True}
                    else:
                        return {"success": False, "error": result.get("Description", "חיוב נכשל")}
                        
        except Exception as e:
            logger.error(f"Error charging CardCom token: {e}")
            return {"success": False, "error": str(e)}
    
    @staticmethod
    async def _charge_payplus_token(
        transaction: PaymentTransaction,
        token: str
    ) -> Dict[str, Any]:
        """חיוב טוקן ב-PayPlus"""
        try:
            headers = {
                "Authorization": json.dumps({
                    "api_key": Config.PAYPLUS_API_KEY,
                    "secret_key": Config.PAYPLUS_SECRET_KEY
                }),
                "Content-Type": "application/json"
            }
            
            payload = {
                "terminal_uid": Config.PAYPLUS_TERMINAL_UID,
                "customer_uid": str(transaction.user_id),
                "token_uid": token,
                "amount": int(transaction.amount * 100),
                "currency_code": "ILS",
                "more_info": str(transaction._id)
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(
                    f"{Config.PAYPLUS_API_URL}/Transactions/ChargeByToken",
                    headers=headers,
                    json=payload
                ) as response:
                    result = await response.json()
                    
                    if result.get("results", {}).get("status") == "success":
                        txn_col = await database.get_payment_gateway_transactions_collection()
                        await txn_col.update_one(
                            {"_id": transaction._id},
                            {
                                "$set": {
                                    "status": PaymentTransactionStatus.COMPLETED.value,
                                    "gateway_transaction_id": result.get("data", {}).get("transaction_uid"),
                                    "completed_at": datetime.utcnow()
                                }
                            }
                        )
                        
                        await PaymentGatewayService._complete_payment(
                            transaction.user_id,
                            transaction.amount,
                            str(transaction._id)
                        )
                        
                        return {"success": True}
                    else:
                        return {"success": False, "error": result.get("results", {}).get("description", "חיוב נכשל")}
                        
        except Exception as e:
            logger.error(f"Error charging PayPlus token: {e}")
            return {"success": False, "error": str(e)}
    
    # ==================== Payment Completion ====================
    
    @staticmethod
    async def _complete_payment(
        user_id: int,
        amount: float,
        transaction_id: str
    ) -> None:
        """השלמת תשלום - הוספת יתרה ושליחת התראה"""
        try:
            # עדכון הגבלה יומית
            await PaymentGatewayService._update_daily_limit(user_id, amount)
            
            # הוספת יתרה
            await UserService.update_user_balance(user_id, amount)
            
            # רישום טרנזקציה
            from database import db
            await db.transactions.insert_one({
                "user_id": user_id,
                "type": "credit_card_deposit",
                "amount": amount,
                "description": f"טעינת יתרה בכרטיס אשראי",
                "reference_id": transaction_id,
                "status": "completed",
                "created_at": datetime.utcnow()
            })
            
            # התראה למשתמש
            await NotificationService.send_notification(
                user_id=user_id,
                title="💳 תשלום בכרטיס אשראי",
                message=f"התשלום בסך {amount:.2f}₪ התקבל בהצלחה!\n"
                        f"היתרה שלך עודכנה.",
                notification_type="payment_received"
            )
            
            logger.info(f"Payment completed: {amount}₪ for user {user_id}")
            
        except Exception as e:
            logger.error(f"Error completing payment: {e}")
    
    @staticmethod
    async def _update_daily_limit(user_id: int, amount: float) -> None:
        """עדכון הגבלה יומית"""
        try:
            limit_col = await database.get_daily_card_limits_collection()
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            
            await limit_col.update_one(
                {"user_id": user_id, "date": today},
                {
                    "$inc": {
                        "total_amount": amount,
                        "transaction_count": 1
                    },
                    "$setOnInsert": {
                        "user_id": user_id,
                        "date": today
                    }
                },
                upsert=True
            )
            
        except Exception as e:
            logger.error(f"Error updating daily limit: {e}")
    
    # ==================== Transaction Queries ====================
    
    @staticmethod
    async def get_transaction(transaction_id: str) -> Optional[PaymentTransaction]:
        """קבלת עסקה לפי מזהה"""
        try:
            txn_col = await database.get_payment_gateway_transactions_collection()
            data = await txn_col.find_one({"_id": ObjectId(transaction_id)})
            
            if data:
                return PaymentTransaction.from_dict(data)
            return None
            
        except Exception as e:
            logger.error(f"Error getting transaction: {e}")
            return None
    
    @staticmethod
    async def get_user_transactions(
        user_id: int,
        status: Optional[PaymentTransactionStatus] = None,
        limit: int = 50
    ) -> List[PaymentTransaction]:
        """קבלת עסקאות של משתמש"""
        try:
            txn_col = await database.get_payment_gateway_transactions_collection()
            
            query = {"user_id": user_id}
            if status:
                query["status"] = status.value
            
            cursor = txn_col.find(query).sort("created_at", -1).limit(limit)
            
            transactions = []
            async for data in cursor:
                transactions.append(PaymentTransaction.from_dict(data))
            
            return transactions
            
        except Exception as e:
            logger.error(f"Error getting user transactions: {e}")
            return []
    
    @staticmethod
    async def get_pending_transactions() -> List[PaymentTransaction]:
        """קבלת עסקאות ממתינות"""
        try:
            txn_col = await database.get_payment_gateway_transactions_collection()
            
            cursor = txn_col.find({
                "status": PaymentTransactionStatus.PENDING.value,
                "expires_at": {"$gt": datetime.utcnow()}
            }).sort("created_at", 1)
            
            transactions = []
            async for data in cursor:
                transactions.append(PaymentTransaction.from_dict(data))
            
            return transactions
            
        except Exception as e:
            logger.error(f"Error getting pending transactions: {e}")
            return []
    
    @staticmethod
    async def expire_old_transactions() -> int:
        """סימון עסקאות שפג תוקפן"""
        try:
            txn_col = await database.get_payment_gateway_transactions_collection()
            
            result = await txn_col.update_many(
                {
                    "status": PaymentTransactionStatus.PENDING.value,
                    "expires_at": {"$lte": datetime.utcnow()}
                },
                {
                    "$set": {"status": PaymentTransactionStatus.EXPIRED.value}
                }
            )
            
            return result.modified_count
            
        except Exception as e:
            logger.error(f"Error expiring transactions: {e}")
            return 0
    
    # ==================== Statistics ====================
    
    @staticmethod
    async def get_payment_stats() -> Dict[str, Any]:
        """סטטיסטיקות תשלומים"""
        try:
            txn_col = await database.get_payment_gateway_transactions_collection()
            
            today = datetime.utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
            
            # עסקאות היום
            today_pipeline = [
                {"$match": {
                    "status": PaymentTransactionStatus.COMPLETED.value,
                    "completed_at": {"$gte": today}
                }},
                {"$group": {
                    "_id": None,
                    "count": {"$sum": 1},
                    "total": {"$sum": "$amount"}
                }}
            ]
            
            cursor = txn_col.aggregate(today_pipeline)
            today_results = await cursor.to_list(1)
            
            # עסקאות לפי ספק
            gateway_pipeline = [
                {"$match": {"status": PaymentTransactionStatus.COMPLETED.value}},
                {"$group": {
                    "_id": "$gateway",
                    "count": {"$sum": 1},
                    "total": {"$sum": "$amount"}
                }}
            ]
            
            cursor = txn_col.aggregate(gateway_pipeline)
            gateway_results = await cursor.to_list(None)
            
            return {
                "today": {
                    "count": today_results[0]["count"] if today_results else 0,
                    "total": today_results[0]["total"] if today_results else 0
                },
                "by_gateway": {r["_id"]: {"count": r["count"], "total": r["total"]} for r in gateway_results}
            }
            
        except Exception as e:
            logger.error(f"Error getting payment stats: {e}")
            return {"today": {"count": 0, "total": 0}, "by_gateway": {}}
    
    # ==================== Webhook Verification ====================
    
    @staticmethod
    def verify_webhook_signature(
        gateway: PaymentGateway,
        payload: bytes,
        signature: str
    ) -> bool:
        """אימות חתימת webhook"""
        try:
            if not Config.WEBHOOK_SECRET:
                return True  # Skip verification if no secret configured
            
            expected_signature = hmac.new(
                Config.WEBHOOK_SECRET.encode(),
                payload,
                hashlib.sha256
            ).hexdigest()
            
            return hmac.compare_digest(expected_signature, signature)
            
        except Exception as e:
            logger.error(f"Error verifying webhook signature: {e}")
            return False
