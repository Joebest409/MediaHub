import os
import sqlite3
import uuid
import secrets
import smtplib

from datetime import datetime, timedelta
from email.message import EmailMessage

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    send_from_directory
)

from werkzeug.security import (
    generate_password_hash,
    check_password_hash
)

from werkzeug.utils import secure_filename


# =========================================================
# APP
# =========================================================

app = Flask(__name__)

app.secret_key = os.environ["SECRET_KEY"]

# =========================================================
# EMAIL CONFIGURATION
# =========================================================

MAIL_SERVER = "smtp.gmail.com"
MAIL_PORT = 465

MAIL_USERNAME = os.environ.get(
    "MEDIAHUB_EMAIL"
)

MAIL_PASSWORD = os.environ.get(
    "MEDIAHUB_EMAIL_PASSWORD"
)


# =========================================================
# DATABASE
# =========================================================

DATA_FOLDER = "/var/data"

DATABASE = os.path.join(
    DATA_FOLDER,
    "database.db"
)


# =========================================================
# FOLDERS
# =========================================================

VIDEO_FOLDER = os.path.join(
    DATA_FOLDER,
    "uploads",
    "videos"
)

AUDIO_FOLDER = os.path.join(
    DATA_FOLDER,
    "uploads",
    "audio"
)

THUMBNAIL_FOLDER = os.path.join(
    DATA_FOLDER,
    "uploads",
    "thumbnails"
)

PROFILE_FOLDER = os.path.join(
    DATA_FOLDER,
    "uploads",
    "profiles"
)
app.config["VIDEO_FOLDER"] = VIDEO_FOLDER
app.config["AUDIO_FOLDER"] = AUDIO_FOLDER
app.config["THUMBNAIL_FOLDER"] = THUMBNAIL_FOLDER
app.config["PROFILE_FOLDER"] = PROFILE_FOLDER


# =========================================================
# ALLOWED FILE TYPES
# =========================================================

ALLOWED_VIDEO_EXTENSIONS = {
    "mp4",
    "webm",
    "mkv",
    "mov",
    "avi"
}

ALLOWED_AUDIO_EXTENSIONS = {
    "mp3",
    "wav",
    "m4a",
    "aac",
    "ogg"
}

ALLOWED_IMAGE_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp"
}


# =========================================================
# DATABASE CONNECTION
# =========================================================

def get_db():

    conn = sqlite3.connect(DATABASE)

    conn.row_factory = sqlite3.Row

    return conn


# =========================================================
# CREATE NOTIFICATION
# =========================================================

def create_notification(
    message,
    notification_type="info"
):

    conn = get_db()

    conn.execute("""
        INSERT INTO notifications (
            message,
            notification_type
        )
        VALUES (?, ?)
    """, (
        message,
        notification_type
    ))

    conn.commit()

    conn.close()


# =========================================================
# GLOBAL ADMIN NOTIFICATION COUNT
# =========================================================

@app.context_processor
def inject_notification_count():

    unread_notifications = 0

    if session.get("admin_id"):

        conn = get_db()

        unread_notifications = conn.execute("""
            SELECT COUNT(*)
            FROM notifications
            WHERE is_read = 0
        """).fetchone()[0]

        conn.close()

    return {
        "unread_notifications": unread_notifications
    }


# =========================================================
# INITIALIZE DATABASE
# =========================================================

def init_db():

    # -----------------------------------------------------
    # CREATE FOLDERS
    # -----------------------------------------------------

    os.makedirs(
        VIDEO_FOLDER,
        exist_ok=True
    )

    os.makedirs(
        AUDIO_FOLDER,
        exist_ok=True
    )

    os.makedirs(
        THUMBNAIL_FOLDER,
        exist_ok=True
    )

    os.makedirs(
        PROFILE_FOLDER,
        exist_ok=True
    )

    conn = get_db()

    # =====================================================
    # MEDIA TABLE
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS media (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            filename TEXT NOT NULL,
            media_type TEXT NOT NULL,
            category TEXT,
            downloads INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # ADMIN TABLE
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # USERS TABLE
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            email TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # =====================================================
    # PASSWORD RESETS TABLE
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS password_resets (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            token TEXT UNIQUE NOT NULL,
            expires_at TIMESTAMP NOT NULL,
            used INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)
                REFERENCES users(id)
        )
    """)

    # =====================================================
    # DOWNLOADS TABLE
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS downloads (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            media_id INTEGER NOT NULL,
            downloaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (user_id)
                REFERENCES users(id),
            FOREIGN KEY (media_id)
                REFERENCES media(id)
        )
    """)

    # =====================================================
    # FAVORITES TABLE
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS favorites (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER NOT NULL,
            media_id INTEGER NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            UNIQUE(user_id, media_id),
            FOREIGN KEY (user_id)
                REFERENCES users(id),
            FOREIGN KEY (media_id)
                REFERENCES media(id)
        )
    """)

    # =====================================================
    # NOTIFICATIONS TABLE
    # =====================================================

    conn.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            message TEXT NOT NULL,
            notification_type TEXT DEFAULT 'info',
            is_read INTEGER DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
    """)

    conn.commit()

    conn.close()

    # -----------------------------------------------------
    # DATABASE MIGRATIONS
    # -----------------------------------------------------

    add_thumbnail_column()

    add_profile_picture_column()


# =========================================================
# ADD THUMBNAIL COLUMN
# =========================================================

def add_thumbnail_column():

    conn = get_db()

    columns = conn.execute(
        "PRAGMA table_info(media)"
    ).fetchall()

    column_names = [
        column["name"]
        for column in columns
    ]

    if "thumbnail" not in column_names:

        conn.execute("""
            ALTER TABLE media
            ADD COLUMN thumbnail TEXT
        """)

        conn.commit()

    conn.close()


# =========================================================
# ADD PROFILE PICTURE COLUMN
# =========================================================

def add_profile_picture_column():

    conn = get_db()

    columns = conn.execute(
        "PRAGMA table_info(users)"
    ).fetchall()

    column_names = [
        column["name"]
        for column in columns
    ]

    if "profile_picture" not in column_names:

        conn.execute("""
            ALTER TABLE users
            ADD COLUMN profile_picture TEXT
        """)

        conn.commit()

    conn.close()


# =========================================================
# FILE VALIDATION
# =========================================================

def allowed_video(filename):

    return (
        "."
        in filename
        and
        filename.rsplit(
            ".",
            1
        )[1].lower()
        in ALLOWED_VIDEO_EXTENSIONS
    )


def allowed_audio(filename):

    return (
        "."
        in filename
        and
        filename.rsplit(
            ".",
            1
        )[1].lower()
        in ALLOWED_AUDIO_EXTENSIONS
    )


def allowed_image(filename):

    return (
        "."
        in filename
        and
        filename.rsplit(
            ".",
            1
        )[1].lower()
        in ALLOWED_IMAGE_EXTENSIONS
    )


# =========================================================
# SEND PASSWORD RESET EMAIL
# =========================================================

def send_reset_email(
    recipient,
    reset_link
):

    if not MAIL_USERNAME:

        print(
            "EMAIL ERROR: "
            "MEDIAHUB_EMAIL is not set."
        )

        return False

    if not MAIL_PASSWORD:

        print(
            "EMAIL ERROR: "
            "MEDIAHUB_EMAIL_PASSWORD is not set."
        )

        return False

    message = EmailMessage()

    message["Subject"] = (
        "MediaHub Password Reset"
    )

    message["From"] = MAIL_USERNAME

    message["To"] = recipient

    message.set_content(f"""
Hello,

We received a request to reset your MediaHub password.

Click the link below to reset your password:

{reset_link}

This password reset link will expire after 30 minutes.

If you did not request this password reset,
you can safely ignore this email.

Regards,
MediaHub
""")

    try:

        print(
            "Connecting to Gmail..."
        )

        with smtplib.SMTP_SSL(
            MAIL_SERVER,
            MAIL_PORT,
            timeout=30
        ) as server:

            print(
                "Connected to Gmail."
            )

            server.login(
                MAIL_USERNAME,
                MAIL_PASSWORD
            )

            print(
                "Gmail login successful."
            )

            server.send_message(
                message
            )

            print(
                "Password reset email sent successfully."
            )

        return True

    except Exception as e:

        print(
            "EMAIL ERROR:",
            repr(e)
        )

        return False


# =========================================================
# HOME
# =========================================================

@app.route("/")
def home():

    page = request.args.get(
        "page",
        1,
        type=int
    )

    if page < 1:

        page = 1

    per_page = 8

    offset = (
        page - 1
    ) * per_page

    conn = get_db()

    media = conn.execute("""
        SELECT *
        FROM media
        ORDER BY created_at DESC
        LIMIT ? OFFSET ?
    """, (
        per_page,
        offset
    )).fetchall()

    total = conn.execute("""
        SELECT COUNT(*)
        FROM media
    """).fetchone()[0]

    conn.close()

    total_pages = (
        (total + per_page - 1)
        // per_page
    )

    return render_template(
        "index.html",
        media=media,
        page=page,
        total_pages=total_pages
    )


# =========================================================
# VIDEOS
# =========================================================

@app.route("/videos")
def videos():

    conn = get_db()

    media = conn.execute("""
        SELECT *
        FROM media
        WHERE media_type = 'video'
        ORDER BY created_at DESC
    """).fetchall()

    conn.close()

    return render_template(
        "videos.html",
        media=media
    )


# =========================================================
# AUDIO
# =========================================================

@app.route("/audio")
def audio():

    conn = get_db()

    media = conn.execute("""
        SELECT *
        FROM media
        WHERE media_type = 'audio'
        ORDER BY created_at DESC
    """).fetchall()

    conn.close()

    return render_template(
        "audio.html",
        media=media
    )


# =========================================================
# SEARCH
# =========================================================

@app.route("/search")
def search():

    query = request.args.get(
        "q",
        ""
    ).strip()

    conn = get_db()

    if query:

        search_text = (
            f"%{query}%"
        )

        media = conn.execute("""
            SELECT *
            FROM media
            WHERE title LIKE ?
               OR description LIKE ?
               OR category LIKE ?
            ORDER BY created_at DESC
        """, (
            search_text,
            search_text,
            search_text
        )).fetchall()

    else:

        media = []

    conn.close()

    return render_template(
        "search.html",
        media=media,
        query=query
    )


# =========================================================
# ADMIN REGISTER
# =========================================================

@app.route(
    "/admin/register",
    methods=["GET", "POST"]
)
def admin_register():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        if not username:

            return "Username is required."

        if not password:

            return "Password is required."

        if len(password) < 6:

            return (
                "Password must be at least "
                "6 characters."
            )

        hashed_password = (
            generate_password_hash(
                password
            )
        )

        conn = get_db()

        try:

            conn.execute("""
                INSERT INTO admins
                (
                    username,
                    password
                )
                VALUES (?, ?)
            """, (
                username,
                hashed_password
            ))

            conn.commit()

        except sqlite3.IntegrityError:

            conn.close()

            return (
                "Username already exists."
            )

        conn.close()

        return redirect(
            url_for("admin_login")
        )

    return render_template(
        "admin_register.html"
    )


# =========================================================
# ADMIN LOGIN
# =========================================================

@app.route(
    "/admin/login",
    methods=["GET", "POST"]
)
def admin_login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        conn = get_db()

        admin = conn.execute("""
            SELECT *
            FROM admins
            WHERE username = ?
        """, (
            username,
        )).fetchone()

        conn.close()

        if admin:

            valid_password = (
                check_password_hash(
                    admin["password"],
                    password
                )
            )

        else:

            valid_password = False

        if valid_password:

            session["admin_id"] = (
                admin["id"]
            )

            session["admin_username"] = (
                admin["username"]
            )

            return redirect(
                url_for("admin_dashboard")
            )

        return (
            "Invalid username or password."
        )

    return render_template(
        "admin_login.html"
    )


# =========================================================
# ADMIN LOGOUT
# =========================================================

@app.route("/admin/logout")
def admin_logout():

    session.clear()

    return redirect(
        url_for("admin_login")
    )


# =========================================================
# ADMIN DASHBOARD
# =========================================================

@app.route("/admin/dashboard")
def admin_dashboard():

    if "admin_id" not in session:

        return redirect(
            url_for("admin_login")
        )

    search = request.args.get(
        "search",
        ""
    ).strip()

    category = request.args.get(
        "category",
        ""
    ).strip()

    media_type = request.args.get(
        "media_type",
        ""
    ).strip()

    conn = get_db()

    # =====================================================
    # MEDIA SEARCH / FILTER
    # =====================================================

    query = """
        SELECT *
        FROM media
        WHERE 1=1
    """

    params = []

    if search:

        query += """
            AND title LIKE ?
        """

        params.append(
            "%" + search + "%"
        )

    if category:

        query += """
            AND category = ?
        """

        params.append(
            category
        )

    if media_type:

        query += """
            AND media_type = ?
        """

        params.append(
            media_type
        )

    query += """
        ORDER BY created_at DESC
    """

    media = conn.execute(
        query,
        params
    ).fetchall()

    # =====================================================
    # CATEGORIES
    # =====================================================

    categories = conn.execute("""
        SELECT DISTINCT category
        FROM media
        WHERE category IS NOT NULL
        AND category != ''
        ORDER BY category
    """).fetchall()

    # =====================================================
    # ANALYTICS
    # =====================================================

    total_media = conn.execute("""
        SELECT COUNT(*)
        FROM media
    """).fetchone()[0]

    total_videos = conn.execute("""
        SELECT COUNT(*)
        FROM media
        WHERE media_type = 'video'
    """).fetchone()[0]

    total_audio = conn.execute("""
        SELECT COUNT(*)
        FROM media
        WHERE media_type = 'audio'
    """).fetchone()[0]

    total_downloads = conn.execute("""
        SELECT COALESCE(
            SUM(downloads),
            0
        )
        FROM media
    """).fetchone()[0]

    total_categories = conn.execute("""
        SELECT COUNT(
            DISTINCT category
        )
        FROM media
        WHERE category IS NOT NULL
        AND category != ''
    """).fetchone()[0]

    # =====================================================
    # MOST DOWNLOADED MEDIA
    # =====================================================

    popular_media = conn.execute("""
        SELECT *
        FROM media
        ORDER BY downloads DESC
        LIMIT 5
    """).fetchall()

    # =====================================================
    # CATEGORY STATISTICS
    # =====================================================

    category_stats = conn.execute("""
        SELECT
            category,
            COUNT(*) AS media_count,
            COALESCE(
                SUM(downloads),
                0
            ) AS download_count
        FROM media
        WHERE category IS NOT NULL
        AND category != ''
        GROUP BY category
        ORDER BY media_count DESC
    """).fetchall()

    # =====================================================
    # RECENT NOTIFICATIONS
    # =====================================================

    recent_notifications = conn.execute("""
        SELECT *
        FROM notifications
        ORDER BY created_at DESC
        LIMIT 5
    """).fetchall()

    conn.close()

    return render_template(
        "admin_dashboard.html",
        media=media,
        categories=categories,
        search=search,
        selected_category=category,
        selected_media_type=media_type,
        total_media=total_media,
        total_videos=total_videos,
        total_audio=total_audio,
        total_downloads=total_downloads,
        total_categories=total_categories,
        popular_media=popular_media,
        category_stats=category_stats,
        recent_notifications=recent_notifications
    )


# =========================================================
# ADMIN NOTIFICATIONS
# =========================================================

@app.route("/admin/notifications")
def admin_notifications():

    if "admin_id" not in session:

        return redirect(
            url_for("admin_login")
        )

    conn = get_db()

    notifications = conn.execute("""
        SELECT *
        FROM notifications
        ORDER BY created_at DESC
        LIMIT 50
    """).fetchall()

    conn.close()

    return render_template(
        "admin_notifications.html",
        notifications=notifications
    )


# =========================================================
# MARK ALL NOTIFICATIONS AS READ
# =========================================================

@app.route(
    "/admin/notifications/read",
    methods=["POST"]
)
def mark_notifications_read():

    if "admin_id" not in session:

        return redirect(
            url_for("admin_login")
        )

    conn = get_db()

    conn.execute("""
        UPDATE notifications
        SET is_read = 1
        WHERE is_read = 0
    """)

    conn.commit()

    conn.close()

    return redirect(
        url_for("admin_notifications")
    )


# =========================================================
# ADMIN USER MANAGEMENT
# =========================================================

@app.route("/admin/users")
def admin_users():

    if "admin_id" not in session:

        return redirect(
            url_for("admin_login")
        )

    search = request.args.get(
        "search",
        ""
    ).strip()

    conn = get_db()

    if search:

        users = conn.execute("""
            SELECT *
            FROM users
            WHERE username LIKE ?
               OR email LIKE ?
            ORDER BY created_at DESC
        """, (
            "%" + search + "%",
            "%" + search + "%"
        )).fetchall()

    else:

        users = conn.execute("""
            SELECT *
            FROM users
            ORDER BY created_at DESC
        """).fetchall()

    total_users = conn.execute("""
        SELECT COUNT(*)
        FROM users
    """).fetchone()[0]

    total_downloads = conn.execute("""
        SELECT COUNT(*)
        FROM downloads
    """).fetchone()[0]

    total_favorites = conn.execute("""
        SELECT COUNT(*)
        FROM favorites
    """).fetchone()[0]

    conn.close()

    return render_template(
        "admin_users.html",
        users=users,
        search=search,
        total_users=total_users,
        total_downloads=total_downloads,
        total_favorites=total_favorites
    )


# =========================================================
# DELETE USER
# =========================================================

@app.route(
    "/admin/delete-user/<int:user_id>",
    methods=["POST"]
)
def delete_user(user_id):

    if "admin_id" not in session:

        return redirect(
            url_for("admin_login")
        )

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE id = ?
    """, (
        user_id,
    )).fetchone()

    if not user:

        conn.close()

        return (
            "User not found.",
            404
        )

    username = user["username"]

    # Delete password reset records
    conn.execute("""
        DELETE FROM password_resets
        WHERE user_id = ?
    """, (
        user_id,
    ))

    # Delete downloads
    conn.execute("""
        DELETE FROM downloads
        WHERE user_id = ?
    """, (
        user_id,
    ))

    # Delete favorites
    conn.execute("""
        DELETE FROM favorites
        WHERE user_id = ?
    """, (
        user_id,
    ))

    # Delete user
    conn.execute("""
        DELETE FROM users
        WHERE id = ?
    """, (
        user_id,
    ))

    conn.commit()

    conn.close()

    create_notification(
        "User deleted: " + username,
        "user"
    )

    return redirect(
        url_for("admin_users")
    )


# =========================================================
# ADMIN DOWNLOAD ACTIVITY
# =========================================================

@app.route("/admin/downloads")
def admin_downloads():

    if "admin_id" not in session:

        return redirect(
            url_for("admin_login")
        )

    search = request.args.get(
        "search",
        ""
    ).strip()

    conn = get_db()

    if search:

        downloads = conn.execute("""
            SELECT
                downloads.id,
                downloads.downloaded_at,
                users.username,
                users.email,
                media.title,
                media.media_type,
                media.category
            FROM downloads

            LEFT JOIN users
                ON downloads.user_id = users.id

            LEFT JOIN media
                ON downloads.media_id = media.id

            WHERE users.username LIKE ?
               OR users.email LIKE ?
               OR media.title LIKE ?
               OR media.category LIKE ?

            ORDER BY
                downloads.downloaded_at DESC
        """, (
            "%" + search + "%",
            "%" + search + "%",
            "%" + search + "%",
            "%" + search + "%"
        )).fetchall()

    else:

        downloads = conn.execute("""
            SELECT
                downloads.id,
                downloads.downloaded_at,
                users.username,
                users.email,
                media.title,
                media.media_type,
                media.category
            FROM downloads

            LEFT JOIN users
                ON downloads.user_id = users.id

            LEFT JOIN media
                ON downloads.media_id = media.id

            ORDER BY
                downloads.downloaded_at DESC
        """).fetchall()

    total_downloads = conn.execute("""
        SELECT COUNT(*)
        FROM downloads
    """).fetchone()[0]

    unique_downloaders = conn.execute("""
        SELECT COUNT(
            DISTINCT user_id
        )
        FROM downloads
        WHERE user_id IS NOT NULL
    """).fetchone()[0]

    popular_media = conn.execute("""
        SELECT
            media.title,
            media.media_type,
            media.category,
            COUNT(downloads.id)
                AS download_count

        FROM downloads

        JOIN media
            ON downloads.media_id = media.id

        GROUP BY downloads.media_id

        ORDER BY download_count DESC

        LIMIT 10
    """).fetchall()

    conn.close()

    return render_template(
        "admin_downloads.html",
        downloads=downloads,
        search=search,
        total_downloads=total_downloads,
        unique_downloaders=unique_downloaders,
        popular_media=popular_media
    )


# =========================================================
# UPLOAD MEDIA
# =========================================================

@app.route(
    "/admin/upload",
    methods=["GET", "POST"]
)
def upload():

    if "admin_id" not in session:

        return redirect(
            url_for("admin_login")
        )

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        category = request.form.get(
            "category",
            ""
        ).strip()

        media_type = request.form.get(
            "media_type",
            ""
        )

        file = request.files.get(
            "file"
        )

        thumbnail = request.files.get(
            "thumbnail"
        )

        if not title:

            return "Please enter a title."

        if not file or not file.filename:

            return (
                "Please select a media file."
            )

        filename = secure_filename(
            file.filename
        )

        if not filename:

            return "Invalid filename."

        # -------------------------------------------------
        # DETERMINE MEDIA FOLDER
        # -------------------------------------------------

        if media_type == "video":

            if not allowed_video(
                filename
            ):

                return (
                    "Invalid video file type."
                )

            folder = app.config[
                "VIDEO_FOLDER"
            ]

        elif media_type == "audio":

            if not allowed_audio(
                filename
            ):

                return (
                    "Invalid audio file type."
                )

            folder = app.config[
                "AUDIO_FOLDER"
            ]

        else:

            return "Invalid media type."

        # -------------------------------------------------
        # CREATE UNIQUE FILENAME
        # -------------------------------------------------

        extension = filename.rsplit(
            ".",
            1
        )[1].lower()

        unique_filename = (
            str(uuid.uuid4())
            + "."
            + extension
        )

        filepath = os.path.join(
            folder,
            unique_filename
        )

        file.save(filepath)

        # -------------------------------------------------
        # THUMBNAIL
        # -------------------------------------------------

        thumbnail_filename = None

        if (
            thumbnail
            and
            thumbnail.filename
        ):

            thumbnail_name = (
                secure_filename(
                    thumbnail.filename
                )
            )

            if not allowed_image(
                thumbnail_name
            ):

                if os.path.exists(
                    filepath
                ):

                    os.remove(
                        filepath
                    )

                return (
                    "Invalid thumbnail image."
                )

            thumbnail_extension = (
                thumbnail_name.rsplit(
                    ".",
                    1
                )[1].lower()
            )

            thumbnail_filename = (
                str(uuid.uuid4())
                + "."
                + thumbnail_extension
            )

            thumbnail_path = os.path.join(
                app.config[
                    "THUMBNAIL_FOLDER"
                ],
                thumbnail_filename
            )

            thumbnail.save(
                thumbnail_path
            )

        # -------------------------------------------------
        # SAVE TO DATABASE
        # -------------------------------------------------

        conn = get_db()

        conn.execute("""
            INSERT INTO media
            (
                title,
                description,
                filename,
                media_type,
                category,
                thumbnail
            )
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            title,
            description,
            unique_filename,
            media_type,
            category,
            thumbnail_filename
        ))

        conn.commit()

        conn.close()

        # -------------------------------------------------
        # NOTIFICATION
        # -------------------------------------------------

        create_notification(
            "New media uploaded: "
            + title,
            "upload"
        )

        return redirect(
            url_for("home")
        )

    return render_template(
        "upload.html"
    )


# =========================================================
# DOWNLOAD
# =========================================================

@app.route(
    "/download/<int:media_id>"
)
def download(media_id):

    conn = get_db()

    media = conn.execute("""
        SELECT *
        FROM media
        WHERE id = ?
    """, (
        media_id,
    )).fetchone()

    if not media:

        conn.close()

        return (
            "Media not found.",
            404
        )

    # -----------------------------------------------------
    # DETERMINE FOLDER FIRST
    # -----------------------------------------------------

    if media["media_type"] == "video":

        folder = VIDEO_FOLDER

    elif media["media_type"] == "audio":

        folder = AUDIO_FOLDER

    else:

        conn.close()

        return (
            "Invalid media type.",
            400
        )

    filepath = os.path.join(
        folder,
        media["filename"]
    )

    if not os.path.isfile(filepath):

        conn.close()

        return (
            "File not found on server.",
            404
        )

    # -----------------------------------------------------
    # INCREASE DOWNLOAD COUNT
    # -----------------------------------------------------

    conn.execute("""
        UPDATE media
        SET downloads = downloads + 1
        WHERE id = ?
    """, (
        media_id,
    ))

    # -----------------------------------------------------
    # SAVE USER DOWNLOAD HISTORY
    # -----------------------------------------------------

    if session.get("user_id"):

        conn.execute("""
            INSERT INTO downloads
            (
                user_id,
                media_id
            )
            VALUES (?, ?)
        """, (
            session["user_id"],
            media_id
        ))

    conn.commit()

    conn.close()

    # -----------------------------------------------------
    # NOTIFICATION
    # -----------------------------------------------------

    create_notification(
        "Media downloaded: "
        + media["title"],
        "download"
    )

    return send_from_directory(
        folder,
        media["filename"],
        as_attachment=True
    )


# =========================================================
# MEDIA DETAILS
# =========================================================

@app.route(
    "/media-details/<int:media_id>"
)
def media_details(media_id):

    conn = get_db()

    media = conn.execute("""
        SELECT *
        FROM media
        WHERE id = ?
    """, (
        media_id,
    )).fetchone()

    if not media:

        conn.close()

        return (
            "Media not found.",
            404
        )

    is_favorite = False

    if session.get("user_id"):

        favorite = conn.execute("""
            SELECT id
            FROM favorites
            WHERE user_id = ?
            AND media_id = ?
        """, (
            session["user_id"],
            media_id
        )).fetchone()

        if favorite:

            is_favorite = True

    recommendations = conn.execute("""
        SELECT *
        FROM media
        WHERE category = ?
        AND id != ?
        ORDER BY created_at DESC
        LIMIT 6
    """, (
        media["category"],
        media_id
    )).fetchall()

    conn.close()

    return render_template(
        "media_details.html",
        media=media,
        is_favorite=is_favorite,
        recommendations=recommendations
    )


# =========================================================
# STREAM MEDIA
# =========================================================

@app.route(
    "/media/<int:media_id>"
)
def stream_media(media_id):

    conn = get_db()

    media = conn.execute("""
        SELECT *
        FROM media
        WHERE id = ?
    """, (
        media_id,
    )).fetchone()

    conn.close()

    if media is None:

        return (
            "Media not found.",
            404
        )

    if media["media_type"] == "video":

        folder = app.config[
            "VIDEO_FOLDER"
        ]

    elif media["media_type"] == "audio":

        folder = app.config[
            "AUDIO_FOLDER"
        ]

    else:

        return (
            "Invalid media type.",
            400
        )

    filepath = os.path.join(
        folder,
        media["filename"]
    )

    if not os.path.isfile(filepath):

        return (
            "File not found on server.",
            404
        )

    return send_from_directory(
        folder,
        media["filename"]
    )


# =========================================================
# THUMBNAIL
# =========================================================

@app.route(
    "/thumbnail/<filename>"
)
def thumbnail(filename):

    safe_filename = secure_filename(
        filename
    )

    if not safe_filename:

        return (
            "Invalid thumbnail.",
            400
        )

    filepath = os.path.join(
        app.config[
            "THUMBNAIL_FOLDER"
        ],
        safe_filename
    )

    if not os.path.isfile(filepath):

        return (
            "Thumbnail not found.",
            404
        )

    return send_from_directory(
        app.config[
            "THUMBNAIL_FOLDER"
        ],
        safe_filename
    )


# =========================================================
# EDIT MEDIA
# =========================================================

@app.route(
    "/admin/edit/<int:media_id>",
    methods=["GET", "POST"]
)
def edit_media(media_id):

    if "admin_id" not in session:

        return redirect(
            url_for("admin_login")
        )

    conn = get_db()

    media = conn.execute("""
        SELECT *
        FROM media
        WHERE id = ?
    """, (
        media_id,
    )).fetchone()

    if media is None:

        conn.close()

        return (
            "Media not found.",
            404
        )

    if request.method == "POST":

        title = request.form.get(
            "title",
            ""
        ).strip()

        description = request.form.get(
            "description",
            ""
        ).strip()

        category = request.form.get(
            "category",
            ""
        ).strip()

        if not title:

            conn.close()

            return "Title is required."

        conn.execute("""
            UPDATE media
            SET
                title = ?,
                description = ?,
                category = ?
            WHERE id = ?
        """, (
            title,
            description,
            category,
            media_id
        ))

        conn.commit()

        conn.close()

        return redirect(
            url_for("admin_dashboard")
        )

    conn.close()

    return render_template(
        "edit_media.html",
        media=media
    )


# =========================================================
# DELETE MEDIA
# =========================================================

@app.route(
    "/admin/delete/<int:media_id>",
    methods=["POST"]
)
def delete_media(media_id):

    if "admin_id" not in session:

        return redirect(
            url_for("admin_login")
        )

    conn = get_db()

    media = conn.execute("""
        SELECT *
        FROM media
        WHERE id = ?
    """, (
        media_id,
    )).fetchone()

    if media is None:

        conn.close()

        return (
            "Media not found.",
            404
        )

    media_title = media["title"]

    if media["media_type"] == "video":

        folder = app.config[
            "VIDEO_FOLDER"
        ]

    elif media["media_type"] == "audio":

        folder = app.config[
            "AUDIO_FOLDER"
        ]

    else:

        conn.close()

        return (
            "Invalid media type.",
            400
        )

    file_path = os.path.join(
        folder,
        media["filename"]
    )

    if os.path.isfile(file_path):

        os.remove(file_path)

    if media["thumbnail"]:

        thumbnail_path = os.path.join(
            app.config[
                "THUMBNAIL_FOLDER"
            ],
            media["thumbnail"]
        )

        if os.path.isfile(
            thumbnail_path
        ):

            os.remove(
                thumbnail_path
            )

    conn.execute("""
        DELETE FROM favorites
        WHERE media_id = ?
    """, (
        media_id,
    ))

    conn.execute("""
        DELETE FROM downloads
        WHERE media_id = ?
    """, (
        media_id,
    ))

    conn.execute("""
        DELETE FROM media
        WHERE id = ?
    """, (
        media_id,
    ))

    conn.commit()

    conn.close()

    create_notification(
        "Media deleted: "
        + media_title,
        "delete"
    )

    return redirect(
        url_for("admin_dashboard")
    )


# =========================================================
# CATEGORY
# =========================================================

@app.route(
    "/category/<category_name>"
)
def category(category_name):

    conn = get_db()

    media = conn.execute("""
        SELECT *
        FROM media
        WHERE category = ?
        ORDER BY created_at DESC
    """, (
        category_name,
    )).fetchall()

    conn.close()

    return render_template(
        "category.html",
        media=media,
        category_name=category_name
    )


# =========================================================
# USER REGISTER
# =========================================================

@app.route(
    "/register",
    methods=["GET", "POST"]
)
def register():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        if not username:

            return "Username is required."

        if not email:

            return "Email is required."

        if not password:

            return "Password is required."

        if len(password) < 6:

            return (
                "Password must be at least "
                "6 characters."
            )

        if password != confirm_password:

            return "Passwords do not match."

        hashed_password = (
            generate_password_hash(
                password
            )
        )

        conn = get_db()

        try:

            conn.execute("""
                INSERT INTO users
                (
                    username,
                    email,
                    password
                )
                VALUES (?, ?, ?)
            """, (
                username,
                email,
                hashed_password
            ))

            conn.commit()

        except sqlite3.IntegrityError:

            conn.close()

            return (
                "Username or email already exists."
            )

        conn.close()

        create_notification(
            "A new user has registered: "
            + username,
            "user"
        )

        return redirect(
            url_for("login")
        )

    return render_template(
        "register.html"
    )


# =========================================================
# USER LOGIN
# =========================================================

@app.route(
    "/login",
    methods=["GET", "POST"]
)
def login():

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        password = request.form.get(
            "password",
            ""
        )

        conn = get_db()

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE username = ?
        """, (
            username,
        )).fetchone()

        conn.close()

        if user:

            valid_password = (
                check_password_hash(
                    user["password"],
                    password
                )
            )

        else:

            valid_password = False

        if valid_password:

            session["user_id"] = (
                user["id"]
            )

            session["username"] = (
                user["username"]
            )

            session["user_email"] = (
                user["email"]
            )

            return redirect(
                url_for("home")
            )

        return (
            "Invalid username or password."
        )

    return render_template(
        "login.html"
    )


# =========================================================
# USER LOGOUT
# =========================================================

@app.route("/logout")
def logout():

    session.pop(
        "user_id",
        None
    )

    session.pop(
        "username",
        None
    )

    session.pop(
        "user_email",
        None
    )

    return redirect(
        url_for("home")
    )


# =========================================================
# PROFILE
# =========================================================

@app.route("/profile")
def profile():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    )).fetchone()

    if not user:

        conn.close()

        return redirect(
            url_for("logout")
        )

    downloads = conn.execute("""
        SELECT
            downloads.*,
            media.title,
            media.media_type
        FROM downloads
        JOIN media
            ON downloads.media_id = media.id
        WHERE downloads.user_id = ?
        ORDER BY downloads.downloaded_at DESC
    """, (
        session["user_id"],
    )).fetchall()

    favorites = conn.execute("""
        SELECT
            favorites.*,
            media.title,
            media.media_type,
            media.thumbnail
        FROM favorites
        JOIN media
            ON favorites.media_id = media.id
        WHERE favorites.user_id = ?
        ORDER BY favorites.created_at DESC
    """, (
        session["user_id"],
    )).fetchall()

    conn.close()

    return render_template(
        "profile.html",
        user=user,
        downloads=downloads,
        favorites=favorites
    )


# =========================================================
# ADD FAVORITE
# =========================================================

@app.route(
    "/favorite/<int:media_id>",
    methods=["POST"]
)
def add_favorite(media_id):

    if not session.get("user_id"):

        return redirect(
            url_for("login")
        )

    conn = get_db()

    media = conn.execute("""
        SELECT *
        FROM media
        WHERE id = ?
    """, (
        media_id,
    )).fetchone()

    if not media:

        conn.close()

        return (
            "Media not found.",
            404
        )

    favorite_added = False

    try:

        conn.execute("""
            INSERT INTO favorites
            (
                user_id,
                media_id
            )
            VALUES (?, ?)
        """, (
            session["user_id"],
            media_id
        ))

        conn.commit()

        favorite_added = True

    except sqlite3.IntegrityError:

        conn.rollback()

    conn.close()

    if favorite_added:

        create_notification(
            "Media added to favorites: "
            + media["title"],
            "favorite"
        )

    return redirect(
        request.referrer
        or url_for("home")
    )


# =========================================================
# REMOVE FAVORITE
# =========================================================

@app.route(
    "/unfavorite/<int:media_id>",
    methods=["POST"]
)
def remove_favorite(media_id):

    if not session.get("user_id"):

        return redirect(
            url_for("login")
        )

    conn = get_db()

    conn.execute("""
        DELETE FROM favorites
        WHERE user_id = ?
        AND media_id = ?
    """, (
        session["user_id"],
        media_id
    ))

    conn.commit()

    conn.close()

    return redirect(
        request.referrer
        or url_for("home")
    )


# =========================================================
# EDIT PROFILE
# =========================================================

@app.route(
    "/edit-profile",
    methods=["GET", "POST"]
)
def edit_profile():

    if not session.get("user_id"):

        return redirect(
            url_for("login")
        )

    conn = get_db()

    user = conn.execute("""
        SELECT *
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    )).fetchone()

    if not user:

        conn.close()

        return redirect(
            url_for("logout")
        )

    if request.method == "POST":

        username = request.form.get(
            "username",
            ""
        ).strip()

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        password = request.form.get(
            "password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        if not username:

            conn.close()

            return "Username is required."

        if not email:

            conn.close()

            return "Email is required."

        if password:

            if len(password) < 6:

                conn.close()

                return (
                    "Password must be at least "
                    "6 characters."
                )

            if password != confirm_password:

                conn.close()

                return "Passwords do not match."

            hashed_password = (
                generate_password_hash(
                    password
                )
            )

            try:

                conn.execute("""
                    UPDATE users
                    SET
                        username = ?,
                        email = ?,
                        password = ?
                    WHERE id = ?
                """, (
                    username,
                    email,
                    hashed_password,
                    session["user_id"]
                ))

            except sqlite3.IntegrityError:

                conn.close()

                return (
                    "Username or email already exists."
                )

        else:

            try:

                conn.execute("""
                    UPDATE users
                    SET
                        username = ?,
                        email = ?
                    WHERE id = ?
                """, (
                    username,
                    email,
                    session["user_id"]
                ))

            except sqlite3.IntegrityError:

                conn.close()

                return (
                    "Username or email already exists."
                )

        conn.commit()

        conn.close()

        session["username"] = username

        session["user_email"] = email

        return redirect(
            url_for("profile")
        )

    conn.close()

    return render_template(
        "edit_profile.html",
        user=user
    )


# =========================================================
# UPLOAD PROFILE PICTURE
# =========================================================

@app.route(
    "/profile/upload-picture",
    methods=["POST"]
)
def upload_profile_picture():

    if "user_id" not in session:

        return redirect(
            url_for("login")
        )

    file = request.files.get(
        "profile_picture"
    )

    if not file or file.filename == "":

        return redirect(
            url_for("profile")
        )

    filename = secure_filename(
        file.filename
    )

    if not filename:

        return redirect(
            url_for("profile")
        )

    if not allowed_image(filename):

        return redirect(
            url_for("profile")
        )

    extension = filename.rsplit(
        ".",
        1
    )[1].lower()

    unique_filename = (
        str(uuid.uuid4())
        + "."
        + extension
    )

    filepath = os.path.join(
        PROFILE_FOLDER,
        unique_filename
    )

    file.save(filepath)

    conn = get_db()

    user = conn.execute("""
        SELECT profile_picture
        FROM users
        WHERE id = ?
    """, (
        session["user_id"],
    )).fetchone()

    # -----------------------------------------------------
    # DELETE OLD PROFILE PICTURE
    # -----------------------------------------------------

    if user and user["profile_picture"]:

        old_file = os.path.join(
            PROFILE_FOLDER,
            user["profile_picture"]
        )

        if os.path.exists(old_file):

            os.remove(old_file)

    # -----------------------------------------------------
    # SAVE NEW PROFILE PICTURE
    # -----------------------------------------------------

    conn.execute("""
        UPDATE users
        SET profile_picture = ?
        WHERE id = ?
    """, (
        unique_filename,
        session["user_id"]
    ))

    conn.commit()

    conn.close()

    return redirect(
        url_for("profile")
    )


# =========================================================
# PROFILE PICTURE
# =========================================================

@app.route(
    "/profile-picture/<filename>"
)
def profile_picture(filename):

    safe_filename = secure_filename(
        filename
    )

    if not safe_filename:

        return (
            "Invalid profile picture.",
            400
        )

    filepath = os.path.join(
        PROFILE_FOLDER,
        safe_filename
    )

    if not os.path.isfile(filepath):

        return (
            "Profile picture not found.",
            404
        )

    return send_from_directory(
        PROFILE_FOLDER,
        safe_filename
    )


# =========================================================
# FORGOT PASSWORD
# =========================================================

@app.route(
    "/forgot-password",
    methods=["GET", "POST"]
)
def forgot_password():

    if request.method == "POST":

        # -------------------------------------------------
        # GET EMAIL
        # -------------------------------------------------

        email = request.form.get(
            "email",
            ""
        ).strip().lower()

        if not email:

            return render_template(
                "forgot_password.html",
                error=(
                    "Please enter your email address."
                )
            )

        conn = get_db()

        # -------------------------------------------------
        # FIND USER
        # -------------------------------------------------

        user = conn.execute("""
            SELECT *
            FROM users
            WHERE LOWER(TRIM(email)) = ?
        """, (
            email,
        )).fetchone()

        if not user:

            conn.close()

            return render_template(
                "forgot_password.html",
                error=(
                    "No account was found "
                    "with that email."
                )
            )

        # -------------------------------------------------
        # INVALIDATE OLD TOKENS
        # -------------------------------------------------

        conn.execute("""
            UPDATE password_resets
            SET used = 1
            WHERE user_id = ?
            AND used = 0
        """, (
            user["id"],
        ))

        # -------------------------------------------------
        # CREATE NEW SECURE TOKEN
        # -------------------------------------------------

        token = secrets.token_urlsafe(
            32
        )

        expires_at = (
            datetime.now()
            + timedelta(minutes=30)
        )

        # -------------------------------------------------
        # SAVE TOKEN
        # -------------------------------------------------

        conn.execute("""
            INSERT INTO password_resets
            (
                user_id,
                token,
                expires_at,
                used
            )
            VALUES (?, ?, ?, 0)
        """, (
            user["id"],
            token,
            expires_at
        ))

        conn.commit()

        conn.close()

        # -------------------------------------------------
        # CREATE RESET LINK
        # -------------------------------------------------

        reset_link = url_for(
            "reset_password",
            token=token,
            _external=True
        )

        print(
            "RESET LINK:",
            reset_link
        )

        # -------------------------------------------------
        # SEND EMAIL
        # -------------------------------------------------

        email_sent = send_reset_email(
            user["email"],
            reset_link
        )

        if not email_sent:

            return render_template(
                "forgot_password.html",
                error=(
                    "We could not send the reset email. "
                    "Check the Pydroid terminal for "
                    "the exact EMAIL ERROR."
                )
            )

        return render_template(
            "forgot_password.html",
            success=(
                "A password reset link has been "
                "sent to your email."
            )
        )

    return render_template(
        "forgot_password.html"
    )


# =========================================================
# RESET PASSWORD
# =========================================================

@app.route(
    "/reset-password/<token>",
    methods=["GET", "POST"]
)
def reset_password(token):

    conn = get_db()

    # -----------------------------------------------------
    # FIND RESET TOKEN
    # -----------------------------------------------------

    reset = conn.execute("""
        SELECT
            password_resets.*,
            users.email
        FROM password_resets
        JOIN users
            ON password_resets.user_id = users.id
        WHERE password_resets.token = ?
        AND password_resets.used = 0
    """, (
        token,
    )).fetchone()

    if not reset:

        conn.close()

        return render_template(
            "reset_password.html",
            error=(
                "This password reset link is "
                "invalid or has already been used."
            )
        )

    # -----------------------------------------------------
    # CHECK EXPIRATION
    # -----------------------------------------------------

    try:

        expires_at = datetime.fromisoformat(
            reset["expires_at"]
        )

    except (
        ValueError,
        TypeError
    ):

        conn.close()

        return render_template(
            "reset_password.html",
            error="Invalid reset token."
        )

    if datetime.now() > expires_at:

        conn.execute("""
            UPDATE password_resets
            SET used = 1
            WHERE id = ?
        """, (
            reset["id"],
        ))

        conn.commit()

        conn.close()

        return render_template(
            "reset_password.html",
            error=(
                "This password reset link "
                "has expired. Please request "
                "a new one."
            )
        )

    # -----------------------------------------------------
    # PROCESS NEW PASSWORD
    # -----------------------------------------------------

    if request.method == "POST":

        new_password = request.form.get(
            "new_password",
            ""
        )

        confirm_password = request.form.get(
            "confirm_password",
            ""
        )

        # -------------------------------------------------
        # EMPTY FIELDS
        # -------------------------------------------------

        if not new_password:

            conn.close()

            return render_template(
                "reset_password.html",
                error=(
                    "Please enter a new password."
                ),
                token=token
            )

        if not confirm_password:

            conn.close()

            return render_template(
                "reset_password.html",
                error=(
                    "Please confirm your "
                    "new password."
                ),
                token=token
            )

        # -------------------------------------------------
        # PASSWORD LENGTH
        # -------------------------------------------------

        if len(new_password) < 6:

            conn.close()

            return render_template(
                "reset_password.html",
                error=(
                    "Password must be at least "
                    "6 characters."
                ),
                token=token
            )

        # -------------------------------------------------
        # PASSWORD MATCH
        # -------------------------------------------------

        if new_password != confirm_password:

            conn.close()

            return render_template(
                "reset_password.html",
                error=(
                    "Passwords do not match."
                ),
                token=token
            )

        # -------------------------------------------------
        # GET CURRENT PASSWORD
        # -------------------------------------------------

        user = conn.execute("""
            SELECT password
            FROM users
            WHERE id = ?
        """, (
            reset["user_id"],
        )).fetchone()

        if not user:

            conn.close()

            return render_template(
                "reset_password.html",
                error="User account not found."
            )

        # -------------------------------------------------
        # MAKE SURE PASSWORD IS DIFFERENT
        # -------------------------------------------------

        if check_password_hash(
            user["password"],
            new_password
        ):

            conn.close()

            return render_template(
                "reset_password.html",
                error=(
                    "Your new password must be "
                    "different from your old password."
                ),
                token=token
            )

        # -------------------------------------------------
        # HASH NEW PASSWORD
        # -------------------------------------------------

        hashed_password = (
            generate_password_hash(
                new_password
            )
        )

        # -------------------------------------------------
        # UPDATE PASSWORD
        # -------------------------------------------------

        conn.execute("""
            UPDATE users
            SET password = ?
            WHERE id = ?
        """, (
            hashed_password,
            reset["user_id"]
        ))

        # -------------------------------------------------
        # MARK TOKEN USED
        # -------------------------------------------------

        conn.execute("""
            UPDATE password_resets
            SET used = 1
            WHERE id = ?
        """, (
            reset["id"],
        ))

        # -------------------------------------------------
        # INVALIDATE OTHER RESET TOKENS
        # -------------------------------------------------

        conn.execute("""
            UPDATE password_resets
            SET used = 1
            WHERE user_id = ?
            AND id != ?
            AND used = 0
        """, (
            reset["user_id"],
            reset["id"]
        ))

        conn.commit()

        conn.close()

        return render_template(
            "reset_password.html",
            success=(
                "Your password has been reset "
                "successfully. You can now log in."
            )
        )

    # -----------------------------------------------------
    # SHOW RESET PAGE
    # -----------------------------------------------------

    conn.close()

    return render_template(
        "reset_password.html",
        token=token
    )


# =========================================================
# RUN APP
# =========================================================

# =========================================================
# INITIALIZE DATABASE
# =========================================================

init_db()


# =========================================================
# RUN APP LOCALLY
# =========================================================

if __name__ == "__main__":
    app.run(
        host="0.0.0.0",
        port=5000
    )