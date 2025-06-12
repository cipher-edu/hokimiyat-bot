import asyncio
import logging
import os
import random
import time
from typing import List, Union, Dict, Optional, Callable, Any, Awaitable, Tuple

from aiogram import Bot, Dispatcher, F, BaseMiddleware, Router
from aiogram.client.bot import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.exceptions import TelegramBadRequest, TelegramForbiddenError, TelegramRetryAfter
from aiogram.filters import CommandStart, Command
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
from aiogram.types import (
    Message, CallbackQuery, ReplyKeyboardMarkup, KeyboardButton,
    InlineKeyboardMarkup, InlineKeyboardButton, ReplyKeyboardRemove, TelegramObject
)
from aiogram.filters.command import CommandObject
from aiogram.utils.keyboard import InlineKeyboardBuilder

from sqlalchemy import (create_engine, Column, BigInteger, String, DateTime, ForeignKey, Integer, LargeBinary, UniqueConstraint, JSON, Boolean, Text, select, update, func)
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import declarative_base, relationship
from sqlalchemy.exc import IntegrityError

from cryptography.fernet import Fernet, InvalidToken

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(name)s - %(message)s")
logger = logging.getLogger(__name__)


class AppSettings:
    BOT_TOKEN: str = "bot tokenini shu yerga yozing"
    ADMIN_IDS: List[int] = [1062838548]
    REQUIRED_CHANNELS: List[Union[str, int]] = [-1002217048438, "@adsasdsfeqf3"]
    ENCRYPTION_KEY: str = "AJUcGHHG2TItJ_Bf0Lcqn_NsKHDazXKinREdJt88PWM="
    DB_NAME: str = "vote_bot_broadcast.db"
    CAPTCHA_TIMEOUT_SECONDS: int = 60
    CAPTCHA_MAX_ATTEMPTS: int = 3
    CAPTCHA_BLOCK_DURATION_MINUTES: int = 5
    @property
    def DATABASE_URL(self) -> str:
        base_dir = os.path.dirname(os.path.abspath(__file__)); db_path = os.path.join(base_dir, self.DB_NAME); return f"sqlite+aiosqlite:///{db_path}"
settings = AppSettings()


class CryptoService:
    def __init__(self, key: str):
        try: self.fernet = Fernet(key.encode())
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
    async with engine.begin() as conn: await conn.run_sync(Base.metadata.create_all); logger.info("DB jadvallari yaratildi.")
async def get_or_create_user(s: AsyncSession, u_id: int, u: str = None, f_n: str = None) -> User:
    r = await s.execute(select(User).where(User.id == u_id)); user = r.scalar_one_or_none()
    if not user: user = User(id=u_id, username=u, first_name=f_n); s.add(user); await s.commit(); await s.refresh(user)
    return user
async def save_user_phone(s: AsyncSession, u_id: int, p: bytes): await s.execute(update(User).where(User.id==u_id).values(phone_number_encrypted=p)); await s.commit()
async def get_active_poll(s: AsyncSession) -> Optional[Poll]: return await s.scalar(select(Poll).where(Poll.is_active==True).order_by(Poll.created_at.desc()).limit(1))
async def get_poll_by_id(s: AsyncSession, p_id: int) -> Optional[Poll]: return await s.get(Poll, p_id)
async def has_user_voted(s: AsyncSession, u_id: int, p_id: int) -> bool: return await s.scalar(select(Vote.id).where(Vote.user_id==u_id, Vote.poll_id==p_id).limit(1)) is not None
async def add_vote(s: AsyncSession, u_id: int, p_id: int, c_key: str): s.add(Vote(user_id=u_id, poll_id=p_id, choice_key=c_key)); await s.commit()
async def create_poll(s: AsyncSession, q: str, o: Dict[str, str], a_id: int, active: bool = False) -> Poll:
    if active: await s.execute(update(Poll).values(is_active=False))
    p = Poll(question=q, options=o, created_by_admin_id=a_id, is_active=active); s.add(p); await s.commit(); await s.refresh(p); return p
async def get_all_polls(s: AsyncSession) -> List[Poll]: return (await s.execute(select(Poll).order_by(Poll.created_at.desc()))).scalars().all()
async def set_poll_active_status(s: AsyncSession, p_id: int, active: bool) -> Optional[Poll]:
    if active: await s.execute(update(Poll).values(is_active=False))
    r = await s.execute(update(Poll).where(Poll.id == p_id).values(is_active=active).returning(Poll)); await s.commit(); return r.scalar_one_or_none()
async def get_poll_results(s: AsyncSession, p_id: int) -> Dict[str, int]:
    r = await s.execute(select(Vote.choice_key, func.count(Vote.id).label("c")).where(Vote.poll_id == p_id).group_by(Vote.choice_key)); return {row.choice_key: row.c for row in r.all()}
async def get_all_user_ids(session: AsyncSession) -> List[int]: # <-- OMMIVIY XABAR UCHUN YANGI FUNKSIYA
    result = await session.execute(select(User.id))
    return result.scalars().all()

class CaptchaServiceMemory:
    def __init__(self): self.captchas: Dict[int, Tuple[str, float]] = {}; self.attempts: Dict[int, Tuple[int, float]] = {}; self.block_list: Dict[int, float] = {}
    def _cleanup_user(self, u_id:int): self.captchas.pop(u_id, None); self.attempts.pop(u_id, None)
    def _generate_math_captcha(self)->tuple[str,str]: n1,n2=random.randint(1,10),random.randint(1,10);ops={'+':n1+n2,'-':abs(n1-n2),'*':n1*n2};op=random.choice(list(ops.keys()));q_n1,q_n2=(n1,n2) if n1>=n2 else (n2,n1);q=f"{q_n1} {op} {q_n2} = ?";a=str(ops[op]);return q,a
    async def create_captcha(self,u_id:int)->str: q,a=self._generate_math_captcha();t=time.time();self.captchas[u_id]=(a,t);self.attempts[u_id]=(0,t);return q
    async def verify_captcha(self,u_id:int,u_a:str)->bool:
        if u_id not in self.captchas: return False
        ans, c_time = self.captchas[u_id]
        if time.time()-c_time > settings.CAPTCHA_TIMEOUT_SECONDS: self._cleanup_user(u_id); return False
        if ans == u_a.strip(): self._cleanup_user(u_id); return True
        else:
            a_made,_=self.attempts.get(u_id,(0,0));a_made+=1;self.attempts[u_id]=(a_made,c_time)
            if a_made >= settings.CAPTCHA_MAX_ATTEMPTS: self.block_list[u_id]=time.time()+settings.CAPTCHA_BLOCK_DURATION_MINUTES*60;self._cleanup_user(u_id)
            return False
    async def is_user_blocked(self,u_id:int)->bool:
        if u_id in self.block_list:
            if time.time() < self.block_list[u_id]: return True
            else: self.block_list.pop(u_id, None)
        return False
    async def get_attempts_left(self,u_id:int)->int: a_made,_=self.attempts.get(u_id,(0,0));return settings.CAPTCHA_MAX_ATTEMPTS-a_made


class VotingProcess(StatesGroup): awaiting_subscription_check=State();awaiting_contact=State();awaiting_captcha=State();awaiting_vote_choice=State()
class AdminPollManagement(StatesGroup): awaiting_poll_question=State();awaiting_poll_options=State()
class AdCreation(StatesGroup): awaiting_poll_selection=State();awaiting_post_text=State();awaiting_post_photo=State()
class Broadcast(StatesGroup): awaiting_ad_text=State();awaiting_ad_photo=State();awaiting_confirmation=State() # <-- OMMIVIY XABAR UCHUN YANGI FSM

class DbSessionMiddleware(BaseMiddleware):
    def __init__(self,pool:async_sessionmaker[AsyncSession]): self.session_pool=pool
    async def __call__(self,handler:Callable,event:TelegramObject,data:Dict[str,Any])->Any:
        async with self.session_pool() as session: data["session"]=session; return await handler(event,data)

def get_contact_keyboard()->ReplyKeyboardMarkup:return ReplyKeyboardMarkup(keyboard=[[KeyboardButton(text="Telefon raqamni yuborish 📞",request_contact=True)]],resize_keyboard=True,one_time_keyboard=True)
def get_channel_subscription_keyboard(chans:List[Dict[str,str]],txt:str="✅ A'zo bo'ldim")->InlineKeyboardMarkup:
    b=InlineKeyboardBuilder();[b.row(InlineKeyboardButton(text=f"➡️ {c['title']}",url=c['url'])) for c in chans];b.row(InlineKeyboardButton(text=txt,callback_data="check_subscription"));return b.as_markup()
def get_poll_options_keyboard(p:Poll)->InlineKeyboardMarkup:b=InlineKeyboardBuilder();[b.row(InlineKeyboardButton(text=t,callback_data=f"vote_poll:{p.id}:choice:{k}")) for k,t in p.options.items()];return b.as_markup()
def get_admin_poll_list_keyboard(polls:List[Poll])->InlineKeyboardMarkup:b=InlineKeyboardBuilder();[b.row(InlineKeyboardButton(text=f"{'🟢' if p.is_active else '⚪️'} {p.question[:35]}...",callback_data=f"admin:poll:view:{p.id}")) for p in polls];b.row(InlineKeyboardButton(text="➕ Yangi so'rovnoma",callback_data="admin:poll:create"));return b.as_markup()
def get_admin_poll_manage_keyboard(p_id:int,is_active:bool)->InlineKeyboardMarkup:b=InlineKeyboardBuilder();b.row(InlineKeyboardButton(text="⚪️ Noaktiv qilish" if is_active else "🟢 Aktiv qilish",callback_data=f"admin:poll:toggle:{p_id}"));b.row(InlineKeyboardButton(text="📊 Natijalar",callback_data=f"admin:poll:results:{p_id}"));b.row(InlineKeyboardButton(text="🔙 Ortga",callback_data="admin:poll:list"));return b.as_markup()
def get_poll_selection_for_ad_keyboard(polls:List[Poll])->InlineKeyboardMarkup:b=InlineKeyboardBuilder();[b.row(InlineKeyboardButton(text=f"{p.question[:40]}...",callback_data=f"ad_select_poll:{p.id}")) for p in polls];return b.as_markup()
def get_ad_post_keyboard(p:Poll,bot_username:str)->InlineKeyboardMarkup:
    b=InlineKeyboardBuilder();[b.row(InlineKeyboardButton(text=t,url=f"https://t.me/{bot_username}?start=vote_{p.id}_{k}")) for k,t in p.options.items()];return b.as_markup()
remove_keyboard=ReplyKeyboardRemove()

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

admin_router = Router(); admin_router.message.filter(F.from_user.id.in_(settings.ADMIN_IDS)); admin_router.callback_query.filter(F.from_user.id.in_(settings.ADMIN_IDS))
user_router = Router()

@admin_router.message(Command("admin", "polls"))
async def cmd_admin_polls(m: Message, s: AsyncSession): await m.answer("Mavjud so'rovnomalar:", reply_markup=get_admin_poll_list_keyboard(await get_all_polls(s)))

@admin_router.message(Command("rek"))
async def cmd_create_ad(m: Message, s: AsyncSession, state: FSMContext):
    polls = await get_all_polls(s)
    if not polls: return await m.answer("Reklama uchun avval so'rovnoma yarating.")
    await m.answer("Reklama posti uchun so'rovnomani tanlang:", reply_markup=get_poll_selection_for_ad_keyboard(polls)); await state.set_state(AdCreation.awaiting_poll_selection)

@admin_router.message(Command("send_ad"))
async def cmd_broadcast_start(message: Message, state: FSMContext):
    await state.set_state(Broadcast.awaiting_ad_text)
    await message.answer("Barcha foydalanuvchilarga yuborish uchun reklama matnini yuboring.\n\nBekor qilish uchun: /bekor_qilish")

@admin_router.message(Command("bekor_qilish"), F.state.in_(AdCreation.__all_states__ + Broadcast.__all_states__))
async def cancel_any_state(message: Message, state: FSMContext):
    await state.clear()
    await message.answer("Jarayon bekor qilindi.", reply_markup=remove_keyboard)

@admin_router.message(Broadcast.awaiting_ad_text)
async def broadcast_get_text(message: Message, state: FSMContext):
    await state.update_data(post_text=message.html_text)
    await state.set_state(Broadcast.awaiting_ad_photo)
    await message.answer("Matn qabul qilindi. Endi post uchun suratni yuboring.")

@admin_router.message(F.photo, Broadcast.awaiting_ad_photo)
async def broadcast_get_photo(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    await state.update_data(photo_file_id=message.photo[-1].file_id)
    data = await state.get_data()
    
    user_ids = await get_all_user_ids(session)
    user_count = len(user_ids)
    
    await state.update_data(user_count=user_count)


    await bot.send_photo(
        chat_id=message.from_user.id,
        photo=data['photo_file_id'],
        caption=data['post_text']
    )
    
    await message.answer(
        f"Post tayyor. Sizda <b>{user_count}</b> ta foydalanuvchi mavjud.\n\n"
        f"Ushbu xabarni barcha foydalanuvchilarga yuborishga ishonchingiz komilmi?\n\n"
        f"Tasdiqlash uchun <b>ha</b> deb yozing. Bekor qilish uchun boshqa har qanday matn yuboring yoki /bekor_qilish buyrug'ini bering.",
        parse_mode=ParseMode.HTML
    )
    await state.set_state(Broadcast.awaiting_confirmation)

@admin_router.message(Broadcast.awaiting_confirmation)
async def broadcast_confirmation(message: Message, state: FSMContext, session: AsyncSession, bot: Bot):
    if message.text.lower() != 'ha':
        await state.clear()
        return await message.answer("Reklama yuborish bekor qilindi.")

    data = await state.get_data()
    user_ids = await get_all_user_ids(session)
    
    await state.clear()
    await message.answer(f"Reklama yuborish boshlandi... ({len(user_ids)} ta foydalanuvchiga)")
    
    success_count = 0
    failure_count = 0
    
    for user_id in user_ids:
        try:
            await bot.send_photo(
                chat_id=user_id,
                photo=data['photo_file_id'],
                caption=data['post_text']
            )
            success_count += 1
            await asyncio.sleep(0.1) 
        except TelegramRetryAfter as e:
            logger.warning(f"Telegram API limiti: {e.retry_after} soniya kutish kerak.")
            await asyncio.sleep(e.retry_after)
            # Qayta urinib ko'rish
            try:
                await bot.send_photo(chat_id=user_id, photo=data['photo_file_id'], caption=data['post_text'])
                success_count += 1
            except Exception:
                failure_count += 1
        except (TelegramForbiddenError, TelegramBadRequest):
            failure_count += 1
        except Exception as e:
            logger.error(f"Reklamani {user_id} ga yuborishda noma'lum xato: {e}")
            failure_count += 1

    await message.answer(
        f"Reklama yuborish yakunlandi.\n\n"
        f"✅ Muvaffaqiyatli: <b>{success_count}</b>\n"
        f"❌ Xatolik (bloklaganlar): <b>{failure_count}</b>"
    )

@user_router.message(CommandStart())
async def cmd_start(m: Message, state: FSMContext, data: dict, command: CommandObject = None):
    s = data["session"]
    bot = m.bot
    await state.clear(); await get_or_create_user(s, m.from_user.id, m.from_user.username, m.from_user.first_name)
    unsub = await check_all_channels_membership(bot, m.from_user.id)
    if command and command.args:
        try:
            _, p_id_s, c_key = command.args.split("_"); p_id = int(p_id_s)
            if unsub: await m.answer("Ovoz berishdan avval kanallarga a'zo bo'ling:", reply_markup=get_channel_subscription_keyboard(unsub)); await state.set_data({'deep_link_vote': (p_id, c_key)}); await state.set_state(VotingProcess.awaiting_subscription_check); return
            await process_deep_link_vote(m, s, bot, p_id, c_key); return
        except (ValueError, IndexError): pass
    if unsub: await m.answer("Assalomu alaykum! Ishtirok etish uchun kanallarga a'zo bo'ling:", reply_markup=get_channel_subscription_keyboard(unsub)); await state.set_state(VotingProcess.awaiting_subscription_check)
    else: await m.answer("Assalomu alaykum! Ovoz berish uchun telefon raqamingizni yuboring:", reply_markup=get_contact_keyboard()); await state.set_state(VotingProcess.awaiting_contact)

async def process_deep_link_vote(m: Message, s: AsyncSession, bot: Bot, p_id: int, c_key: str):
    u_id = m.from_user.id; p = await get_poll_by_id(s, p_id)
    if not p or not p.is_active: return await m.answer("Afsuski, bu so'rovnoma aktiv emas.")
    if await has_user_voted(s, u_id, p_id): return await m.answer("Siz bu so'rovnomada allaqachon ovoz bergansiz.")
    unsub = await check_all_channels_membership(bot, u_id)
    if unsub: return await m.answer("Ovoz berish uchun, iltimos, avval kanallarga a'zo bo'ling:", reply_markup=get_channel_subscription_keyboard(unsub))
    try: await add_vote(s, u_id, p_id, c_key); c_text = p.options.get(c_key, ""); await m.answer(f"✅ Rahmat! Ovozingiz qabul qilindi: <b>\"{c_text}\"</b>.")
    except Exception as e: logger.error(f"Deep link ovoz berishda xato: {e}"); await m.answer("Xatolik yuz berdi.")

@user_router.callback_query(F.data=="check_subscription", VotingProcess.awaiting_subscription_check)
async def cb_check_subscription(c: CallbackQuery, state: FSMContext, bot: Bot, s: AsyncSession):
    await c.answer("Tekshirilmoqda...", cache_time=1)
    unsub = await check_all_channels_membership(bot, c.from_user.id)
    if unsub: await c.message.edit_text("Afsuski, hali ham barcha kanallarga a'zo emassiz.", reply_markup=get_channel_subscription_keyboard(unsub,"🔄 Qayta tekshirish"))
    else:
        await c.message.delete(); data = await state.get_data(); deep_link_vote = data.get('deep_link_vote')
        if deep_link_vote: p_id,c_key=deep_link_vote; await process_deep_link_vote(c.message,s,bot,p_id,c_key); await state.clear(); return
        await c.message.answer("Rahmat! Endi telefon raqamingizni yuboring:",reply_markup=get_contact_keyboard()); await state.set_state(VotingProcess.awaiting_contact)
@user_router.message(F.contact,VotingProcess.awaiting_contact)
async def handle_contact(m: Message, state: FSMContext, s: AsyncSession, crypto: CryptoService, captcha: CaptchaServiceMemory):
    if await captcha.is_user_blocked(m.from_user.id):await m.answer(f"Siz {settings.CAPTCHA_BLOCK_DURATION_MINUTES} daqiqaga bloklangansiz.",reply_markup=remove_keyboard);await state.clear();return
    await save_user_phone(s,m.from_user.id,crypto.encrypt(m.contact.phone_number))
    q=await captcha.create_captcha(m.from_user.id); await m.answer(f"Raqam qabul qilindi. Bot emasligingizni tasdiqlang ({settings.CAPTCHA_TIMEOUT_SECONDS}s):\n<b>{q}</b>",reply_markup=remove_keyboard);await state.set_state(VotingProcess.awaiting_captcha)
@user_router.message(VotingProcess.awaiting_contact)
async def invalid_contact_input(m: Message): await m.reply("Iltimos, 'Telefon raqamni yuborish 📞' tugmasi orqali yuboring.")
@user_router.message(VotingProcess.awaiting_captcha)
async def process_captcha_answer(m: Message, state: FSMContext, s: AsyncSession, captcha: CaptchaServiceMemory):
    u_id = m.from_user.id
    if await captcha.is_user_blocked(u_id): await m.answer("Siz vaqtinchalik bloklangansiz."); await state.clear(); return
    is_corr=await captcha.verify_captcha(u_id,m.text)
    if is_corr:
        await m.answer("✅ To'g'ri!");ap=await get_active_poll(s)
        if not ap:await m.answer("Hozircha aktiv so'rovnomalar yo'q.");await state.clear();return
        if await has_user_voted(s,u_id,ap.id):await m.answer("Siz bu so'rovnomada allaqachon ovoz bergansiz.");await state.clear();return
        await m.answer(f"So'rovnoma:\n<b>{ap.question}</b>\n\nVariantni tanlang:",reply_markup=get_poll_options_keyboard(ap));await state.set_state(VotingProcess.awaiting_vote_choice)
    else:
        if await captcha.is_user_blocked(u_id):await m.answer(f"Noto'g'ri. Urinishlar tugadi. Siz {settings.CAPTCHA_BLOCK_DURATION_MINUTES} daqiqaga bloklandingiz.");await state.clear()
        else:att_left=await captcha.get_attempts_left(u_id);await m.answer(f"Noto'g'ri. Yana {att_left} ta urinish qoldi.")

@user_router.callback_query(F.data.startswith("vote_poll:"),VotingProcess.awaiting_vote_choice)
async def process_vote_choice(c: CallbackQuery, state: FSMContext, s: AsyncSession, bot: Bot):
    try: _, p_id_s, _, c_key = c.data.split(":"); p_id = int(p_id_s)
    except (ValueError, IndexError): await c.answer("Xato!", show_alert=True); return
    u_id = c.from_user.id
    unsub = await check_all_channels_membership(bot, u_id)
    if unsub:
        await c.message.answer("❌ Kechirasiz, ovoz berish uchun avval kanallarga a'zo bo'lishingiz shart.", reply_markup=get_channel_subscription_keyboard(unsub, "✅ A'zo bo'ldim, qayta ovoz berish"))
        await c.answer("Iltimos, avval kanallarga to'liq a'zo bo'ling.", show_alert=True); return
    p=await get_poll_by_id(s,p_id)
    if not p or not p.is_active:await c.message.edit_text("Bu so'rovnoma aktiv emas.");await state.clear();return await c.answer()
    if await has_user_voted(s,u_id,p_id):await c.message.edit_text("Siz allaqon ovoz bergansiz.");await state.clear();return await c.answer("Allaqon ovoz berilgan!",show_alert=True)
    try:
        await add_vote(s,u_id,p_id,c_key);c_t=p.options.get(c_key,"")
        await c.message.edit_text(f"Ovozingiz qabul qilindi: <b>\"{c_t}\"</b>.\nRahmat!");await c.answer("Ovozingiz qabul qilindi!",show_alert=True)
    except IntegrityError:await c.message.edit_text("Xatolik: Siz allaqachon ovoz bergansiz.");await c.answer("Xatolik!",show_alert=True)
    except Exception as e:logger.error(f"Ovoz berishda xato: {e}");await c.message.edit_text("Texnik nosozlik.");await c.answer("Xatolik!",show_alert=True)
    await state.clear()


async def main():
    storage=MemoryStorage();captcha_service=CaptchaServiceMemory();crypto_service=CryptoService(settings.ENCRYPTION_KEY)
    bot=Bot(token=settings.BOT_TOKEN,default=DefaultBotProperties(parse_mode=ParseMode.HTML));dp=Dispatcher(storage=storage)
    dp.update.middleware(DbSessionMiddleware(pool=AsyncSessionFactory))
    dp.workflow_data.update({"crypto_service":crypto_service,"captcha_service":captcha_service,"bot":bot})
    dp.include_router(admin_router);dp.include_router(user_router)
    await create_db_and_tables()
    logger.info("Bot ishga tushirilmoqda (ommaviy xabar yuborish funksiyasi bilan)...")
    try: await bot.delete_webhook(drop_pending_updates=True); await dp.start_polling(bot)
    except Exception as e: logger.critical(f"Botni ishga tushirishda xatolik: {e}", exc_info=True)
    finally: await bot.session.close(); logger.info("Bot to'xtatildi.")

if __name__ == "__main__":
    try: asyncio.run(main())
    except (KeyboardInterrupt, SystemExit): logger.info("Bot foydalanuvchi tomonidan to'xtatildi.")