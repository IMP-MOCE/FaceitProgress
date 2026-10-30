from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class RevokedToken(Base):
    """Отозванный JWT (выход из аккаунта). Хранится до истечения срока токена"""

    __tablename__ = "revoked_tokens"

    jti: Mapped[str] = mapped_column(String(64), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    # После expires_at токен отклоняется по exp, запись можно удалить
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
