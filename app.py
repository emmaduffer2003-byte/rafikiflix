from flask import Flask, request, send_from_directory, redirect, url_for, session, Response
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
import os, time, json
from functools import wraps
from dotenv import load_dotenv

# ----------------- INIT -----------------
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))  # secure key

# ----------------- CONFIG -----------------
UPLOAD_FOLDER = "videos"
ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "mkv"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Load admin credentials
ADMIN_PHONE = os.getenv("ADMIN_PHONE")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")

if not ADMIN_PHONE or not ADMIN_PASSWORD_HASH:
    print("⚠️ Please set ADMIN_PHONE and ADMIN_PASSWORD_HASH in .env")
    exit(1)

# Ensure folders exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ----------------- VIEW COUNTER -----------------
VIEWS_FILE = "views.json"

def load_views():
    if os.path.exists(VIEWS_FILE):
        with open(VIEWS_FILE, "r") as f:
            return json.load(f)
    return {}

def save_views(data):
    with open(VIEWS_FILE, "w") as f:
        json.dump(data, f)

def increment_view(video_key):
    views = load_views()
    views[video_key] = views.get(video_key, 0) + 1
    save_views(views)
    return views[video_key]

# ----------------- HELPERS -----------------
def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def admin_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get("admin_logged_in"):
            return redirect(url_for("admin_login"))
        return f(*args, **kwargs)
    return decorated_function

def get_categories():
    categories = [d for d in os.listdir(UPLOAD_FOLDER) if os.path.isdir(os.path.join(UPLOAD_FOLDER, d))]
    categories.sort()
    return categories

# ----------------- FLOATING ICONS -----------------
FLOATING_ICONS = """
<div style="
    position: fixed;
    bottom: 20px;
    right: 20px;
    display: flex;
    flex-direction: column;
    gap: 15px;
    z-index: 1000;
">
    <a href="https://wa.me/250782973514" target="_blank">
        <img src="https://upload.wikimedia.org/wikipedia/commons/6/6b/WhatsApp.svg" 
             alt="WhatsApp" style="width:70px; height:70px; transition: transform 0.3s;">
    </a>
    <a href="https://www.youtube.com/@dokurise" target="_blank">
        <img src="https://upload.wikimedia.org/wikipedia/commons/b/b8/YouTube_Logo_2017.svg" 
             alt="YouTube" style="width:70px; height:70px; transition: transform 0.3s;">
    </a>
</div>
<script>
    const icons = document.querySelectorAll('img');
    icons.forEach(icon => {
        icon.addEventListener('mouseenter', () => { icon.style.transform = 'scale(1.2)'; });
        icon.addEventListener('mouseleave', () => { icon.style.transform = 'scale(1)'; });
    });
</script>
"""

# ----------------- HOME -----------------
@app.route("/")
def home():
    return f"""
    <html>
        <head>
            <title>RafikiFlix</title>
            <style>
                body {{ display: flex; justify-content: center; align-items: center; height: 100vh; background-color: #1a1a1a; font-family: Arial, sans-serif; }}
                .button {{ background-color: #ff6600; color: white; padding: 20px 40px; font-size: 50px; border: none; border-radius: 10px; cursor: pointer; text-decoration: none; }}
                .button:hover {{ background-color: #ff8533; }}
                .admin-btn {{ position: fixed; top: 20px; right: 20px; background-color: #333; color: white; padding:10px 15px; text-decoration:none; border-radius:5px; }}
            </style>
        </head>
        <body>
            <a href="/videos" class="button">RafikiFlix</a>
            <a href="/admin/login" class="admin-btn">Admin</a>
            {FLOATING_ICONS}
        </body>
    </html>
    """

# ----------------- VIDEOS -----------------
@app.route("/videos")
def videos():
    search_query = request.args.get("search", "").lower()
    selected_category = request.args.get("category", "")

    categories = get_categories()
    categories.insert(0, "All")

    video_files = []
    if selected_category and selected_category != "All":
        category_path = os.path.join(UPLOAD_FOLDER, selected_category)
        video_files = [(f, selected_category) for f in os.listdir(category_path) if os.path.isfile(os.path.join(category_path, f))]
    else:
        video_files += [(f, "") for f in os.listdir(UPLOAD_FOLDER) if os.path.isfile(os.path.join(UPLOAD_FOLDER, f))]
        for cat in categories:
            if cat == "All": continue
            cat_path = os.path.join(UPLOAD_FOLDER, cat)
            video_files += [(f, cat) for f in os.listdir(cat_path) if os.path.isfile(os.path.join(cat_path, f))]

    filtered_videos = [(video, cat) for video, cat in video_files if search_query in video.lower()]
    views = load_views()

    video_html = ""
    for video, cat in filtered_videos:
        category_label = f"[{cat}]" if cat else ""
        video_path = f"/videos/{cat}/{video}" if cat else f"/videos/{video}"
        video_key = f"{cat}/{video}" if cat else video
        count = views.get(video_key, 0)
        video_html += f"""
        <div style='margin:20px;'>
            <h3>{video} {category_label} - {count} views</h3>
            <video width='600' controls>
                <source src='{video_path}' type='video/mp4'>
                Your browser does not support the video tag.
            </video>
            <br>
            <a href='/download/{cat}/{video}' style='color:#ff6600; font-size:18px;'>⬇ Download</a>
        </div>
        """

    category_html = ""
    for cat in categories:
        active = "style='background-color:#ff8533;'" if cat == selected_category else ""
        category_html += f"<a href='/videos?category={cat}' class='category' {active}>{cat}</a>"

    return f"""
    <html>
        <head>
            <title>RafikiFlix Videos</title>
            <style>
                body {{ font-family: Arial, sans-serif; background-color: #1a1a1a; color: #ff6600; text-align: center; }}
                h1 {{ font-size: 50px; }}
                .category {{ display: inline-block; margin: 10px 20px; padding: 15px 25px; background-color: #333; border-radius: 10px; font-size: 25px; cursor: pointer; text-decoration: none; color: #ff6600; }}
                .category:hover {{ background-color: #444; }}
                input[type='text'] {{ padding: 10px; width: 300px; font-size:18px; border-radius:5px; border:none; }}
                input[type='submit'] {{ padding: 10px 20px; font-size:18px; cursor:pointer; border-radius:5px; border:none; background-color:#ff6600; color:white; }}
            </style>
        </head>
        <body>
            <h1>RafikiFlix Videos</h1>

            <form method='get'>
                <input type='text' name='search' placeholder='Search videos...' value='{search_query}'>
                <input type='submit' value='Search'>
            </form>

            <h2>Categories</h2>
            {category_html}

            <h2>Uploaded Videos</h2>
            {video_html}

            {FLOATING_ICONS}
        </body>
    </html>
    """

# ----------------- SERVE FILES -----------------
@app.route('/videos/<category>/<path:filename>')
@app.route('/videos/<path:filename>')
def serve_video(filename, category=None):
    path = os.path.join(UPLOAD_FOLDER, category, filename) if category else os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(path):
        video_key = f"{category}/{filename}" if category else filename
        increment_view(video_key)  # count views
        return send_from_directory(os.path.dirname(path), os.path.basename(path))
    return "File not found", 404

# ----------------- THROTTLED DOWNLOAD -----------------
def stream_file(path, chunk_size=1024, speed_limit=200*1024):
    def generate():
        with open(path, "rb") as f:
            while True:
                data = f.read(chunk_size)
                if not data:
                    break
                yield data
                time.sleep(chunk_size / speed_limit)
    return Response(generate(), headers={
        "Content-Disposition": f"attachment; filename={os.path.basename(path)}"
    }, mimetype="application/octet-stream")

@app.route('/download/<category>/<path:filename>')
@app.route('/download/<path:filename>')
def download_video(filename, category=None):
    path = os.path.join(UPLOAD_FOLDER, category, filename) if category else os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(path):
        return stream_file(path)
    return "File not found", 404

# ----------------- ADMIN LOGIN -----------------
@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        phone = request.form.get("phone")
        password = request.form.get("password")
        if phone == ADMIN_PHONE and check_password_hash(ADMIN_PASSWORD_HASH, password):
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))
        return "Incorrect credentials. <a href='/admin/login'>Try again</a>"
    return """
    <html>
        <body style="background-color:#1a1a1a; color:#ff6600; font-family:Arial; text-align:center;">
            <h1>Admin Login</h1>
            <form method="post">
                <label>Phone:</label><br><input type="text" name="phone" required><br><br>
                <label>Password:</label><br><input type="password" name="password" required><br><br>
                <input type="submit" value="Login" style="padding:10px 20px; font-size:18px; cursor:pointer;">
            </form>
        </body>
    </html>
    """

# ----------------- ADMIN LOGOUT -----------------
@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("home"))

# ----------------- ADMIN DASHBOARD -----------------
@app.route("/admin/dashboard", methods=["GET", "POST"])
@admin_required
def admin_dashboard():
    msg = ""

    if request.method == "POST":
        file = request.files.get("video")
        category = secure_filename(request.form.get("category", "").strip())
        new_category = secure_filename(request.form.get("new_category", "").strip())

        if new_category:
            category = new_category

        save_path = os.path.join(UPLOAD_FOLDER, category) if category else UPLOAD_FOLDER
        if file and allowed_file(file.filename):
            if not os.path.exists(save_path):
                os.makedirs(save_path)
            filename = secure_filename(file.filename)
            file.save(os.path.join(save_path, filename))
            msg = f"Uploaded successfully: {filename} → {category or 'root'}"
        else:
            msg = "Invalid file type or no file selected."

    video_html = ""
    for video in [f for f in os.listdir(UPLOAD_FOLDER) if os.path.isfile(os.path.join(UPLOAD_FOLDER, f))]:
        video_html += f'<div style="margin:20px;"><h3>{video}</h3><a href="/admin/delete/{video}" style="color:#ff6600;">Delete</a></div>'

    for cat in get_categories():
        for video in [f for f in os.listdir(os.path.join(UPLOAD_FOLDER, cat)) if os.path.isfile(os.path.join(UPLOAD_FOLDER, cat, f))]:
            video_html += f'<div style="margin:20px;"><h3>{video} [{cat}]</h3><a href="/admin/delete/{cat}/{video}" style="color:#ff6600;">Delete</a></div>'

    category_options = "".join([f'<option value="{cat}">{cat}</option>' for cat in get_categories()])

    return f"""
    <html>
        <body style="font-family:Arial; background-color:#1a1a1a; color:#ff6600; text-align:center;">
            <h1>Admin Dashboard</h1>
            <p>{msg}</p>

            <h2>Upload Video</h2>
            <form method="post" enctype="multipart/form-data">
                <input type="file" name="video" accept="video/*" required><br><br>
                <label>Select Category:</label>
                <select name="category">
                    <option value="">None</option>
                    {category_options}
                </select><br><br>
                <label>Or Create New Category:</label>
                <input type="text" name="new_category" placeholder="New Category"><br><br>
                <input type="submit" value="Upload" style="padding:10px 20px; font-size:18px; cursor:pointer;">
            </form>

            <h2>Delete Videos</h2>
            {video_html}

            <br><a href="/admin/logout" style="color:#ff6600;">Logout</a>
        </body>
    </html>
    """

# ----------------- DELETE VIDEO -----------------
@app.route("/admin/delete/<path:filename>")
@app.route("/admin/delete/<category>/<path:filename>")
@admin_required
def delete_video(filename, category=None):
    path = os.path.join(UPLOAD_FOLDER, category, filename) if category else os.path.join(UPLOAD_FOLDER, filename)
    if os.path.exists(path):
        os.remove(path)
    return redirect(url_for("admin_dashboard"))

# ----------------- RUN APP -----------------
if __name__ == "__main__":
    app.run(debug=True)
