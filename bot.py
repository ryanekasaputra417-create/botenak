import asyncio, uuid, os, aiosqlite, traceback, random, string
from datetime import datetime
from aiogram import Bot, Dispatcher, F, types
from aiogram.types import (Message, InlineKeyboardMarkup, InlineKeyboardButton, 
    BotCommand, BotCommandScopeDefault, FSInputFile, CallbackQuery)
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
    wait_broadcast = State() # Fitur Broadcast
    set_val = State()

def gen_code():
    # Format start=get_ + 30 Karakter sesuai permintaan
    char = ''.join(random.choices(string.ascii_letters + string.digits, k=30))
    return f"get_{char}"

# ================= DATABASE =================
async def init_db():
    async with aiosqlite.connect("master.db") as db:
        await db.execute("CREATE TABLE IF NOT EXISTS media (code TEXT PRIMARY KEY, fid TEXT, mtype TEXT, title TEXT, bk_id TEXT)")
        await db.execute("CREATE TABLE IF NOT EXISTS users (uid INTEGER PRIMARY KEY)")
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

# ================= ADMIN AREA =================
@dp.message(CommandStart(), F.from_user.id == ADMIN_ID)
async def admin_start(m: Message):
    s = await get_conf()
    # Tombol Log Ringkas, Broadcast, Stats
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="📜 LOG RINGKAS", callback_data="adm_log"), InlineKeyboardButton(text="📢 BROADCAST", callback_data="adm_bc")],
        [InlineKeyboardButton(text="📊 STATISTIK", callback_data="conf_stats"), InlineKeyboardButton(text="⚙️ SETTINGS", callback_data="adm_sett")]
    ])
    await m.answer("Slamat datang Admin. Pilih menu:", reply_markup=kb)

@dp.callback_query(F.data == "adm_sett")
async def open_settings(c: CallbackQuery):
    s = await get_conf()
    kb = InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="Teks Start", callback_data="conf_start_txt"), InlineKeyboardButton(text="Teks FSub", callback_data="conf_fsub_txt")],
        [InlineKeyboardButton(text="Link FSub", callback_data="conf_fsub_link"), InlineKeyboardButton(text="ID CH Post", callback_data="conf_post_ch_id")],
        [InlineKeyboardButton(text="ID CH DB", callback_data="conf_db_ch_id"), InlineKeyboardButton(text="Username FSub", callback_data="conf_fsub_list")],
        [InlineKeyboardButton(text="BATAL", callback_data="conf_close")]
    ])
    await c.message.edit_text(f"SETTINGS\nPost: {s['post_ch_id']}\nDB: {s['db_ch_id']}", reply_markup=kb)

@dp.callback_query(F.data == "adm_log")
async def quick_log(c: CallbackQuery):
    # Log ringkas: Hanya tampilkan status kritikal
    s = await get_conf()
    status_db = "✅ SET" if s['db_ch_id'] else "❌ UNSET"
    status_post = "✅ SET" if s['post_ch_id'] else "❌ UNSET"
    await c.answer(f"DB: {status_db} | Post: {status_post}", show_alert=True)

@dp.callback_query(F.data == "adm_bc")
async def pre_bc(c: CallbackQuery, state: FSMContext):
    await state.set_state(BotState.wait_broadcast)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ BATAL", callback_data="adm_cancel")]])
    await c.message.answer("Kirim pesan broadcast kamu:", reply_markup=kb)

@dp.callback_query(F.data == "adm_cancel")
async def cancel_state(c: CallbackQuery, state: FSMContext):
    await state.clear()
    await c.message.edit_text("Aksi dibatalkan.")
    await c.answer()

@dp.callback_query(F.data.startswith("conf_"))
async def config_cb(c: CallbackQuery, state: FSMContext):
    action = c.data.replace("conf_", "")
    if action == "close": return await c.message.delete()
    if action == "stats":
        async with aiosqlite.connect("master.db") as db:
            async with db.execute("SELECT COUNT(*) FROM users") as c1: u = await c1.fetchone()
            async with db.execute("SELECT COUNT(*) FROM media") as c2: m = await c2.fetchone()
        return await c.answer(f"User: {u[0]} | Media: {m[0]}", show_alert=True)
    
    await state.update_data(field=action)
    await state.set_state(BotState.set_val)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ BATAL", callback_data="adm_cancel")]])
    await c.message.answer(f"Kirim data baru untuk {action}:", reply_markup=kb)

@dp.message(BotState.set_val)
async def save_config(m: Message, state: FSMContext):
    data = await state.get_data()
    async with aiosqlite.connect("master.db") as db:
        await db.execute(f"UPDATE settings SET {data['field']}=? WHERE id=1", (m.text,))
        await db.commit()
    await m.answer(f"✅ Berhasil simpan {data['field']}")
    await state.clear()

# ================= AUTO POST & DONASI =================
@dp.message(F.chat.type == "private", (F.photo | F.video | F.document | F.animation), StateFilter(None))
async def upload_handler(m: Message, state: FSMContext):
    if m.from_user.id != ADMIN_ID:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text="APPROVE", callback_data=f"don_app_{m.from_user.id}_{m.message_id}"),
             InlineKeyboardButton(text="REJECT", callback_data=f"don_rej_{m.from_user.id}")]
        ])
        await bot.forward_message(ADMIN_ID, m.chat.id, m.message_id)
        await bot.send_message(ADMIN_ID, f"Donasi dari {m.from_user.full_name}", reply_markup=kb)
        return await m.answer("Konten sudah dikirim ke admin")
    
    fid = m.photo[-1].file_id if m.photo else (m.video.file_id if m.video else m.document.file_id)
    await state.update_data(fid=fid, mtype="photo" if m.photo else "video")
    await state.set_state(BotState.wait_title)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ BATAL", callback_data="adm_cancel")]])
    await m.reply("Judul konten?", reply_markup=kb)

@dp.callback_query(F.data.startswith("don_"))
async def don_action(c: CallbackQuery, state: FSMContext):
    parts = c.data.split("_")
    action, uid, mid = parts[1], parts[2], (parts[3] if len(parts)>3 else None)
    if action == "app":
        try:
            msg = await bot.forward_message(ADMIN_ID, uid, int(mid))
            fid = msg.photo[-1].file_id if msg.photo else (msg.video.file_id if msg.video else msg.document.file_id)
            await state.update_data(fid=fid, mtype="photo" if msg.photo else "video")
            await state.set_state(BotState.wait_title)
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ BATAL", callback_data="adm_cancel")]])
            await c.message.answer("Donasi diterima. Masukkan judul:", reply_markup=kb)
            await bot.delete_message(ADMIN_ID, msg.message_id)
        except: await c.answer("Gagal mengambil media. User mungkin hapus chat.", show_alert=True)
    else:
        await state.update_data(target_uid=uid)
        await state.set_state(BotState.wait_reject_reason)
        kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ BATAL", callback_data="adm_cancel")]])
        await c.message.answer("Alasan reject?", reply_markup=kb)
    await c.answer()

@dp.message(BotState.wait_title)
async def get_title(m: Message, state: FSMContext):
    await state.update_data(title=m.text)
    await state.set_state(BotState.wait_cover)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ BATAL", callback_data="adm_cancel")]])
    await m.answer("Kirim Foto Cover:", reply_markup=kb)

@dp.message(BotState.wait_cover, F.photo)
async def finalize_post(m: Message, state: FSMContext):
    try:
        data = await state.get_data()
        s = await get_conf()
        code = gen_code() # Output: get_...30karakter
        
        bk_id = ""
        if s['db_ch_id']:
            bk = await bot.send_photo(s['db_ch_id'], m.photo[-1].file_id, caption=f"ID: {code}\nTITLE: {data['title']}")
            bk_id = str(bk.message_id)
        
        async with aiosqlite.connect("master.db") as db:
            await db.execute("INSERT INTO media VALUES (?,?,?,?,?)", (code, data['fid'], data['mtype'], data['title'], bk_id))
            await db.commit()
            
        if s['post_ch_id']:
            link = f"https://t.me/{BOT_USN}?start={code}"
            kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text=s['btn_nonton'], url=link)]])
            await bot.send_photo(s['post_ch_id'], m.photo[-1].file_id, caption=data['title'], reply_markup=kb)
            await m.answer(f"✅ BERHASIL!\nLink: `{link}`")
        else:
            await m.answer("⚠️ Post CH ID belum di-set di settings!")
    except Exception as e:
        err = traceback.format_exc()
        await bot.send_message(ADMIN_ID, f"🚨 SISTEM ERROR\nLokasi: Finalize Post\nDetail: {err}")
    finally: await state.clear()

# ================= MEMBER AREA =================
@dp.message(CommandStart())
async def member_start(m: Message, code_override=None):
    s = await get_conf()
    arg = code_override if code_override else (m.text.split()[1] if len(m.text.split()) > 1 else None)
    
    if not arg:
        kb = InlineKeyboardMarkup(inline_keyboard=[
            [InlineKeyboardButton(text=s['btn_donasi'], callback_data="mem_don"), 
             InlineKeyboardButton(text=s['btn_ask'], callback_data="mem_ask")]
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
        if s['fsub_link']: kb.append([InlineKeyboardButton(text="JOIN DISINI", url=s['fsub_link'])])
        kb.append([InlineKeyboardButton(text="🔄 COBA LAGI", callback_data=f"retry_{arg}")])
        return await m.answer(s['fsub_txt'], reply_markup=InlineKeyboardMarkup(inline_keyboard=kb))

    async with aiosqlite.connect("master.db") as db:
        db.row_factory = aiosqlite.Row
        async with db.execute("SELECT * FROM media WHERE code=?", (arg,)) as cur: row = await cur.fetchone()
    
    if row:
        if row['mtype'] == "photo": await bot.send_photo(m.chat.id, row['fid'], caption=row['title'])
        else: await bot.send_video(m.chat.id, row['fid'], caption=row['title'])

@dp.callback_query(F.data.startswith("retry_"))
async def retry_cb(c: CallbackQuery):
    code = c.data.split("_")[1]
    # Panggil fungsi start lagi dengan link penanda dari DB
    await c.message.delete()
    await member_start(c.message, code_override=code)

@dp.callback_query(F.data == "mem_ask")
async def mem_ask(c: CallbackQuery, state: FSMContext):
    await state.set_state(BotState.wait_ask)
    kb = InlineKeyboardMarkup(inline_keyboard=[[InlineKeyboardButton(text="❌ BATAL", callback_data="adm_cancel")]])
    await c.message.answer("Tulis pesan untuk admin:", reply_markup=kb)

@dp.message(BotState.wait_ask)
async def process_ask(m: Message, state: FSMContext):
    await bot.send_message(ADMIN_ID, f"ASK: {m.from_user.full_name}\n\n{m.text}")
    await m.answer("Terkirim.")
    await state.clear()

@dp.callback_query(F.data == "mem_don")
async def mem_don(c: CallbackQuery):
    await c.message.answer("Kirim media donasi langsung ke sini.")

# ================= RUN =================
async def main():
    await init_db()
    await bot.delete_webhook(drop_pending_updates=True)
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())

