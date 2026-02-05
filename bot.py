import os, asyncio, logging, sqlite3, random, string
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery, InlineKeyboardMarkup,
    InlineKeyboardButton, ChatPermissions, FSInputFile
)
from aiogram.filters import CommandStart, Command
from aiogram.enums import ChatType
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import StatesGroup, State
from aiogram.fsm.storage.memory import MemoryStorage

# ================== CONFIG ==================
BOT_TOKEN = os.getenv("BOT_TOKEN", "")
ADMIN_IDS = set(map(int, os.getenv("ADMIN_IDS", "123456789").split(",")))

# ================== INIT ==================
logging.basicConfig(level=logging.INFO)
bot = Bot(BOT_TOKEN, parse_mode="HTML")
dp = Dispatcher(storage=MemoryStorage())

# ================== DATABASE ==================
db = sqlite3.connect("bot.db")
c = db.cursor()

c.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
c.execute("CREATE TABLE IF NOT EXISTS users (id INTEGER PRIMARY KEY, first_seen TEXT)")
c.execute("""
CREATE TABLE IF NOT EXISTS media (
 code TEXT PRIMARY KEY,
 file_id TEXT,
 type TEXT,
 caption TEXT,
 created TEXT
)
""")
db.commit()

# ================== HELPERS ==================
def get_setting(key, default=None):
    r = c.execute("SELECT value FROM settings WHERE key=?", (key,)).fetchone()
    return r[0] if r else default

def set_setting(key, val):
    c.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (key, str(val)))
    db.commit()

def gen_code():
    import string, random
    return ''.join(random.choices(string.ascii_letters+string.digits, k=8))

# ================== ADMIN PANEL ==================
@dp.message(Command("settings"))
async def settings_panel(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Set Channel Post", callback_data="set:post")],
        [InlineKeyboardButton(text="📦 Set Channel DB", callback_data="set:db")],
        [InlineKeyboardButton(text="🔒 Set Force Sub", callback_data="set:fsub")],
        [InlineKeyboardButton(text="✏️ Set Teks Start", callback_data="set:start")],
        [InlineKeyboardButton(text="📝 Set Exempt Username", callback_data="set:exempt")],
    ])
    await msg.answer("⚙️ PANEL ADMIN", reply_markup=kb)

class SetState(StatesGroup):
    waiting = State()

@dp.callback_query(F.data.startswith("set:"))
async def set_menu(cb: CallbackQuery, state: FSMContext):
    await state.set_state(SetState.waiting)
    await state.update_data(key=cb.data.split(":")[1])
    await cb.message.edit_text("Kirim ID / teks sekarang")

@dp.message(SetState.waiting)
async def save_setting(msg: Message, state: FSMContext):
    data = await state.get_data()
    set_setting(data['key'], msg.text)
    await msg.answer("✅ Disimpan")
    await state.clear()

# ================== START & FORCE JOIN ==================
async def check_force_join(user_id):
    # ambil daftar channel/grup wajib join dari DB
    fsub = get_setting("fsub")
    if not fsub: return True
    ids = fsub.split(",")
    for cid in ids:
        try:
            member = await bot.get_chat_member(int(cid), user_id)
            if member.status not in ("member","administrator","creator"):
                return False
        except: return False
    return True

@dp.message(CommandStart())
async def start(msg: Message):
    c.execute("INSERT OR IGNORE INTO users VALUES (?,?)",
              (msg.from_user.id, datetime.now().isoformat()))
    db.commit()
    if not await check_force_join(msg.from_user.id):
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🔄 COBA LAGI", callback_data="retry")]
        ])
        await msg.answer("❌ Kamu harus join semua channel/grup dulu", reply_markup=kb)
        return
    code = msg.text.split(" ",1)[1] if len(msg.text.split())>1 else None
    if code:
        r = c.execute("SELECT file_id,type,caption FROM media WHERE code=?",(code,)).fetchone()
        if r:
            if r[1]=="photo":
                await msg.answer_photo(r[0], caption=r[2])
            elif r[1]=="video":
                await msg.answer_video(r[0], caption=r[2])
            elif r[1]=="document":
                await msg.answer_document(r[0], caption=r[2])
            else:
                await msg.answer(r[2] or "")
            return
    text = get_setting("start","Selamat datang 👋")
    await msg.answer(text)

@dp.callback_query(F.data=="retry")
async def retry(cb: CallbackQuery):
    if await check_force_join(cb.from_user.id):
        await cb.message.edit_text("✅ Kamu sudah join, silakan akses konten lagi")
    else:
        await cb.answer("Belum join semua!")

# ================== FILTER KATA ==================
BAD_WORDS = ["biyo","biyoh","promosi","bio"]

@dp.message(F.text, F.chat.type.in_({ChatType.GROUP, ChatType.SUPERGROUP}))
async def filter_word(msg: Message):
    exempt = get_setting("exempt","").split(",")
    if msg.from_user.id in ADMIN_IDS or (msg.from_user.username and msg.from_user.username in exempt):
        return
    for w in BAD_WORDS:
        if w in msg.text.lower():
            try:
                await msg.delete()
                await bot.restrict_chat_member(
                    msg.chat.id,
                    msg.from_user.id,
                    permissions=ChatPermissions(can_send_messages=False),
                    until_date=datetime.now()+timedelta(hours=24)
                )
            except: pass

# ================== MEDIA UPLOAD & AUTO POST ==================
@dp.message(F.content_type.in_({"photo","video","document","animation"}))
async def save_media(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    code = gen_code()
    if msg.photo: file_id, mtype = msg.photo[-1].file_id, "photo"
    elif msg.video: file_id, mtype = msg.video.file_id, "video"
    elif msg.document: file_id, mtype = msg.document.file_id, "document"
    elif msg.animation: file_id, mtype = msg.animation.file_id, "animation"
    else: return
    c.execute("INSERT INTO media VALUES (?,?,?,?,?)",(code,file_id,mtype,msg.caption or "",datetime.now().isoformat()))
    db.commit()
    # backup ke channel DB
    dbch = get_setting("db")
    if dbch:
        await bot.copy_message(int(dbch), msg.chat.id, msg.message_id)
    # auto post ke channel post
    postch = get_setting("post")
    if postch:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎬 NONTON", url=f"https://t.me/{(await bot.get_me()).username}?start={code}")]
        ])
        await bot.send_message(int(postch), msg.caption or "Konten baru", reply_markup=kb)

# ================== STATS & SENDDB ==================
@dp.message(Command("stats"))
async def stats(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    u = c.execute("SELECT COUNT(*) FROM users").fetchone()[0]
    m = c.execute("SELECT COUNT(*) FROM media").fetchone()[0]
    await msg.answer(f"👤 User: {u}\n📦 Media: {m}")

@dp.message(Command("senddb"))
async def senddb(msg: Message):
    if msg.from_user.id not in ADMIN_IDS: return
    await msg.answer_document(FSInputFile("bot.db"))

# ================== RUN ==================
async def main():
    await dp.start_polling(bot)

if __name__ == '__main__':
    asyncio.run(main())
