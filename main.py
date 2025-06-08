# main.py (Barcha sozlamalar kod ichida, .env faylsiz, Redis'siz, to'liq versiya)

"""
Telegram Ovoz Berish Boti (MemoryStorage bilan, sozlamalar kod ichida)

Redis o'rniga barcha vaqtinchalik ma'lumotlar (FSM, CAPTCHA)
botning o'z xotirasida saqlanadi. Barcha sozlamalar ham
tashqi fayldan o'qilmaydi, kodning o'zida berilgan.
"""

import asyncio
import logging
import os
import random
import time
from typing import List, Union, Dict, Optional, Callable, Any, Awaitable, Tuple

# Aiogram imports
from aiogram import Bot, Dispatcher, F, BaseMiddleware, Router
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
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

# Cryptography import (shifrlash uchun)
from cryptography.fernet import Fernet, InvalidToken

# --- 0. Logging sozlamalari ---
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(name)s - %(message)s"
)
logger = logging.getLogger(__name__)


# --- 1. Konfiguratsiya (to'g'ridan-to'g'ri kodda) ---
class AppSettings:
    """ Barcha sozlamalar saqlanadigan klass """
    BOT_TOKEN: str = "7611825109:AAHfh9DSZc7E2LJMB7LlRhWUFqLtadAXHYg" # <-- BOT TOKENI
    ADMIN_IDS: List[int] = [1062838548] # <-- ADMIN ID
    REQUIRED_CHANNELS: List[Union[str, int]] = [-1002217048438, "@adsasdsfeqf3"] # <-- KANALLAR
    
    ENCRYPTION_KEY: str = "AJUcGHHG2TItJ_Bf0Lcqn_NsKHDazXKinREdJt88PWM="
    DB_NAME: str = "vote_bot_hardcoded.db"
    
    CAPTCHA_TIMEOUT_SECONDS: int = 60
    CAPTCHA_MAX_ATTEMPTS: int = 3
    CAPTCHA_BLOCK_DURATION_MINUTES: int = 5

    @property
    def DATABASE_URL(self) -> str:
        base_dir = os.path.dirname(os.path.abspath(__file__))
        db_path = os.path.join(base_dir, self.DB_NAME)
        return f"sqlite+aiosqlite:///{db_path}"

settings = AppSettings()


# --- 2. Shifrlash Xizmati (CryptoService) ---
class CryptoService:
    def __init__(self, key: str):
        try:
            self.fernet = Fernet(key.encode())
        except (ValueError, TypeError) as e:
            logger.critical(f"ENCRYPTION_KEY yaroqsiz formatda: {e}"); exit(1)
            
    def encrypt(self, data: str) -> bytes:
        return self.fernet.encrypt(data.encode('utf-8'))

    def decrypt(self, encrypted_data: bytes) -> Optional[str]:
        try:
            return self.fernet.decrypt(encrypted_data).decode('utf-8')
        except (InvalidToken, Exception):
            return None


# --- 3. Ma'lumotlar Bazasi (SQLAlchemy) va CRUD ---
Base = declarative_base()

class User(Base):
    __tablename__ = "users"; id = Column(BigInteger, primary_key=True); username = Column(String); first_name = Column(String); phone_number_encrypted = Column(LargeBinary); created_at = Column(DateTime, server_default=func.now()); votes = relationship("Vote", back_populates="user")
class Poll(Base):
    __tablename__ = "polls"; id = Column(Integer, primary_key=True, autoincrement=True); question = Column(Text, nullable=False); options = Column(JSON, nullable=False); is_active = Column(Boolean, default=False); created_by_admin_id = Column(BigInteger, nullable=False); created_at = Column(DateTime, server_default=func.now()); votes = relationship("Vote", back_populates="poll")
class Vote(Base):
    __tablename__ = "votes"; id = Column(Integer, primary_key=True, autoincrement=True); user_id = Column(BigInteger, ForeignKey("users.id")); poll_id = Column(Integer, ForeignKey("polls.id")); choice_key = Column(String); created_at = Column(DateTime, server_default=func.now()); user = relationship("User", back_populates="votes"); poll = relationship("Poll", back_populates="votes"); __table_args__ = (UniqueConstraint('user_id', 'poll_id'),)

engine = create_async_engine(settings.DATABASE_URL)
AsyncSessionFactory = async_sessionmaker(engine, expire_on_commit=False)

async def create_db_and_tables():
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    logger.info("Ma'lumotlar bazasi jadvallari yaratildi/tekshirildi.")

async def get_or_create_user(session: AsyncSession, user_id: int, username: Optional[str] = None, first_name: Optional[str] = None) -> User:
    result = await session.execute(select(User).where(User.id == user_id))
    user = result.scalar_one_or_none()
    if not user:
        user = User(id=user_id, username=username, first_name=first_name)
        session.add(user)
        await session.commit(); await session.refresh(user)
    return user

async def save_user_phone(session: AsyncSession, user_id: int, encrypted_phone_number: bytes):
    stmt = update(User).where(User.id == user_id).values(phone_number_encrypted=encrypted_phone_number)
    await session.execute(stmt); await session.commit()

async def get_active_poll(session: AsyncSession) -> Optional[Poll]:
    return await session.scalar(select(Poll).where(Poll.is_active == True).order_by(Poll.created_at.desc()).limit(1))

async def get_poll_by_id(session: AsyncSession, poll_id: int) -> Optional[Poll]:
    return await session.get(Poll, poll_id)

async def has_user_voted(session: AsyncSession, user_id: int, poll_id: int) -> bool:
    return await session.scalar(select(Vote.id).where(Vote.user_id == user_id, Vote.poll_id == poll_id).limit(1)) is not None

async def add_vote(session: AsyncSession, user_id: int, poll_id: int, choice_key: str):
    vote = Vote(user_id=user_id, poll_id=poll_id, choice_key=choice_key)
    session.add(vote); await session.commit()

async def create_poll(session: AsyncSession, question: str, options: Dict[str, str], admin_id: int, is_active: bool = False) -> Poll:
    if is_active: await session.execute(update(Poll).values(is_active=False))
    poll = Poll(question=question, options=options, created_by_admin_id=admin_id, is_active=is_active)
    session.add(poll); await session.commit(); await session.refresh(poll)
    return poll

async def get_all_polls(session: AsyncSession) -> List[Poll]:
    return (await session.execute(select(Poll).order_by(Poll.created_at.desc()))).scalars().all()

async def set_poll_active_status(session: AsyncSession, poll_id: int, active: bool) -> Optional[Poll]:
    if active: await session.execute(update(Poll).values(is_active=False))
    result = await session.execute(update(Poll).where(Poll.id == poll_id).values(is_active=active).returning(Poll))
    await session.commit(); return result.scalar_one_or_none()

async def get_poll_results(session: AsyncSession, poll_id: int) -> Dict[str, int]:
    result = await session.execute(select(Vote.choice_key, func.count(Vote.id).label("c")).where(Vote.poll_id == poll_id).group_by(Vote.choice_key))
    return {row.choice_key: row.c for row in result.all()}


# --- 4. CAPTCHA Xizmati (Xotirada ishlaydigan versiya) ---
class CaptchaServiceMemory:
    def __init__(self):
        self.captchas: Dict[int, Tuple[str, float]] = {}
        self.attempts: Dict[int, Tuple[int, float]] = {}
        self.block_list: Dict[int, float] = {}

    def _cleanup_user(self, user_id: int):
        self.captchas.pop(user_id, None); self.attempts.pop(user_id, None)

    def _generate_math_captcha(self) -> tuple[str, str]:
        n1,n2=random.randint(1,10),random.randint(1,10);ops={'+':n1+n2,'-':abs(n1-n2),'*':n1*n2};op=random.choice(list(ops.keys()));q_n1,q_n2=(n1,n2) if n1>=n2 else (n2,n1);q=f"{q_n1} {op} {q_n2} = ?";a=str(ops[op]);return q,a

    async def create_captcha(self, user_id: int) -> str:
        q, a = self._generate_math_captcha(); t = time.time(); self.captchas[user_id] = (a, t); self.attempts[user_id] = (0, t); return q

    async def verify_captcha(self, user_id: int, user_answer: str) -> bool:
        if user_id not in self.captchas: return False
        correct_answer, creation_time = self.captchas[user_id]
        if time.time() - creation_time > settings.CAPTCHA_TIMEOUT_SECONDS: self._cleanup_user(user_id); return False
        if correct_answer == user_answer.strip(): self._cleanup_user(user_id); return True
        else:
            attempts_made, _ = self.attempts.get(user_id, (0, 0)); attempts_made += 1; self.attempts[user_id] = (attempts_made, creation_time)
            if attempts_made >= settings.CAPTCHA_MAX_ATTEMPTS: self.block_list[user_id] = time.time() + settings.CAPTCHA_BLOCK_DURATION_MINUTES * 60; self._cleanup_user(user_id)
            return False

    async def is_user_blocked(self, user_id: int) -> bool:
        if user_id in self.block_list:
            if time.time() < self.block_list[user_id]: return True
            else: self.block_list.pop(user_id, None)
        return False

    async def get_attempts_left(self, user_id: int) -> int:
        attempts_made, _ = self.attempts.get(user_id, (0, 0))
        return settings.CAPTCHA_MAX_ATTEMPTS - attempts_made


# --- 5. FSM States, Keyboards, Middleware, Helpers ---
class VotingProcess(StatesGroup): awaiting_subscription_check=State();awaiting_contact=State();awaiting_captcha=State();awaiting_vote_choice=State()
class AdminPollManagement(StatesGroup): awaiting_poll_question=State();awaiting_poll_options=State()

class DbSessionMiddleware(BaseMiddleware):
    def __init__(self,pool:async_sessionmaker[AsyncSession]): self.session_pool=pool
    async def __call__(self,handler:Callable,event:TelegramObject,data:Dict[str,Any])->Any:
        async with self.session_pool() as session: data["session"]=session; return await handler(event,data)

def get_contact_keyboard() -> ReplyKeyboardMarkup: return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Telefon raqamni yuborish 📞", request_contact=True)]], resize_keyboard=True, one_time_keyboard=True)
def get_channel_subscription_keyboard(chans:List[Dict[str,str]],txt:str="✅ A'zo bo'ldim")->InlineKeyboardMarkup:
    b=InlineKeyboardBuilder();[b.row(InlineKeyboardButton(text=f"➡️ {c['title']}",url=c['url'])) for c in chans];b.row(InlineKeyboardButton(text=txt,callback_data="check_subscription"));return b.as_markup()
def get_poll_options_keyboard(p:Poll)->InlineKeyboardMarkup:b=InlineKeyboardBuilder();[b.row(InlineKeyboardButton(text=t,callback_data=f"vote_poll:{p.id}:choice:{k}")) for k,t in p.options.items()];return b.as_markup()
def get_admin_poll_list_keyboard(polls:List[Poll])->InlineKeyboardMarkup:b=InlineKeyboardBuilder();[b.row(InlineKeyboardButton(text=f"{'🟢' if p.is_active else '⚪️'} {p.question[:35]}...",callback_data=f"admin:poll:view:{p.id}")) for p in polls];b.row(InlineKeyboardButton(text="➕ Yangi so'rovnoma",callback_data="admin:poll:create"));return b.as_markup()
def get_admin_poll_manage_keyboard(p_id:int,is_active:bool)->InlineKeyboardMarkup:b=InlineKeyboardBuilder();b.row(InlineKeyboardButton(text="⚪️ Noaktiv qilish" if is_active else "🟢 Aktiv qilish",callback_data=f"admin:poll:toggle:{p_id}"));b.row(InlineKeyboardButton(text="📊 Natijalar",callback_data=f"admin:poll:results:{p_id}"));b.row(InlineKeyboardButton(text="🔙 Ortga",callback_data="admin:poll:list"));return b.as_markup()
remove_keyboard=ReplyKeyboardRemove()

async def check_all_channels_membership(bot: Bot, user_id: int) -> List[Dict[str, str]]:
    unsubscribed = []
    if not settings.REQUIRED_CHANNELS: return []
    for channel_id in settings.REQUIRED_CHANNELS:
        try:
            member = await bot.get_chat_member(chat_id=channel_id, user_id=user_id)
            if member.status not in ("member", "administrator", "creator"): raise TelegramBadRequest("User not member")
        except TelegramBadRequest:
            try:
                chat = await bot.get_chat(channel_id)
                link = chat.invite_link if hasattr(chat, 'invite_link') and chat.invite_link else f"https://t.me/{chat.username}"
                unsubscribed.append({"title": chat.title, "url": link})
            except Exception as e: logger.error(f"Kanal ma'lumotini olishda xato ({channel_id}): {e}")
        except Exception as e: logger.error(f"Kanal tekshirishda xato ({channel_id}): {e}")
    return unsubscribed


# --- 9. Handlerlar (Routers) ---
admin_router = Router(); admin_router.message.filter(F.from_user.id.in_(settings.ADMIN_IDS)); admin_router.callback_query.filter(F.from_user.id.in_(settings.ADMIN_IDS))
user_router = Router()

@admin_router.message(Command("admin", "polls"))
async def cmd_admin_polls(m: Message, session: AsyncSession): await m.answer("Mavjud so'rovnomalar:", reply_markup=get_admin_poll_list_keyboard(await get_all_polls(session)))
@admin_router.callback_query(F.data == "admin:poll:list")
async def cb_admin_poll_list(c: CallbackQuery, session: AsyncSession): await c.message.edit_text("Mavjud so'rovnomalar:", reply_markup=get_admin_poll_list_keyboard(await get_all_polls(session))); await c.answer()
@admin_router.callback_query(F.data == "admin:poll:create")
async def cb_admin_poll_create(c: CallbackQuery, state: FSMContext): await c.message.edit_text("Yangi so'rovnoma uchun savolni yuboring:"); await state.set_state(AdminPollManagement.awaiting_poll_question); await c.answer()
@admin_router.message(AdminPollManagement.awaiting_poll_question)
async def process_poll_question(m: Message, state: FSMContext): await state.update_data(question=m.text); await m.answer("Variantlarni yuboring (har biri yangi qatorda, kamida 2ta):\nVariant A\nVariant B"); await state.set_state(AdminPollManagement.awaiting_poll_options)
@admin_router.message(AdminPollManagement.awaiting_poll_options)
async def process_poll_options(m: Message, state: FSMContext, session: AsyncSession):
    opts=[opt.strip() for opt in m.text.split('\n') if opt.strip()];_d={str(i+1):o for i,o in enumerate(opts)};d=await state.get_data()
    if len(opts)<2: return await m.answer("Kamida 2 ta variant kerak.")
    p=await create_poll(session,question=d["question"],options=_d,admin_id=m.from_user.id);await m.answer(f"So'rovnoma '{p.question}' yaratildi!")
    await state.clear(); await m.answer("Mavjud so'rovnomalar:", reply_markup=get_admin_poll_list_keyboard(await get_all_polls(session)))
@admin_router.callback_query(F.data.startswith("admin:poll:view:"))
async def cb_admin_poll_view(c: CallbackQuery, session: AsyncSession):
    p_id=int(c.data.split(":")[-1]); p=await get_poll_by_id(session, p_id)
    if not p: return await c.answer("So'rovnoma topilmadi!", show_alert=True)
    o_s="\n".join([f"▪️ {v}" for k,v in p.options.items()]);s_t='🟢 Aktiv' if p.is_active else '⚪️ Noaktiv'
    await c.message.edit_text(f"<b>So'rovnoma:</b> {p.question}\n\n<b>Variantlar:</b>\n{o_s}\n\n<b>Status:</b> {s_t}", reply_markup=get_admin_poll_manage_keyboard(p.id,p.is_active));await c.answer()
@admin_router.callback_query(F.data.startswith("admin:poll:toggle:"))
async def cb_admin_poll_toggle(c: CallbackQuery, session: AsyncSession):
    p_id=int(c.data.split(":")[-1]);curr_p=await get_poll_by_id(session,p_id)
    if not curr_p: return await c.answer("So'rovnoma topilmadi!",show_alert=True)
    upd_p=await set_poll_active_status(session,p_id,not curr_p.is_active)
    await c.answer(f"Status {'🟢 Aktiv' if upd_p.is_active else '⚪️ Noaktiv'} qilindi.",show_alert=True)
    await cb_admin_poll_view(c, session)
@admin_router.callback_query(F.data.startswith("admin:poll:results:"))
async def cb_admin_poll_results(c: CallbackQuery, session: AsyncSession):
    p_id=int(c.data.split(":")[-1]);p=await get_poll_by_id(session,p_id)
    if not p: return await c.answer("So'rovnoma topilmadi!",show_alert=True)
    res=await get_poll_results(session,p_id);txt=f"📊 <b>'{p.question}'</b> natijalari:\n\n"
    if not res:txt+="Hali ovozlar yo'q."
    else:
        tot=sum(res.values());[txt:=txt+f"▫️ {p.options.get(k,f'Noma`lum({k})')}: <b>{v} ta</b> ({v/tot*100 if tot>0 else 0:.2f}%)\n" for k,v in sorted(res.items(),key=lambda i:i[1],reverse=True)]
        txt+=f"\nJami: <b>{tot}</b>"
    await c.message.edit_text(txt,reply_markup=get_admin_poll_manage_keyboard(p.id,p.is_active));await c.answer()

@user_router.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    await state.clear();await get_or_create_user(session,m.from_user.id,m.from_user.username,m.from_user.first_name)
    unsub=await check_all_channels_membership(bot,m.from_user.id)
    if unsub:await m.answer("Assalomu alaykum! Ishtirok etish uchun kanallarga a'zo bo'ling:",reply_markup=get_channel_subscription_keyboard(unsub));await state.set_state(VotingProcess.awaiting_subscription_check)
    else:await m.answer("Assalomu alaykum! Telefon raqamingizni yuboring:",reply_markup=get_contact_keyboard());await state.set_state(VotingProcess.awaiting_contact)
@user_router.callback_query(F.data=="check_subscription",VotingProcess.awaiting_subscription_check)
async def cb_check_subscription(c: CallbackQuery, state: FSMContext, bot: Bot):
    await c.answer("Tekshirilmoqda...", cache_time=1)
    unsub=await check_all_channels_membership(bot,c.from_user.id)
    if unsub:await c.message.edit_text("Afsuski, siz hali ham barcha kanallarga a'zo bo'lmagansiz.",reply_markup=get_channel_subscription_keyboard(unsub,"🔄 Qayta tekshirish"))
    else:await c.message.delete();await c.message.answer("Rahmat! Endi telefon raqamingizni yuboring:",reply_markup=get_contact_keyboard());await state.set_state(VotingProcess.awaiting_contact)
@user_router.message(F.contact,VotingProcess.awaiting_contact)
async def handle_contact(m: Message, state: FSMContext, session: AsyncSession, crypto_service: CryptoService, captcha_service: CaptchaServiceMemory):
    if await captcha_service.is_user_blocked(m.from_user.id):await m.answer(f"Siz {settings.CAPTCHA_BLOCK_DURATION_MINUTES} daqiqaga bloklangansiz.",reply_markup=remove_keyboard);await state.clear();return
    await save_user_phone(session, m.from_user.id, crypto_service.encrypt(m.contact.phone_number))
    q=await captcha_service.create_captcha(m.from_user.id)
    await m.answer(f"Raqam qabul qilindi. Bot emasligingizni tasdiqlang ({settings.CAPTCHA_TIMEOUT_SECONDS}s):\n<b>{q}</b>",reply_markup=remove_keyboard);await state.set_state(VotingProcess.awaiting_captcha)
@user_router.message(VotingProcess.awaiting_contact)
async def invalid_contact_input(m: Message):await m.reply("Iltimos, 'Telefon raqamni yuborish 📞' tugmasi orqali yuboring.")
@user_router.message(VotingProcess.awaiting_captcha)
async def process_captcha_answer(m: Message, state: FSMContext, session: AsyncSession, captcha_service: CaptchaServiceMemory):
    uid=m.from_user.id
    if await captcha_service.is_user_blocked(uid):await m.answer("Siz vaqtinchalik bloklangansiz.");await state.clear();return
    is_corr=await captcha_service.verify_captcha(uid,m.text)
    if is_corr:
        await m.answer("✅ To'g'ri!");ap=await get_active_poll(session)
        if not ap:await m.answer("Hozircha aktiv so'rovnomalar yo'q.");await state.clear();return
        if await has_user_voted(session,uid,ap.id):await m.answer("Siz bu so'rovnomada allaqachon ovoz bergansiz.");await state.clear();return
        await m.answer(f"So'rovnoma:\n<b>{ap.question}</b>\n\nVariantni tanlang:",reply_markup=get_poll_options_keyboard(ap));await state.set_state(VotingProcess.awaiting_vote_choice)
    else:
        if await captcha_service.is_user_blocked(uid):await m.answer(f"Noto'g'ri. Urinishlar tugadi. Siz {settings.CAPTCHA_BLOCK_DURATION_MINUTES} daqiqaga bloklandingiz.");await state.clear()
        else:att_left=await captcha_service.get_attempts_left(uid);await m.answer(f"Noto'g'ri. Yana {att_left} ta urinish qoldi.")
@user_router.callback_query(F.data.startswith("vote_poll:"),VotingProcess.awaiting_vote_choice)
async def process_vote_choice(c: CallbackQuery, state: FSMContext, session: AsyncSession):
    uid=c.from_user.id;p_id=int(c.data.split(":")[1]);ch_k=c.data.split(":")[-1]
    p=await get_poll_by_id(session,p_id)
    if not p or not p.is_active:await c.message.edit_text("Bu so'rovnoma aktiv emas.");await state.clear();return await c.answer()
    if await has_user_voted(session,uid,p_id):await c.message.edit_text("Siz allaqachon ovoz bergansiz.");await state.clear();return await c.answer("Allaqachon ovoz berilgan!",show_alert=True)
    try:
        await add_vote(session,uid,p_id,ch_k);ch_t=p.options.get(ch_k,"")
        await c.message.edit_text(f"Ovozingiz qabul qilindi: <b>\"{ch_t}\"</b>.\nRahmat!");await c.answer("Ovozingiz qabul qilindi!",show_alert=True)
    except IntegrityError:await c.message.edit_text("Xatolik: Siz allaqachon ovoz bergansiz.");await c.answer("Xatolik!",show_alert=True)
    except Exception as e:logger.error(f"Ovoz berishda xato: {e}");await c.message.edit_text("Texnik nosozlik.");await c.answer("Xatolik!",show_alert=True)
    await state.clear()


# --- 10. Botni Ishga Tushirish ---
async def main():
    storage = MemoryStorage()
    captcha_service = CaptchaServiceMemory()
    crypto_service = CryptoService(settings.ENCRYPTION_KEY)
    
    bot = Bot(token=settings.BOT_TOKEN, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher(storage=storage)

    dp.update.middleware(DbSessionMiddleware(pool=AsyncSessionFactory))
    dp.workflow_data.update({
        "crypto_service": crypto_service,
        "captcha_service": captcha_service,
        "bot": bot
    })

    dp.include_router(admin_router)
    dp.include_router(user_router)
    
    await create_db_and_tables()

    logger.info("Bot ishga tushirilmoqda (sozlamalar kod ichida)...")
    try:
        await bot.delete_webhook(drop_pending_updates=True)
        await dp.start_polling(bot)
    except Exception as e:
        logger.critical(f"Botni ishga tushirishda kutilmagan xatolik: {e}", exc_info=True)
    finally:
        await bot.session.close()
        logger.info("Bot to'xtatildi.")

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except (KeyboardInterrupt, SystemExit):
        logger.info("Bot foydalanuchi tomonidan to'xtatildi.")
