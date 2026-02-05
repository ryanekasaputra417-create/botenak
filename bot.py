import asyncio, os, uuid, datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.filters import CommandStart
from aiogram.types import (
    InlineKeyboardMarkup,
    InlineKeyboardButton,
    ChatPermissions
)
from aiogram.client.default import DefaultBotProperties
import aiosqlite

# ================= ENV =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_IDS = list(map(int, os.getenv("ADMIN_IDS").split(",")))

bot = Bot(
    BOT_TOKEN,
    default=DefaultBotProperties(parse_mode="HTML")
)
dp = Dispatcher()

DB = "media.db"

# ================= DATABASE =================
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS media (
            code TEXT,
            file_id TEXT,
            type TEXT,
            caption TEXT
        )""")
        await db.execute("""
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY
        )""")
        await db.commit()

async def set_setting(k, v):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings VALUES (?,?)",
            (k, v)
        )
        await db.commit()

async def get_setting(k, default=None):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT value FROM settings WHERE key=?",
            (k,)
        )
        r = await cur.fetchone()
        return r[0] if r else default

def is_admin(uid: int) -> bool:
    return uid in ADMIN_IDS

# ================= FORCE SUB =================
async def check_fsub(user_id: int):
    links = await get_setting("fsub_links", "")
    if not links:
        return True

    for chat in links.split(","):
        chat = chat.strip()
        if not chat:
            continue
        try:
            member = await bot.get_chat_member(chat, user_id)
            if member.status in ("left", "kicked"):
                return False
        except:
            return False
    return True

# ================= START =================
@dp.message(CommandStart())
async def start(m: types.Message):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR IGNORE INTO users VALUES (?)",
            (m.from_user.id,)
        )
        await db.commit()

    if not await check_fsub(m.from_user.id):
        links = await get_setting("fsub_links", "")
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="📢 Join Channel", url=links.split(",")[0])],
            [InlineKeyboardButton(text="✅ Saya Sudah Join", callback_data="recheck_fsub")]
        ])
        await m.answer("⚠️ Join channel dulu untuk lanjut", reply_markup=kb)
        return

    text = await get_setting("start_text", "👋 Selamat datang")
    buttons = []

    if not is_admin(m.from_user.id):
        buttons.append([
            InlineKeyboardButton(text="💬 Ask Admin", callback_data="ask")
        ])

    if is_admin(m.from_user.id):
        buttons.append([
            InlineKeyboardButton(text="⚙️ PANEL ADMIN", callback_data="admin_panel")
        ])

    kb = InlineKeyboardMarkup(inline_keyboard=buttons) if buttons else None
    await m.answer(text, reply_markup=kb)

@dp.callback_query(F.data == "recheck_fsub")
async def recheck(cb: types.CallbackQuery):
    if await check_fsub(cb.from_user.id):
        await cb.message.edit_text("✅ Akses dibuka, /start ulang")
    else:
        await cb.answer("❌ Belum join semua", show_alert=True)

# ================= ADMIN PANEL =================
@dp.callback_query(F.data == "admin_panel")
async def admin_panel(cb: types.CallbackQuery):
    if not is_admin(cb.from_user.id):
        return

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 Set Force Sub", callback_data="set_fsub")],
        [InlineKeyboardButton(text="📝 Set Start Text", callback_data="set_start")],
        [InlineKeyboardButton(text="📊 Stats", callback_data="stats")],
        [InlineKeyboardButton(text="💾 Backup DB", callback_data="backup")]
    ])
    await cb.message.edit_text("⚙️ ADMIN DASHBOARD", reply_markup=kb)

# ================= SET FORCE SUB =================
@dp.callback_query(F.data == "set_fsub")
async def set_fsub(cb: types.CallbackQuery):
    await cb.message.edit_text(
        "Kirim username channel/grup\ncontoh:\n@channel1,@group2"
    )

    @dp.message()
    async def save_fsub(m: types.Message):
        if not is_admin(m.from_user.id):
            return
        await set_setting("fsub_links", m.text)
        await m.answer("✅ Force sub disimpan")
        dp.message.handlers.pop()

# ================= SET START TEXT =================
@dp.callback_query(F.data == "set_start")
async def set_start(cb: types.CallbackQuery):
    await cb.message.edit_text("Kirim start text baru")

    @dp.message()
    async def save_start(m: types.Message):
        if not is_admin(m.from_user.id):
            return
        await set_setting("start_text", m.text)
        await m.answer("✅ Start text diupdate")
        dp.message.handlers.pop()

# ================= SAVE MEDIA =================
@dp.message(F.content_type.in_({"photo", "video", "document", "animation"}))
async def save_media(m: types.Message):
    if not is_admin(m.from_user.id):
        return

    file_id = (
        m.photo[-1].file_id if m.photo else
        m.video.file_id if m.video else
        m.document.file_id
    )

    code = uuid.uuid4().hex[:20]

    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO media VALUES (?,?,?,?)",
            (code, file_id, m.content_type, m.caption or "")
        )
        await db.commit()

    await m.answer(f"✅ MEDIA DISIMPAN\nCODE:\n<code>{code}</code>")

# ================= AUTO POST =================
@dp.message(F.text.startswith("/post "))
async def post_media(m: types.Message):
    if not is_admin(m.from_user.id):
        return

    _, code, channel = m.text.split(maxsplit=2)

    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT file_id,type,caption FROM media WHERE code=?",
            (code,)
        )
        r = await cur.fetchone()

    if not r:
        await m.answer("❌ Code tidak ditemukan")
        return

    file_id, ftype, caption = r

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="▶️ NONTON", url=f"https://t.me/{bot.username}?start={code}")]
    ])

    send = getattr(bot, f"send_{ftype}")
    await send(channel, file_id, caption=caption, reply_markup=kb)

    await m.answer("✅ Posted")

# ================= GET MEDIA =================
@dp.message(F.text.regexp(r"^[a-f0-9]{20}$"))
async def get_media(m: types.Message):
    if not await check_fsub(m.from_user.id):
        await m.answer("⚠️ Join channel dulu")
        return

    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT file_id,type,caption FROM media WHERE code=?",
            (m.text,)
        )
        r = await cur.fetchone()

    if not r:
        return

    file_id, ftype, caption = r
    send = getattr(bot, f"send_{ftype}")
    await send(
        m.chat.id,
        file_id,
        caption=caption,
        protect_content=True
    )

# ================= STATS =================
@dp.callback_query(F.data == "stats")
async def stats(cb: types.CallbackQuery):
    async with aiosqlite.connect(DB) as db:
        u = await db.execute("SELECT COUNT(*) FROM users")
        m = await db.execute("SELECT COUNT(*) FROM media")
        users = (await u.fetchone())[0]
        media = (await m.fetchone())[0]

    await cb.message.edit_text(
        f"📊 USERS: {users}\n📁 MEDIA: {media}"
    )

# ================= BACKUP =================
@dp.callback_query(F.data == "backup")
async def backup(cb: types.CallbackQuery):
    await cb.message.answer_document(types.FSInputFile(DB))

# ================= RUN =================
async def main():
    await init_db()
    await dp.start_polling(bot)

asyncio.run(main())
