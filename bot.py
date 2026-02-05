import asyncio, os, uuid, aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message, CallbackQuery,
    InlineKeyboardMarkup, InlineKeyboardButton
)
from aiogram.filters import CommandStart
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
DB = "bot.db"

# ================= STATES =================
class AutoPost(StatesGroup):
    waiting_title = State()
    waiting_cover = State()

class AddFSubCheck(StatesGroup):
    waiting_link = State()

class AddFSubList(StatesGroup):
    waiting_link = State()

class SetPostChannel(StatesGroup):
    waiting_channel = State()

# ================= DB =================
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""CREATE TABLE IF NOT EXISTS media
            (code TEXT PRIMARY KEY, file_id TEXT, type TEXT, caption TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS settings
            (key TEXT PRIMARY KEY, value TEXT)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS fsub_check (link TEXT PRIMARY KEY)""")
        await db.execute("""CREATE TABLE IF NOT EXISTS fsub_list (link TEXT PRIMARY KEY)""")
        await db.commit()

async def get_setting(k, d=None):
    async with aiosqlite.connect(DB) as db:
        r = await (await db.execute(
            "SELECT value FROM settings WHERE key=?", (k,))
        ).fetchone()
        return r[0] if r else d

async def set_setting(k, v):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR REPLACE INTO settings VALUES (?,?)", (k, v))
        await db.commit()

# ================= FORCE SUB =================
async def check_fsub(uid):
    async with aiosqlite.connect(DB) as db:
        rows = await (await db.execute("SELECT link FROM fsub_check")).fetchall()

    for (link,) in rows:
        try:
            u = link.replace("https://t.me/", "").replace("@", "")
            m = await bot.get_chat_member(f"@{u}", uid)
            if m.status not in ("member", "administrator", "creator"):
                return False
        except:
            return False
    return True

async def get_fsub_buttons():
    async with aiosqlite.connect(DB) as db:
        a = await (await db.execute("SELECT link FROM fsub_check")).fetchall()
        b = await (await db.execute("SELECT link FROM fsub_list")).fetchall()
    return [x[0] for x in a + b]

# ================= START =================
@dp.message(CommandStart())
async def start(m: Message):
    args = m.text.split(maxsplit=1)

    if len(args) == 2:
        code = args[1]
        if not await check_fsub(m.from_user.id):
            links = await get_fsub_buttons()
            kb = [[InlineKeyboardButton(text="🔔 JOIN", url=l)] for l in links]
            kb.append([InlineKeyboardButton(
                text="🔄 Coba Lagi", callback_data=f"retry:{code}")])
            return await m.answer("🚫 Join dulu semua:", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))
        return await send_media(m.chat.id, code)

    kb = [
        [InlineKeyboardButton(text="🎁 Donasi", callback_data="donasi")],
        [InlineKeyboardButton(text="💬 Ask Admin", callback_data="ask")]
    ]
    if m.from_user.id == ADMIN_ID:
        kb.append([InlineKeyboardButton(text="⚙️ Panel Admin", callback_data="admin")])

    await m.answer("👋 Selamat datang", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

# ================= RETRY =================
@dp.callback_query(F.data.startswith("retry:"))
async def retry(cb: CallbackQuery):
    code = cb.data.split(":",1)[1]
    if not await check_fsub(cb.from_user.id):
        return await cb.answer("❌ Masih belum join", show_alert=True)
    await cb.message.delete()
    await send_media(cb.from_user.id, code)

# ================= SEND MEDIA =================
async def send_media(chat_id, code):
    async with aiosqlite.connect(DB) as db:
        r = await (await db.execute(
            "SELECT file_id,type,caption FROM media WHERE code=?", (code,))
        ).fetchone()

    if not r:
        return await bot.send_message(chat_id, "❌ Konten tidak ditemukan")

    protect = (await get_setting("antifwd","0")) == "1"
    fid, t, cap = r

    if t == "photo":
        await bot.send_photo(chat_id, fid, caption=cap, protect_content=protect)
    else:
        await bot.send_video(chat_id, fid, caption=cap, protect_content=protect)

# ================= DONASI / ASK =================
@dp.callback_query(F.data == "donasi")
async def donasi(cb: CallbackQuery):
    await cb.message.answer("🎁 Kirim pesan / media donasi")

@dp.callback_query(F.data == "ask")
async def ask(cb: CallbackQuery):
    await cb.message.answer("💬 Kirim pesan untuk admin")

@dp.message(F.chat.type=="private")
async def user_msg(m: Message):
    if m.from_user.id == ADMIN_ID:
        return

    await bot.forward_message(ADMIN_ID, m.chat.id, m.message_id)
    await m.answer("✅ Pesan kamu sudah terkirim ke admin")

# ================= ADMIN PANEL =================
@dp.callback_query(F.data == "admin")
async def panel(cb: CallbackQuery):
    af = await get_setting("antifwd","0")
    kb = [
        [InlineKeyboardButton(
            text=f"🛡 Anti Forward: {'ON' if af=='1' else 'OFF'}",
            callback_data="toggle_af")],
        [InlineKeyboardButton(text="📢 Set Channel Post", callback_data="set_ch")],
        [InlineKeyboardButton(text="➕ Add FSub Check", callback_data="add_fsub_check")],
        [InlineKeyboardButton(text="➕ Add FSub List", callback_data="add_fsub_list")],
    ]
    await cb.message.edit_text("⚙️ PANEL ADMIN", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

@dp.callback_query(F.data=="toggle_af")
async def toggle_af(cb: CallbackQuery):
    cur = await get_setting("antifwd","0")
    await set_setting("antifwd","0" if cur=="1" else "1")
    await panel(cb)

# ================= SET CHANNEL =================
@dp.callback_query(F.data=="set_ch")
async def set_ch(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📢 Kirim @channel")
    await state.set_state(SetPostChannel.waiting_channel)

@dp.message(SetPostChannel.waiting_channel)
async def save_ch(m: Message, state: FSMContext):
    await set_setting("post_channel", m.text.strip())
    await m.answer("✅ Channel disimpan")
    await state.clear()

# ================= FSUB =================
@dp.callback_query(F.data=="add_fsub_check")
async def fsub_c(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("➕ Kirim link channel (dicek join)")
    await state.set_state(AddFSubCheck.waiting_link)

@dp.message(AddFSubCheck.waiting_link)
async def save_fc(m: Message, state: FSMContext):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO fsub_check VALUES (?)",(m.text,))
        await db.commit()
    await m.answer("✅ FSub Check ditambahkan")
    await state.clear()

@dp.callback_query(F.data=="add_fsub_list")
async def fsub_l(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("➕ Kirim link (tombol join saja)")
    await state.set_state(AddFSubList.waiting_link)

@dp.message(AddFSubList.waiting_link)
async def save_fl(m: Message, state: FSMContext):
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO fsub_list VALUES (?)",(m.text,))
        await db.commit()
    await m.answer("✅ FSub List ditambahkan")
    await state.clear()

# ================= AUTO POST =================
@dp.message(F.from_user.id==ADMIN_ID, F.photo | F.video)
async def admin_media(m: Message, state: FSMContext):
    await state.update_data(fid=m.photo[-1].file_id if m.photo else m.video.file_id,
                            type="photo" if m.photo else "video")
    await state.set_state(AutoPost.waiting_title)
    await m.answer("📝 Masukkan judul")

@dp.message(AutoPost.waiting_title)
async def title(m: Message, state: FSMContext):
    await state.update_data(title=m.text)
    await state.set_state(AutoPost.waiting_cover)
    await m.answer("🖼 Kirim cover (photo)")

@dp.message(AutoPost.waiting_cover, F.photo)
async def post(m: Message, state: FSMContext):
    d = await state.get_data()
    code = uuid.uuid4().hex[:8]

    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO media VALUES (?,?,?,?)",
            (code, d["fid"], d["type"], d["title"])
        )
        await db.commit()

    ch = await get_setting("post_channel")
    botname = (await bot.me()).username
    link = f"https://t.me/{botname}?start={code}"

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎬 NONTON", url=link)]
    ])

    await bot.send_photo(ch, m.photo[-1].file_id,
        caption=d["title"], reply_markup=kb)

    await m.answer("✅ Auto post berhasil")
    await state.clear()

# ================= RUN =================
async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

asyncio.run(main())
