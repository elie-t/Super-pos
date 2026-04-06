"""
Authentication service — login, session management, current operator.
"""
import bcrypt
from dataclasses import dataclass
from datetime import datetime, timezone
from database.engine import get_session, init_db
from database.models.users import OperatorSession
from database.models.base import new_uuid


@dataclass
class OperatorInfo:
    """Detached snapshot of user data — lives beyond any DB session."""
    id: str
    username: str
    full_name: str
    role: str
    warehouse_id: str  = ""    # branch assigned to this user (cashiers)
    is_power_user: bool = False  # can perform restricted POS actions without password


class AuthService:
    """Singleton-style service; holds the active operator for the app lifetime."""

    _current_user: OperatorInfo | None = None
    _current_session_id: str | None = None

    @classmethod
    def login(cls, username: str, password: str) -> tuple[bool, str]:
        """Returns (success, error_message)."""
        init_db()  # ensures all models are registered
        session = get_session()
        try:
            from database.models.users import User
            user = session.query(User).filter_by(username=username.strip()).first()
            if not user:
                return False, "Invalid username or password."
            if not user.is_active:
                return False, "Account is disabled. Contact your manager."

            if not bcrypt.checkpw(password.encode(), user.password_hash.encode()):
                return False, "Invalid username or password."

            # Snapshot attributes before closing session
            op_info = OperatorInfo(
                id=user.id,
                username=user.username,
                full_name=user.full_name,
                role=user.role,
                warehouse_id=user.warehouse_id or "",
                is_power_user=bool(getattr(user, "is_power_user", False)),
            )

            # Record session start
            op_session = OperatorSession(
                id=new_uuid(),
                user_id=user.id,
                started_at=datetime.now(timezone.utc).isoformat(),
            )
            session.add(op_session)
            session.commit()

            cls._current_user = op_info
            cls._current_session_id = op_session.id
            return True, ""

        except Exception as exc:
            session.rollback()
            return False, f"Login error: {exc}"
        finally:
            session.close()

    @classmethod
    def logout(cls) -> None:
        if not cls._current_session_id:
            return
        session = get_session()
        try:
            op_session = session.get(OperatorSession, cls._current_session_id)
            if op_session:
                op_session.ended_at = datetime.now(timezone.utc).isoformat()
                session.commit()
        finally:
            session.close()
        cls._current_user = None
        cls._current_session_id = None

    @classmethod
    def current_user(cls) -> OperatorInfo | None:
        return cls._current_user

    @classmethod
    def is_logged_in(cls) -> bool:
        return cls._current_user is not None

    @classmethod
    def has_role(cls, *roles: str) -> bool:
        if not cls._current_user:
            return False
        return cls._current_user.role in roles
