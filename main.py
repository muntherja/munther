import logging
from telegram import InlineKeyboardButton, InlineKeyboardMarkup, Update, BotCommand
from telegram.ext import Application, CommandHandler, CallbackQueryHandler, MessageHandler, ContextTypes, filters, JobQueue
from sqlalchemy import create_engine, Column, Integer, String, Text, ForeignKey, DateTime
from sqlalchemy.orm import declarative_base, sessionmaker, relationship
from sqlalchemy.exc import IntegrityError
import datetime
from datetime import timedelta, timezone
import os
import shutil

# إعداد توقيت اليمن (GMT+3)
YEMEN_TZ = timezone(timedelta(hours=3))

def get_yemen_time():
    return datetime.datetime.now(YEMEN_TZ)

# ================== إعدادات ==================

BOT_TOKEN = "8334633730:AAHpY3dNhAg2UbRoo9znwJxCnv5RJnnhPHE"
ADMIN_IDS = {833001594}  # معرفات الإدمن
SUPER_ADMIN_ID = 833001594  # المشرف الأساسي (تم تصحيح الآيدي)
SUPPORT_USER = "@Ow1_O"  # يوزر التواصل مع المشرف
BACKUP_DIR = "./backups" # دليل حفظ النسخ الاحتياطية

logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

Base = declarative_base()
engine = create_engine("sqlite:///college_v3.db", connect_args={"check_same_thread": False})
Session = sessionmaker(bind=engine)

STATE = {}  # لتتبع خطوات الإدمن

# ================== الجداول ==================

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False)
    username = Column(String)
    first_name = Column(String)
    joined_at = Column(DateTime, default=get_yemen_time)
    status = Column(String, default='active') # 'active', 'blocked', 'restricted'
    restricted_until = Column(DateTime, nullable=True)
    last_seen = Column(DateTime, default=get_yemen_time)

class BlockedUser(Base):
    __tablename__ = "blocked_users"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False)
    blocked_by = Column(Integer, nullable=False)
    blocked_at = Column(DateTime, default=get_yemen_time)

class RestrictedUser(Base):
    __tablename__ = "restricted_users"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False)
    restricted_by = Column(Integer, nullable=False)
    restricted_at = Column(DateTime, default=get_yemen_time)
    restricted_until = Column(DateTime, nullable=False)

class Level(Base):
    __tablename__ = "levels"
    id = Column(Integer, primary_key=True)
    name = Column(String, unique=True, nullable=False)
    subjects = relationship("Subject", back_populates="level", cascade="all, delete-orphan")

class Subject(Base):
    __tablename__ = "subjects"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    level_id = Column(Integer, ForeignKey("levels.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=get_yemen_time)
    level = relationship("Level", back_populates="subjects")
    sections = relationship("Section", back_populates="subject", cascade="all, delete-orphan")

class Section(Base):
    __tablename__ = "sections"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    subject_id = Column(Integer, ForeignKey("subjects.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=get_yemen_time)
    subject = relationship("Subject", back_populates="sections")
    items = relationship("Item", back_populates="section", cascade="all, delete-orphan")

class Item(Base):
    __tablename__ = "items"
    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    section_id = Column(Integer, ForeignKey("sections.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=get_yemen_time)
    section = relationship("Section", back_populates="items")
    contents = relationship("Content", back_populates="item", cascade="all, delete-orphan")

class Content(Base):
    __tablename__ = "contents"
    id = Column(Integer, primary_key=True)
    type = Column(String, nullable=False)  # text / photo / document / video
    value = Column(Text, nullable=False)
    item_id = Column(Integer, ForeignKey("items.id", ondelete="CASCADE"), nullable=False)
    created_at = Column(DateTime, default=get_yemen_time)
    is_assignment = Column(Integer, default=0) # 0: No, 1: Yes
    deadline = Column(DateTime, nullable=True)
    reminder_sent = Column(Integer, default=0) # 0: No, 1: Yes
    item = relationship("Item", back_populates="contents")

class Admin(Base):
    __tablename__ = "admins"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, unique=True, nullable=False)
    permissions = Column(String, default="all") # "all" or comma separated: "add", "users", "broadcast"

class BroadcastView(Base):
    __tablename__ = "broadcast_views"
    id = Column(Integer, primary_key=True)
    broadcast_id = Column(String, nullable=False)
    user_id = Column(Integer, nullable=False)
    viewed_at = Column(DateTime, default=get_yemen_time)

class BroadcastMessage(Base):
    __tablename__ = "broadcast_messages"
    id = Column(Integer, primary_key=True)
    broadcast_id = Column(String, nullable=False)
    user_id = Column(Integer, nullable=False)
    message_id = Column(Integer, nullable=False)
    created_at = Column(DateTime, default=get_yemen_time)

class DownloadTrack(Base):
    __tablename__ = "download_tracks"
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    content_id = Column(Integer, ForeignKey("contents.id", ondelete="CASCADE"), nullable=False)
    action_name = Column(String) # اسم العملية (مثلاً اسم العنصر)
    downloaded_at = Column(DateTime, default=get_yemen_time)

Base.metadata.create_all(engine)

# تحديث قاعدة البيانات لإضافة الأعمدة الجديدة إذا لم تكن موجودة
def migrate_db():
    import sqlite3
    conn = sqlite3.connect("college_v3.db")
    cursor = conn.cursor()
    try:
        cursor.execute("ALTER TABLE download_tracks ADD COLUMN action_name TEXT")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN status TEXT DEFAULT 'active'")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN restricted_until DATETIME")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN last_seen DATETIME")
    except sqlite3.OperationalError: pass
    
    # إضافة أعمدة تاريخ الإنشاء للجداول الأساسية
    for table in ["subjects", "sections", "items", "contents"]:
        try:
            cursor.execute(f"ALTER TABLE {table} ADD COLUMN created_at DATETIME")
        except sqlite3.OperationalError: pass
    
    try:
        cursor.execute("ALTER TABLE admins ADD COLUMN permissions TEXT DEFAULT 'all'")
    except sqlite3.OperationalError: pass

    try:
        cursor.execute("ALTER TABLE contents ADD COLUMN is_assignment INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE contents ADD COLUMN deadline DATETIME")
    except sqlite3.OperationalError: pass
    try:
        cursor.execute("ALTER TABLE contents ADD COLUMN reminder_sent INTEGER DEFAULT 0")
    except sqlite3.OperationalError: pass

    try:
        cursor.execute("ALTER TABLE download_tracks ADD COLUMN viewed_at DATETIME")
    except sqlite3.OperationalError: pass
        
    conn.close()

migrate_db()

# ================== وظائف مساعدة ==================

def is_admin(uid):
    if uid in ADMIN_IDS or uid == SUPER_ADMIN_ID: return True
    s = Session()
    try:
        admin = s.query(Admin).filter_by(user_id=uid).first()
        return admin is not None
    except: return False
    finally: s.close()

def has_permission(uid, permission):
    """
    التحقق من صلاحية معينة للمشرف.
    الصلاحيات: 'add', 'users', 'broadcast', 'all'
    """
    if uid in ADMIN_IDS or uid == SUPER_ADMIN_ID: return True
    s = Session()
    try:
        admin = s.query(Admin).filter_by(user_id=uid).first()
        if not admin: return False
        if admin.permissions == "all": return True
        return permission in admin.permissions.split(",")
    except: return False
    finally: s.close()

async def notify_super_admin(context: ContextTypes.DEFAULT_TYPE, admin_id: int, action: str):
    """إرسال إشعار للمشرف الأساسي عند قيام مشرف آخر بإجراء"""
    if admin_id == SUPER_ADMIN_ID:
        return
    
    try:
        message = (
            f"⚠️ **تنبيه إداري جديد**\n\n"
            f"👤 **المشرف:** `{admin_id}`\n"
            f"📝 **الإجراء:** {action}\n"
            f"⏰ **الوقت:** {get_yemen_time().strftime('%Y-%m-%d %H:%M:%S')}"
        )
        await context.bot.send_message(chat_id=SUPER_ADMIN_ID, text=message, parse_mode='Markdown')
    except Exception as e:
        logger.error(f"Error notifying super admin: {e}")

async def notify_new_content_batch(context: ContextTypes.DEFAULT_TYPE, content_ids: list):
    """إرسال إشعار واحد لجميع المستخدمين عند إضافة مجموعة ملفات جديدة"""
    if not content_ids: return
    s = Session()
    try:
        # جلب أول محتوى للحصول على معلومات العنصر والمستوى
        first_content = s.query(Content).filter(Content.id == content_ids[0]).first()
        if not first_content: return
        
        item = first_content.item
        sec = item.section
        sub = sec.subject
        lvl = sub.level
        
        count = len(content_ids)
        text = (
            f"🆕 **تم إضافة تحديث جديد!**\n\n"
            f"📚 **المستوى:** {lvl.name}\n"
            f"📖 **المادة:** {sub.name}\n"
            f"📁 **القسم:** {sec.name}\n"
            f"🔹 **العنصر:** {item.name}\n"
            f"📎 **عدد الملفات المضافة:** {count}\n"
        )
        
        # إذا كان أي من الملفات تكليفاً، نظهر موعد التسليم
        is_assign = any(c.is_assignment for c in s.query(Content).filter(Content.id.in_(content_ids)).all())
        if is_assign:
            deadline = first_content.deadline
            if deadline:
                text += f"📅 **موعد التسليم:** {deadline.strftime('%Y-%m-%d %I:%M %p')}\n"
                text += "⚠️ هذا التحديث يتضمن تكليفاً/واجباً.\n"
        
        text += "\nاستخدم البوت الآن للمشاهدة أو التحميل."
        
        kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔍 عرض العنصر", callback_data=f"item:{item.id}")]])
        
        users = s.query(User).filter_by(status='active').all()
        for u in users:
            try:
                await context.bot.send_message(chat_id=u.user_id, text=text, reply_markup=kb, parse_mode='Markdown')
            except Exception: continue
    except Exception as e:
        logger.error(f"Error in notify_new_content_batch: {e}")
    finally:
        s.close()

async def check_deadlines(context: ContextTypes.DEFAULT_TYPE):
    """فحص المواعيد النهائية وإرسال تذكيرات قبل 10 ساعات"""
    s = Session()
    try:
        now = get_yemen_time()
        # جلب التكاليف التي لم يرسل لها تذكير بعد
        assignments = s.query(Content).filter(Content.is_assignment == 1, Content.reminder_sent == 0).all()
        
        for assign in assignments:
            if not assign.deadline: continue
            
            # حساب الوقت المتبقي
            # التأكد من أن وقت التسليم يحتوي على معلومات المنطقة الزمنية
            deadline = assign.deadline
            if deadline.tzinfo is None:
                deadline = deadline.replace(tzinfo=YEMEN_TZ)
                
            time_diff = deadline - now
            
            # إذا كان الوقت المتبقي أقل من أو يساوي 10 ساعات
            if time_diff <= timedelta(hours=10) and time_diff > timedelta(0):
                item = assign.item
                text = (
                    f"⏰ **تذكير بموعد تسليم!**\n\n"
                    f"⚠️ يتبقى أقل من 10 ساعات على موعد تسليم التكليف:\n"
                    f"🔹 **العنصر:** {item.name}\n"
                    f"📅 **موعد التسليم:** {deadline.strftime('%Y-%m-%d %I:%M %p')}\n\n"
                    f"يرجى سرعة الإنجاز والتسليم."
                )
                kb = InlineKeyboardMarkup([[InlineKeyboardButton("🔍 عرض التفاصيل", callback_data=f"item:{item.id}")]])
                
                users = s.query(User).filter_by(status='active').all()
                for u in users:
                    try:
                        await context.bot.send_message(chat_id=u.user_id, text=text, reply_markup=kb, parse_mode='Markdown')
                    except Exception: continue
                
                assign.reminder_sent = 1
                s.commit()
    except Exception as e:
        logger.error(f"Error in check_deadlines: {e}")
    finally:
        s.close()

def get_admin_keyboard(uid):
    kb = []
    # صلاحية الإضافة والتعديل
    if has_permission(uid, "add"):
        kb.append([InlineKeyboardButton("➕ إضافة مستوى جديد", callback_data="add_level")])
        kb.append([InlineKeyboardButton("🛠 إدارة الهيكل (تعديل/حذف)", callback_data="manage_v4")])
    
    # صلاحية الإذاعة
    if has_permission(uid, "broadcast"):
        kb.append([InlineKeyboardButton("📢 إذاعة رسالة", callback_data="broadcast"), InlineKeyboardButton("🗑 حذف إذاعة", callback_data="del_br_list")])
    
    kb.append([InlineKeyboardButton("📊 الإحصائيات", callback_data="stats")])
    
    # صلاحية إدارة المستخدمين والمشرفين
    if has_permission(uid, "users"):
        kb.append([InlineKeyboardButton("👮 إدارة المشرفين", callback_data="manage_admins")])
        kb.append([InlineKeyboardButton("🚫 إدارة المستخدمين", callback_data="manage_users")])
    
    # النسخة الاحتياطية للمشرف الأساسي أو من لديه صلاحية إدارة المستخدمين
    if uid == SUPER_ADMIN_ID or has_permission(uid, "users"):
        kb.append([InlineKeyboardButton("📦 نسخة احتياطية (إرسال للمشرف)", callback_data="send_backup")])
    
    kb.append([InlineKeyboardButton("🏠 القائمة الرئيسية", callback_data="back_start")])
    return InlineKeyboardMarkup(kb)

def get_permissions_keyboard(target_user_id, current_perms):
    """لوحة مفاتيح للتحكم في الصلاحيات بنظام التبديل (Toggle)"""
    perms_list = current_perms.split(",") if current_perms != "all" else ["add", "users", "broadcast"]
    if current_perms == "all":
        perms_list = ["add", "users", "broadcast"]
    
    def get_status(p): return "✅" if p in perms_list else "❌"
    
    kb = [
        [InlineKeyboardButton(f"{get_status('add')} إضافة وتعديل المحتوى", callback_data=f"tgl_perm:{target_user_id}:add")],
        [InlineKeyboardButton(f"{get_status('users')} إدارة المستخدمين والمشرفين", callback_data=f"tgl_perm:{target_user_id}:users")],
        [InlineKeyboardButton(f"{get_status('broadcast')} إرسال الإذاعة", callback_data=f"tgl_perm:{target_user_id}:broadcast")],
        [InlineKeyboardButton("🏁 إنهاء التعديل", callback_data="manage_admins")]
    ]
    return InlineKeyboardMarkup(kb)

def register_user(u):
    s = Session()
    try:
        user = s.query(User).filter_by(user_id=u.id).first()
        if not user:
            new_user = User(user_id=u.id, username=u.username, first_name=u.first_name, last_seen=get_yemen_time())
            s.add(new_user)
            s.commit()
        else:
            user.last_seen = get_yemen_time()
            s.commit()
    except Exception as e:
        logger.error(f"Error registering user: {e}")
    finally:
        s.close()

def update_user_activity(user_id):
    s = Session()
    try:
        user = s.query(User).filter_by(user_id=user_id).first()
        if user:
            user.last_seen = get_yemen_time()
            s.commit()
    except Exception as e:
        logger.error(f"Error updating activity: {e}")
    finally:
        s.close()

async def backup_database(context: ContextTypes.DEFAULT_TYPE):
    os.makedirs(BACKUP_DIR, exist_ok=True)
    timestamp = get_yemen_time().strftime("%Y%m%d_%H%M%S")
    backup_filename = os.path.join(BACKUP_DIR, f"college_v3_backup_{timestamp}.db")
    try:
        shutil.copy2("college_v3.db", backup_filename)
        logger.info(f"Database backup created: {backup_filename}")
        for admin_id in ADMIN_IDS:
            await context.bot.send_message(chat_id=admin_id, text=f"✅ تم إنشاء نسخة احتياطية لقاعدة البيانات بنجاح: {os.path.basename(backup_filename)}")
    except Exception as e:
        logger.error(f"Error creating database backup: {e}")
        for admin_id in ADMIN_IDS:
            await context.bot.send_message(chat_id=admin_id, text=f"❌ فشل إنشاء نسخة احتياطية لقاعدة البيانات: {e}")

# ================== أوامر الطلاب ==================

async def start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    user = update.effective_user
    register_user(user)
    update_user_activity(user.id)

    s = Session()
    try:
        db_user = s.query(User).filter_by(user_id=user.id).first()
        if db_user and db_user.status == 'blocked':
            await update.message.reply_text("🚫 تم حظر حسابك من استخدام البوت. لا يمكنك الوصول إلى أي ميزات.")
            return
        if db_user and db_user.status == 'restricted':
            await update.message.reply_text(f"⏱ تم تقييد حسابك مؤقتاً من استخدام البوت حتى {db_user.restricted_until.strftime('%Y-%m-%d %H:%M:%S')}. لا يمكنك الوصول إلى أي ميزات حالياً.")
            return
    finally:
        s.close()

    
    s = Session()
    try:
        levels = s.query(Level).all()
        message_text = "📚 أهلاً بك في البوت التعليمي.\n\nيمكنك التنقل بين المستويات والمواد من الأزرار أدناه."
        
        kb = [[InlineKeyboardButton(l.name, callback_data=f"lvl:{l.id}")] for l in levels]
        kb.append([InlineKeyboardButton("🔍 بحث شامل", callback_data="search_start")])
        kb.append([InlineKeyboardButton("👨‍💻 تواصل مع المشرف", url=f"https://t.me/{SUPPORT_USER[1:]}")])
        
        if is_admin(user.id):
            kb.append([InlineKeyboardButton("🛠 لوحة الإدارة", callback_data="back_admin")])

        reply_markup = InlineKeyboardMarkup(kb)
        if update.callback_query:
            await update.callback_query.edit_message_text(message_text, reply_markup=reply_markup)
        else:
            await update.message.reply_text(message_text, reply_markup=reply_markup)
    except Exception as e: logger.error(f"Error in start: {e}")
    finally: s.close()

# ================== لوحة الإدارة ==================

async def admin(update: Update, context: ContextTypes.DEFAULT_TYPE):
    # Check for expired restrictions
    s = Session()
    try:
        now = get_yemen_time()
        expired_restrictions = s.query(RestrictedUser).filter(RestrictedUser.restricted_until <= now).all()
        for r_user in expired_restrictions:
            user = s.query(User).filter_by(user_id=r_user.user_id).first()
            if user and user.status == 'restricted':
                user.status = 'active'
                user.restricted_until = None
                s.delete(r_user)
                await context.bot.send_message(chat_id=user.user_id, text="✅ تم رفع التقييد عن حسابك. يمكنك الآن استخدام البوت بشكل طبيعي.")
                await notify_super_admin(context, SUPER_ADMIN_ID, f"تم رفع التقييد تلقائياً عن المستخدم {user.user_id}")
        s.commit()
    except Exception as e:
        logger.error(f"Error checking for expired restrictions: {e}")
        s.rollback()
    finally:
        s.close()


    user_id = update.effective_user.id
    if not is_admin(user_id):
        msg = "⛔ ليس لديك صلاحية الوصول."
        if update.callback_query: await update.callback_query.edit_message_text(msg)
        else: await update.message.reply_text(msg)
        return
    
    msg = "🛠 لوحة الإدارة المتطورة\nاختر المهمة المطلوبة:"
    kb = get_admin_keyboard(user_id)
    if update.callback_query:
        await update.callback_query.edit_message_text(msg, reply_markup=kb)
    else:
        await update.message.reply_text(msg, reply_markup=kb)

# ================== التعامل مع الأزرار ==================

async def callbacks(update: Update, context: ContextTypes.DEFAULT_TYPE):
    q = update.callback_query
    uid = q.from_user.id
    data = q.data
    update_user_activity(uid)
    
    # التحقق من حالة المستخدم
    s = Session()
    try:
        db_user = s.query(User).filter_by(user_id=uid).first()
        if db_user and db_user.status == 'blocked':
            await q.answer("🚫 أنت محظور من استخدام البوت.", show_alert=True)
            return
        if db_user and db_user.status == 'restricted':
            await q.answer(f"⏱ حسابك مقيد حتى {db_user.restricted_until.strftime('%Y-%m-%d %H:%M:%S')}.", show_alert=True)
            return
    finally:
        s.close()

    # التحقق من الصلاحيات للعمليات الإدارية
    admin_actions = {
        "add": ["add_level", "manage_v4", "edit_lvl", "edit_sub", "edit_sec", "edit_item", "edit_content", "do_del_lvl", "do_del_sub", "do_del_sec", "do_del_itm", "do_del_cnt", "m_lvl", "m_sub", "m_sec", "m_item", "m_item", "is_assign"],
        "broadcast": ["broadcast", "del_br_list", "do_del_br"],
        "users": ["manage_admins", "manage_users", "block_user_start", "unblock_user_start", "restrict_user_start", "add_admin_start", "del_admin_list", "do_del_admin", "perm:"]
    }

    for perm, actions in admin_actions.items():
        for action in actions:
            if data.startswith(action) and not has_permission(uid, perm):
                await q.answer("⛔ ليس لديك صلاحية للقيام بهذا الإجراء.", show_alert=True)
                return

    s = Session()
    
    try:
        # ---------- طالب ----------
        if data.startswith("lvl:"):
            lvl_id = int(data[4:])
            subs = s.query(Subject).filter_by(level_id=lvl_id).all()
            kb = [[InlineKeyboardButton(x.name, callback_data=f"sub:{x.id}")] for x in subs]
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_start")])
            await q.edit_message_text("اختر المادة:", reply_markup=InlineKeyboardMarkup(kb))

        elif data == "search_start":
            STATE[uid] = {"step": "searching"}
            await q.edit_message_text("🔍 أرسل كلمة البحث (اسم المادة، القسم، أو المحتوى):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="back_start")]]))

        elif data.startswith("sub:"):
            sub_id = int(data[4:])
            secs = s.query(Section).filter_by(subject_id=sub_id).all()
            kb = [[InlineKeyboardButton(x.name, callback_data=f"sec:{x.id}")] for x in secs]
            sub = s.query(Subject).filter_by(id=sub_id).first()

            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"lvl:{sub.level_id}")])
            await q.edit_message_text(f"مادة {sub.name}\nاختر القسم:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("sec:"):
            sec_id = int(data[4:])
            items = s.query(Item).filter_by(section_id=sec_id).all()
            kb = [[InlineKeyboardButton(x.name, callback_data=f"item:{x.id}")] for x in items]
            sec = s.query(Section).filter_by(id=sec_id).first()

            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"sub:{sec.subject_id}")])
            await q.edit_message_text(f"قسم {sec.name}\nاختر العنصر:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("item:"):
            item_id = int(data[5:])
            contents = s.query(Content).filter_by(item_id=item_id).all()
            item = s.query(Item).filter_by(id=item_id).first()
            if not contents:
                await q.message.reply_text("⚠️ لا يوجد محتوى مضاف لهذا العنصر حالياً.")
            else:
                # جلب المشاهدات
                for c in contents:
                    try:
                        # تسجيل المشاهدة
                        track = DownloadTrack(user_id=uid, content_id=c.id, action_name=item.name)
                        s.add(track)
                        s.commit()

                        # جلب عدد المشاهدات وقائمة المشاهدين (تظهر للمشرف الأساسي فقط)
                        v_text = ""
                        if uid == SUPER_ADMIN_ID:
                            views = s.query(DownloadTrack).filter_by(content_id=c.id).all()
                            v_count = len(views)
                            v_users = []
                            seen_uids = set()
                            for v in views:
                                if v.user_id not in seen_uids:
                                    u = s.query(User).filter_by(user_id=v.user_id).first()
                                    if u: v_users.append(u.first_name)
                                    seen_uids.add(v.user_id)
                            v_text = f"\n\n👁 المشاهدات ({v_count}): " + (", ".join(v_users[:5]) + ("..." if len(v_users) > 5 else ""))

                        if c.type == "text": await q.message.reply_text(c.value + v_text)
                        elif c.type == "photo": await q.message.reply_photo(c.value, caption=v_text)
                        elif c.type == "video": await q.message.reply_video(c.value, caption=v_text)
                        elif c.type == "document": await q.message.reply_document(c.value, caption=v_text)
                        
                    except Exception as e: logger.error(f"Error sending content: {e}")
            kb = [[InlineKeyboardButton("🔙 رجوع للقسم", callback_data=f"sec:{item.section_id}")]]
            await q.message.reply_text(f"انتهى عرض: {item.name}", reply_markup=InlineKeyboardMarkup(kb))

        # ---------- إدارة الهيكل المتطورة (V4) - النظام الهرمي الجديد ----------
        elif data == "manage_v4":
            lvls = s.query(Level).all()
            kb = [[InlineKeyboardButton(l.name, callback_data=f"adm_lvl:{l.id}")] for l in lvls]
            kb.append([InlineKeyboardButton("🔙 رجوع للوحة الإدارة", callback_data="back_admin")])
            await q.edit_message_text("🛠 إدارة الهيكل الهرمي:\nاختر مستوى للبدء بالتعديل أو الحذف أو الإضافة:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("adm_lvl:"):
            l_id = int(data[8:])
            lvl = s.query(Level).filter_by(id=l_id).first()
            subs = s.query(Subject).filter_by(level_id=l_id).all()
            kb = [[InlineKeyboardButton(f"📖 {x.name}", callback_data=f"adm_sub:{x.id}")] for x in subs]
            kb.append([InlineKeyboardButton("➕ إضافة مادة جديدة", callback_data=f"m_lvl:{l_id}")])
            kb.append([InlineKeyboardButton("✏️ تعديل اسم المستوى", callback_data=f"edit_lvl:{l_id}")])
            kb.append([InlineKeyboardButton("🗑 حذف هذا المستوى", callback_data=f"do_del_lvl:{l_id}")])
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="manage_v4")])
            await q.edit_message_text(f"📂 المستوى: {lvl.name}\nاختر مادة أو إجراء:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("adm_sub:"):
            s_id = int(data[8:])
            sub = s.query(Subject).filter_by(id=s_id).first()
            secs = s.query(Section).filter_by(subject_id=s_id).all()
            kb = [[InlineKeyboardButton(f"📁 {x.name}", callback_data=f"adm_sec:{x.id}")] for x in secs]
            kb.append([InlineKeyboardButton("➕ إضافة قسم جديد", callback_data=f"m_sub:{s_id}")])
            kb.append([InlineKeyboardButton("✏️ تعديل اسم المادة", callback_data=f"edit_sub:{s_id}")])
            kb.append([InlineKeyboardButton("🗑 حذف هذه المادة", callback_data=f"do_del_sub:{s_id}")])
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"adm_lvl:{sub.level_id}")])
            await q.edit_message_text(f"📖 المادة: {sub.name}\n(المستوى: {sub.level.name})\nاختر قسماً أو إجراء:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("adm_sec:"):
            sec_id = int(data[8:])
            sec = s.query(Section).filter_by(id=sec_id).first()
            items = s.query(Item).filter_by(section_id=sec_id).all()
            kb = [[InlineKeyboardButton(f"🔹 {x.name}", callback_data=f"adm_itm:{x.id}")] for x in items]
            kb.append([InlineKeyboardButton("➕ إضافة عنصر جديد", callback_data=f"m_sec:{sec_id}")])
            kb.append([InlineKeyboardButton("✏️ تعديل اسم القسم", callback_data=f"edit_sec:{sec_id}")])
            kb.append([InlineKeyboardButton("🗑 حذف هذا القسم", callback_data=f"do_del_sec:{sec_id}")])
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"adm_sub:{sec.subject_id}")])
            await q.edit_message_text(f"📁 القسم: {sec.name}\n(المادة: {sec.subject.name})\nاختر عنصراً أو إجراء:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("adm_itm:"):
            i_id = int(data[8:])
            item = s.query(Item).filter_by(id=i_id).first()
            kb = [
                [InlineKeyboardButton("➕ إضافة محتوى جديد", callback_data=f"m_item:{i_id}")],
                [InlineKeyboardButton("📋 إدارة المحتويات الحالية", callback_data=f"manage_cnts:{i_id}")],
                [InlineKeyboardButton("✏️ تعديل اسم العنصر", callback_data=f"edit_item:{i_id}")],
                [InlineKeyboardButton("🗑 حذف هذا العنصر", callback_data=f"do_del_item:{i_id}")],
                [InlineKeyboardButton("🔙 رجوع", callback_data=f"adm_sec:{item.section_id}")]
            ]
            await q.edit_message_text(f"🔹 العنصر: {item.name}\n(القسم: {item.section.name} - المادة: {item.section.subject.name})\nاختر إجراءً:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("manage_cnts:"):
            i_id = int(data[12:])
            item = s.query(Item).filter_by(id=i_id).first()
            contents = s.query(Content).filter_by(item_id=i_id).all()
            kb = []
            for c in contents:
                preview = c.value[:15] + "..." if len(c.value) > 15 else c.value
                kb.append([InlineKeyboardButton(f"✏️ {c.type}: {preview}", callback_data=f"edit_content:{c.id}")])
                kb.append([InlineKeyboardButton(f"🗑 حذف هذا المحتوى", callback_data=f"do_del_cnt:{c.id}")])
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data=f"adm_itm:{i_id}")])
            await q.edit_message_text(f"📋 محتويات العنصر: {item.name}\nاختر محتوى لتعديله أو حذفه:", reply_markup=InlineKeyboardMarkup(kb))

        # ---------- إدمن - الحذف المؤكد ----------
        elif data.startswith("do_del_lvl:"):
            lvl = s.query(Level).filter_by(id=int(data[11:])).first()
            if lvl:
                name = lvl.name
                s.delete(lvl)
                s.commit()
                await notify_super_admin(context, uid, f"حذف المستوى: {name}")
                await q.message.reply_text(f"✅ تم حذف المستوى '{name}' بنجاح.")
            await admin(update, context)

        elif data.startswith("do_del_sub:"):
            sub = s.query(Subject).filter_by(id=int(data[11:])).first()
            if sub:
                name = sub.name
                s.delete(sub)
                s.commit()
                await notify_super_admin(context, uid, f"حذف المادة: {name}")
                await q.message.reply_text(f"✅ تم حذف المادة '{name}' بنجاح.")
            await admin(update, context)

        elif data.startswith("do_del_sec:"):
            sec = s.query(Section).filter_by(id=int(data[11:])).first()
            if sec:
                name = sec.name
                s.delete(sec)
                s.commit()
                await notify_super_admin(context, uid, f"حذف القسم: {name}")
                await q.message.reply_text(f"✅ تم حذف القسم '{name}' بنجاح.")
            await admin(update, context)

        elif data.startswith("do_del_item:"):
            item = s.query(Item).filter_by(id=int(data[12:])).first()
            if item:
                name = item.name
                s.delete(item)
                s.commit()
                await notify_super_admin(context, uid, f"حذف العنصر: {name}")
                await q.message.reply_text(f"✅ تم حذف العنصر '{name}' بنجاح.")
            await admin(update, context)

        elif data.startswith("do_del_cnt:"):
            cnt = s.query(Content).filter_by(id=int(data[11:])).first()
            if cnt:
                item_id = cnt.item_id
                s.delete(cnt)
                s.commit()
                await notify_super_admin(context, uid, f"حذف محتوى من العنصر آيدي: {item_id}")
                await q.message.reply_text(f"✅ تم حذف المحتوى بنجاح.")
                # العودة لقائمة المحتويات لنفس العنصر
                data = f"manage_cnts:{item_id}"
                return await callbacks(update, context)
            await admin(update, context)

        # ---------- إدمن - الإضافة ----------
        elif data == "add_level":
            STATE[uid] = {"step": "level"}
            await q.message.reply_text("✏️ أرسل اسم المستوى الجديد:")

        elif data.startswith("m_lvl:"):
            STATE[uid] = {"level": int(data[6:]), "step": "subject"}
            await q.message.reply_text("✏️ أرسل اسم المادة الجديدة:")

        elif data.startswith("m_sub:"):
            STATE[uid] = {"subject": int(data[6:]), "step": "section"}
            await q.message.reply_text("✏️ أرسل اسم القسم الجديد:")

        elif data.startswith("m_sec:"):
            STATE[uid] = {"section": int(data[6:]), "step": "item"}
            await q.message.reply_text("✏️ أرسل اسم العنصر الجديد:")

        elif data.startswith("m_item:"):
            STATE[uid] = {"item": int(data[7:]), "step": "content"}
            await q.message.reply_text("📎 أرسل المحتوى (نص، صورة، فيديو، أو ملف):")

        # ---------- إدمن - التعديل ----------
        elif data.startswith("edit_lvl:"):
            lvl_id = int(data[9:])
            STATE[uid] = {"step": "edit_level_name", "id": lvl_id}
            await q.message.reply_text("✏️ أرسل الاسم الجديد للمستوى:")

        elif data.startswith("edit_sub:"):
            sub_id = int(data[9:])
            STATE[uid] = {"step": "edit_subject_name", "id": sub_id}
            await q.message.reply_text("✏️ أرسل الاسم الجديد للمادة:")

        elif data.startswith("edit_sec:"):
            sec_id = int(data[9:])
            STATE[uid] = {"step": "edit_section_name", "id": sec_id}
            await q.message.reply_text("✏️ أرسل الاسم الجديد للقسم:")

        elif data.startswith("edit_item:"):
            item_id = int(data[10:])
            STATE[uid] = {"step": "edit_item_name", "id": item_id}
            await q.message.reply_text("✏️ أرسل الاسم الجديد للعنصر:")

        elif data.startswith("edit_content:"):
            content_id = int(data[13:])
            STATE[uid] = {"step": "edit_content_value", "id": content_id}
            await q.message.reply_text("📎 أرسل المحتوى الجديد (نص، صورة، فيديو، أو ملف):")

        # ---------- إدمن - إحصائيات ----------
        elif data == "stats":
            kb = [
                [InlineKeyboardButton("👥 إحصائيات الطلاب المسجلين", callback_data="stats_users")],
                [InlineKeyboardButton("🌐 من يستخدم البوت الآن", callback_data="stats_active")],
                [InlineKeyboardButton("📥 آخر 5 عمليات تحميل", callback_data="stats_recent")],
                [InlineKeyboardButton("📊 تفاصيل العمليات والإجمالي", callback_data="stats_details")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_admin")]
            ]
            await q.edit_message_text("📊 قائمة الإحصائيات:\nاختر نوع الإحصائيات الذي تريد عرضه:", reply_markup=InlineKeyboardMarkup(kb))

        elif data == "stats_users":
            try:
                users = s.query(User).all()
                u_count = len(users)
                text = f"👥 إحصائيات الطلاب:\n\nعدد المسجلين: {u_count}\n\n"
                if users:
                    for u in users:
                        safe_name = str(u.first_name).replace("_", " ").replace("*", " ").replace("`", " ")
                        text += f"👤 {safe_name} | ID: {u.user_id}\n"
                else: text += "⚠️ لا يوجد مسجلين."
                if len(text) > 4000: text = text[:3900] + "..."
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="stats")]]
                await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
            except Exception as e: await q.message.reply_text(f"❌ خطأ: {e}")

        elif data == "stats_active":
            try:
                now = get_yemen_time()
                five_mins_ago = now - timedelta(minutes=5)
                active_users = s.query(User).filter(User.last_seen >= five_mins_ago).all()
                count = len(active_users)
                text = f"🌐 من يستخدم البوت الآن (آخر 5 دقائق):\n\nعدد المستخدمين النشطين: {count}\n\n"
                if active_users:
                    for u in active_users:
                        safe_name = str(u.first_name).replace("_", " ").replace("*", " ").replace("`", " ")
                        text += f"👤 {safe_name} | ID: {u.user_id}\n"
                else:
                    text += "⚠️ لا يوجد مستخدمين نشطين حالياً."
                
                if len(text) > 4000: text = text[:3900] + "..."
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="stats")]]
                await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
            except Exception as e:
                logger.error(f"Error in stats_active: {e}")
                await q.message.reply_text(f"❌ خطأ: {e}")

        elif data == "stats_recent":
            try:
                # جلب آخر العمليات مع منع التكرار لنفس المستخدم ونفس المحتوى
                # سنقوم بجلب عدد أكبر ثم تصفيتهم برمجياً لضمان الدقة
                recent_all = s.query(DownloadTrack).order_by(DownloadTrack.downloaded_at.desc()).limit(200).all()
                
                unique_recent = []
                seen_pairs = set()
                
                for rd in recent_all:
                    # المعرف الفريد هو (المستخدم + اسم العملية/العنصر)
                    # إذا أردت منع تكرار نفس الشخص تماماً حتى لو حمل أشياء مختلفة، اجعل المعرف rd.user_id فقط
                    pair = (rd.user_id, rd.action_name) 
                    if pair not in seen_pairs:
                        seen_pairs.add(pair)
                        unique_recent.append(rd)
                    if len(unique_recent) >= 10: # نكتفي بآخر 10 عمليات فريدة
                        break
                
                text = "📥 آخر 10 عمليات تحميل فريدة (توقيت اليمن):\n\n"
                if unique_recent:
                    for r in unique_recent:
                        user = s.query(User).filter_by(user_id=r.user_id).first()
                        u_name = user.first_name if user else "غير معروف"
                        
                        # جلب تفاصيل المحتوى والمسار الكامل
                        content = s.query(Content).filter_by(id=r.content_id).first()
                        path_info = "محتوى محذوف"
                        if content and content.item:
                            item = content.item
                            sec = item.section
                            sub = sec.subject if sec else None
                            lvl = sub.level if sub else None
                            path_info = f"{lvl.name if lvl else '؟'} ➔ {sub.name if sub else '؟'} ➔ {sec.name if sec else '؟'} ➔ {item.name}"
                        else:
                            path_info = r.action_name # استخدام الاسم المسجل إذا حذف المحتوى
                        
                        # تحويل الوقت لتوقيت اليمن إذا كان مخزناً كـ UTC (اختياري حسب طريقة التخزين)
                        # هنا سنفترض أننا سنخزن الوقت الجديد بتوقيت اليمن مباشرة في العمليات القادمة
                        display_time = r.downloaded_at.strftime('%Y-%m-%d %I:%M %p')
                        
                        text += f"👤 **{u_name}**\n📥 {path_info}\n⏰ {display_time}\n"
                        text += "-------------------\n"
                else:
                    text += "⚠️ لا توجد عمليات تحميل مسجلة بعد."
                
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="stats")]]
                await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
            except Exception as e: 
                logger.error(f"Error in stats_recent: {e}")
                await q.message.reply_text(f"❌ حدث خطأ أثناء جلب الإحصائيات.")

        elif data == "stats_details":
            try:
                u_count = s.query(User).count()
                l_count = s.query(Level).count()
                s_count = s.query(Subject).count()
                sec_count = s.query(Section).count()
                i_count = s.query(Item).count()
                c_count = s.query(Content).count()
                t_count = s.query(DownloadTrack).count()
                
                text = (
                    f"📊 إحصائيات النظام الإجمالية:\n\n"
                    f"👥 عدد الطلاب: {u_count}\n"
                    f"📚 المستويات: {l_count}\n"
                    f"📖 المواد: {s_count}\n"
                    f"📁 الأقسام: {sec_count}\n"
                    f"🔹 العناصر: {i_count}\n"
                    f"📎 المحتويات: {c_count}\n"
                    f"📥 إجمالي التحميلات: {t_count}\n"
                )
                kb = [[InlineKeyboardButton("🔙 رجوع", callback_data="stats")]]
                await q.edit_message_text(text, reply_markup=InlineKeyboardMarkup(kb))
            except Exception as e: await q.message.reply_text(f"❌ خطأ: {e}")

        # ---------- إدمن - إذاعة ----------
        elif data == "broadcast":
            STATE[uid] = {"step": "broadcast"}
            await q.message.reply_text("📢 أرسل الرسالة التي تريد إذاعتها (نص، صورة، فيديو، أو ملف):")

        elif data == "del_br_list":
            brs = s.query(BroadcastMessage.broadcast_id).distinct().all()
            if not brs:
                await q.message.reply_text("⚠️ لا توجد إذاعات مسجلة.")
                return
            kb = [[InlineKeyboardButton(f"🗑 {b[0]}", callback_data=f"do_del_br:{b[0]}")] for b in brs]
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="back_admin")])
            await q.edit_message_text("اختر إذاعة لحذفها من عند المستخدمين:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("do_del_br:"):
            br_id = data[10:]
            messages_to_del = s.query(BroadcastMessage).filter_by(broadcast_id=br_id).all()
            del_count = 0
            for m in messages_to_del:
                try:
                    await context.bot.delete_message(chat_id=m.user_id, message_id=m.message_id)
                    del_count += 1
                except Exception as e: logger.warning(f"Failed to delete message for user {m.user_id}: {e}")
            s.query(BroadcastMessage).filter_by(broadcast_id=br_id).delete()
            s.query(BroadcastView).filter_by(broadcast_id=br_id).delete()
            s.commit()
            await notify_super_admin(context, uid, f"حذف إذاعة بآيدي: {br_id}")
            await q.message.reply_text(f"✅ تم حذف الإذاعة بنجاح من {del_count} مستخدم.")
            await admin(update, context)

        # ---------- إدارة المستخدمين ----------
        elif data == "manage_users":
            kb = [
                [InlineKeyboardButton("🚫 حظر مستخدم", callback_data="block_user_start")],
                [InlineKeyboardButton("✅ إلغاء حظر مستخدم", callback_data="unblock_user_start")],
                [InlineKeyboardButton("⏱ تقييد مستخدم مؤقت", callback_data="restrict_user_start")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_admin")]
            ]
            await q.edit_message_text("🚫 إدارة المستخدمين:\nاختر الإجراء المطلوب:", reply_markup=InlineKeyboardMarkup(kb))

        elif data == "block_user_start":
            STATE[uid] = {"step": "block_user"}
            await q.message.reply_text("🚫 أرسل (ID) المستخدم الذي تريد حظره:")

        elif data == "unblock_user_start":
            STATE[uid] = {"step": "unblock_user"}
            await q.message.reply_text("✅ أرسل (ID) المستخدم الذي تريد إلغاء حظره:")

        elif data == "restrict_user_start":
            STATE[uid] = {"step": "restrict_user_id"}
            await q.message.reply_text("⏱ أرسل (ID) المستخدم الذي تريد تقييده مؤقتاً:")

        # ---------- إدارة المشرفين ----------
        elif data == "manage_admins":
            kb = [
                [InlineKeyboardButton("➕ إضافة مشرف جديد", callback_data="add_admin_start")],
                [InlineKeyboardButton("✏️ تعديل صلاحيات مشرف", callback_data="edit_admin_list")],
                [InlineKeyboardButton("🗑 حذف مشرف", callback_data="del_admin_list")],
                [InlineKeyboardButton("🔙 رجوع", callback_data="back_admin")]
            ]
            await q.edit_message_text("👮 إدارة المشرفين والصلاحيات:\nاختر الإجراء المطلوب:", reply_markup=InlineKeyboardMarkup(kb))

        elif data == "edit_admin_list":
            db_admins = s.query(Admin).all()
            if not db_admins:
                await q.answer("⚠️ لا يوجد مشرفين لتعديل صلاحياتهم.", show_alert=True)
                return
            kb = [[InlineKeyboardButton(f"👤 {a.user_id} ({a.permissions})", callback_data=f"edit_perm_start:{a.user_id}")] for a in db_admins]
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="manage_admins")])
            await q.edit_message_text("اختر مشرفاً لتعديل صلاحياته:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("edit_perm_start:"):
            target_id = int(data[16:])
            adm = s.query(Admin).filter_by(user_id=target_id).first()
            current_perms = adm.permissions if adm else ""
            await q.edit_message_text(f"👮 تعديل صلاحيات المشرف {target_id}:\n(✅ مسموح | ❌ ممنوع)", reply_markup=get_permissions_keyboard(target_id, current_perms))

        elif data.startswith("tgl_perm:"):
            _, target_id, perm_to_toggle = data.split(":")
            target_id = int(target_id)
            
            adm = s.query(Admin).filter_by(user_id=target_id).first()
            if not adm:
                # إذا لم يكن مشرفاً، نقوم بإنشائه بصلاحية واحدة فارغة ثم تبديلها
                adm = Admin(user_id=target_id, permissions="")
                s.add(adm)
            
            current_perms = adm.permissions.split(",") if adm.permissions else []
            if adm.permissions == "all": current_perms = ["add", "users", "broadcast"]
            
            if perm_to_toggle in current_perms:
                current_perms.remove(perm_to_toggle)
            else:
                current_perms.append(perm_to_toggle)
            
            new_perms_str = ",".join(current_perms)
            adm.permissions = new_perms_str
            s.commit()
            
            await q.edit_message_reply_markup(reply_markup=get_permissions_keyboard(target_id, new_perms_str))
            await q.answer("تم تحديث الصلاحية ✅")

        elif data == "add_admin_start":
            STATE[uid] = {"step": "add_admin"}
            await q.edit_message_text("👮 أرسل (ID) المستخدم الذي تريد تعيينه كمشرف:", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 رجوع", callback_data="manage_admins")]]))

        elif data == "del_admin_list":
            db_admins = s.query(Admin).all()
            if not db_admins:
                await q.message.reply_text("⚠️ لا يوجد مشرفين مضافين حالياً.")
                return await admin(update, context)
            kb = [[InlineKeyboardButton(f"🗑 {a.user_id}", callback_data=f"do_del_admin:{a.id}")] for a in db_admins]
            kb.append([InlineKeyboardButton("🔙 رجوع", callback_data="manage_admins")])
            await q.edit_message_text("اختر مشرفاً لحذفه:", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("do_del_admin:"):
            adm = s.query(Admin).filter_by(id=int(data[13:])).first()
            if adm:
                admin_user_id = adm.user_id
                s.delete(adm)
                s.commit()
                await notify_super_admin(context, uid, f"حذف مشرف بآيدي: {admin_user_id}")
                await q.message.reply_text("✅ تم حذف المشرف بنجاح.")
            await admin(update, context)

        elif data.startswith("perm:"):
            if uid not in STATE or STATE[uid].get("step") != "add_admin_perms":
                await q.answer("⚠️ انتهت الجلسة.")
                return
            
            target_user_id = STATE[uid].get("target_user_id")
            permissions = data[5:]
            
            try:
                existing_admin = s.query(Admin).filter_by(user_id=target_user_id).first()
                if existing_admin:
                    existing_admin.permissions = permissions
                    s.commit()
                    await q.message.reply_text(f"✅ تم تحديث صلاحيات المشرف {target_user_id} إلى ({permissions}) بنجاح.")
                else:
                    new_admin = Admin(user_id=target_user_id, permissions=permissions)
                    s.add(new_admin)
                    s.commit()
                    await q.message.reply_text(f"✅ تم إضافة المشرف {target_user_id} بصلاحيات ({permissions}) بنجاح.")
                
                await notify_super_admin(context, uid, f"تعديل/إضافة مشرف: {target_user_id} بصلاحيات: {permissions}")
            except Exception as e:
                await q.message.reply_text(f"❌ خطأ: {e}")
            finally:
                if uid in STATE: del STATE[uid]
                await admin(update, context)

        elif data == "back_start": await start(update, context)
        elif data == "back_admin": await admin(update, context)

        elif data == "send_backup":
            try:
                if os.path.exists("college_v3.db"):
                    await context.bot.send_document(chat_id=uid, document=open("college_v3.db", "rb"), filename=f"backup_{get_yemen_time().strftime('%Y%m%d')}.db", caption="📦 نسخة احتياطية من قاعدة البيانات.")
                    await q.answer("✅ تم إرسال النسخة الاحتياطية.")
                else:
                    await q.answer("❌ ملف قاعدة البيانات غير موجود.", show_alert=True)
            except Exception as e:
                await q.answer(f"❌ خطأ: {e}", show_alert=True)

        elif data == "finish_adding":
            if uid not in STATE or "added_contents" not in STATE[uid]:
                await q.answer("⚠️ لا توجد ملفات مضافة.")
                return
            
            STATE[uid]["step"] = "ask_assignment"
            kb = [
                [InlineKeyboardButton("نعم، هذه الملفات عبارة عن تكليف", callback_data="is_assign:yes")],
                [InlineKeyboardButton("لا، محتوى عادي", callback_data="is_assign:no")]
            ]
            await q.edit_message_text("❓ هل هذه الملفات التي قمت بإضافتها عبارة عن تكليف (واجب) يتطلب موعد تسليم؟", reply_markup=InlineKeyboardMarkup(kb))

        elif data.startswith("is_assign:"):
            if uid not in STATE or STATE[uid].get("step") != "ask_assignment":
                await q.answer("⚠️ انتهت الجلسة.")
                return
            
            content_ids = STATE[uid].get("added_contents", [])
            first_content = s.query(Content).filter(Content.id.in_(content_ids)).first()
            item_id = first_content.item_id if first_content else None

            if data == "is_assign:no":
                await q.message.reply_text(f"✅ تم إضافة {len(content_ids)} ملف كمحتوى عادي. يتم الآن إرسال الإشعار المجمع...")
                # إرسال إشعار واحد فقط للمجموعة بالكامل
                context.application.create_task(notify_new_content_batch(context, content_ids))
                
                if uid in STATE: del STATE[uid]
                if item_id:
                    update.callback_query.data = f"manage_cnts:{item_id}"
                    return await callbacks(update, context)
                await admin(update, context)
            else:
                STATE[uid]["step"] = "set_deadline"
                await q.message.reply_text("📅 يرجى إرسال موعد التسليم بالتنسيق التالي:\n`YYYY-MM-DD HH:MM`\n\nمثال: `2024-12-31 23:59`", parse_mode='Markdown')

        elif data.startswith("vw_br:"):
            br_id = data[6:]
            exists = s.query(BroadcastView).filter_by(broadcast_id=br_id, user_id=uid).first()
            if not exists:
                new_view = BroadcastView(broadcast_id=br_id, user_id=uid)
                s.add(new_view)
                s.commit()
            await q.answer("تم تسجيل المشاهدة ✅")



    except Exception as e: logger.error(f"Error in callbacks: {e}")
    finally: s.close()

# ================== التعامل مع الرسائل ==================

async def messages(update: Update, context: ContextTypes.DEFAULT_TYPE):
    uid = update.effective_user.id

    s = Session()
    try:
        db_user = s.query(User).filter_by(user_id=uid).first()
        if db_user and (db_user.status == 'blocked' or db_user.status == 'restricted'):
            if db_user.status == 'blocked':
                await update.message.reply_text("🚫 تم حظر حسابك من استخدام البوت.")
            elif db_user.status == 'restricted':
                await update.message.reply_text(f"⏱ حسابك مقيد حتى {db_user.restricted_until.strftime('%Y-%m-%d %H:%M:%S')}.")
            return
    finally:
        s.close()

    if uid not in STATE: return
    
    s = Session()
    try:
        step = STATE[uid].get("step")

        # --- البحث الشامل التفصيلي (لجميع المستخدمين) ---
        if step == "searching" and update.message.text:
            query = update.message.text.strip()
            if len(query) < 2:
                await update.message.reply_text("⚠️ يرجى إدخال كلمة بحث أطول (حرفين على الأقل).")
                return

            results_text = f"🔍 نتائج البحث عن: *{query}*\n\n"
            kb = []
            
            # البحث في المستويات
            lvls = s.query(Level).filter(Level.name.like(f"%{query}%")).all()
            for l in lvls:
                kb.append([InlineKeyboardButton(f"📚 مستوى: {l.name}", callback_data=f"lvl:{l.id}")])
            
            # البحث في المواد
            subs = s.query(Subject).filter(Subject.name.like(f"%{query}%")).all()
            for sub in subs:
                l_name = sub.level.name if sub.level else "؟"
                kb.append([InlineKeyboardButton(f"📖 {l_name} ➔ {sub.name}", callback_data=f"sub:{sub.id}")])
            
            # البحث في الأقسام
            secs = s.query(Section).filter(Section.name.like(f"%{query}%")).all()
            for sec in secs:
                sub = sec.subject
                l_name = sub.level.name if sub and sub.level else "؟"
                sub_name = sub.name if sub else "؟"
                kb.append([InlineKeyboardButton(f"📁 {l_name} ➔ {sub_name} ➔ {sec.name}", callback_data=f"sec:{sec.id}")])
            
            # البحث في العناصر
            items = s.query(Item).filter(Item.name.like(f"%{query}%")).all()
            for itm in items:
                sec = itm.section
                sub = sec.subject if sec else None
                l_name = sub.level.name if sub and sub.level else "؟"
                sub_name = sub.name if sub else "؟"
                sec_name = sec.name if sec else "؟"
                kb.append([InlineKeyboardButton(f"🔹 {l_name} ➔ {sub_name} ➔ {sec_name} ➔ {itm.name}", callback_data=f"item:{itm.id}")])

            # البحث في المحتوى (النصوص)
            contents = s.query(Content).filter(Content.type == 'text', Content.value.like(f"%{query}%")).all()
            seen_items = set() # لتجنب تكرار نفس العنصر إذا وجد البحث في عدة نصوص داخله
            for cnt in contents:
                itm = cnt.item
                if not itm or itm.id in seen_items: continue
                seen_items.add(itm.id)
                sec = itm.section
                sub = sec.subject if sec else None
                l_name = sub.level.name if sub and sub.level else "؟"
                sub_name = sub.name if sub else "؟"
                sec_name = sec.name if sec else "؟"
                kb.append([InlineKeyboardButton(f"📎 {l_name} ➔ {sub_name} ➔ {sec_name} ➔ {itm.name}", callback_data=f"item:{itm.id}")])

            if not kb:
                await update.message.reply_text("❌ لم يتم العثور على نتائج تطابق بحثك.")
            else:
                # تقسيم الأزرار إذا كانت كثيرة جداً (تجنب خطأ التليجرام)
                if len(kb) > 15:
                    kb = kb[:15]
                    results_text += "⚠️ تم عرض أول 15 نتيجة فقط، يرجى تخصيص البحث أكثر.\n\n"
                
                kb.append([InlineKeyboardButton("🔙 العودة للقائمة الرئيسية", callback_data="back_start")])
                await update.message.reply_text(results_text, reply_markup=InlineKeyboardMarkup(kb), parse_mode='Markdown')
            
            if uid in STATE: del STATE[uid]
            return

        # التحقق من صلاحية الإدمن للخطوات التالية
        if not is_admin(uid): return

        # التحقق من الصلاحيات بناءً على الخطوة
        step_perms = {
            "broadcast": "broadcast",
            "block_user": "users", "unblock_user": "users", "restrict_user_id": "users", "restrict_user_duration": "users", "add_admin": "users", "add_admin_perms": "users",
            "level": "add", "subject": "add", "section": "add", "item": "add", "content": "add", "ask_assignment": "add", "set_deadline": "add",
            "edit_level_name": "add", "edit_subject_name": "add", "edit_section_name": "add", "edit_item_name": "add", "edit_content_value": "add"
        }
        
        if step in step_perms and not has_permission(uid, step_perms[step]):
            await update.message.reply_text("⛔ ليس لديك صلاحية للقيام بهذا الإجراء.")
            if uid in STATE: del STATE[uid]
            return
        
        # --- إذاعة رسالة ---
        if step == "broadcast":
            users = s.query(User).all()
            sent_count = 0
            br_id = get_yemen_time().strftime("%Y%m%d%H%M%S")
            kb = InlineKeyboardMarkup([[InlineKeyboardButton("👁 تم الاطلاع", callback_data=f"vw_br:{br_id}")]])
            for user_obj in users:
                try:
                    msg = None
                    if update.message.text: msg = await context.bot.send_message(chat_id=user_obj.user_id, text=update.message.text, reply_markup=kb)
                    elif update.message.photo: msg = await context.bot.send_photo(chat_id=user_obj.user_id, photo=update.message.photo[-1].file_id, caption=update.message.caption, reply_markup=kb)
                    elif update.message.video: msg = await context.bot.send_video(chat_id=user_obj.user_id, video=update.message.video.file_id, caption=update.message.caption, reply_markup=kb)
                    elif update.message.document: msg = await context.bot.send_document(chat_id=user_obj.user_id, document=update.message.document.file_id, caption=update.message.caption, reply_markup=kb)
                    
                    if msg:
                        new_br = BroadcastMessage(broadcast_id=br_id, user_id=user_obj.user_id, message_id=msg.message_id)
                        s.add(new_br)
                        sent_count += 1
                except Exception as e: logger.warning(f"Failed to send broadcast to {user_obj.user_id}: {e}")
            s.commit()
            await update.message.reply_text(f"✅ تم إرسال الإذاعة إلى {sent_count} مستخدم.")
            if uid in STATE: del STATE[uid]
            await admin(update, context)

        # --- حظر / تقييد ---
        elif step == "block_user":
            try:
                target_user_id = int(update.message.text)
                user_to_block = s.query(User).filter_by(user_id=target_user_id).first()
                if not user_to_block:
                    await update.message.reply_text("⚠️ المستخدم غير موجود.")
                elif user_to_block.status == 'blocked':
                    await update.message.reply_text("⚠️ المستخدم محظور بالفعل.")
                else:
                    user_to_block.status = 'blocked'
                    new_blocked = BlockedUser(user_id=target_user_id, blocked_by=uid)
                    s.add(new_blocked)
                    s.commit()
                    await notify_super_admin(context, uid, f"حظر المستخدم: {target_user_id}")
                    await update.message.reply_text(f"✅ تم حظر المستخدم {target_user_id} بنجاح.")
            except ValueError: await update.message.reply_text("❌ يرجى إرسال ID صحيح.")
            except Exception as e: await update.message.reply_text(f"❌ خطأ: {e}")
            finally:
                if uid in STATE: del STATE[uid]
                await admin(update, context)

        elif step == "unblock_user":
            try:
                target_user_id = int(update.message.text)
                user_to_unblock = s.query(User).filter_by(user_id=target_user_id).first()
                if not user_to_unblock:
                    await update.message.reply_text("⚠️ المستخدم غير موجود.")
                elif user_to_unblock.status != 'blocked':
                    await update.message.reply_text("⚠️ المستخدم غير محظور.")
                else:
                    user_to_unblock.status = 'active'
                    s.query(BlockedUser).filter_by(user_id=target_user_id).delete()
                    s.commit()
                    await notify_super_admin(context, uid, f"إلغاء حظر المستخدم: {target_user_id}")
                    await update.message.reply_text(f"✅ تم إلغاء حظر المستخدم {target_user_id} بنجاح.")
            except ValueError: await update.message.reply_text("❌ يرجى إرسال ID صحيح.")
            except Exception as e: await update.message.reply_text(f"❌ خطأ: {e}")
            finally:
                if uid in STATE: del STATE[uid]
                await admin(update, context)

        elif step == "restrict_user_id":
            try:
                target_user_id = int(update.message.text)
                user_to_restrict = s.query(User).filter_by(user_id=target_user_id).first()
                if not user_to_restrict:
                    await update.message.reply_text("⚠️ المستخدم غير موجود.")
                    if uid in STATE: del STATE[uid]
                    await admin(update, context)
                    return
                STATE[uid] = {"step": "restrict_user_duration", "target_user_id": target_user_id}
                await update.message.reply_text("⏱ أرسل مدة التقييد بالدقائق:")
            except ValueError: await update.message.reply_text("❌ يرجى إرسال ID صحيح.")
            finally: pass

        elif step == "restrict_user_duration":
            target_user_id = STATE[uid].get("target_user_id")
            try:
                duration_minutes = int(update.message.text)
                user_to_restrict = s.query(User).filter_by(user_id=target_user_id).first()
                if user_to_restrict:
                    restricted_until = get_yemen_time() + datetime.timedelta(minutes=duration_minutes)
                    user_to_restrict.status = 'restricted'
                    user_to_restrict.restricted_until = restricted_until
                    new_restricted = RestrictedUser(user_id=target_user_id, restricted_by=uid, restricted_at=get_yemen_time(), restricted_until=restricted_until)
                    s.add(new_restricted)
                    s.commit()
                    await update.message.reply_text(f"✅ تم تقييد المستخدم {target_user_id} حتى {restricted_until.strftime('%Y-%m-%d %H:%M:%S')}.")
            except Exception as e: await update.message.reply_text(f"❌ خطأ: {e}")
            finally:
                if uid in STATE: del STATE[uid]
                await admin(update, context)

        elif step == "add_admin":
            try:
                target_user_id = int(update.message.text)
                # التحقق إذا كان المشرف موجوداً بالفعل
                existing = s.query(Admin).filter_by(user_id=target_user_id).first()
                if existing:
                    await update.message.reply_text("⚠️ هذا المستخدم مشرف بالفعل. يمكنك تعديل صلاحياته من قائمة التعديل.")
                    if uid in STATE: del STATE[uid]
                    await admin(update, context)
                    return
                
                # إنشاء المشرف بصلاحيات فارغة أولاً
                new_admin = Admin(user_id=target_user_id, permissions="")
                s.add(new_admin)
                s.commit()
                
                if uid in STATE: del STATE[uid]
                await update.message.reply_text(f"👮 تم تسجيل {target_user_id} كمشرف. يرجى الآن تحديد صلاحياته (منح/منع):", reply_markup=get_permissions_keyboard(target_user_id, ""))
            except ValueError: 
                await update.message.reply_text("❌ يرجى إرسال ID صحيح.")
                if uid in STATE: del STATE[uid]
                await admin(update, context)
            except Exception as e: 
                await update.message.reply_text(f"❌ خطأ: {e}")
                if uid in STATE: del STATE[uid]
                await admin(update, context)

        # --- إضافة الهيكل ---
        elif step == "level":
            name = update.message.text
            try:
                new_level = Level(name=name)
                s.add(new_level)
                s.commit()
                await update.message.reply_text(f"✅ تم إضافة المستوى '{name}' بنجاح.")
            except IntegrityError: await update.message.reply_text("⚠️ موجود بالفعل.")
            finally:
                if uid in STATE: del STATE[uid]
                # العودة لقائمة إدارة الهيكل
                update.callback_query = type('obj', (object,), {'from_user': update.effective_user, 'data': "manage_v4", 'message': update.message, 'answer': lambda *args, **kwargs: None, 'edit_message_text': lambda *args, **kwargs: update.message.reply_text(*args, **kwargs)})
                return await callbacks(update, context)

        elif step == "subject":
            name = update.message.text
            level_id = STATE[uid]["level"]
            new_subject = Subject(name=name, level_id=level_id)
            s.add(new_subject)
            s.commit()
            await update.message.reply_text(f"✅ تم إضافة المادة '{name}' بنجاح.")
            if uid in STATE: del STATE[uid]
            # العودة لقائمة إدارة المستوى
            update.callback_query = type('obj', (object,), {'from_user': update.effective_user, 'data': f"adm_lvl:{level_id}", 'message': update.message, 'answer': lambda *args, **kwargs: None, 'edit_message_text': lambda *args, **kwargs: update.message.reply_text(*args, **kwargs)})
            return await callbacks(update, context)

        elif step == "section":
            name = update.message.text
            subject_id = STATE[uid]["subject"]
            new_section = Section(name=name, subject_id=subject_id)
            s.add(new_section)
            s.commit()
            await update.message.reply_text(f"✅ تم إضافة القسم '{name}' بنجاح.")
            if uid in STATE: del STATE[uid]
            # العودة لقائمة إدارة المادة
            update.callback_query = type('obj', (object,), {'from_user': update.effective_user, 'data': f"adm_sub:{subject_id}", 'message': update.message, 'answer': lambda *args, **kwargs: None, 'edit_message_text': lambda *args, **kwargs: update.message.reply_text(*args, **kwargs)})
            return await callbacks(update, context)

        elif step == "item":
            name = update.message.text
            section_id = STATE[uid]["section"]
            new_item = Item(name=name, section_id=section_id)
            s.add(new_item)
            s.commit()
            await update.message.reply_text(f"✅ تم إضافة العنصر '{name}' بنجاح.")
            if uid in STATE: del STATE[uid]
            # العودة لقائمة إدارة القسم
            update.callback_query = type('obj', (object,), {'from_user': update.effective_user, 'data': f"adm_sec:{section_id}", 'message': update.message, 'answer': lambda *args, **kwargs: None, 'edit_message_text': lambda *args, **kwargs: update.message.reply_text(*args, **kwargs)})
            return await callbacks(update, context)

        elif step == "content":
            item_id = STATE[uid]["item"]
            content_type = "text"
            content_value = update.message.text
            if update.message.photo:
                content_type = "photo"
                content_value = update.message.photo[-1].file_id
            elif update.message.video:
                content_type = "video"
                content_value = update.message.video.file_id
            elif update.message.document:
                content_type = "document"
                content_value = update.message.document.file_id
            
            new_content = Content(type=content_type, value=content_value, item_id=item_id)
            s.add(new_content)
            s.commit()
            
            # تحديث قائمة المحتويات المضافة في الجلسة الحالية
            if "added_contents" not in STATE[uid]:
                STATE[uid]["added_contents"] = []
            STATE[uid]["added_contents"].append(new_content.id)
            
            kb = [
                [InlineKeyboardButton("✅ إنهاء الإضافة وإرسال الإشعارات", callback_data="finish_adding")],
                [InlineKeyboardButton("🔙 إلغاء الإضافة بالكامل", callback_data=f"adm_sec:{STATE[uid].get('section', '')}")]
            ]
            await update.message.reply_text(
                f"📥 تم استلام الملف بنجاح.\n\n"
                f"يمكنك إرسال ملف آخر الآن، أو الضغط على الزر أدناه لإنهاء الإضافة وتحديد إذا كانت هذه الملفات تكليفاً.",
                reply_markup=InlineKeyboardMarkup(kb)
            )
            return # سننتظر المزيد من الملفات أو الكولباك

        elif step == "set_deadline":
            content_ids = STATE[uid].get("added_contents", [])
            deadline_str = update.message.text
            try:
                deadline_dt = datetime.datetime.strptime(deadline_str, "%Y-%m-%d %H:%M")
                deadline_dt = deadline_dt.replace(tzinfo=YEMEN_TZ)
                
                item_id = None
                for cid in content_ids:
                    content = s.query(Content).filter_by(id=cid).first()
                    if content:
                        item_id = content.item_id
                        content.is_assignment = 1
                        content.deadline = deadline_dt
                        s.commit()
                
                # إرسال إشعار واحد فقط للمجموعة بالكامل
                context.application.create_task(notify_new_content_batch(context, content_ids))
                
                await update.message.reply_text(f"✅ تم تحديد موعد التسليم لـ {len(content_ids)} ملف: {deadline_str}. تم إرسال الإشعار المجمع.")
                
                if uid in STATE: del STATE[uid]
                if item_id:
                    update.callback_query = type('obj', (object,), {'from_user': update.effective_user, 'data': f"manage_cnts:{item_id}", 'message': update.message, 'answer': lambda *args, **kwargs: None, 'edit_message_text': lambda *args, **kwargs: update.message.reply_text(*args, **kwargs)})
                    return await callbacks(update, context)
                await admin(update, context)
            except ValueError:
                await update.message.reply_text("❌ التنسيق غير صحيح. يرجى الإرسال كالتالي:\n`YYYY-MM-DD HH:MM`\nمثال: `2024-12-31 23:59`", parse_mode='Markdown')

        # --- تعديل الهيكل ---
        elif step == "edit_level_name":
            level_id = STATE[uid]["id"]
            new_name = update.message.text
            level = s.query(Level).filter_by(id=level_id).first()
            if level:
                level.name = new_name
                s.commit()
                await update.message.reply_text(f"✅ تم تعديل اسم المستوى إلى '{new_name}'.")
            if uid in STATE: del STATE[uid]
            await admin(update, context)

        elif step == "edit_subject_name":
            subject_id = STATE[uid]["id"]
            new_name = update.message.text
            subject = s.query(Subject).filter_by(id=subject_id).first()
            if subject:
                subject.name = new_name
                s.commit()
                await update.message.reply_text(f"✅ تم تعديل اسم المادة إلى '{new_name}'.")
            if uid in STATE: del STATE[uid]
            await admin(update, context)

        elif step == "edit_section_name":
            section_id = STATE[uid]["id"]
            new_name = update.message.text
            section = s.query(Section).filter_by(id=section_id).first()
            if section:
                section.name = new_name
                s.commit()
                await update.message.reply_text(f"✅ تم تعديل اسم القسم إلى '{new_name}'.")
            if uid in STATE: del STATE[uid]
            await admin(update, context)

        elif step == "edit_item_name":
            item_id = STATE[uid]["id"]
            new_name = update.message.text
            item = s.query(Item).filter_by(id=item_id).first()
            if item:
                item.name = new_name
                s.commit()
                await update.message.reply_text(f"✅ تم تعديل اسم العنصر إلى '{new_name}'.")
            if uid in STATE: del STATE[uid]
            await admin(update, context)

        elif step == "edit_content_value":
            content_id = STATE[uid]["id"]
            content_type = "text"
            content_value = update.message.text
            if update.message.photo:
                content_type = "photo"
                content_value = update.message.photo[-1].file_id
            elif update.message.video:
                content_type = "video"
                content_value = update.message.video.file_id
            elif update.message.document:
                content_type = "document"
                content_value = update.message.document.file_id
            
            content = s.query(Content).filter_by(id=content_id).first()
            if content:
                content.type = content_type
                content.value = content_value
                s.commit()
                await update.message.reply_text(f"✅ تم تعديل المحتوى بنجاح.")
            if uid in STATE: del STATE[uid]
            await admin(update, context)

    except Exception as e: logger.error(f"Error in messages: {e}")
    finally: s.close()

# ================== Main ==================

async def search_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر البحث السريع"""
    uid = update.effective_user.id
    STATE[uid] = {"step": "searching"}
    await update.message.reply_text("🔍 أرسل كلمة البحث (اسم المادة، القسم، أو المحتوى):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="back_start")]]))

async def broadcast_command(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """أمر إرسال إذاعة سريع للمشرفين"""
    uid = update.effective_user.id
    if not is_admin(uid) or not has_permission(uid, "broadcast"):
        await update.message.reply_text("⛔ ليس لديك صلاحية لإرسال الإذاعة.")
        return
    STATE[uid] = {"step": "broadcast"}
    await update.message.reply_text("📢 أرسل الرسالة التي تريد إذاعتها لجميع الطلاب (نص، صورة، أو ملف):", reply_markup=InlineKeyboardMarkup([[InlineKeyboardButton("🔙 إلغاء", callback_data="back_admin")]]))

async def post_init(application: Application):
    """إعداد قائمة الأوامر التي تظهر بجانب خانة الرسائل"""
    commands = [
        BotCommand("start", "القائمة الرئيسية 🏠"),
        BotCommand("search", "البحث السريع 🔍"),
        BotCommand("broadcast", "إرسال إشعار عام 📢"),
        BotCommand("admin", "لوحة التحكم للمشرفين 🛠"),
    ]
    await application.bot.set_my_commands(commands)

def main():
    app = Application.builder().token(BOT_TOKEN).post_init(post_init).build()
    
    # جدولة فحص المواعيد النهائية كل 30 دقيقة
    if app.job_queue:
        app.job_queue.run_repeating(check_deadlines, interval=1800, first=10)
    
    app.add_handler(CommandHandler("start", start))
    app.add_handler(CommandHandler("search", search_command))
    app.add_handler(CommandHandler("broadcast", broadcast_command))
    app.add_handler(CommandHandler("admin", admin))
    app.add_handler(CallbackQueryHandler(callbacks))
    app.add_handler(MessageHandler(filters.TEXT & ~filters.COMMAND, messages))
    app.add_handler(MessageHandler(filters.PHOTO | filters.VIDEO | filters.Document.ALL, messages))
    
    logger.info("Bot started...")
    app.run_polling()

if __name__ == '__main__':
    main()
