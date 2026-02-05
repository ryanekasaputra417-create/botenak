import asyncio, uuid, os, aiosqlite, traceback, random, string
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton, 
    BotCommand, BotCommandScopeDefault, FSInputFile, CallbackQuery, ChatMemberUpdated)
from aiogram.filters import CommandStart, Command, StateFilter
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

# ================= CONFIG =================
BOT_TOKEN = os.getenv("BOT_TOKEN")
ADMIN_ID = int(os.getenv("ADMIN_ID"))
BOT_USN = os.getenv("BOT_USERNAME", "").replace("@", "")

bot = Bot(BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())

class BotState(StatesGroup):
    wait_title = State()
    wait_cover = State()
    wait_ask = State()
    wait_reject_reason = State()
    wait_broadcast = State()
    set_val = State()

def gen_code():
    char = ''.join(random.choices(string.ascii_letters + string.digits, k=30))
    return f"get_{char}"

# ================= DATABASE =================
async def init_db():
    async with aiosqlite.connect("master.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS media (code TEXT PRIMARY KEY, fid TEXT, mtype TEXT, title TEXT, bk_id TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (uid INTEGER PRIMARY KEY, name TEXT)")
        await db.execute("""CREATE TABLE IF NOT EXISTS settings (
            id INTEGER PRIMARY KEY, start_txt TEXT, fsub_txt TEXT, 
            btn_nonton TEXT, btn_donasi TEXT, btn_ask TEXT,
            fsub_list TEXT, fsub_link TEXT, db_ch_id TEXT, post_ch_id TEXT, 
            log_id TEXT, exempt_usn TEXT)""")
        await db.execute("""INSERT OR IGNORE INTO settings 
            (id, start_txt, fsub_txt, btn_nonton, btn_donasi, btn_ask, fsub_list, fsub_link, db_ch_id, post_ch_id, log_id, exempt_usn) 
            VALUES (1, 'Halo Selamat datang', 'Join dulu ya', 'NONTON', 'DONASI', 'TANYA ADMIN', '', '', '', '', '', '')""")
        await db.commit()

async def get_conf():
    async with aiosqlite.connect("master.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM settings WHERE id=1") as cur: return await cur.fetchone()

# ================= LOG SYSTEM (START/JOIN/OUT) =================
async def send_log(text: str):
    s = await get_conf()
    if s['log_id']:
        try: await bot.send_message(s['log_id'], f"📑 **LOG SYSTEM**\n{text}")
        except: pass

@dp.chat_member()
async def chat_member_update(update: ChatMemberUpdated):
    user = update.from_user
    chat = update.chat
    status_msg = ""
    if update.new_chat_member.status == "member":
        status_msg = f"🆕 **USER JOIN**\n👤 Name: {user.full_name}\n🆔 ID: `{user.id}`\n🌐 GC: {chat.title or 'Private'}"
    elif update.new_chat_member.status in ["left", "kicked"]:
        status_msg = f"🚪 **USER OUT**\n👤 Name: {user.full_name}\n🆔 ID: `{user.id}`\n🌐 GC: {chat.title or 'Private'}"
    if status_msg: await send_log(status_msg)

# ================= GLOBAL ERROR =================
@dp.errors()
async def error_handler(event: types.ErrorEvent):
    err = f"🚨 **DETEKSI ERROR**\n`{event.exception}`\n\n`{traceback.format_exc()[-500:]}`"
    try: await bot.send_message(ADMIN_ID, err)
    except: print(err)

# ================= ADMIN MENU =================
@dp.message(CommandStart(), F.from_user.id == ADMIN_ID)
async def admin_start(m: Message):
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📢 BROADCAST", callback_data="adm_bc"), InlineKeyboardButton(text="📊 STATS", callback_data="adm_stats")],
        [InlineKeyboardButton(text="⚙️ SETTINGS", callback_data="adm_sett"), InlineKeyboardButton(text="📜 STATUS LOG", callback_data="adm_check_log")],
        [InlineKeyboardButton(text="❌ TUTUP", callback_data="adm_close")]
    ])
    await m.answer("🛠 **ADMIN DASHBOARD**", reply_markup=kb)

@dp.callback_query(F.data == "adm_sett")
async def open_settings(c: CallbackQuery):
    s = await get_conf()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Teks Start", callback_data="set_start_txt"), InlineKeyboardButton(text="ID Log Channel", callback_data="set_log_id")],
        [InlineKeyboardButton(text="Link FSub", callback_data="set_fsub_link"), InlineKeyboardButton(text="ID CH Post", callback_data="set_post_ch_id")],
        [InlineKeyboardButton(text="ID CH DB", callback_data="set_db_ch_id"), InlineKeyboardButton(text="Username FSub", callback_data="set_fsub_list")],
        [InlineKeyboardButton(text="🔙 BATAL", callback_data="adm_close")]
    ])
    await c.message.edit_text(f"⚙️ **SETTINGS**\nLog CH: `{s['log_id']}`\nPost CH: `{s['post_ch_id']}`", reply_markup=kb)

@dp.callback_query(F.data.startswith("set_"))
async def config_set(c: CallbackQuery, state: FSMContext):
    field = c.data.replace("set_", "")
    await state.update_data(field=field)
    await state.set_state(BotState.set_val)
    await c.message.answer(f"Masukkan nilai baru untuk `{field}`:\n(Gunakan -100 untuk ID Channel)")

@dp.message(BotState.set_val)
async def save_config(m: Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect("master.db") as db:
        await db.execute(f"UPDATE settings SET {data['field']}=? WHERE id=1", (m.text,))
        await db.commit()
    await m.answer(f"✅ `{data['field']}` Berhasil diperbarui.")
    await state.clear()

# ================= BROADCAST SYSTEM =================
@dp.callback_query(F.data == "adm_bc")
async def bc_cmd(c: CallbackQuery, state: FSMContext):
    await state.set_state(BotState.wait_broadcast)
    await c.message.answer("📝 Kirim pesan broadcast (Teks/Foto/Video):")

@dp.message(BotState.wait_broadcast)
async def do_broadcast(m: Message, state: FSMContext):
    async with aiosqlite.connect("master.db") as db:
        async with db.execute("SELECT uid FROM users") as cur: users = await cur.fetchall()
    
    count = 0
    for u in users:
        try:
            await bot.copy_message(u[0], m.chat.id, m.message_id)
            count += 1
            await asyncio.sleep(0.05)
        except: pass
    await m.answer(f"✅ Broadcast selesai ke {count} user.")
    await state.clear()

# ================= MEMBER & LOGIKA TOMBOL =================
@dp.message(CommandStart())
async def member_start(m: Message, code_override=None):
    s = await get_conf()
    arg = code_override if code_override else (m.text.split()[1] if len(m.text.split()) > 1 else None)
    
    # Simpan User Baru & Kirim Log
    async with aiosqlite.connect("master.db") as db:
        cur = await db.execute("SELECT uid FROM users WHERE uid=?", (m.from_user.id,))
        exists = await cur.fetchone()
        if not exists:
            await db.execute("INSERT INTO users VALUES (?,?)", (m.from_user.id, m.from_user.full_name))
            await db.commit()
            await send_log(f"🚀 **USER PERTAMA KALI START**\n👤 Name: {m.from_user.full_name}\n🆔 ID: `{m.from_user.id}`\n🔗 Arg: `{arg or 'None'}`")

    if not arg:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=s['btn_donasi'], callback_data="btn_donasi_klik"), 
             InlineKeyboardButton(text=s['btn_ask'], callback_data="btn_ask_klik")]
        ])
        return await m.answer(s['start_txt'], reply_markup=kb)

    # FSub Check
    must_join = False
    if s['fsub_list']:
        for ch in s['fsub_list'].replace("@","").split(","):
            if not ch.strip(): continue
            try:
                mem = await bot.get_chat_member(f"@{ch.strip()}", m.from_user.id)
                if mem.status not in ["member", "administrator", "creator"]:
                    must_join = True; break
            except: pass
    
    if must_join:
        kb = []
        if s['fsub_link']: kb.append([InlineKeyboardButton(text="🔗 JOIN DISINI", url=s['fsub_link'])])
        kb.append([InlineKeyboardButton(text="🔄 COBA LAGI", callback_data=f"retry_{arg}")])
        return await m.answer(s['fsub_txt'], reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

    # Ambil Media dari DB (Bot Mengingat)
    async with aiosqlite.connect("master.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM media WHERE code=?", (arg,)) as cur: row = await cur.fetchone()
    
    if row:
        if row['mtype'] == "photo": await bot.send_photo(m.chat.id, row['fid'], caption=row['title'])
        else: await bot.send_video(m.chat.id, row['fid'], caption=row['title'])

@dp.callback_query(F.data.startswith("retry_"))
async def retry_handler(c: CallbackQuery):
    code = c.data.replace("retry_", "")
    await c.message.delete()
    await member_start(c.message, code_override=code)

# ================= FIX TOMBOL DONASI & ASK =================
@dp.callback_query(F.data == "btn_donasi_klik")
async def donasi_klik(c: CallbackQuery):
    await c.message.answer("🎁 **MENU DONASI**\nSilakan kirim Media (Foto/Video) yang ingin kamu donasikan langsung ke sini.")
    await c.answer()

@dp.callback_query(F.data == "btn_ask_klik")
async def ask_klik(c: CallbackQuery, state: FSMContext):
    await state.set_state(BotState.wait_ask)
    await c.message.answer("💬 **TANYA ADMIN**\nSilakan ketik pertanyaan/pesan kamu:")
    await c.answer()

@dp.message(BotState.wait_ask)
async def process_ask(m: Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"📩 **PESAN ASK BARU**\nDari: {m.from_user.full_name}\nID: `{m.from_user.id}`\n\nPesan:\n{m.text}")
    await m.answer("✅ Pesan terkirim ke admin.")
    await state.clear()

# ================= AUTO POST DONASI =================
@dp.message(F.chat.type == "private", (F.photo | F.video))
async def handle_donasi_media(m: Message, state: FSMContext):
    if m.from_user.id == ADMIN_ID:
        fid = m.photo[-1].file_id if m.photo else m.video.file_id
        await state.update_data(fid=fid, mtype="photo" if m.photo else "video")
        await state.set_state(BotState.wait_title)
        return await m.reply("🏷 **JUDUL:**\nMasukkan judul untuk postingan ini:")
    
    # Member Donasi
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ APPROVE", callback_data=f"don_app_{m.from_user.id}_{m.message_id}")]
    ])
    await bot.forward_message(ADMIN_ID, m.chat.id, m.message_id)
    await bot.send_message(ADMIN_ID, f"🎁 **DONASI DARI {m.from_user.full_name}**", reply_markup=kb)
    await m.answer("✅ Media donasi kamu sudah terkirim ke admin untuk di-review.")

@dp.callback_query(F.data.startswith("don_app_"))
async def approve_donasi(c: CallbackQuery, state: FSMContext):
    parts = c.data.split("_")
    uid, mid = parts[2], parts[3]
    msg = await bot.forward_message(ADMIN_ID, uid, int(mid))
    fid = msg.photo[-1].file_id if msg.photo else msg.video.file_id
    await state.update_data(fid=fid, mtype="photo" if msg.photo else "video")
    await state.set_state(BotState.wait_title)
    await c.message.answer("Donasi di-approve. Sekarang masukkan **JUDUL**:")

@dp.message(BotState.wait_title)
async def get_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text)
    await state.set_state(BotState.wait_cover)
    await m.answer("📸 Sekarang kirim **FOTO COVER**:")

@dp.message(BotState.wait_cover, F.photo)
async def finalize_donasi(m: Message, state: FSMContext):
    try:
        data = await state.get_data()
        s = await get_conf()
        code = gen_code()
        
        # Backup ke DB Channel
        bk_id = ""
        if s['db_ch_id']:
            bk = await bot.send_photo(s['db_ch_id'], m.photo[-1].file_id, caption=f"ID: {code}\nTITLE: {data['title']}")
            bk_id = str(bk.message_id)

        async with aiosqlite.connect("master.db") as db:
            await db.execute("INSERT INTO media VALUES (?,?,?,?,?)", (code, data['fid'], data['mtype'], data['title'], bk_id))
            await db.commit()

        # Post ke Channel Utama
        if s['post_ch_id']:
            link = f"https://t.me/{emsamasamaenak_bot}?start={code}"
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=s['btn_nonton'], url=link)]])
            await bot.send_photo(s['post_ch_id'], m.photo[-1].file_id, caption=data['title'], reply_markup=kb)
            await m.answer(f"✅ **POST BERHASIL!**\nLink: `{link}`")
    except Exception: await m.answer("❌ Gagal post. Cek ID Channel di Settings.")
    finally: await state.clear()

# ================= RUN =================
async def main():
    await init_db()
    await bot.set_my_commands([BotCommand(command="start", description="Mulai Bot")])
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot, allowed_updates=["message", "callback_query", "chat_member"])

if __name__ == "__main__":
    asyncio.run(main())
