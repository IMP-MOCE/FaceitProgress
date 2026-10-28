from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.errors import Conflict, InvalidCredentials
from app.core.security import hash_password, verify_password
from app.models import User
from app.repositories import users

EMAIL_TAKEN = "Пользователь с таким email уже зарегистрирован"


def register(db: Session, email: str, password: str) -> User:
    if users.get_by_email(db, email) is not None:
        raise Conflict(EMAIL_TAKEN)
    user = users.add(db, email, hash_password(password))
    try:
        db.commit()
    except IntegrityError as exc:
        # Параллельная регистрация того же email: проверку выше прошли оба запроса
        db.rollback()
        raise Conflict(EMAIL_TAKEN) from exc
    return user


def authenticate(db: Session, email: str, password: str) -> User:
    user = users.get_by_email(db, email)
    # Один и тот же ответ для «нет пользователя» и «неверный пароль».
    if not verify_password(password, user.password_hash if user else None):
        raise InvalidCredentials()
    if user is None or not user.is_active:
        raise InvalidCredentials()
    return user


def delete_account(db: Session, user: User) -> None:
    # Игроки, матчи и цели удаляются каскадом (ON DELETE CASCADE)
    db.delete(user)
    db.commit()
