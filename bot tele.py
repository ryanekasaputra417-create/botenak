import asyncio
import uuid
import os
import aiosqlite
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import CommandStart

# ================= KONFIG =================
BOT_TOKEN = "8317197195:AAF1ALwZx3XQGnnEePrn1aJtGeI_CP_Fu3I"
CHANNEL_USERNAME = "@emsamasamaenak"
ADMIN_ID = 5609976748
BOT_USERNAME = "emsamasamaenak_bot"
# ================= PATH DB (PASTI ADA) =================
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_NAME = os.path.join(BASE_DIR, "media.db")

print("DB PATH:", DB_NAME)

bot = Bot(BOT_TOKEN)
dp = Dispatcher()

# ================= DATABASE =================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("""
        CREATE TABLE IF NOT EXISTS media (
            code TEXT PRIMARY KEY,
            file_id TEXT,
            type TEXT
        )
        """)

        # auto tambah kolom caption jika belum ada
        async with db.execute("PRAGMA table_info(media)") as cursor:
            cols = [row[1] for row in await cursor.fetchall()]

        if "caption" not in cols:
            await db.execute("ALTER TABLE media ADD COLUMN caption TEXT")

        await db.commit()

# ================= JOIN CHECK =================
async def is_member(user_id: int) -> bool:
    try:
        member = await bot.get_chat_member(CHANNEL_USERNAME, user_id)
        return member.status in ("member", "administrator", "creator")
    except:
        return False

# ================= KEYBOARD =================
def join_keyboard(code: str):
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [
                InlineKeyboardButton(
                    text="📢 JOIN CHANNEL",
                    url=f"https://t.me/{CHANNEL_USERNAME[1:]}"
                )
            ],
            [
                InlineKeyboardButton(
                    text="🔄 COBA LAGI",
                    callback_data=f"retry:{code}"
                )
            ]
        ]
    )

# ================= START =================
@dp.message(CommandStart())
async def start_handler(message: Message):
    args = message.text.split(" ", 1)
    if len(args) == 1:
        await message.answer("👋 Kirim link untuk mengakses media.")
        return
    await send_media(message.chat.id, message.from_user.id, args[1])

# ================= RETRY =================
@dp.callback_query(F.data.startswith("retry:"))
async def retry_handler(callback):
    code = callback.data.split(":", 1)[1]
    await callback.answer()
    await send_media(callback.message.chat.id, callback.from_user.id, code)

# ================= SEND MEDIA =================
async def send_media(chat_id: int, user_id: int, code: str):
    if not await is_member(user_id):
        await bot.send_message(
            chat_id,
            "🚫 Kamu wajib join channel dulu.",
            reply_markup=join_keyboard(code)
        )
        return

    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute(
            "SELECT file_id, type, caption FROM media WHERE code=?",
            (code,)
        ) as cursor:
            row = await cursor.fetchone()

    if not row:
        await bot.send_message(chat_id, "❌ Link tidak valid.")
        return

    file_id, media_type, caption = row
    caption = caption or ""

    if media_type == "photo":
        await bot.send_photo(
            chat_id,
            file_id,
            caption=caption,
            protect_content=True
        )
    else:
        await bot.send_video(
            chat_id,
            file_id,
            caption=caption,
            protect_content=True
        )

# ================= ADMIN UPLOAD =================
@dp.message(F.from_user.id == ADMIN_ID)
async def admin_upload(message: Message):
    if not (message.photo or message.video):
        return

    code = uuid.uuid4().hex[:8]
    caption = message.caption or ""

    if message.photo:
        file_id = message.photo[-1].file_id
        media_type = "photo"
    else:
        file_id = message.video.file_id
        media_type = "video"

    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute(
            "INSERT OR REPLACE INTO media (code, file_id, type, caption) VALUES (?, ?, ?, ?)",
            (code, file_id, media_type, caption)
        )
        await db.commit()

    link = f"https://t.me/{BOT_USERNAME}?start={code}"

    await message.reply(
        f"✅ Media tersimpan\n"
        f"🔗 Link:\n{link}"
    )

# ================= MAIN =================
async def main():
    await init_db()
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
