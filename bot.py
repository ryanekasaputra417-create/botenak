import asyncio
import uuid
import os
import aiosqlite
from datetime import datetime, timedelta

from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (
    Message, InlineKeyboardMarkup, InlineKeyboardButton, 
    BotCommand, BotCommandScopeChat, FSInputFile, 
    CallbackQuery, ChatMemberUpdated, ChatPermissions
)
from aiogram.filters import CommandStart, Command, StateFilter, ChatMemberUpdatedFilter, IS_MEMBER, LEFT
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ================= KONFIGURASI =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BOT_USERNAME = os.getenv("BOT_USERNAME")
DB_NAME = os.path.join(os.path.dirname(os.path.abspath(__file__)), "media_pro.db")
KATA_KOTOR = ["biyo", "promosi", "bio", "byoh", "biyoh"]

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class BotState(StatesGroup):
    waiting_input = State()      
    waiting_ask_reply = State()  
    waiting_post_title = State() 
    waiting_post_cover = State() 

# ================= DATABASE ENGINE =================
async def init_db():
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS media (code TEXT PRIMARY KEY, file_id TEXT, type TEXT, title TEXT, backup_id INTEGER)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (user_id INTEGER PRIMARY KEY)")
        defs = [('db_channel', '0'), ('fsub_ids', ''), ('addlist_url', ''), ('start_text', 'Halo {name}!'), ('log_ch', '0')]
        for k, v in defs:
            await db.execute("INSERT OR IGNORE INTO settings VALUES (?,?)", (k, v))
        await db.commit()

async def set_setting(key, value):
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR REPLACE INTO settings (key, value) VALUES (?,?)", (key, str(value)))
        await db.commit()

async def get_setting(key):
    async with aiosqlite.connect(DB_NAME) as db:
        async with db.execute("SELECT value FROM settings WHERE key=?", (key,)) as cursor:
            row = await cursor.fetchone()
            return row[0] if row else ""

# ================= HANDLER LOG JOIN/LEFT (FITUR AWAL) =================
@dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=IS_MEMBER))
async def on_user_join(event: ChatMemberUpdated):
    log_ch = await get_setting('log_ch')
    if log_ch and log_ch != "0":
        user = event.new_chat_member.user
        await bot.send_message(log_ch, f"✅ **MEMBER JOIN**\n👤 {user.full_name}\n🆔 `{user.id}`")

@dp.chat_member(ChatMemberUpdatedFilter(member_status_changed=LEFT))
async def on_user_left(event: ChatMemberUpdated):
    log_ch = await get_setting('log_ch')
    if log_ch and log_ch != "0":
        user = event.old_chat_member.user
        await bot.send_message(log_ch, f"❌ **MEMBER KELUAR**\n👤 {user.full_name}\n🆔 `{user.id}`")

# ================= FILTER KATA (HANYA DI GRUP - FITUR AWAL) =================
@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def filter_kata(message: Message):
    if message.from_user.id == ADMIN_ID: return
    if any(k in message.text.lower() for k in KATA_KOTOR):
        try:
            await message.delete()
            until = datetime.now() + timedelta(hours=24)
            await bot.restrict_chat_member(message.chat.id, message.from_user.id, ChatPermissions(can_send_messages=False), until_date=until)
            await message.answer(f"🚫 {message.from_user.first_name} Mute 24 Jam.")
        except: pass

# ================= HANDLER MEDIA /START (DIPERBAIKI) =================
@dp.message(CommandStart())
async def start_cmd(m: Message):
    uid = m.from_user.id
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT OR IGNORE INTO users (user_id) VALUES (?)", (uid,))
        await db.commit()

    # Ambil kode setelah /start
    args = m.text.split()
    code = args[1] if len(args) > 1 else None
    
    # 1. Cek FSUB
    fsubs = await get_setting('fsub_ids')
    addlist = await get_setting('addlist_url')
    not_j = []
    if fsubs:
        for cid in fsubs.split(","):
            try:
                mem = await bot.get_chat_member(cid.strip(), uid)
                if mem.status not in ["member", "administrator", "creator"]: not_j.append(cid.strip())
            except: continue

    if not_j:
        kb = [[InlineKeyboardButton(text="➕ Join Channel", url=addlist if addlist else "https://t.me/")]]
        kb.append([InlineKeyboardButton(text="🔄 Coba Lagi", url=f"https://t.me/{BOT_USERNAME}?start={code or ''}")])
        return await m.answer("Silakan bergabung ke channel sponsor kami terlebih dahulu.", reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

    # 2. Jika ada KODE (Link Media)
    if code:
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT file_id, type, title FROM media WHERE code=?", (code,)) as cur:
                row = await cur.fetchone()
        if row:
            if row[1] == "photo": return await bot.send_photo(m.chat.id, row[0], caption=f"✅ {row[2]}")
            else: return await bot.send_video(m.chat.id, row[0], caption=f"✅ {row[2]}")
        else:
            return await m.answer("❌ Konten tidak ditemukan.")

    # 3. Tampilan Menu Utama Member
    stext = await get_setting('start_text')
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🎁 Kirim Konten", callback_data="m_donasi"),
         InlineKeyboardButton(text="💬 Tanya Admin", callback_data="m_ask")]
    ])
    await m.answer(stext.format(name=m.from_user.first_name), reply_markup=kb)

# ================= ADMIN DASHBOARD & AUTO-POST =================
@dp.message(Command("settings"), F.from_user.id == ADMIN_ID)
async def open_settings(m: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="🆔 Multi-FSUB", callback_data="conf_fsub"), InlineKeyboardButton(text="🔗 Addlist", callback_data="conf_addlist")],
        [InlineKeyboardButton(text="📝 Teks Start", callback_data="conf_start_txt"), InlineKeyboardButton(text="🗄 DB Channel", callback_data="conf_db_ch")],
        [InlineKeyboardButton(text="📊 Stats", callback_data="conf_stats"), InlineKeyboardButton(text="❌ Tutup", callback_data="conf_close")]
    ])
    await m.answer("🛠 **ADMIN DASHBOARD**", reply_markup=kb)

@dp.callback_query(F.data.startswith("conf_"), F.from_user.id == ADMIN_ID)
async def admin_callback(c: CallbackQuery, state: FSMContext):
    action = c.data.replace("conf_", "")
    if action == "close": return await c.message.delete()
    if action == "stats":
        async with aiosqlite.connect(DB_NAME) as db:
            async with db.execute("SELECT COUNT(*) FROM users") as c1: u = (await c1.fetchone())[0]
            async with db.execute("SELECT COUNT(*) FROM media") as c2: m = (await c2.fetchone())[0]
        return await c.answer(f"User: {u} | Media: {m}", show_alert=True)
    
    targets = {"fsub": "fsub_ids", "addlist": "addlist_url", "start_txt": "start_text", "db_ch": "db_channel"}
    if action in targets:
        await state.update_data(target=targets[action])
        await c.message.edit_text(f"📥 Kirim data baru untuk {action}:", reply_markup=InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="⬅️ Kembali", callback_data="conf_back")]]))
        await state.set_state(BotState.waiting_input)

@dp.message(BotState.waiting_input, F.from_user.id == ADMIN_ID)
async def save_setting_input(m: Message, state: FSMContext):
    data = await state.get_data()
    await set_setting(data['target'], m.text)
    await m.reply(f"✅ {data['target']} updated!")
    await state.clear()

# Auto Post Logic
@dp.message(F.chat.type == "private", (F.photo | F.video | F.document), F.from_user.id == ADMIN_ID, StateFilter(None))
async def auto_post_start(m: Message, state: FSMContext):
    fid = m.photo[-1].file_id if m.photo else (m.video.file_id if m.video else m.document.file_id)
    await state.update_data(fid=fid, ftype="photo" if m.photo else "video")
    await m.answer("📝 Judul Konten?")
    await state.set_state(BotState.waiting_post_title)

@dp.message(BotState.waiting_post_title)
async def auto_post_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text)
    await m.answer("📸 Kirim Foto Cover:")
    await state.set_state(BotState.waiting_post_cover)

@dp.message(BotState.waiting_post_cover, F.photo)
async def auto_post_final(m: Message, state: FSMContext):
    data = await state.get_data()
    code = uuid.uuid4().hex[:8]
    db_ch = await get_setting('db_channel')
    # Backup
    backup = await bot.send_photo(db_ch, data['fid'], caption=f"Backup: {data['title']}\nCode: `{code}`")
    async with aiosqlite.connect(DB_NAME) as db:
        await db.execute("INSERT INTO media VALUES (?,?,?,?,?)", (code, data['fid'], data['ftype'], data['title'], backup.message_id))
        await db.commit()
    # Post
    fsubs = await get_setting('fsub_ids')
    if fsubs:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="🎬 NONTON", url=f"https://t.me/{BOT_USERNAME}?start={code}")]])
        await bot.send_photo(fsubs.split(",")[0], m.photo[-1].file_id, caption=f"🔥 **NEW**\n\n📌 {data['title']}", reply_markup=kb)
    await m.answer(f"✅ Sukses!\nLink: `https://t.me/{BOT_USERNAME}?start={code}`")
    await state.clear()

# ================= DONASI & ASK =================
@dp.callback_query(F.data == "m_donasi")
async def donasi_btn(c: CallbackQuery):
    await c.message.answer("🙏 Silakan kirim media donasi kamu langsung ke sini.")
    await c.answer()

@dp.callback_query(F.data == "m_ask")
async def ask_btn(c: CallbackQuery, state: FSMContext):
    await c.message.answer("📝 Tulis pesan untuk Admin:")
    await state.set_state(BotState.waiting_ask_reply)
    await c.answer()

@dp.message(BotState.waiting_ask_reply)
async def process_ask_reply(m: Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"📩 **ASK**: {m.text}\nDari: {m.from_user.full_name}")
    await m.reply("✅ Terkirim.")
    await state.clear()

# ================= HELPERS (STATS & SENDDB) =================
@dp.message(Command("senddb"), F.from_user.id == ADMIN_ID)
async def admin_senddb(m: Message):
    if os.path.exists(DB_NAME): await m.reply_document(FSInputFile(DB_NAME))

async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
