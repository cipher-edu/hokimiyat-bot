# bot_postgress_sql.py (SQLite va PostgreSQL'ni qo'llab-quvvatlaydi)

import asyncio
import logging
import os
import random
from typing import List, Union, Dict, Optional, Callable, Any, Awaitable

from aiogram import Bot, Dispatcher, F, BaseMiddleware, Router
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.redis import RedisStorage
from aiogram.types import (Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, TelegramObject)
from aiogram.filters.command import CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import (create_engine, Column, BigInteger, String, DateTime, ForeignKey, Integer, LargeBinary, UniqueConstraint, JSON, Boolean, Text, select, update, func)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.exc import IntegrityError

import redis.asyncio as aioredis
from redis.exceptions import ConnectionError as RedisConnectionError
from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import SecretStr, Field
from cryptography.fernet import Fernet, InvalidToken

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
ENV_FILE_PATH = os.path.join(BASE_DIR, '.env')

class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=ENV_FILE_PATH, env_file_encoding='utf-8', extra='ignore')
    
    BOT_TOKEN: SecretStr
    ADMIN_IDS_STR: str = Field("1062838548", alias='ADMIN_IDS')
    REQUIRED_CHANNELS_STR: str = Field("", alias='REQUIRED_CHANNELS')
    ENCRYPTION_KEY: SecretStr
    
    DB_TYPE: str = "sqlite"
    SQLITE_DB_NAME: str = "vote_bot.db"
    
    POSTGRES_DB: Optional[str] = None
    POSTGRES_USER: Optional[str] = None
    POSTGRES_PASSWORD: Optional[SecretStr] = None
    POSTGRES_HOST: Optional[str] = "localhost"
    POSTGRES_PORT: Optional[int] = 5432
    
    REDIS_HOST: str = "localhost"
    REDIS_PORT: int = 6379
    REDIS_PASSWORD: Optional[str] = None
    REDIS_DB_FSM: int = 0
    REDIS_DB_CAPTCHA: int = 1
    
    CAPTCHA_TIMEOUT_SECONDS: int = 60
    CAPTCHA_MAX_ATTEMPTS: int = 3
    CAPTCHA_BLOCK_DURATION_MINUTES: int = 5
    
    @property
    def ADMIN_IDS(self) -> List[int]: return [int(i.strip()) for i in self.ADMIN_IDS_STR.split(',') if i.strip()]
    
    @property
    def DATABASE_URL(self) -> str:
        db_type = self.DB_TYPE.lower()
        if db_type == "postgresql":
            if not all([self.POSTGRES_DB, self.POSTGRES_USER, self.POSTGRES_PASSWORD, self.POSTGRES_HOST, self.POSTGRES_PORT]):
                raise ValueError("PostgreSQL uchun barcha kerakli sozlamalar kiritilmagan (.env faylini tekshiring)")
            return (f"postgresql+asyncpg://{self.POSTGRES_USER}:{self.POSTGRES_PASSWORD.get_secret_value()}"
                    f"@{self.POSTGRES_HOST}:{self.POSTGRES_PORT}/{self.POSTGRES_DB}")
        elif db_type == "sqlite":
            return f"sqlite+aiosqlite:///{os.path.join(BASE_DIR, self.SQLITE_DB_NAME)}"
        else:
            raise ValueError(f"Noto'g'ri DB_TYPE: '{self.DB_TYPE}'. Faqat 'sqlite' yoki 'postgresql' bo'lishi mumkin.")

    @property
    def REQUIRED_CHANNELS(self) -> List[Union[str, int]]:
        channels = [];
        if not self.REQUIRED_CHANNELS_STR: return []
        for ch_str in self.REQUIRED_CHANNELS_STR.split(','):
            ch = ch_str.strip();
            if not ch: continue
            if ch.startswith('@') or ch.startswith('-100'): channels.append(ch)
            else:
                try: channels.append(int(ch))
                except ValueError: logger.warning(f"Kanal IDsi '{ch}' noto'g'ri formatda.")
        return channels
try:
    settings = Settings()
except Exception as e:
    logger.critical(f".env faylini yuklashda xatolik: {e}. Majburiy maydonlarni tekshiring."); exit(1)

class CryptoService:
    def __init__(self, key: SecretStr):
        try: self.fernet = Fernet(key.get_secret_value().encode())
        except (ValueError, TypeError) as e: logger.critical(f"ENCRYPTION_KEY yaroqsiz: {e}"); exit(1)
    def encrypt(self, data: str) -> bytes: return self.fernet.encrypt(data.encode('utf-8'))
    def decrypt(self, encrypted_data: bytes) -> Optional[str]:
        try: return self.fernet.decrypt(encrypted_data).decode('utf-8')
        except (InvalidToken, Exception): return None

Base = declarative_base()
class User(Base): __tablename__ = "users"; id = Column(BigInteger, primary_key=True); username = Column(String); first_name = Column(String); phone_number_encrypted = Column(LargeBinary); created_at = Column(DateTime, server_default=func.now()); votes = relationship("Vote", back_populates="user")
class Poll(Base): __tablename__ = "polls"; id = Column(Integer, primary_key=True, autoincrement=True); question = Column(Text, nullable=False); options = Column(JSON, nullable=False); is_active = Column(Boolean, default=False); created_by_admin_id = Column(BigInteger, nullable=False); created_at = Column(DateTime, server_default=func.now()); votes = relationship("Vote", back_populates="poll")
class Vote(Base): __tablename__ = "votes"; id = Column(Integer, primary_key=True, autoincrement=True); user_id = Column(BigInteger, ForeignKey("users.id")); poll_id = Column(Integer, ForeignKey("polls.id")); choice_key = Column(String); created_at = Column(DateTime, server_default=func.now()); user = relationship("User", back_populates="votes"); poll = relationship("Poll", back_populates="votes"); __table_args__ = (UniqueConstraint('user_id', 'poll_id'),)
engine = create_async_engine(settings.DATABASE_URL); AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)
async def create_db_and_tables(): 
    async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all); logger.info(f"DB ({settings.DB_TYPE}) jadvallari yaratildi.")
async def get_or_create_user(session: AsyncSession, user_id: int, username: str = None, first_name: str = None) -> User: r = await session.execute(select(User).where(User.id == user_id)); user = r.scalar_one_or_none();_ = user or (user := User(id=user_id, username=username, first_name=first_name), session.add(user), await session.commit(), await session.refresh(user)); return user
async def save_user_phone(session: AsyncSession, user_id: int, encrypted_phone: bytes): await session.execute(update(User).where(User.id==user_id).values(phone_number_encrypted=encrypted_phone)); await session.commit()
async def get_active_poll(session: AsyncSession) -> Optional[Poll]: return await session.scalar(select(Poll).where(Poll.is_active==True).order_by(Poll.created_at.desc()).limit(1))
async def get_poll_by_id(session: AsyncSession, poll_id: int) -> Optional[Poll]: return await session.get(Poll, poll_id)
async def has_user_voted(session: AsyncSession, user_id: int, poll_id: int) -> bool: return await session.scalar(select(Vote.id).where(Vote.user_id==user_id, Vote.poll_id==poll_id).limit(1)) is not None
async def add_vote(session: AsyncSession, user_id: int, poll_id: int, choice_key: str): session.add(Vote(user_id=user_id, poll_id=poll_id, choice_key=choice_key)); await session.commit()
async def create_poll(session: AsyncSession, question: str, options: Dict[str, str], admin_id: int, is_active: bool = False) -> Poll:
    if is_active: await session.execute(update(Poll).values(is_active=False))
    poll = Poll(question=question, options=options, created_by_admin_id=admin_id, is_active=is_active); session.add(poll); await session.commit(); await session.refresh(poll); return poll
async def get_all_polls(session: AsyncSession) -> List[Poll]: return (await session.execute(select(Poll).order_by(Poll.created_at.desc()))).scalars().all()
async def set_poll_active_status(session: AsyncSession, poll_id: int, active: bool) -> Optional[Poll]:
    if active: await session.execute(update(Poll).values(is_active=False))
    result = await session.execute(update(Poll).where(Poll.id == poll_id).values(is_active=active).returning(Poll)); await session.commit(); return result.scalar_one_or_none()
async def get_poll_results(session: AsyncSession, poll_id: int) -> Dict[str, int]:
    result = await session.execute(select(Vote.choice_key, func.count(Vote.id).label("c")).where(Vote.poll_id == poll_id).group_by(Vote.choice_key)); return {row.choice_key: row.c for row in result.all()}
async def get_all_user_ids(session: AsyncSession) -> List[int]: return (await session.execute(select(User.id))).scalars().all()

class CaptchaService:
    def __init__(self, redis_client: aioredis.Redis): self.redis = redis_client
    def _generate_math_captcha(self)->tuple[str,str]: n1,n2=random.randint(1,10),random.randint(1,10);ops={'+':n1+n2,'-':abs(n1-n2),'*':n1*n2};op=random.choice(list(ops.keys()));q_n1,q_n2=(n1,n2) if n1>=n2 else (n2,n1);q=f"{q_n1} {op} {q_n2} = ?";a=str(ops[op]);return q,a
    async def create_captcha(self,user_id:int)->str: q,a=self._generate_math_captcha(); await self.redis.set(f"captcha:{user_id}:answer",a,ex=settings.CAPTCHA_TIMEOUT_SECONDS); await self.redis.set(f"captcha:{user_id}:attempts",0,ex=settings.CAPTCHA_TIMEOUT_SECONDS+10); return q
    async def verify_captcha(self,user_id:int,user_answer:str)->bool:
        correct_answer = await self.redis.get(f"captcha:{user_id}:answer")
        if not correct_answer: return False
        if correct_answer == user_answer.strip(): await self.redis.delete(f"captcha:{user_id}:answer", f"captcha:{user_id}:attempts"); return True
        else:
            attempts = await self.redis.incr(f"captcha:{user_id}:attempts")
            if attempts >= settings.CAPTCHA_MAX_ATTEMPTS: await self.redis.set(f"captcha_block:{user_id}","1",ex=settings.CAPTCHA_BLOCK_DURATION_MINUTES*60); await self.redis.delete(f"captcha:{user_id}:answer", f"captcha:{user_id}:attempts")
            return False
    async def is_user_blocked(self, user_id: int) -> bool: return await self.redis.exists(f"captcha_block:{user_id}")
    async def get_attempts_left(self, user_id: int) -> int:
        attempts = await self.redis.get(f"captcha:{user_id}:attempts")
        return settings.CAPTCHA_MAX_ATTEMPTS - int(attempts) if attempts else settings.CAPTCHA_MAX_ATTEMPTS

class VotingProcess(StatesGroup): awaiting_subscription_check=State();awaiting_contact=State();awaiting_captcha=State();awaiting_vote_choice=State()
class AdminPollManagement(StatesGroup): awaiting_poll_question=State();awaiting_poll_options=State()
class AdCreation(StatesGroup): awaiting_poll_selection=State();awaiting_post_text=State();awaiting_post_photo=State()
class Broadcast(StatesGroup): awaiting_ad_text=State();awaiting_ad_photo=State();awaiting_confirmation=State()

class DbSessionMiddleware(BaseMiddleware):
    def __init__(self,pool:async_sessionmaker[AsyncSession]): self.session_pool=pool
    async def __call__(self,handler:Callable,event:TelegramObject,data:Dict[str,Any])->Any:
        async with self.session_pool() as session: data["session"]=session; return await handler(event,data)

def get_contact_keyboard()->ReplyKeyboardMarkup:return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Telefon raqamni yuborish 📞",request_contact=True)]],resize_keyboard=True,one_time_keyboard=True)
def get_channel_subscription_keyboard(channels: List[Dict[str, str]], button_text: str = "✅ A'zo bo'ldim") -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder();[builder.row(InlineKeyboardButton(text=f"➡️ {c['title']}", url=c['url'])) for c in channels];builder.row(InlineKeyboardButton(text=button_text, callback_data="check_subscription"));return builder.as_markup()
def get_poll_options_keyboard(poll: Poll) -> InlineKeyboardMarkup: builder = InlineKeyboardBuilder();[builder.row(InlineKeyboardButton(text=t, callback_data=f"vote_poll:{poll.id}:choice:{k}")) for k,t in poll.options.items()];return builder.as_markup()
def get_admin_poll_list_keyboard(polls: List[Poll]) -> InlineKeyboardMarkup: builder = InlineKeyboardBuilder();[builder.row(InlineKeyboardButton(text=f"{'🟢' if p.is_active else '⚪️'} {p.question[:35]}...", callback_data=f"admin:poll:view:{p.id}")) for p in polls];builder.row(InlineKeyboardButton(text="➕ Yangi so'rovnoma", callback_data="admin:poll:create"));return builder.as_markup()
def get_admin_poll_manage_keyboard(poll_id: int, is_active: bool) -> InlineKeyboardMarkup: builder = InlineKeyboardBuilder();builder.row(InlineKeyboardButton(text="⚪️ Noaktiv qilish" if is_active else "🟢 Aktiv qilish", callback_data=f"admin:poll:toggle:{poll_id}"));builder.row(InlineKeyboardButton(text="📊 Natijalar", callback_data=f"admin:poll:results:{poll_id}"));builder.row(InlineKeyboardButton(text="🔙 Ortga", callback_data="admin:poll:list"));return builder.as_markup()
def get_poll_selection_for_ad_keyboard(polls: List[Poll]) -> InlineKeyboardMarkup: builder = InlineKeyboardBuilder();[builder.row(InlineKeyboardButton(text=f"{p.question[:40]}...", callback_data=f"ad_select_poll:{p.id}")) for p in polls];return builder.as_markup()
def get_ad_post_keyboard(poll: Poll, bot_username: str) -> InlineKeyboardMarkup:
    builder = InlineKeyboardBuilder();[builder.row(InlineKeyboardButton(text=t, url=f"https://t.me/{bot_username}?start=vote_{poll.id}_{k}")) for k,t in poll.options.items()];return builder.as_markup()
remove_keyboard = ReplyKeyboardRemove()

async def check_all_channels_membership(bot: Bot, user_id: int) -> List[Dict[str, str]]:
    unsubscribed = [];
    if not settings.REQUIRED_CHANNELS: return []
    for channel_id in settings.REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status not in ("member", "administrator", "creator"): raise Exception("User is not a subscribed member.")
        except Exception as e:
            if isinstance(e, TelegramBadRequest) or "User is not a subscribed member" in str(e):
                try:
                    chat = await bot.get_chat(channel_id)
                    invite_link = getattr(chat,'invite_link',None) or (f"https://t.me/{chat.username}" if getattr(chat,'username',None) else None)
                    if invite_link: unsubscribed.append({"title": chat.title, "url": invite_link})
                    else: logger.warning(f"Kanal ({channel_id}) uchun havola topilmadi.")
                except Exception as ex_info: logger.error(f"Kanal ({channel_id}) ma'lumotini olishda xatolik: {ex_info}")
            else: logger.error(f"Kanal tekshirishda kutilmagan xatolik ({channel_id}): {e}", exc_info=True)
    return unsubscribed

# --- 9. Handlerlar (Routers) ---
admin_router = Router(); admin_router.message.filter(F.from_user.id.in_(settings.ADMIN_IDS)); admin_router.callback_query.filter(F.from_user.id.in_(settings.ADMIN_IDS))
user_router = Router()

@admin_router.message(Command("admin", "polls"))
async def cmd_admin_polls(message: Message, session: AsyncSession): await message.answer("Mavjud so'rovnomalar:", reply_markup=get_admin_poll_list_keyboard(await get_all_polls(session)))
@admin_router.callback_query(F.data == "admin:poll:list")
async def cb_admin_poll_list(callback_query: CallbackQuery, session: AsyncSession): await callback_query.message.edit_text("Mavjud so'rovnomalar:", reply_markup=get_admin_poll_list_keyboard(await get_all_polls(session))); await callback_query.answer()
@admin_router.callback_query(F.data == "admin:poll:create")
async def cb_admin_poll_create(callback_query: CallbackQuery, state: FSMContext): await callback_query.message.edit_text("Yangi so'rovnoma uchun savolni yuboring:"); await state.set_state(AdminPollManagement.awaiting_poll_question); await callback_query.answer()
@admin_router.message(AdminPollManagement.awaiting_poll_question)
async def process_poll_question(message: Message, state: FSMContext): await state.update_data(question=message.text); await message.answer("Variantlarni yuboring (har biri yangi qatorda, kamida 2ta):\nVariant A\nVariant B"); await state.set_state(AdminPollManagement.awaiting_poll_options)
@admin_router.message(AdminPollManagement.awaiting_poll_options)
async def process_poll_options(message: Message, state: FSMContext, session: AsyncSession):
    options_list = [opt.strip() for opt in message.text.split('\n') if opt.strip()]; options_dict = {str(i+1): opt for i, opt in enumerate(options_list)}; data = await state.get_data()
    if len(options_list) < 2: return await message.answer("Kamida 2 ta variant kerak.")
    poll = await create_poll(session, data["question"], options_dict, message.from_user.id); await message.answer(f"So'rovnoma '{poll.question}' yaratildi!")
    await state.clear(); await message.answer("Mavjud so'rovnomalar:", reply_markup=get_admin_poll_list_keyboard(await get_all_polls(session)))
@admin_router.callback_query(F.data.startswith("admin:poll:view:"))
async def cb_admin_poll_view(callback_query: CallbackQuery, session: AsyncSession):
    poll_id = int(callback_query.data.split(":")[-1]); poll = await get_poll_by_id(session, poll_id)
    if not poll: return await callback_query.answer("So'rovnoma topilmadi!", show_alert=True)
    options_str = "\n".join([f"▪️ {v}" for k, v in poll.options.items()]); status_str = '🟢 Aktiv' if poll.is_active else '⚪️ Noaktiv'
    await callback_query.message.edit_text(f"<b>So'rovnoma:</b> {poll.question}\n\n<b>Variantlar:</b>\n{options_str}\n\n<b>Status:</b> {status_str}", reply_markup=get_admin_poll_manage_keyboard(poll.id, poll.is_active)); await callback_query.answer()
@admin_router.callback_query(F.data.startswith("admin:poll:toggle:"))
async def cb_admin_poll_toggle(callback_query: CallbackQuery, session: AsyncSession):
    poll_id = int(callback_query.data.split(":")[-1]); current_poll = await get_poll_by_id(session, poll_id)
    if not current_poll: return await callback_query.answer("So'rovnoma topilmadi!", show_alert=True)
    updated_poll = await set_poll_active_status(session, poll_id, not current_poll.is_active)
    await callback_query.answer(f"Status {'🟢 Aktiv' if updated_poll.is_active else '⚪️ Noaktiv'} qilindi.", show_alert=True)
    await cb_admin_poll_view(callback_query, session)
@admin_router.callback_query(F.data.startswith("admin:poll:results:"))
async def cb_admin_poll_results(callback_query: CallbackQuery, session: AsyncSession):
    poll_id = int(callback_query.data.split(":")[-1]); poll = await get_poll_by_id(session, poll_id)
    if not poll: return await callback_query.answer("So'rovnoma topilmadi!", show_alert=True)
    results = await get_poll_results(session, poll_id); text = f"📊 <b>'{poll.question}'</b> natijalari:\n\n"
    if not results: text += "Hali ovozlar yo'q."
    else:
        total_votes = sum(results.values())
        for key, count in sorted(results.items(), key=lambda item: item[1], reverse=True):
            option_text = poll.options.get(key, f'Noma`lum({key})'); percentage = (count/total_votes*100) if total_votes>0 else 0
            text += f"▫️ {option_text}: <b>{count} ta</b> ({percentage:.2f}%)\n"
        text += f"\nJami: <b>{total_votes}</b>"
    await callback_query.message.edit_text(text, reply_markup=get_admin_poll_manage_keyboard(poll.id, poll.is_active)); await callback_query.answer()

@admin_router.message(Command("rek"))
async def cmd_create_ad(message: Message, session: AsyncSession, state: FSMContext):
    all_polls = await get_all_polls(session);
    if not all_polls: return await message.answer("Reklama uchun avval so'rovnoma yarating.")
    await message.answer("Reklama posti uchun so'rovnomani tanlang:", reply_markup=get_poll_selection_for_ad_keyboard(all_polls)); await state.set_state(AdCreation.awaiting_poll_selection)
@admin_router.callback_query(F.data.startswith("ad_select_poll:"), AdCreation.awaiting_poll_selection)
async def cb_ad_poll_selected(callback_query: CallbackQuery, state: FSMContext):
    poll_id = int(callback_query.data.split(":")[1]); await state.update_data(poll_id=poll_id)
    await callback_query.message.edit_text("Ajoyib! Endi reklama matnini yuboring."); await state.set_state(AdCreation.awaiting_post_text)
@admin_router.message(AdCreation.awaiting_post_text)
async def process_ad_text(message: Message, state: FSMContext): await state.update_data(post_text=message.html_text); await message.answer("Matn qabul qilindi. Endi post uchun suratni yuboring."); await state.set_state(AdCreation.awaiting_post_photo)
@admin_router.message(F.photo, AdCreation.awaiting_post_photo)
async def process_ad_photo(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    data = await state.get_data(); poll = await get_poll_by_id(session, data.get("poll_id"))
    if not poll: await message.answer("Xatolik: So'rovnoma topilmadi. /rek"); await state.clear(); return
    bot_info = await bot.get_me(); keyboard = get_ad_post_keyboard(poll, bot_info.username)
    await message.answer("Tayyor post. Buni kerakli kanallarga yuborishingiz mumkin:")
    await bot.send_photo(chat_id=message.chat.id, photo=message.photo[-1].file_id, caption=data.get("post_text"), reply_markup=keyboard)
    await state.clear()
@admin_router.message(AdCreation.awaiting_post_photo)
async def process_ad_photo_invalid(message: Message): await message.reply("Iltimos, faqat surat (rasm) yuboring.")

@admin_router.message(Command("send_ad"))
async def cmd_broadcast_start(message: Message, state: FSMContext): await state.set_state(Broadcast.awaiting_ad_text); await message.answer("Barcha foydalanuvchilarga yuborish uchun reklama matnini yuboring.\n\nBekor qilish uchun: /bekor_qilish")
@admin_router.message(Command("bekor_qilish"), F.state.in_(AdCreation.__all_states__ + Broadcast.__all_states__))
async def cancel_any_state(message: Message, state: FSMContext): await state.clear(); await message.answer("Jarayon bekor qilindi.", reply_markup=remove_keyboard)
@admin_router.message(Broadcast.awaiting_ad_text)
async def broadcast_get_text(message: Message, state: FSMContext): await state.update_data(post_text=message.html_text); await state.set_state(Broadcast.awaiting_ad_photo); await message.answer("Matn qabul qilindi. Endi post uchun suratni yuboring.")
@admin_router.message(F.photo, Broadcast.awaiting_ad_photo)
async def broadcast_get_photo(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    await state.update_data(photo_file_id=message.photo[-1].file_id); data = await state.get_data()
    user_count = len(await get_all_user_ids(session)); await state.update_data(user_count=user_count)
    await bot.send_photo(chat_id=message.from_user.id, photo=data['photo_file_id'], caption=data['post_text'])
    await message.answer(f"Post tayyor. <b>{user_count}</b> ta foydalanuvchiga yuborilsinmi?\n\nTasdiqlash uchun <b>ha</b> deb yozing.", parse_mode=ParseMode.HTML); await state.set_state(Broadcast.awaiting_confirmation)
@admin_router.message(Broadcast.awaiting_confirmation)
async def broadcast_confirmation(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    if message.text.lower() != 'ha': await state.clear(); return await message.answer("Reklama yuborish bekor qilindi.")
    data = await state.get_data(); user_ids = await get_all_user_ids(session); await state.clear();
    await message.answer(f"Reklama yuborish boshlandi... ({len(user_ids)} ta foydalanuvchiga)")
    success, failure = 0, 0
    for user_id in user_ids:
        try: await bot.send_photo(chat_id=user_id, photo=data['photo_file_id'], caption=data['post_text']); success += 1; await asyncio.sleep(0.1)
        except TelegramRetryAfter as e: logger.warning(f"API limiti: {e.retry_after}s kutish."); await asyncio.sleep(e.retry_after); success-=1
        except (TelegramForbiddenError, TelegramBadRequest): failure += 1
        except Exception as e: logger.error(f"Reklamani {user_id} ga yuborishda xato: {e}"); failure += 1
    await message.answer(f"Yuborish yakunlandi.\n\n✅ Muvaffaqiyatli: <b>{success}</b>\n❌ Xatolik: <b>{failure}</b>")

# User Handlers
@user_router.message(CommandStart())
async def cmd_start(message: Message, state: FSMContext, session: AsyncSession, bot: Bot, command: CommandObject = None):
    await state.clear(); await get_or_create_user(session, message.from_user.id, message.from_user.username, message.from_user.first_name)
    unsubscribed = await check_all_channels_membership(bot, message.from_user.id)
    if command and command.args:
        try:
            _, poll_id_str, choice_key = command.args.split("_"); poll_id = int(poll_id_str)
            if unsubscribed: await message.answer("Ovoz berishdan avval kanallarga a'zo bo'ling:", reply_markup=get_channel_subscription_keyboard(unsubscribed)); await state.set_data({'deep_link_vote': (poll_id, choice_key)}); await state.set_state(VotingProcess.awaiting_subscription_check); return
            await process_deep_link_vote(message, session, bot, poll_id, choice_key); return
        except (ValueError, IndexError): pass
    if unsubscribed: await message.answer("Assalomu alaykum! Ishtirok etish uchun kanallarga a'zo bo'ling:", reply_markup=get_channel_subscription_keyboard(unsubscribed)); await state.set_state(VotingProcess.awaiting_subscription_check)
    else: await message.answer("Assalomu alaykum! Ovoz berish uchun telefon raqamingizni yuboring:", reply_markup=get_contact_keyboard()); await state.set_state(VotingProcess.awaiting_contact)

async def process_deep_link_vote(message: Message, session: AsyncSession, bot: Bot, poll_id: int, choice_key: str):
    user_id = message.from_user.id; poll = await get_poll_by_id(session, poll_id)
    if not poll or not poll.is_active: return await message.answer("Afsuski, bu so'rovnoma aktiv emas.")
    if await has_user_voted(session, user_id, poll_id): return await message.answer("Siz bu so'rovnomada allaqachon ovoz bergansiz.")
    unsubscribed = await check_all_channels_membership(bot, user_id)
    if unsubscribed: return await message.answer("Ovoz berish uchun, iltimos, avval kanallarga a'zo bo'ling:", reply_markup=get_channel_subscription_keyboard(unsubscribed))
    try: await add_vote(session, user_id, poll_id, choice_key); choice_text = poll.options.get(choice_key, ""); await message.answer(f"✅ Rahmat! Ovozingiz qabul qilindi: <b>\"{choice_text}\"</b>.")
    except Exception as e: logger.error(f"Deep link ovoz berishda xato: {e}"); await message.answer("Xatolik yuz berdi.")

@user_router.callback_query(F.data=="check_subscription", VotingProcess.awaiting_subscription_check)
async def cb_check_subscription(callback_query: CallbackQuery, state: FSMContext, bot: Bot, session: AsyncSession):
    await callback_query.answer("Tekshirilmoqda...", cache_time=1)
    unsubscribed = await check_all_channels_membership(bot, callback_query.from_user.id)
    if unsubscribed: await callback_query.message.edit_text("Afsuski, hali ham barcha kanallarga a'zo emassiz.", reply_markup=get_channel_subscription_keyboard(unsubscribed, "🔄 Qayta tekshirish"))
    else:
        await callback_query.message.delete(); data = await state.get_data(); deep_link_vote = data.get('deep_link_vote')
        if deep_link_vote: poll_id, choice_key = deep_link_vote; await process_deep_link_vote(callback_query.message, session, bot, poll_id, choice_key); await state.clear(); return
        await callback_query.message.answer("Rahmat! Endi telefon raqamingizni yuboring:", reply_markup=get_contact_keyboard()); await state.set_state(VotingProcess.awaiting_contact)
@user_router.message(F.contact, VotingProcess.awaiting_contact)
async def handle_contact(message: Message, state: FSMContext, session: AsyncSession, crypto_service: CryptoService, captcha_service: CaptchaService):
    if await captcha_service.is_user_blocked(message.from_user.id): await message.answer(f"Siz {settings.CAPTCHA_BLOCK_DURATION_MINUTES} daqiqaga bloklangansiz.", reply_markup=remove_keyboard); await state.clear(); return
    await save_user_phone(session, message.from_user.id, crypto_service.encrypt(message.contact.phone_number))
    question = await captcha_service.create_captcha(message.from_user.id); await message.answer(f"Raqam qabul qilindi. Bot emasligingizni tasdiqlang ({settings.CAPTCHA_TIMEOUT_SECONDS}s):\n<b>{question}</b>", reply_markup=remove_keyboard); await state.set_state(VotingProcess.awaiting_captcha)
@user_router.message(VotingProcess.awaiting_contact)
async def invalid_contact_input(message: Message): await message.reply("Iltimos, 'Telefon raqamni yuborish 📞' tugmasi orqali yuboring.")
@user_router.message(VotingProcess.awaiting_captcha)
async def process_captcha_answer(message: Message, state: FSMContext, session: AsyncSession, captcha_service: CaptchaService):
    user_id = message.from_user.id
    if await captcha_service.is_user_blocked(user_id): await message.answer("Siz vaqtinchalik bloklangansiz."); await state.clear(); return
    is_correct = await captcha_service.verify_captcha(user_id, message.text)
    if is_correct:
        await message.answer("✅ To'g'ri!"); active_poll = await get_active_poll(session)
        if not active_poll: await message.answer("Hozircha aktiv so'rovnomalar yo'q."); await state.clear(); return
        if await has_user_voted(session, user_id, active_poll.id): await message.answer("Siz bu so'rovnomada allaqachon ovoz bergansiz."); await state.clear(); return
        await message.answer(f"So'rovnoma:\n<b>{active_poll.question}</b>\n\nVariantni tanlang:", reply_markup=get_poll_options_keyboard(active_poll)); await state.set_state(VotingProcess.awaiting_vote_choice)
    else:
        if await captcha_service.is_user_blocked(user_id): await message.answer(f"Noto'g'ri. Urinishlar tugadi. Siz {settings.CAPTCHA_BLOCK_DURATION_MINUTES} daqiqaga bloklandingiz."); await state.clear()
        else: attempts_left = await captcha_service.get_attempts_left(user_id); await message.answer(f"Noto'g'ri. Yana {attempts_left} ta urinish qoldi.")

@user_router.callback_query(F.data.startswith("vote_poll:"), VotingProcess.awaiting_vote_choice)
async def process_vote_choice(callback_query: CallbackQuery, state: FSMContext, session: AsyncSession, bot: Bot):
    try: _, poll_id_str, _, choice_key = callback_query.data.split(":"); poll_id = int(poll_id_str)
    except (ValueError, IndexError): await callback_query.answer("Xato!", show_alert=True); return
    user_id = callback_query.from_user.id
    unsubscribed_channels = await check_all_channels_membership(bot, user_id)
    if unsubscribed_channels:
        await callback_query.message.answer("❌ Kechirasiz, ovoz berish uchun avval kanallarga a'zo bo'lishingiz shart.", reply_markup=get_channel_subscription_keyboard(unsubscribed_channels, "✅ A'zo bo'ldim, qayta ovoz berish"))
        await callback_query.answer("Iltimos, avval kanallarga to'liq a'zo bo'ling.", show_alert=True); return
    poll = await get_poll_by_id(session, poll_id)
    if not poll or not poll.is_active: await callback_query.message.edit_text("Bu so'rovnoma aktiv emas."); await state.clear(); return await callback_query.answer()
    if await has_user_voted(session, user_id, poll_id): await callback_query.message.edit_text("Siz allaqachon ovoz bergansiz."); await state.clear(); return await callback_query.answer("Allaqon ovoz berilgan!", show_alert=True)
    try:
        await add_vote(session, user_id, poll_id, choice_key); choice_text = poll.options.get(choice_key, "")
        await callback_query.message.edit_text(f"Ovozingiz qabul qilindi: <b>\"{choice_text}\"</b>.\nRahmat!"); await callback_query.answer("Ovozingiz qabul qilindi!", show_alert=True)
    except IntegrityError: await callback_query.message.edit_text("Xatolik: Siz allaqachon ovoz bergansiz."); await callback_query.answer("Xatolik!", show_alert=True)
    except Exception as e: logger.error(f"Ovoz berishda xato: {e}"); await callback_query.message.edit_text("Texnik nosozlik."); await callback_query.answer("Xatolik!", show_alert=True)
    await state.clear()


# --- 10. Botni Ishga Tushirish ---
async def main():
    redis_connection_params = {"host": settings.REDIS_HOST, "port": settings.REDIS_PORT}
    if settings.REDIS_PASSWORD: redis_connection_params["password"] = settings.REDIS_PASSWORD
    
    redis_fsm_client = aioredis.Redis(db=settings.REDIS_DB_FSM, decode_responses=True, **redis_connection_params)
    redis_captcha_client = aioredis.Redis(db=settings.REDIS_DB_CAPTCHA, decode_responses=True, **redis_connection_params)
    
    storage = RedisStorage(redis=redis_fsm_client)
    captcha_service = CaptchaService(redis_client=redis_captcha_client)
    crypto_service = CryptoService(settings.ENCRYPTION_KEY)
    
    bot = Bot(token=settings.BOT_TOKEN.get_secret_value(), default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=storage)

    dp.update.middleware(DbSessionMiddleware(pool=AsyncSessionFactory))
    dp.workflow_data.update({"crypto_service": crypto_service, "captcha_service": captcha_service, "bot": bot})

    dp.include_router(admin_router); dp.include_router(user_router)
    await create_db_and_tables()
    logger.info(f"Bot Redis va {settings.DB_TYPE.upper()} bilan ishga tushirilmoqda...")
    try:
        await redis_fsm_client.ping(); logger.info("FSM uchun Redis'ga ulanish muvaffaqiyatli.")
        await redis_captcha_client.ping(); logger.info("CAPTCHA uchun Redis'ga ulanish muvaffaqiyatli.")
        await bot.delete_webhook(drop_pending_updates=True); await dp.start_polling(bot)
    except RedisConnectionError as e: logger.critical(f"Redis serveriga ulanib bo'lmadi: {e}. Sozlamalarni tekshiring.")
    except Exception as e: logger.critical(f"Botni ishga tushirishda kutilmagan xatolik: {e}", exc_info=True)
    finally: await bot.session.close(); await redis_fsm_client.close(); await redis_captcha_client.close(); logger.info("Bot to'xtatildi.")

if __name__ == "__main__":
    try: asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): logger.info("Bot foydalanuvchi tomonidan to'xtatildi.")