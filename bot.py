import asyncio, os, uuid, datetime, re
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart, Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.client.default import DefaultBotProperties
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage
import aiosqlite

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))

bot = Bot(BOT_TOKEN, default=DefaultBotProperties(parse_mode="HTML"))
dp = Dispatcher(storage=MemoryStorage())
DB = "media.db"

# ================= FSM =================
class AdminState(StatesGroup):
    badword = State()
    exempt = State()
    fsub = State()
    post_channel = State()
    ask = State()
    donasi = State()
    post_title = State()
    post_cover = State()

# ================= DATABASE =================
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS media (code TEXT, file_id TEXT, type TEXT, caption TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await db.commit()

async def set_setting(k,v):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)",(k,v))
        await db.commit()

async def get_setting(k, default=None):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT value FROM settings WHERE key=?",(k,))
        r = await cur.fetchone()
        return r[0] if r else default

def is_admin(uid): 
    return uid in ADMIN_IDS

# ================= UTIL =================
async def check_fsub(uid):
    raw = await get_setting("fsub_ids","")
    if not raw:
        return True
    for cid in raw.split(","):
        try:
            m = await bot.get_chat_member(int(cid), uid)
            if m.status not in ["member","administrator","creator"]:
                return False
        except:
            return False
    return True

# ================= START =================
@dp.message(CommandStart())
async def start(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO users VALUES (?)",(m.from_user.id,))
        await db.commit()

    if not await check_fsub(m.from_user.id):
        links = (await get_setting("fsub_links","")).split(",")
        kb = [[InlineKeyboardButton("➕ JOIN", url=l)] for l in links if l]
        kb.append([InlineKeyboardButton("🔄 COBA LAGI", callback_data="retry_fsub")])
        await m.answer("🚫 Wajib join dulu", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return

    kb = [
        [InlineKeyboardButton("💬 ASK ADMIN", callback_data="ask")],
        [InlineKeyboardButton("❤️ DONASI", callback_data="donasi")]
    ]
    if is_admin(m.from_user.id):
        kb.append([InlineKeyboardButton("⚙️ PANEL ADMIN", callback_data="admin_panel")])

    await m.answer(await get_setting("start_text","👋 Selamat datang"),
                   reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# ================= RETRY FSUB =================
@dp.callback_query(F.data=="retry_fsub")
async def retry(cb):
    if await check_fsub(cb.from_user.id):
        await cb.message.edit_text("✅ Akses dibuka, kirim /start")
    else:
        await cb.answer("❌ Belum join semua", show_alert=True)

# ================= ADMIN PANEL =================
@dp.callback_query(F.data=="admin_panel")
async def panel(cb):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton("🔐 Security", callback_data="sec")],
        [InlineKeyboardButton("📢 Force Join", callback_data="fsub")],
        [InlineKeyboardButton("📤 Set Post Channel", callback_data="set_post")],
        [InlineKeyboardButton("📊 Stats", callback_data="stats")],
        [InlineKeyboardButton("💾 Backup DB", callback_data="backup")]
    ])
    await cb.message.edit_text("⚙️ ADMIN DASHBOARD", reply_markup=kb)

# ================= SECURITY =================
@dp.callback_query(F.data=="sec")
async def sec(cb):
    st = await get_setting("filter_on","0")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(f"Filter: {'ON' if st=='1' else 'OFF'}", callback_data="toggle_filter")],
        [InlineKeyboardButton("✏️ Edit Badword", callback_data="edit_badword")],
        [InlineKeyboardButton("🛡 Exempt Username", callback_data="edit_exempt")],
        [InlineKeyboardButton("⬅️ Back", callback_data="admin_panel")]
    ])
    await cb.message.edit_text("🔐 SECURITY", reply_markup=kb)

@dp.callback_query(F.data=="toggle_filter")
async def toggle(cb):
    cur = await get_setting("filter_on","0")
    await set_setting("filter_on","0" if cur=="1" else "1")
    await sec(cb)

@dp.callback_query(F.data=="edit_badword")
async def ask_bw(cb, state:FSMContext):
    await state.set_state(AdminState.badword)
    await cb.message.edit_text("Kirim kata terlarang (koma)")

@dp.message(AdminState.badword)
async def save_bw(m, state:FSMContext):
    await set_setting("bad_words", m.text.lower())
    await m.answer("✅ Badword disimpan")
    await state.clear()

@dp.callback_query(F.data=="edit_exempt")
async def ask_ex(cb, state:FSMContext):
    await state.set_state(AdminState.exempt)
    await cb.message.edit_text("Username exempt (tanpa @)")

@dp.message(AdminState.exempt)
async def save_ex(m, state:FSMContext):
    await set_setting("exempt_users", m.text.lower())
    await m.answer("✅ Exempt disimpan")
    await state.clear()

# ================= FILTER CHAT =================
@dp.message(F.chat.type.in_(["group","supergroup"]))
async def filter_chat(m:types.Message):
    if is_admin(m.from_user.id): return
    if await get_setting("filter_on","0")!="1": return
    exempt = (await get_setting("exempt_users","")).split(",")
    if m.from_user.username and m.from_user.username.lower() in exempt: return
    bad = (await get_setting("bad_words","")).split(",")
    if any(w and w in (m.text or "").lower() for w in bad):
        await m.delete()
        until = datetime.datet
