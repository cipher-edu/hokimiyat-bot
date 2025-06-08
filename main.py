# main.py

"""
Telegram Ovoz Berish Boti (Refactored & Render.com'ga moslashtirilgan)

Ushbu bot quyidagi funksiyalarni amalga oshiradi:
- Foydalanuvchilarni majburiy kanallarga a'zoligini tekshirish.
- Telefon raqamini olish va xavfsiz shifrlab saqlash.
- Botlardan himoyalanish uchun CAPTCHA tizimi.
- Adminlar uchun so'rovnomalarni boshqarish paneli.
- Foydalanuvchilar uchun ovoz berish jarayoni.

Texnologiyalar steki:
- aiogram 3.x
- SQLAlchemy 2.0 (async) + aiosqlite
- Redis (FSM va CAPTCHA uchun)
- Pydantic Settings (.env fayli uchun)
- Cryptography (ma'lumotlarni shifrlash uchun)
"""

import asyncio
import logging
import os
import random
from typing import List, Union, Dict, Optional, Callable, Any, Awaitable

# Aiogram imports
from aiogram import Bot, Dispatcher, F, BaseMiddleware, Router
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, TelegramObject
)
from aiogram.utils.keyboard import InlineKeyboardBuilder

# Database imports
from sqlalchemy import (
    create_engine, Column, BigInteger, String, DateTime, ForeignKey, Integer,
    LargeBinary, UniqueConstraint, JSON, Boolean, Text, select, update, func
)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.exc import IntegrityError

# Other libraries
import redis.asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field
from cryptography.fernet import Fernet, InvalidToken

# --- 0. Logging sozlamalari ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)


# --- 1. Konfiguratsiya (Pydantic Settings) ---
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE_PATH = os.path.join(BASE_DIR, '.env')

class Settings(BaseSettings):
    """ .env faylidan sozlamalarni o'qiydigan Pydantic modeli """
    model_config = SettingsConfigDict(
        env_file=ENV_FILE_PATH, env_file_encoding='utf-8', extra='ignore'
    )

    BOT_TOKEN: SecretStr
    ADMIN_IDS_STR: str = Field("12345678", alias='ADMIN_IDS')
    REQUIRED_CHANNELS_STR: str = Field("", alias='REQUIRED_CHANNELS')
    ENCRYPTION_KEY: SecretStr

    DB_NAME: str = "vote_bot_prod.db"
    
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB_FSM: int = 0
    REDIS_DB_CAPTCHA: int = 1

    CAPTCHA_TIMEOUT_SECONDS: int = 60
    CAPTCHA_MAX_ATTEMPTS: int = 3
    CAPTCHA_BLOCK_DURATION_MINUTES: int = 5

    @property
    def ADMIN_IDS(self) -> List[int]:
        if not self.ADMIN_IDS_STR: return []
        return [int(admin_id.strip()) for admin_id in self.ADMIN_IDS_STR.split(',') if admin_id.strip()]

    @property
    def DATABASE_URL(self) -> str:
        """ Ma'lumotlar bazasi URL manzilini Render.com dagi diskka moslashtiradi """
        render_disk_path = "/var/data/db" 
        
        if os.path.exists(render_disk_path):
            base_path = render_disk_path
        else:
            base_path = BASE_DIR
        
        os.makedirs(base_path, exist_ok=True)
        
        db_path = os.path.join(base_path, self.DB_NAME)
        logger.info(f"Database path: {db_path}")
        return f"sqlite+aiosqlite:///{db_path}"

    @property
    def REQUIRED_CHANNELS(self) -> List[Union[str, int]]:
        channels = []
        if not self.REQUIRED_CHANNELS_STR: return []
        for ch_str in self.REQUIRED_CHANNELS_STR.split(','):
            ch = ch_str.strip()
            if not ch: continue
            if ch.startswith('@') or ch.startswith('-100'):
                channels.append(ch)
            else:
                try:
                    channels.append(int(ch))
                except ValueError:
                    logger.warning(f"Kanal IDsi '{ch}' noto'g'ri formatda e'tiborsiz qoldirildi.")
        return channels

try:
    settings = Settings()
except Exception as e:
    logger.critical(f".env faylini o'qishda yoki Sozlamalarni yuklashda xatolik: {e}")
    logger.critical("Iltimos, .env fayli mavjudligini va to'g'ri formatdaligini tekshiring.")
    logger.critical("Majburiy maydonlar: BOT_TOKEN, ADMIN_IDS, ENCRYPTION_KEY.")
    exit(1)


# --- 2. Shifrlash Xizmati (CryptoService) ---
class CryptoService:
    def __init__(self, key: bytes):
        try:
            self.fernet = Fernet(key)
        except (ValueError, TypeError) as e:
            logger.critical(f"ENCRYPTION_KEY yaroqsiz formatda: {e}")
            logger.critical("Kalitni to'g'ri generatsiya qilganingizga ishonch hosil qiling.")
            exit(1)

    def encrypt(self, data: str) -> bytes:
        return self.fernet.encrypt(data.encode('utf-8'))

    def decrypt(self, encrypted_data: bytes) -> Optional[str]:
        try:
            return self.fernet.decrypt(encrypted_data).decode('utf-8')
        except InvalidToken:
            logger.warning("Shifrlangan ma'lumotni ochishda InvalidToken xatosi.")
            return None
        except Exception as e:
            logger.error(f"Ma'lumotni deshifrlashda kutilmagan xato: {e}")
            return None


# --- 3. Ma'lumotlar Bazasi (SQLAlchemy) ---
Base = declarative_base()

class User(Base):
    __tablename__ = "users"
    id = Column(BigInteger, primary_key=True, index=True)
    username = Column(String, nullable=True)
    first_name = Column(String, nullable=True)
    phone_number_encrypted = Column(LargeBinary, nullable=True)
    created_at = Column(DateTime, server_default=func.now())
    votes = relationship("Vote", back_populates="user")

class Poll(Base):
    __tablename__ = "polls"
    id = Column(Integer, primary_key=True, autoincrement=True)
    question = Column(Text, nullable=False)
    options = Column(JSON, nullable=False)
    is_active = Column(Boolean, default=False)
    created_by_admin_id = Column(BigInteger, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    votes = relationship("Vote", back_populates="poll")

class Vote(Base):
    __tablename__ = "votes"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id"), nullable=False)
    poll_id = Column(Integer, ForeignKey("polls.id"), nullable=False)
    choice_key = Column(String, nullable=False)
    created_at = Column(DateTime, server_default=func.now())
    user = relationship("User", back_populates="votes")
    poll = relationship("Poll", back_populates="votes")
    __table_args__ = (UniqueConstraint('user_id', 'poll_id', name='uq_user_poll_vote'),)

engine = create_async_engine(settings.DATABASE_URL, echo=False)
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Ma'lumotlar bazasi jadvallari yaratildi/tekshirildi.")

# --- 3.1. DB CRUD Operatsiyalari ---
async def get_or_create_user(session: AsyncSession, user_id: int, username: Optional[str] = None, first_name: Optional[str] = None) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(id=user_id, username=username, first_name=first_name)
        session.add(user)
        await session.commit()
        await session.refresh(user)
    return user

async def save_user_phone(session: AsyncSession, user_id: int, encrypted_phone_number: bytes):
    stmt = update(User).where(User.id == user_id).values(phone_number_encrypted=encrypted_phone_number)
    await session.execute(stmt)
    await session.commit()

async def get_active_poll(session: AsyncSession) -> Optional[Poll]:
    stmt = select(Poll).where(Poll.is_active == True).order_by(Poll.created_at.desc()).limit(1)
    return await session.scalar(stmt)

async def get_poll_by_id(session: AsyncSession, poll_id: int) -> Optional[Poll]:
    return await session.get(Poll, poll_id)

async def has_user_voted(session: AsyncSession, user_id: int, poll_id: int) -> bool:
    stmt = select(Vote.id).where(Vote.user_id == user_id, Vote.poll_id == poll_id).limit(1)
    return await session.scalar(stmt) is not None

async def add_vote(session: AsyncSession, user_id: int, poll_id: int, choice_key: str):
    vote = Vote(user_id=user_id, poll_id=poll_id, choice_key=choice_key)
    session.add(vote)
    await session.commit()

async def create_poll(session: AsyncSession, question: str, options: Dict[str, str], admin_id: int, is_active: bool = False) -> Poll:
    if is_active:
        await session.execute(update(Poll).values(is_active=False))
    poll = Poll(question=question, options=options, created_by_admin_id=admin_id, is_active=is_active)
    session.add(poll)
    await session.commit()
    await session.refresh(poll)
    return poll

async def get_all_polls(session: AsyncSession) -> List[Poll]:
    stmt = select(Poll).order_by(Poll.created_at.desc())
    result = await session.execute(stmt)
    return result.scalars().all()

async def set_poll_active_status(session: AsyncSession, poll_id: int, active: bool) -> Optional[Poll]:
    if active:
        await session.execute(update(Poll).values(is_active=False))
    stmt = update(Poll).where(Poll.id == poll_id).values(is_active=active).returning(Poll)
    result = await session.execute(stmt)
    await session.commit()
    return result.scalar_one_or_none()

async def get_poll_results(session: AsyncSession, poll_id: int) -> Dict[str, int]:
    stmt = select(Vote.choice_key, func.count(Vote.id).label("vote_count")).where(Vote.poll_id == poll_id).group_by(Vote.choice_key)
    result = await session.execute(stmt)
    return {row.choice_key: row.vote_count for row in result.all()}


# --- 4. CAPTCHA Xizmati (CaptchaService) ---
class CaptchaService:
    def __init__(self, redis_client: aioredis.Redis):
        self.redis = redis_client
        self.timeout = settings.CAPTCHA_TIMEOUT_SECONDS
        self.max_attempts = settings.CAPTCHA_MAX_ATTEMPTS
        self.block_duration = settings.CAPTCHA_BLOCK_DURATION_MINUTES * 60

    def _generate_math_captcha(self) -> tuple[str, str]:
        num1, num2 = random.randint(1, 10), random.randint(1, 10)
        ops = {'+': num1 + num2, '-': abs(num1 - num2), '*': num1 * num2}
        op_char = random.choice(list(ops.keys()))
        question_num1, question_num2 = (num1, num2) if num1 >= num2 else (num2, num1)
        question = f"{question_num1} {op_char} {question_num2} = ?"
        answer = str(ops[op_char])
        return question, answer

    async def create_captcha(self, user_id: int) -> str:
        question, answer = self._generate_math_captcha()
        await self.redis.set(f"captcha:{user_id}:answer", answer, ex=self.timeout)
        await self.redis.set(f"captcha:{user_id}:attempts", 0, ex=self.timeout + 10)
        return question

    async def verify_captcha(self, user_id: int, user_answer: str) -> bool:
        redis_key_answer = f"captcha:{user_id}:answer"
        redis_key_attempts = f"captcha:{user_id}:attempts"
        correct_answer_bytes = await self.redis.get(redis_key_answer)
        if not correct_answer_bytes: return False

        if correct_answer_bytes == user_answer.strip():
            await self.redis.delete(redis_key_answer, redis_key_attempts)
            return True
        else:
            current_attempts = await self.redis.incr(redis_key_attempts)
            if current_attempts >= self.max_attempts:
                await self.redis.set(f"captcha_block:{user_id}", "blocked", ex=self.block_duration)
                await self.redis.delete(redis_key_answer, redis_key_attempts)
            return False

    async def is_user_blocked(self, user_id: int) -> bool:
        return await self.redis.exists(f"captcha_block:{user_id}")

    async def get_attempts_left(self, user_id: int) -> int:
        attempts_made_bytes = await self.redis.get(f"captcha:{user_id}:attempts")
        if attempts_made_bytes:
            return self.max_attempts - int(attempts_made_bytes)
        return self.max_attempts


# --- 5. Foydalanuvchi Holatlari (FSM States) ---
class VotingProcess(StatesGroup):
    awaiting_subscription_check = State()
    awaiting_contact = State()
    awaiting_captcha = State()
    awaiting_vote_choice = State()

class AdminPollManagement(StatesGroup):
    awaiting_poll_question = State()
    awaiting_poll_options = State()


# --- 6. Tugmalar (Keyboards) ---
def get_contact_keyboard() -> ReplyKeyboardMarkup:
    return ReplyKeyboardMarkup(
        keyboard=[[KeyboardButton(text="Telefon raqamni yuborish 📞", request_contact=True)]],
        resize_keyboard=True, one_time_keyboard=True
    )

def get_channel_subscription_keyboard(channels_to_subscribe: List[Dict[str, str]], check_button_text: str = "✅ A'zo bo'ldim") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for channel in channels_to_subscribe:
        builder.row(InlineKeyboardButton(text=f"➡️ {channel['title']}", url=channel['url']))
    builder.row(InlineKeyboardButton(text=check_button_text, callback_data="check_subscription"))
    return builder.as_markup()

def get_poll_options_keyboard(poll: Poll) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for key, text in poll.options.items():
        builder.row(InlineKeyboardButton(text=text, callback_data=f"vote_poll:{poll.id}:choice:{key}"))
    return builder.as_markup()

def get_admin_poll_list_keyboard(polls: List[Poll]) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    for poll in polls:
        status_icon = '🟢' if poll.is_active else '⚪️'
        builder.row(InlineKeyboardButton(text=f"{status_icon} {poll.question[:35]}...", callback_data=f"admin:poll:view:{poll.id}"))
    builder.row(InlineKeyboardButton(text="➕ Yangi so'rovnoma", callback_data="admin:poll:create"))
    return builder.as_markup()

def get_admin_poll_manage_keyboard(poll_id: int, is_active: bool) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder()
    toggle_text = "⚪️ Noaktiv qilish" if is_active else "🟢 Aktiv qilish"
    builder.row(InlineKeyboardButton(text=toggle_text, callback_data=f"admin:poll:toggle:{poll_id}"))
    builder.row(InlineKeyboardButton(text="📊 Natijalar", callback_data=f"admin:poll:results:{poll_id}"))
    builder.row(InlineKeyboardButton(text="🔙 Ortga", callback_data="admin:poll:list"))
    return builder.as_markup()

remove_keyboard = ReplyKeyboardRemove()


# --- 7. Middleware (DB sessiyasi uchun) ---
class DbSessionMiddleware(BaseMiddleware):
    def __init__(self, session_pool: async_sessionmaker[AsyncSession]):
        super().__init__()
        self.session_pool = session_pool

    async def __call__(
        self,
        handler: Callable[[TelegramObject, Dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: Dict[str, Any]
    ) -> Any:
        async with self.session_pool() as session:
            data["session"] = session
            return await handler(event, data)


# --- 8. Yordamchi Funksiyalar ---
async def check_all_channels_membership(bot: Bot, user_id: int) -> List[Dict[str, str]]:
    unsubscribed_channels = []
    if not settings.REQUIRED_CHANNELS:
        return []

    for channel_id in settings.REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status not in ("member", "administrator", "creator"):
                raise TelegramBadRequest(message="User is not a member")
        except TelegramBadRequest:
            try:
                chat = await bot.get_chat(channel_id)
                invite_link = chat.invite_link or f"https://t.me/{chat.username}"
                unsubscribed_channels.append({"title": chat.title, "url": invite_link})
            except Exception as e:
                logger.error(f"Majburiy kanal ({channel_id}) ma'lumotlarini olib bo'lmadi: {e}")
                unsubscribed_channels.append({"title": f"Kanal ({channel_id})", "url": "#error"})
        except Exception as e:
            logger.error(f"Kanal tekshirishda kutilmagan xatolik ({channel_id}): {e}", exc_info=True)

    return unsubscribed_channels


# --- 9. Handlerlar (Routers) ---
admin_router = Router()
admin_router.message.filter(F.from_user.id.in_(settings.ADMIN_IDS))
admin_router.callback_query.filter(F.from_user.id.in_(settings.ADMIN_IDS))
user_router = Router()

# --- 9.1. Admin Handlerlar ---
@admin_router.message(Command("admin", "polls"))
async def cmd_admin_polls(message: Message, session: AsyncSession):
    all_polls = await get_all_polls(session)
    await message.answer("Mavjud so'rovnomalar:", reply_markup=get_admin_poll_list_keyboard(all_polls))

@admin_router.callback_query(F.data == "admin:poll:list")
async def cb_admin_poll_list(callback: CallbackQuery, session: AsyncSession):
    all_polls = await get_all_polls(session)
    await callback.message.edit_text("Mavjud so'rovnomalar:", reply_markup=get_admin_poll_list_keyboard(all_polls))
    await callback.answer()

@admin_router.callback_query(F.data == "admin:poll:create")
async def cb_admin_poll_create(callback: CallbackQuery, state: FSMContext):
    await callback.message.edit_text("Yangi so'rovnoma uchun savolni yuboring:")
    await state.set_state(AdminPollManagement.awaiting_poll_question)
    await callback.answer()

@admin_router.message(AdminPollManagement.awaiting_poll_question)
async def process_poll_question(message: Message, state: FSMContext):
    await state.update_data(question=message.text)
    await message.answer(
        "Endi variantlarni yuboring. Har bir variant yangi qatordan boshlansin (kamida 2 ta).\n\n"
        "Masalan:\nVariant A\nVariant B\nVariant C"
    )
    await state.set_state(AdminPollManagement.awaiting_poll_options)

@admin_router.message(AdminPollManagement.awaiting_poll_options)
async def process_poll_options(message: Message, state: FSMContext, session: AsyncSession):
    options_list = [opt.strip() for opt in message.text.split('\n') if opt.strip()]
    if len(options_list) < 2:
        return await message.answer("Kamida 2 ta variant kiritilishi kerak. Qaytadan urinib ko'ring.")

    options_dict = {str(i + 1): opt for i, opt in enumerate(options_list)}
    data = await state.get_data()
    
    new_poll = await create_poll(session, question=data["question"], options=options_dict, admin_id=message.from_user.id)
    await message.answer(f"✅ So'rovnoma \"{new_poll.question}\" muvaffaqiyatli yaratildi!")
    
    await state.clear()
    all_polls = await get_all_polls(session)
    await message.answer("Mavjud so'rovnomalar:", reply_markup=get_admin_poll_list_keyboard(all_polls))

@admin_router.callback_query(F.data.startswith("admin:poll:view:"))
async def cb_admin_poll_view(callback: CallbackQuery, session: AsyncSession):
    poll_id = int(callback.data.split(":")[-1])
    poll = await get_poll_by_id(session, poll_id)
    if not poll:
        return await callback.answer("So'rovnoma topilmadi!", show_alert=True)
    
    options_text = "\n".join([f"▪️ {v}" for k, v in poll.options.items()])
    status_text = '🟢 Aktiv' if poll.is_active else '⚪️ Noaktiv'
    
    await callback.message.edit_text(
        f"<b>So'rovnoma:</b> {poll.question}\n\n"
        f"<b>Variantlar:</b>\n{options_text}\n\n"
        f"<b>Status:</b> {status_text}",
        reply_markup=get_admin_poll_manage_keyboard(poll.id, poll.is_active)
    )
    await callback.answer()

@admin_router.callback_query(F.data.startswith("admin:poll:toggle:"))
async def cb_admin_poll_toggle(callback: CallbackQuery, session: AsyncSession):
    poll_id = int(callback.data.split(":")[-1])
    current_poll = await get_poll_by_id(session, poll_id)
    if not current_poll:
        return await callback.answer("So'rovnoma topilmadi!", show_alert=True)

    updated_poll = await set_poll_active_status(session, poll_id, not current_poll.is_active)
    if not updated_poll:
        return await callback.answer("Statusni o'zgartirishda xatolik!", show_alert=True)

    await callback.answer(f"Status {'🟢 Aktiv' if updated_poll.is_active else '⚪️ Noaktiv'} holatiga o'zgartirildi.", show_alert=True)
    
    await cb_admin_poll_view(callback, session)

@admin_router.callback_query(F.data.startswith("admin:poll:results:"))
async def cb_admin_poll_results(callback: CallbackQuery, session: AsyncSession):
    poll_id = int(callback.data.split(":")[-1])
    poll = await get_poll_by_id(session, poll_id)
    if not poll:
        return await callback.answer("So'rovnoma topilmadi!", show_alert=True)

    results = await get_poll_results(session, poll_id)
    text = f"📊 <b>\"{poll.question}\"</b> natijalari:\n\n"
    if not results:
        text += "Hozircha hech kim ovoz bermagan."
    else:
        total_votes = sum(results.values())
        sorted_results = sorted(results.items(), key=lambda item: item[1], reverse=True)
        for key, count in sorted_results:
            option_text = poll.options.get(key, f"Noma'lum ({key})")
            percentage = (count / total_votes * 100) if total_votes > 0 else 0
            text += f"▫️ {option_text}: <b>{count} ta ovoz</b> ({percentage:.2f}%)\n"
        text += f"\nJami ovozlar: <b>{total_votes}</b>"
        
    await callback.message.edit_text(text, reply_markup=get_admin_poll_manage_keyboard(poll.id, poll.is_active))
    await callback.answer()


# --- 9.2. User Handlers ---
@user_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    await state.clear()
    await get_or_create_user(session, message.from_user.id, message.from_user.username, message.from_user.first_name)

    unsubscribed_channels = await check_all_channels_membership(bot, message.from_user.id)
    
    if unsubscribed_channels:
        await message.answer(
            "Assalomu alaykum! Ovoz berish jarayonida ishtirok etish uchun, iltimos, quyidagi kanallarga a'zo bo'ling:",
            reply_markup=get_channel_subscription_keyboard(unsubscribed_channels)
        )
        await state.set_state(VotingProcess.awaiting_subscription_check)
    else:
        await message.answer(
            "Assalomu alaykum! Ovoz berish uchun telefon raqamingizni yuboring:",
            reply_markup=get_contact_keyboard()
        )
        await state.set_state(VotingProcess.awaiting_contact)

@user_router.callback_query(F.data == "check_subscription", VotingProcess.awaiting_subscription_check)
async def cb_check_subscription(callback: CallbackQuery, state: FSMContext, bot: Bot):
    await callback.answer("Tekshirilmoqda...", cache_time=1)
    
    unsubscribed_channels = await check_all_channels_membership(bot, callback.from_user.id)
    
    if unsubscribed_channels:
        await callback.message.edit_text(
            "Afsuski, siz hali ham barcha kanallarga a'zo bo'lmagansiz. Iltimos, a'zo bo'lib, qayta tekshiring.",
            reply_markup=get_channel_subscription_keyboard(unsubscribed_channels, "🔄 Qayta tekshirish")
        )
    else:
        await callback.message.delete()
        await callback.message.answer(
            "Barcha kanallarga muvaffaqiyatli a'zo bo'ldingiz! Rahmat!\n\nEndi telefon raqamingizni yuboring:",
            reply_markup=get_contact_keyboard()
        )
        await state.set_state(VotingProcess.awaiting_contact)

@user_router.message(F.contact, VotingProcess.awaiting_contact)
async def handle_contact(message: Message, state: FSMContext, session: AsyncSession, crypto_service: CryptoService, captcha_service: CaptchaService):
    if await captcha_service.is_user_blocked(message.from_user.id):
        await message.answer(
            "CAPTCHAga ko'p sonli noto'g'ri urinishlar tufayli vaqtinchalik bloklangansiz. "
            f"Iltimos, {settings.CAPTCHA_BLOCK_DURATION_MINUTES} daqiqadan so'ng qayta urinib ko'ring.",
            reply_markup=remove_keyboard
        )
        await state.clear()
        return

    encrypted_phone = crypto_service.encrypt(message.contact.phone_number)
    await save_user_phone(session, message.from_user.id, encrypted_phone)

    captcha_question = await captcha_service.create_captcha(message.from_user.id)
    await message.answer(
        f"Raqamingiz qabul qilindi.\n\nEndi bot emasligingizni tasdiqlang. "
        f"Ushbu matematik misolning javobini yozib yuboring ({settings.CAPTCHA_TIMEOUT_SECONDS} soniya vaqt bor):\n\n"
        f"<b>{captcha_question}</b>",
        reply_markup=remove_keyboard
    )
    await state.set_state(VotingProcess.awaiting_captcha)

@user_router.message(VotingProcess.awaiting_contact)
async def invalid_contact_input(message: Message):
    await message.reply("Iltimos, pastdagi 'Telefon raqamni yuborish 📞' tugmasi orqali raqamingizni yuboring.")

@user_router.message(VotingProcess.awaiting_captcha)
async def process_captcha_answer(message: Message, state: FSMContext, session: AsyncSession, captcha_service: CaptchaService):
    user_id = message.from_user.id
    if await captcha_service.is_user_blocked(user_id):
        await message.answer("Siz vaqtinchalik bloklangansiz. Keyinroq /start buyrug'i bilan qayta urining.")
        await state.clear()
        return

    is_correct = await captcha_service.verify_captcha(user_id, message.text)
    
    if is_correct:
        await message.answer("✅ To'g'ri javob!")
        active_poll = await get_active_poll(session)
        
        if not active_poll:
            await message.answer("Ayni vaqtda faol so'rovnomalar mavjud emas. E'tiboringiz uchun rahmat!")
            await state.clear()
            return

        if await has_user_voted(session, user_id, active_poll.id):
            await message.answer("Siz bu so'rovnomada allaqachon ovoz bergansiz. Rahmat!")
            await state.clear()
            return
            
        await message.answer(
            f"So'rovnoma:\n<b>{active_poll.question}</b>\n\nO'zingizga ma'qul variantni tanlang:",
            reply_markup=get_poll_options_keyboard(active_poll)
        )
        await state.set_state(VotingProcess.awaiting_vote_choice)

    else:
        attempts_left = await captcha_service.get_attempts_left(user_id)
        if await captcha_service.is_user_blocked(user_id):
            await message.answer(
                f"Noto'g'ri javob. Urinishlar soni tugadi.\nSiz {settings.CAPTCHA_BLOCK_DURATION_MINUTES} daqiqaga bloklandingiz. "
                "Keyinroq /start buyrug'i bilan qayta urinib ko'rishingiz mumkin."
            )
            await state.clear()
        else:
            await message.answer(f"Noto'g'ri javob. Sizda yana {attempts_left} ta urinish qoldi. Qaytadan kiriting:")

@user_router.callback_query(F.data.startswith("vote_poll:"), VotingProcess.awaiting_vote_choice)
async def process_vote_choice(callback: CallbackQuery, state: FSMContext, session: AsyncSession):
    user_id = callback.from_user.id
    try:
        _, poll_id_str, _, choice_key = callback.data.split(":")
        poll_id = int(poll_id_str)
    except (ValueError, IndexError):
        await callback.answer("So'rovnoma ma'lumotlari xato.", show_alert=True)
        await state.clear()
        return

    poll = await get_poll_by_id(session, poll_id)
    if not poll or not poll.is_active:
        await callback.message.edit_text("Ushbu so'rovnoma yakunlangan yoki faol emas.")
        await state.clear()
        return await callback.answer()

    if await has_user_voted(session, user_id, poll_id):
        await callback.message.edit_text("Siz bu so'rovnomada allaqachon ovoz bergansiz.")
        await state.clear()
        return await callback.answer("Siz allaqachon ovoz bergansiz!", show_alert=True)

    try:
        await add_vote(session, user_id, poll_id, choice_key)
        chosen_option_text = poll.options.get(choice_key, "Tanlangan variant")
        await callback.message.edit_text(f"Ovozingiz qabul qilindi: <b>\"{chosen_option_text}\"</b>.\n\nRahmat!")
        await callback.answer("Ovozingiz qabul qilindi!", show_alert=True)
    except IntegrityError:
        await callback.message.edit_text("Xatolik: Siz allaqachon ovoz bergansiz (DB xatosi).")
        await callback.answer("Xatolik yuz berdi!", show_alert=True)
    except Exception as e:
        logger.error(f"Ovoz berishda kutilmagan xatolik: {e}", exc_info=True)
        await callback.message.edit_text("Ovoz berishda texnik nosozlik yuz berdi. Iltimos, keyinroq urining.")
        await callback.answer("Texnik nosozlik!", show_alert=True)
    
    await state.clear()


# --- 10. Botni Ishga Tushirish ---
async def main():
    """ Botni ishga tushiruvchi asosiy funksiya """
    crypto_service = CryptoService(settings.ENCRYPTION_KEY.get_secret_value().encode())
    
    redis_connection_params = {
        "host": settings.REDIS_HOST,
        "port": settings.REDIS_PORT,
        "decode_responses": True
    }
    if settings.REDIS_PASSWORD:
        redis_connection_params["password"] = settings.REDIS_PASSWORD
        logger.info("Redis'ga parol bilan ulanilmoqda.")
    else:
        logger.info("Redis'ga parolsiz ulanilmoqda.")
        
    redis_fsm_client = aioredis.Redis(db=settings.REDIS_DB_FSM, **redis_connection_params)
    redis_captcha_client = aioredis.Redis(db=settings.REDIS_DB_CAPTCHA, **redis_connection_params)

    captcha_service = CaptchaService(redis_captcha_client)
    storage = RedisStorage(redis=redis_fsm_client)
    
    bot = Bot(token=settings.BOT_TOKEN.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=storage)

    dp.update.middleware(DbSessionMiddleware(session_pool=AsyncSessionFactory))
    dp.workflow_data.update({
        "crypto_service": crypto_service,
        "captcha_service": captcha_service
    })

    dp.include_router(admin_router)
    dp.include_router(user_router)
    
    await create_db_and_tables()

    logger.info("Bot ishga tushirilmoqda...")
    try:
        await redis_fsm_client.ping()
        logger.info(f"FSM uchun Redis'ga ulanish muvaffaqiyatli (DB {settings.REDIS_DB_FSM}).")
        await redis_captcha_client.ping()
        logger.info(f"CAPTCHA uchun Redis'ga ulanish muvaffaqiyatli (DB {settings.REDIS_DB_CAPTCHA}).")
        
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot, allowed_updates=dp.resolve_used_update_types())

    except RedisConnectionError as e:
        logger.critical(f"Redis serveriga ulanib bo'lmadi: {e}")
        logger.critical("Iltimos, Redis serveri ishlayotganligini va .env faylidagi yoki Render'dagi sozlamalar to'g'riligini tekshiring.")
    except Exception as e:
        logger.critical(f"Botni ishga tushirishda kutilmagan xatolik: {e}", exc_info=True)
    finally:
        await bot.session.close()
        await redis_fsm_client.close()
        await redis_captcha_client.close()
        logger.info("Bot to'xtatildi va resurslar yopildi.")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot foydalanuvchi tomonidan to'xtatildi.")
