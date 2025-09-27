# app.py  (FULL RafikiFlix with Google Drive + YouTube integration)
from flask import Flask, request, send_from_directory, redirect, url_for, session, Response, render_template_string
from werkzeug.utils import secure_filename
from werkzeug.security import check_password_hash, generate_password_hash
import os, time, json, io, requests
from functools import wraps
from dotenv import load_dotenv

# Google API imports
from googleapiclient.discovery import build
from google.oauth2 import service_account
from googleapiclient.http import MediaIoBaseDownload

# ----------------- INIT -----------------
load_dotenv()
app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", os.urandom(24))

# ----------------- CONFIG -----------------
UPLOAD_FOLDER = "videos"
ALLOWED_EXTENSIONS = {"mp4", "mov", "avi", "mkv", "jpg", "jpeg", "png", "gif"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# Load admin credentials from environment
ADMIN_PHONE = os.getenv("ADMIN_PHONE")
ADMIN_PASSWORD_HASH = os.getenv("ADMIN_PASSWORD_HASH")

if not ADMIN_PHONE or not ADMIN_PASSWORD_HASH:
    print("⚠️ Please set ADMIN_PHONE and ADMIN_PASSWORD_HASH in .env or Render environment")
    exit(1)

# Ensure local folders exist
if not os.path.exists(UPLOAD_FOLDER):
    os.makedirs(UPLOAD_FOLDER)

# ----------------- GOOGLE DRIVE CONFIG -----------------
# Determine service account file path:
# Prefer environment variable GOOGLE_SERVICE_ACCOUNT_FILE (set in Render)
SERVICE_ACCOUNT_FILE = os.getenv("GOOGLE_SERVICE_ACCOUNT_FILE")

# Fallback common names (if running locally)
if not SERVICE_ACCOUNT_FILE:
    # common local filename (if you put the JSON in project root for local testing)
    if os.path.exists("rafikiflix-service.json"):
        SERVICE_ACCOUNT_FILE = "rafikiflix-service.json"
    elif os.path.exists("service_account.json"):
        SERVICE_ACCOUNT_FILE = "service_account.json"
    else:
        # try Render default mount location if you uploaded secret file there
        if os.path.exists("/etc/secrets/rafikiflix-service.json"):
            SERVICE_ACCOUNT_FILE = "/etc/secrets/rafikiflix-service.json"
        elif os.path.exists("/etc/secrets/service_account.json"):
            SERVICE_ACCOUNT_FILE = "/etc/secrets/service_account.json"

if SERVICE_ACCOUNT_FILE and os.path.exists(SERVICE_ACCOUNT_FILE):
    try:
        SCOPES = ['https://www.googleapis.com/auth/drive.readonly']
        creds = service_account.Credentials.from_service_account_file(
            SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )
        drive_service = build('drive', 'v3', credentials=creds)
    except Exception as e:
        print("⚠️ Error initializing Google Drive client:", e)
        drive_service = None
else:
    print("⚠️ Service account JSON NOT found. Google Drive features will be disabled.")
    drive_service = None

# Set your Drive folder ID (we fetched earlier)
FOLDER_ID = os.getenv("DRIVE_FOLDER_ID", "13TQeux9PEwkyOZqtZ2qRMJwn4zbL6PsI")

# ----------------- YOUTUBE CONFIG -----------------
YOUTUBE_API_KEY = os.getenv("YOUTUBE_API_KEY")      # set this on Render env
YOUTUBE_CHANNEL_ID = os.getenv("YOUTUBE_CHANNEL_ID")  # set this on Render env
print("DEBUG YouTube API KEY:", YOUTUBE_API_KEY)
print("DEBUG YouTube Channel ID:", YOUTUBE_CHANNEL_ID)

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
                .button {{ background-color: #ff6600; color: white; padding: 20px 40px; font-size: 50px; border: none; border-radius: 10px; cursor: pointer; text-decoration: none; margin: 0 10px; }}
                .button:hover {{ background-color: #ff8533; }}
                .admin-btn {{ position: fixed; top: 20px; right: 20px; background-color: #333; color: white; padding:10px 15px; text-decoration:none; border-radius:5px; }}
            </style>
        </head>
        <body>
            <a href="/videos" class="button">RafikiFlix</a>
            <a href="/drive_gallery" class="button">Drive Gallery</a>
            <a href="/youtube_channel" class="button">YouTube Channel</a>
            <a href="/admin/login" class="admin-btn">Admin</a>
            {FLOATING_ICONS}
        </body>
    </html>
    """

# ----------------- GOOGLE DRIVE: helper to stream file using service account -----------------
def stream_drive_file_gen(file_id, chunk_size=1024*512):
    """
    Generator that downloads a Drive file in chunks and yields them progressively.
    """
    if not drive_service:
        yield b''
        return

    request = drive_service.files().get_media(fileId=file_id)
    fh = io.BytesIO()
    downloader = MediaIoBaseDownload(fh, request, chunksize=chunk_size)
    done = False
    last_pos = 0
    try:
        while not done:
            status, done = downloader.next_chunk()
            cur_pos = fh.tell()
            if cur_pos > last_pos:
                fh.seek(last_pos)
                chunk = fh.read(cur_pos - last_pos)
                last_pos = cur_pos
                yield chunk
        # final chunk (if any left)
        fh.seek(last_pos)
        final = fh.read()
        if final:
            yield final
    except Exception as e:
        # on error just stop generator
        print("Drive download error:", e)
        return

@app.route("/drive_stream/<file_id>")
def drive_stream(file_id):
    # get file metadata for content-type and file name
    try:
        meta = drive_service.files().get(fileId=file_id, fields="name, mimeType").execute()
        mime = meta.get("mimeType", "application/octet-stream")
        name = meta.get("name", file_id)
    except Exception as e:
        return f"Error fetching file metadata: {e}", 404

    headers = {"Content-Disposition": f'inline; filename="{name}"'}
    return Response(stream_drive_file_gen(file_id), mimetype=mime, headers=headers)

# ----------------- GOOGLE DRIVE GALLERY -----------------
@app.route("/drive_gallery")
def drive_gallery():
    if not drive_service:
        return "<h3>Google Drive is not configured. Upload the service account file or set GOOGLE_SERVICE_ACCOUNT_FILE.</h3>"

    # List files in folder
    query = f"'{FOLDER_ID}' in parents and trashed=false"
    try:
        results = drive_service.files().list(q=query, fields="files(id, name, mimeType)").execute()
        files = results.get("files", [])
    except Exception as e:
        return f"<h3>Error listing Drive folder: {e}</h3>"

    template = """
    <!doctype html>
    <html>
    <head>
      <title>Drive Gallery</title>
      <style>
        body {{ font-family: Arial; background:#111; color:#ff9900; text-align:center; }}
        .card {{ background:#222; padding:15px; margin:20px auto; width:720px; border-radius:8px; }}
        video, img {{ margin-top:10px; border-radius:6px; max-width:100%; }}
        a.back {{ color:#aaa; display:block; margin-top:20px; }}
      </style>
    </head>
    <body>
      <h1>Google Drive Files</h1>
      {% for file in files %}
        <div class="card">
          <h3>{{ file['name'] }}</h3>
          {% if "video" in file['mimeType'] %}
            <video controls>
              <source src="/drive_stream/{{ file['id'] }}" type="{{ file['mimeType'] }}">
            </video>
          {% elif "image" in file['mimeType'] %}
            <img src="/drive_stream/{{ file['id'] }}" alt="{{ file['name'] }}" />
          {% else %}
            <a href="/drive_stream/{{ file['id'] }}" target="_blank">Download / Open</a>
          {% endif %}
        </div>
      {% endfor %}
      <a class="back" href="/">← Back to home</a>
      {{ floating|safe }}
    </body>
    </html>
    """
    return render_template_string(template, files=files, floating=FLOATING_ICONS)

# ----------------- YOUTUBE CHANNEL LISTING -----------------
@app.route("/youtube_channel")
def youtube_channel():
    if not YOUTUBE_API_KEY or not YOUTUBE_CHANNEL_ID:
        return "<h3>YouTube API key or Channel ID not configured. Set YOUTUBE_API_KEY and YOUTUBE_CHANNEL_ID in environment.</h3>"

    # fetch recent videos
    url = ("https://www.googleapis.com/youtube/v3/search"
           "?part=snippet&order=date&maxResults=12&type=video"
           f"&channelId={YOUTUBE_CHANNEL_ID}&key={YOUTUBE_API_KEY}")
    try:
        r = requests.get(url, timeout=10)
        data = r.json()
    except Exception as e:
        return f"<h3>Error calling YouTube API: {e}</h3>"

    videos = []
    for item in data.get("items", []):
        vid = item.get("id", {}).get("videoId")
        title = item.get("snippet", {}).get("title")
        if vid:
            videos.append({"id": vid, "title": title})

    # render embedded list
    tpl = """
    <!doctype html>
    <html><head><title>YouTube Channel</title>
    <style>body{{background:#111;color:#ff9900;font-family:Arial;text-align:center}} .video{{margin:20px;}}</style>
    </head><body>
    <h1>YouTube Channel Videos</h1>
    {% for v in videos %}
      <div class="video">
        <h3>{{ v.title }}</h3>
        <iframe width="640" height="360" src="https://www.youtube.com/embed/{{ v.id }}" frameborder="0" allow="accelerometer; autoplay; encrypted-media; gyroscope; picture-in-picture" allowfullscreen></iframe>
      </div>
    {% endfor %}
    <a href="/" style="color:#ccc">← Back</a>
    {{ floating|safe }}
    </body></html>
    """
    return render_template_string(tpl, videos=videos, floating=FLOATING_ICONS)

# ----------------- ORIGINAL VIDEOS PAGE (local files) -----------------
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
        # Only show video tag for local video file types
        ext = video.rsplit(".", 1)[-1].lower()
        if ext in ("mp4","mov","avi","mkv"):
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
        else:
            # show link for other file types
            video_html += f"<div style='margin:20px;'><h3>{video} {category_label} - {count} views</h3><a href='{video_path}'>Open</a></div>"

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
                <input type="file" name="video" accept="video/*,image/*" required><br><br>
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
    # For local testing you may run debug=True, but on Render run via gunicorn.
    app.run(debug=True)
