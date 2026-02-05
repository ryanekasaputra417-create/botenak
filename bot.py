import asyncio
import os
import uuid
import aiosqlite

from aiogram import Bot, Dispatcher, F
from aiogram.types import (
    Message,
    CallbackQuery,
    InlineKeyboardMarkup,
    InlineKeyboardButton
)
from aiogram.filters import CommandStart
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.context import FSMContext
from aiogram.fsm.storage.memory import MemoryStorage

# ================= BASIC CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

DB = "bot.db"

# ================= STATE =================
class PostState(StatesGroup):
    title = State()
    media = State()

class AddFSub(StatesGroup):
    waiting_link = State()

# ================= DATABASE =================
async def init_db():
    async with aiosqlite.connect(DB) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS media (
            code TEXT PRIMARY KEY,
            file_id TEXT,
            type TEXT,
            caption TEXT
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS fsub (
            link TEXT PRIMARY KEY
        )
        """)
        await db.execute("""
        CREATE TABLE IF NOT EXISTS settings (
            key TEXT PRIMARY KEY,
            value TEXT
        )
        """)
        await db.commit()

async def get_setting(key, default="0"):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT value FROM settings WHERE key=?",
            (key,)
        )
        row = await cur.fetchone()
        return row[0] if row else default

async def set_setting(key, value):
    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT OR REPLACE INTO settings VALUES (?,?)",
            (key, value)
        )
        await db.commit()

# ================= FORCE SUB =================
async def get_fsub_links():
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute("SELECT link FROM fsub")
        rows = await cur.fetchall()
        return [r[0] for r in rows]

async def check_fsub(user_id: int):
    links = await get_fsub_links()
    for link in links:
        try:
            username = link.replace("https://t.me/", "").replace("@", "")
            member = await bot.get_chat_member(f"@{username}", user_id)
            if member.status not in ("member", "administrator", "creator"):
                return False
        except:
            return False
    return True

# ================= MEDIA SENDER =================
async def send_media_by_code(chat_id: int, code: str):
    async with aiosqlite.connect(DB) as db:
        cur = await db.execute(
            "SELECT file_id, type, caption FROM media WHERE code=?",
            (code,)
        )
        row = await cur.fetchone()

    if not row:
        await bot.send_message(chat_id, "❌ Konten tidak ditemukan.")
        return

    antifwd = await get_setting("antifwd", "0") == "1"

    fid, mtype, cap = row
    if mtype == "photo":
        await bot.send_photo(
            chat_id=chat_id,
            photo=fid,
            caption=cap,
            protect_content=antifwd
        )
    else:
        await bot.send_video(
            chat_id=chat_id,
            video=fid,
            caption=cap,
            protect_content=antifwd
        )

# ================= START =================
@dp.message(CommandStart())
async def start(m: Message):
    args = m.text.split(maxsplit=1)

    if len(args) == 2:
        code = args[1]
        if not await check_fsub(m.from_user.id):
            links = await get_fsub_links()
            kb = []

            for i, link in enumerate(links, start=1):
                kb.append([
                    InlineKeyboardButton(
                        text=f"🔔 Join {i}",
                        url=link
                    )
                ])

            kb.append([
                InlineKeyboardButton(
                    text="🔄 Coba Lagi",
                    callback_data=f"retry:{code}"
                )
            ])

            return await m.answer(
                "🚫 Join dulu semua lalu klik **Coba Lagi**",
                reply_markup=InlineKeyboardMarkup(inline_keyboard=kb)
            )

        return await send_media_by_code(m.chat.id, code)

    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Donasi", callback_data="donasi")],
        [InlineKeyboardButton(text="💬 Ask Admin", callback_data="ask")]
    ])

    if m.from_user.id == ADMIN_ID:
        kb.inline_keyboard.append([
            InlineKeyboardButton(
                text="⚙️ Panel Admin",
                callback_data="admin"
            )
        ])

    await m.answer("👋 Selamat datang", reply_markup=kb)

# ================= RETRY =================
@dp.callback_query(F.data.startswith("retry:"))
async def retry(cb: CallbackQuery):
    code = cb.data.split(":", 1)[1]
    if not await check_fsub(cb.from_user.id):
        return await cb.answer("❌ Belum join semua", show_alert=True)

    await cb.message.delete()
    await send_media_by_code(cb.from_user.id, code)

# ================= ADMIN PANEL =================
@dp.callback_query(F.data == "admin")
async def admin_panel(cb: CallbackQuery):
    antifwd = await get_setting("antifwd", "0")
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(
                text=f"🛡 Anti Forward: {'ON' if antifwd=='1' else 'OFF'}",
                callback_data="toggle_antifwd"
            )
        ],
        [
            InlineKeyboardButton(text="➕ Add FSub Link", callback_data="add_fsub")
        ],
        [
            InlineKeyboardButton(text="📤 Post Media", callback_data="post_media")
        ],
        [
            InlineKeyboardButton(text="⬅️ Kembali", callback_data="back")
        ]
    ])
    await cb.message.edit_text("⚙️ PANEL ADMIN", reply_markup=kb)

@dp.callback_query(F.data == "toggle_antifwd")
async def toggle_antifwd(cb: CallbackQuery):
    cur = await get_setting("antifwd", "0")
    await set_setting("antifwd", "0" if cur == "1" else "1")
    await admin_panel(cb)

# ================= ADD FSUB =================
@dp.callback_query(F.data == "add_fsub")
async def add_fsub(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("🔗 Kirim link channel / grup (https://t.me/...)")
    await state.set_state(AddFSub.waiting_link)

@dp.message(AddFSub.waiting_link)
async def save_fsub(m: Message, state: FSMContext):
    link = m.text.strip()
    async with aiosqlite.connect(DB) as db:
        await db.execute("INSERT OR IGNORE INTO fsub VALUES (?)", (link,))
        await db.commit()

    await state.clear()
    await m.answer("✅ Link ditambahkan")
    await admin_panel(CallbackQuery(id="x", from_user=m.from_user, message=m))

# ================= POST MEDIA =================
@dp.callback_query(F.data == "post_media")
async def post_media(cb: CallbackQuery, state: FSMContext):
    await cb.message.edit_text("📝 Kirim judul konten")
    await state.set_state(PostState.title)

@dp.message(PostState.title)
async def post_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text)
    await state.set_state(PostState.media)
    await m.answer("📸 Kirim foto / video")

@dp.message(PostState.media, F.photo | F.video)
async def post_save(m: Message, state: FSMContext):
    data = await state.get_data()
    code = uuid.uuid4().hex[:10]

    fid = m.photo[-1].file_id if m.photo else m.video.file_id
    mtype = "photo" if m.photo else "video"

    async with aiosqlite.connect(DB) as db:
        await db.execute(
            "INSERT INTO media VALUES (?,?,?,?)",
            (code, fid, mtype, data["title"])
        )
        await db.commit()

    link = f"https://t.me/{(await bot.me()).username}?start={code}"

    await m.answer(f"✅ Konten siap\n\n{link}")
    await state.clear()

# ================= MEMBER UI =================
@dp.callback_query(F.data == "donasi")
async def donasi(cb: CallbackQuery):
    await cb.message.answer("🎁 Kirim media donasi di sini.")

@dp.callback_query(F.data == "ask")
async def ask(cb: CallbackQuery):
    await cb.message.answer("💬 Kirim pesan kamu, admin akan baca.")

@dp.callback_query(F.data == "back")
async def back(cb: CallbackQuery):
    await cb.message.delete()
    await start(cb.message)

# ================= RUN =================
async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
