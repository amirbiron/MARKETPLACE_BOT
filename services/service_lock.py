"""
MongoDB-backed distributed lock (lease + TTL) to ensure only one bot instance
connects to Telegram at a time.

This is designed for platforms like Render where multiple instances can briefly
overlap during deploys/restarts.
"""

from __future__ import annotations

import atexit
import logging
import os
import random
import socket
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Optional

from pymongo import MongoClient, ReturnDocument
from pymongo.errors import DuplicateKeyError

logger = logging.getLogger(__name__)


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "y", "on"}


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or not raw.strip():
        return default
    try:
        return int(raw)
    except ValueError:
        return default


@dataclass(frozen=True)
class LockSettings:
    service_id: str
    instance_id: str
    host: str
    lease_seconds: int = 60
    heartbeat_interval_seconds: int = 0  # 0 => auto (40% of lease, min 5)
    wait_for_acquire: bool = False
    acquire_max_wait_seconds: int = 0  # 0 => no limit (only if wait_for_acquire=True)
    wait_min_seconds: int = 15
    wait_max_seconds: int = 45

    @staticmethod
    def from_env(*, default_service_id: str) -> "LockSettings":
        service_id = os.getenv("SERVICE_ID") or os.getenv("RENDER_SERVICE_NAME") or default_service_id
        instance_id = (
            os.getenv("RENDER_INSTANCE_ID")
            or os.getenv("HOSTNAME")
            or f"{socket.gethostname()}:{os.getpid()}"
        )
        host = os.getenv("RENDER_SERVICE_NAME") or socket.gethostname()

        lease_seconds = max(10, _env_int("LOCK_LEASE_SECONDS", 60))
        hb = _env_int("LOCK_HEARTBEAT_INTERVAL", 0)
        if hb <= 0:
            hb = max(5, int(lease_seconds * 0.4))

        wait_for_acquire = _env_bool("LOCK_WAIT_FOR_ACQUIRE", False)
        acquire_max_wait_seconds = max(0, _env_int("LOCK_ACQUIRE_MAX_WAIT", 0))
        wait_min_seconds = max(1, _env_int("LOCK_WAIT_MIN_SECONDS", 15))
        wait_max_seconds = max(wait_min_seconds, _env_int("LOCK_WAIT_MAX_SECONDS", 45))

        return LockSettings(
            service_id=service_id,
            instance_id=instance_id,
            host=host,
            lease_seconds=lease_seconds,
            heartbeat_interval_seconds=hb,
            wait_for_acquire=wait_for_acquire,
            acquire_max_wait_seconds=acquire_max_wait_seconds,
            wait_min_seconds=wait_min_seconds,
            wait_max_seconds=wait_max_seconds,
        )


class MongoServiceLock:
    """
    A single-document lease stored in MongoDB.

    Collection: bot_locks
    Document _id: SERVICE_ID
    """

    def __init__(self, mongo_uri: str, db_name: str, settings: LockSettings):
        self._settings = settings

        # Short timeouts to avoid hanging during deploy.
        self._client = MongoClient(
            mongo_uri,
            serverSelectionTimeoutMS=5_000,
            connectTimeoutMS=5_000,
            socketTimeoutMS=10_000,
        )
        self._db = self._client[db_name]
        self._coll = self._db["bot_locks"]

        self._acquired = False
        self._stop = threading.Event()
        self._hb_thread: Optional[threading.Thread] = None

        # Ensure TTL index so orphaned locks expire automatically.
        # expireAfterSeconds=0 means "expire at expiresAt".
        try:
            self._coll.create_index("expiresAt", expireAfterSeconds=0, name="expiresAt_ttl")
        except Exception as e:
            logger.warning(f"Failed to ensure TTL index for lock: {e}")

        # Always attempt release on normal interpreter shutdown.
        atexit.register(self.release)

    @property
    def settings(self) -> LockSettings:
        return self._settings

    @property
    def is_acquired(self) -> bool:
        return self._acquired

    def _lease_expires_at(self, now: Optional[datetime] = None) -> datetime:
        now = now or _utcnow()
        return now + timedelta(seconds=self._settings.lease_seconds)

    def try_acquire(self) -> bool:
        """
        Attempt to acquire the lock once.
        Returns True if acquired, False otherwise.
        """
        now = _utcnow()
        expires_at = self._lease_expires_at(now)

        doc = {
            "_id": self._settings.service_id,
            "owner": self._settings.instance_id,
            "host": self._settings.host,
            "expiresAt": expires_at,
            "updatedAt": now,
            "createdAt": now,
        }

        # Fast path: try to insert the lock doc.
        try:
            self._coll.insert_one(doc)
            self._acquired = True
            logger.info(
                f"Acquired lock (insert) service_id={self._settings.service_id} owner={self._settings.instance_id}"
            )
            return True
        except DuplicateKeyError:
            pass
        except Exception as e:
            logger.warning(f"Lock insert attempt failed: {e}")

        # If we already own it (e.g., restart), renew it.
        try:
            renewed = self._coll.find_one_and_update(
                {"_id": self._settings.service_id, "owner": self._settings.instance_id},
                {"$set": {"expiresAt": expires_at, "updatedAt": now, "host": self._settings.host}},
                return_document=ReturnDocument.AFTER,
            )
            if renewed:
                self._acquired = True
                logger.info(
                    f"Acquired lock (renew) service_id={self._settings.service_id} owner={self._settings.instance_id}"
                )
                return True
        except Exception as e:
            logger.warning(f"Lock renew attempt failed: {e}")

        # Try steal if expired.
        try:
            stolen = self._coll.find_one_and_update(
                {"_id": self._settings.service_id, "expiresAt": {"$lte": now}},
                {
                    "$set": {
                        "owner": self._settings.instance_id,
                        "host": self._settings.host,
                        "expiresAt": expires_at,
                        "updatedAt": now,
                    },
                    "$setOnInsert": {"createdAt": now},
                },
                return_document=ReturnDocument.AFTER,
            )
            if stolen and stolen.get("owner") == self._settings.instance_id:
                self._acquired = True
                logger.info(
                    f"Acquired lock (steal) service_id={self._settings.service_id} owner={self._settings.instance_id}"
                )
                return True
        except Exception as e:
            logger.warning(f"Lock steal attempt failed: {e}")

        return False

    def wait_until_acquired(self) -> None:
        """
        Block until the lock is acquired according to environment config.
        Starts heartbeat once acquired.
        """
        started = time.monotonic()

        while not self.try_acquire():
            if self._settings.wait_for_acquire:
                if self._settings.acquire_max_wait_seconds > 0:
                    elapsed = time.monotonic() - started
                    if elapsed >= self._settings.acquire_max_wait_seconds:
                        logger.warning(
                            "Lock not acquired within max wait; exiting cleanly "
                            f"(service_id={self._settings.service_id})"
                        )
                        raise SystemExit(0)

                time.sleep(2.0 + random.random())  # short retry w/ jitter
            else:
                # Passive wait (prevents restart loops on platforms like Render).
                wait_s = random.randint(self._settings.wait_min_seconds, self._settings.wait_max_seconds)
                logger.info(
                    "Lock held by another instance; waiting passively "
                    f"{wait_s}s (service_id={self._settings.service_id})"
                )
                time.sleep(wait_s)

        self._start_heartbeat()

    def _start_heartbeat(self) -> None:
        if self._hb_thread and self._hb_thread.is_alive():
            return

        self._stop.clear()
        self._hb_thread = threading.Thread(
            target=self._heartbeat_loop,
            name="mongo-lock-heartbeat",
            daemon=True,
        )
        self._hb_thread.start()

    def _heartbeat_loop(self) -> None:
        interval = max(1, self._settings.heartbeat_interval_seconds)
        while not self._stop.is_set():
            time.sleep(interval)

            now = _utcnow()
            expires_at = self._lease_expires_at(now)
            try:
                result = self._coll.update_one(
                    {"_id": self._settings.service_id, "owner": self._settings.instance_id},
                    {"$set": {"expiresAt": expires_at, "updatedAt": now, "host": self._settings.host}},
                )
                if result.matched_count == 0:
                    logger.error(
                        "Lost lock ownership; exiting to prevent Telegram Conflict "
                        f"(service_id={self._settings.service_id})"
                    )
                    os._exit(0)
            except Exception as e:
                # If we can't renew, don't immediately exit: transient network can happen.
                # But if the lease expires, another instance may take over; next update will detect.
                logger.warning(f"Lock heartbeat failed: {e}")

    def release(self) -> None:
        """
        Release the lock if currently owned by this instance.
        """
        self._stop.set()
        if not self._acquired:
            return

        try:
            res = self._coll.delete_one({"_id": self._settings.service_id, "owner": self._settings.instance_id})
            if res.deleted_count:
                logger.info(
                    f"Released lock service_id={self._settings.service_id} owner={self._settings.instance_id}"
                )
        except Exception as e:
            logger.warning(f"Failed to release lock: {e}")
        finally:
            self._acquired = False

