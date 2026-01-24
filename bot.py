import asyncio
import uuid
import os
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton, FSInputFile
from aiogram.filters import CommandStart, Command

# ================= KONFIG AMAN (DARI RAILWAY) =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
CH1_USERNAME = os.getenv("CH1_USERNAME")
CH2_USERNAME = os.getenv("CH2_USERNAME")
GROUP_USERNAME = os.getenv("GROUP_USERNAME")
ADMIN_ID = int(os.getenv("ADMIN_ID")) if os.getenv("ADMIN_ID") else 0
BOT_USERNAME = os.getenv("BOT_USERNAME")

# DAFTAR KATA SING DIPISUHI (FILTER)
KATA_KOTOR = ["bio", "promosi", "jual chip", "slot gacor", "b1o", "vcs"]

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "media.db")

# ================= DATABASE INIT =================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS media (code TEXT PRIMARY KEY, file_id TEXT, type TEXT, caption TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        await db.commit()

# ================= HELPER DYNAMIC KEYBOARD =================
async def check_membership(user_id: int):
    results = []
    for chat in [CH1_USERNAME, CH2_USERNAME, GROUP_USERNAME]:
        try:
            m = await bot.get_chat_member(chat, user_id)
            results.append(m.status in ("member", "administrator", "creator"))
        except Exception:
            results.append(False)
    return results # [is_ch1, is_ch2, is_gr]

def join_keyboard(code: str, status: list):
    buttons = []
    names = ["📢 JOIN CHANNEL 1", "📢 JOIN CHANNEL 2", "👥 JOIN GRUP"]
    links = [CH1_USERNAME, CH2_USERNAME, GROUP_USERNAME]
    
    for i in range(3):
        if not status[i]:
            buttons.append([InlineKeyboardButton(text=names[i], url=f"https://t.me/{links[i][1:]}")])
    
    buttons.append([InlineKeyboardButton(text="🔄 UPDATE / COBA LAGI", callback_data=f"retry:{code}")])
    return InlineKeyboardMarkup(inline_keyboard=buttons)

# ================= GRUP HANDLERS (WELCOME, GOODBYE, FILTER DENGAN TAG) =================

@dp.message(F.new_chat_members)
async def welcome_handler(message: Message):
    for user in message.new_chat_members:
        mention = f"[{user.full_name}](tg://user?id={user.id})"
        await message.answer(f"Selamat datang mwah {mention}! Ramein grup ini!", parse_mode="Markdown")

@dp.message(F.left_chat_member)
async def goodbye_handler(message: Message):
    user = message.left_chat_member
    mention = f"[{user.full_name}](tg://user?id={user.id})"
    await message.answer(f"kontol ni si {mention} malah out dari grup asu!", parse_mode="Markdown")

@dp.message(F.chat.type.in_({"group", "supergroup"}))
async def filter_kata_handler(message: Message):
    if not message.text: return
    text_low = message.text.lower()
    if any(kata in text_low for kata in KATA_KOTOR):
        try:
            mention = f"[{message.from_user.first_name}](tg://user?id={message.from_user.id})"
            await message.delete()
            await message.answer(f"he su {mention} kontol gaboleh ngetik itu disini asu!", parse_mode="Markdown")
        except Exception:
            pass

# ================= ADMIN & USER HANDLERS (PRIVATE ONLY) =================

@dp.message(CommandStart(), F.chat.type == "private")
async def start_handler(message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (message.from_user.id,))
        await db.commit()
    
    args = message.text.split(" ", 1)
    if len(args) == 1:
        await message.answer("👋 Halo! Join dulu biar bisa akses konten!")
        return
    await send_media(message.chat.id, message.from_user.id, args[1])

@dp.message(Command("stats"), F.from_user.id == ADMIN_ID)
async def stats_handler(message: Message):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT COUNT(*) FROM users") as c1: u = await c1.fetchone()
        async with db.execute("SELECT COUNT(*) FROM media") as c2: m = await c2.fetchone()
    await message.answer(f"📊 **STATS**\n\n👥 Users: {u[0]}\n📦 Media: {m[0]}")

@dp.message(Command("all"), F.from_user.id == ADMIN_ID)
async def broadcast_handler(message: Message):
    target = message.reply_to_message if message.reply_to_message else message
    cap = (target.caption or target.text or "").replace("/all", "").strip()
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT user_id FROM users") as cursor: rows = await cursor.fetchall()
    
    await message.answer(f"🚀 Memulai broadcast ke {len(rows)} user...")
    for row in rows:
        try:
            if target.photo: await bot.send_photo(row[0], target.photo[-1].file_id, caption=cap)
            elif target.video: await bot.send_video(row[0], target.video.file_id, caption=cap)
            else: await bot.send_message(row[0], cap)
            await asyncio.sleep(0.3)
        except: continue
    await message.answer("✅ Selesai!")

@dp.message(F.from_user.id == ADMIN_ID, (F.photo | F.video), F.chat.type == "private")
async def admin_upload(message: Message):
    code = uuid.uuid4().hex[:8]
    f_id = message.photo[-1].file_id if message.photo else message.video.file_id
    m_t = "photo" if message.photo else "video"
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO media VALUES (?, ?, ?, ?)", (code, f_id, m_t, message.caption or ""))
        await db.commit()
    await message.reply(f"✅ Tersimpan!\n🔗 Link: `https://t.me/{BOT_USERNAME}?start={code}`")

@dp.message(Command("del"), F.from_user.id == ADMIN_ID)
async def delete_handler(message: Message):
    code = message.text.replace("/del", "").strip()
    if not code: return await message.reply("❌ Format: `/del [kode]`")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("DELETE FROM media WHERE code=?", (code,))
        await db.commit()
    await message.reply(f"✅ Kode `{code}` wis dibusak!")

@dp.message(Command("senddb"), F.from_user.id == ADMIN_ID)
async def send_db_handler(message: Message):
    if os.path.exists(DB_NAME):
        await message.answer_document(FSInputFile(DB_NAME), caption="📦 Backup DB")

# ================= SYSTEM =================

@dp.callback_query(F.data.startswith("retry:"))
async def retry_handler(callback):
    code = callback.data.split(":", 1)[1]
    await callback.answer()
    await send_media(callback.message.chat.id, callback.from_user.id, code)

async def send_media(chat_id: int, user_id: int, code: str):
    status = await check_membership(user_id)
    if not all(status):
        await bot.send_message(chat_id, "🚫 harus join semuanya sayang,kalo udah klik cobalagi!", reply_markup=join_keyboard(code, status))
        return
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT file_id, type, caption FROM media WHERE code=?", (code,)) as cursor: row = await cursor.fetchone()
    if not row: return await bot.send_message(chat_id, "❌ Link salah.")
    
    f_id, m_type, cap = row
    if m_type == "photo": await bot.send_photo(chat_id, f_id, caption=cap, protect_content=True)
    else: await bot.send_video(chat_id, f_id, caption=cap, protect_content=True)

async def main():
    await init_db()
    print("Bot is running...")
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
