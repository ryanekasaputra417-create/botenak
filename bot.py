import asyncio, uuid, os, aiosqlite
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton, 
    BotCommand, BotCommandScopeDefault, BotCommandScopeChat, FSInputFile, 
    CallbackQuery, ChatMemberUpdated, ChatPermissions)
from aiogram.filters import CommandStart, Command, StateFilter, ChatMemberUpdatedFilter, IS_MEMBER, LEFT
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ================= RAILWAY CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BOT_USN = os.getenv("BOT_USERNAME").replace("@", "")

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
KATA_KOTOR = ["biyo", "promosi", "bio", "byoh", "biyoh"]

class AdminState(StatesGroup):
    wait_title = State()
    wait_cover = State()
    edit_start = State()
    edit_fsub = State()
    edit_btn = State()
    set_db_ch = State()
    set_post_ch = State()
    set_fsub_list = State()
    set_log_id = State()
    set_exempt = State()

# ================= DATABASE =================
async def init_db():
    async with aiosqlite.connect("master.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS media (code TEXT PRIMARY KEY, fid TEXT, mtype TEXT, title TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (uid INTEGER PRIMARY KEY)")
        await db.execute("""CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY, 
            start_txt TEXT, fsub_txt TEXT, btn_txt TEXT, 
            fsub_list TEXT, db_ch_id TEXT, post_ch_id TEXT, 
            log_id TEXT, exempt_usn TEXT)""")
        
        # Inisialisasi Data Default (Jika Belum Ada)
        await db.execute("""INSERT OR IGNORE INTO settings 
            (id, start_txt, fsub_txt, btn_txt, fsub_list, db_ch_id, post_ch_id, log_id, exempt_usn) 
            VALUES (1, 'Halo! Selamat datang.', 'Silakan Join Channel:', '🎬 NONTON', '', '', '', '', '')""")
        await db.commit()

async def get_s():
    async with aiosqlite.connect("master.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM settings WHERE id=1") as cur: return await cur.fetchone()

# ================= LOGS & FILTER =================
@dp.message(F.chat.type.in_({"group", "supergroup"}), F.text)
async def word_guard(m: Message):
    s = await get_s()
    ex = s['exempt_usn'].lower().split(",")
    if m.from_user.id == ADMIN_ID or (m.from_user.username and m.from_user.username.lower() in ex): return
    if any(k in m.text.lower() for k in KATA_KOTOR):
        try:
            await m.delete()
            await bot.restrict_chat_member(m.chat.id, m.from_user.id, ChatPermissions(can_send_messages=False), until_date=datetime.now()+timedelta(hours=24))
            await m.answer(f"🔇 {m.from_user.first_name} Mute 24 Jam (Bad Word)")
        except: pass

# ================= SETTINGS DASHBOARD =================
@dp.message(Command("settings"), F.from_user.id == ADMIN_ID)
async def dashboard(m: Message):
    s = await get_s()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📝 Edit Start", callback_data="st_start"), InlineKeyboardButton(text="📢 Edit FSub", callback_data="st_fsub")],
        [InlineKeyboardButton(text="🔗 Set FSub List", callback_data="st_fsublist"), InlineKeyboardButton(text="🔘 Set Tombol", callback_data="st_btn")],
        [InlineKeyboardButton(text="📁 Set DB Backup", callback_data="st_dbch"), InlineKeyboardButton(text="📣 Set Post CH", callback_data="st_postch")],
        [InlineKeyboardButton(text="📜 Set Log ID", callback_data="st_log"), InlineKeyboardButton(text="🛡️ Set Exempt", callback_data="st_ex")],
        [InlineKeyboardButton(text="📊 Statistik", callback_data="st_stats"), InlineKeyboardButton(text="💾 Ambil .db", callback_data="st_dbfile")]
    ])
    text = f"⚙️ **ADMIN SETTINGS**\n\n**Post CH:** `{s['post_ch_id']}`\n**DB CH:** `{s['db_ch_id']}`\n**Log ID:** `{s['log_id']}`\n**FSub:** `{s['fsub_list']}`"
    await m.answer(text, reply_markup=kb, parse_mode="Markdown")

@dp.callback_query(F.data.startswith("st_"))
async def cb_settings(c: CallbackQuery, state: FSMContext):
    action = c.data.replace("st_", "")
    if action == "stats":
        async with aiosqlite.connect("master.db") as db:
            async with db.execute("SELECT COUNT(*) FROM users") as c1: u = await c1.fetchone()
            async with db.execute("SELECT COUNT(*) FROM media") as c2: m = await c2.fetchone()
        return await c.answer(f"User: {u[0]} | Media: {m[0]}", show_alert=True)
    if action == "dbfile": return await c.message.answer_document(FSInputFile("master.db"))
    
    prompts = {
        "start": "Kirim teks Start baru:", "fsub": "Kirim teks FSub baru:",
        "btn": "Kirim teks Tombol Nonton:", "fsublist": "Kirim Username CH (pisah koma):",
        "dbch": "Kirim ID Channel Backup (contoh: -100xxx):", "postch": "Kirim ID Channel Post:",
        "log": "Kirim ID Grup Log:", "ex": "Kirim Username Exempt (pisah koma):"
    }
    await state.set_state(getattr(AdminState, f"set_{action}" if f"set_{action}" in AdminState.__states__ else f"edit_{action}"))
    await c.message.answer(prompts.get(action, "Kirim data baru:"))
    await c.answer()

@dp.message(StateFilter(AdminState))
async def save_settings(m: Message, state: FSMContext):
    st = await state.get_state()
    col = {
        "AdminState:edit_start": "start_txt", "AdminState:edit_fsub": "fsub_txt",
        "AdminState:edit_btn": "btn_txt", "AdminState:set_fsub_list": "fsub_list",
        "AdminState:set_db_ch": "db_ch_id", "AdminState:set_post_ch": "post_ch_id",
        "AdminState:set_log_id": "log_id", "AdminState:set_exempt": "exempt_usn"
    }.get(st)
    
    if col:
        async with aiosqlite.connect("master.db") as db:
            await db.execute(f"UPDATE settings SET {col}=? WHERE id=1", (m.text,))
            await db.commit()
        await m.answer(f"✅ Berhasil mengupdate {col}!")
    await state.clear()

# ================= AUTO POST & DONASI =================
@dp.message(F.chat.type == "private", (F.photo | F.video | F.document | F.animation), StateFilter(None))
async def handle_uploads(m: Message, state: FSMContext):
    s = await get_s()
    if m.from_user.id != ADMIN_ID:
        if s['log_id']: await bot.send_message(s['log_id'], f"🎁 **DONASI** dari {m.from_user.full_name}")
        await bot.forward_message(ADMIN_ID, m.chat.id, m.message_id)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="✅ APPROVE", callback_data="app_don")]])
        return await m.answer("✅ Terkirim ke admin!", reply_markup=kb if m.from_user.id == ADMIN_ID else None)

    await state.update_data(fid=m.photo[-1].file_id if m.photo else (m.video.file_id if m.video else m.document.file_id), mtype="photo" if m.photo else "video")
    await state.set_state(AdminState.wait_title)
    await m.reply("🏷 **JUDUL:**")

@dp.callback_query(F.data == "app_don")
async def app_don(c: CallbackQuery, state: FSMContext):
    await state.set_state(AdminState.wait_title)
    await c.message.answer("📝 Masukkan Judul:")
    await c.answer()

@dp.message(AdminState.wait_title)
async def get_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text)
    await state.set_state(AdminState.wait_cover)
    await m.answer("📸 **COVER:**")

@dp.message(AdminState.wait_cover, F.photo)
async def finalize_post(m: Message, state: FSMContext):
    data = await state.get_data()
    s = await get_s()
    code = uuid.uuid4().hex[:8]
    
    if s['db_ch_id']: await bot.copy_message(s['db_ch_id'], m.chat.id, m.message_id)
    
    async with aiosqlite.connect("master.db") as db:
        await db.execute("INSERT INTO media VALUES (?,?,?,?)", (code, data['fid'], data['mtype'], data['title']))
        await db.commit()
    
    link = f"https://t.me/{BOT_USN}?start={code}"
    if s['post_ch_id']:
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=s['btn_txt'], url=link)]])
        await bot.send_photo(s['post_ch_id'], m.photo[-1].file_id, caption=f"🔥 **{data['title']}**", reply_markup=kb)
    
    await m.answer(f"✅ **PUBLISHED**\nLink: `{link}`")
    await state.clear()

# ================= START & FSUB =================
@dp.message(CommandStart())
async def start_handler(m: Message, code_override=None):
    uid = m.from_user.id
    async with aiosqlite.connect("master.db") as db:
        await db.execute("INSERT OR IGNORE INTO users (uid) VALUES (?)", (uid,))
        await db.commit()
    
    s = await get_s()
    args = m.text.split()[1] if len(m.text.split()) > 1 else code_override
    
    if not args:
        return await m.answer(s['start_txt'], reply_markup=InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="🎁 Donasi", callback_data="mb_don"), InlineKeyboardButton(text="💬 Ask", callback_data="mb_ask")]
        ]))

    must_join = []
    if s['fsub_list']:
        for ch in s['fsub_list'].split(","):
            try:
                member = await bot.get_chat_member(f"@{ch.strip().replace('@','')}", uid)
                if member.status not in ("member", "administrator", "creator"): must_join.append(ch.strip())
            except: pass
    
    if must_join:
        btns = [[InlineKeyboardButton(text=f"JOIN {c}", url=f"https://t.me/{c.replace('@','')}")] for c in must_join]
        btns.append([InlineKeyboardButton(text="🔄 COBA LAGI", callback_data=f"retry_{args}")])
        return await m.answer(s['fsub_txt'], reply_markup=InlineKeyboardMarkup(inline_keyboard=btns))

    async with aiosqlite.connect("master.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM media WHERE code=?", (args,)) as cur: row = await cur.fetchone()
    
    if row:
        cap = f"🎬 **{row['title']}**"
        if row['mtype'] == "photo": await bot.send_photo(m.chat.id, row['fid'], caption=cap)
        else: await bot.send_video(m.chat.id, row['fid'], caption=cap)

@dp.callback_query(F.data.startswith("retry_"))
async def retry_cb(c: CallbackQuery):
    code = c.data.split("_")[1]
    await c.message.delete()
    await start_handler(c.message, code_override=code)

@dp.message(Command("ask"))
async def ask_admin(m: Message):
    txt = m.text.split(maxsplit=1)
    if len(txt) < 2: return await m.reply("⚠️ `/ask pesan` ")
    await bot.send_message(ADMIN_ID, f"📩 **ASK**\nDari: {m.from_user.full_name}\nID: `{m.from_user.id}`\n\n{txt[1]}")
    await m.reply("✅ Terkirim.")

# ================= RUN =================
async def main():
    await init_db()
    await bot.set_my_commands([BotCommand(command="start", description="Mulai"), BotCommand(command="ask", description="Tanya Admin"), BotCommand(command="settings", description="Dashboard Admin")], scope=BotCommandScopeDefault())
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
