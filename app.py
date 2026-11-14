import csv
import io
import os
import random
import sqlite3
from datetime import datetime
from functools import wraps

import qrcode
from flask import (
    Flask,
    Response,
    flash,
    g,
    jsonify,
    redirect,
    render_template,
    request,
    send_file,
    session,
    url_for,
)
from werkzeug.security import check_password_hash, generate_password_hash
from werkzeug.utils import secure_filename

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "eco_map.db")
QR_DIR = os.path.join(BASE_DIR, "static", "qr")
UPLOAD_DIR = os.path.join(BASE_DIR, "static", "uploads")
ALLOWED_PHOTOS = {".jpg", ".jpeg", ".png", ".webp"}
PER_PAGE = 12

# 237-maktab (Toshkent) atrofidagi demo koordinatalar
SCHOOL = {
    "name": "237-maktab",
    "lat": 41.32585,
    "lng": 69.26742,
}

app = Flask(__name__)
app.secret_key = "eco-map-237-maktab-2026-yashil-makon"

SPECIES = [
    {"name": "Chinor", "oxygen": 118, "share": 0.28, "photo": "chinor"},
    {"name": "Eman", "oxygen": 102, "share": 0.18, "photo": "eman"},
    {"name": "Archa", "oxygen": 86, "share": 0.22, "photo": "archa"},
    {"name": "Kashtan", "oxygen": 94, "share": 0.12, "photo": "kashtan"},
    {"name": "Terak", "oxygen": 72, "share": 0.10, "photo": "terak"},
    {"name": "Qayrag'och", "oxygen": 78, "share": 0.10, "photo": "qayragoch"},
]


def get_db():
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row
    return g.db


@app.teardown_appcontext
def close_db(_exc):
    db = g.pop("db", None)
    if db is not None:
        db.close()


def query_all(sql, args=()):
    return get_db().execute(sql, args).fetchall()


def query_one(sql, args=()):
    return get_db().execute(sql, args).fetchone()


def as_dicts(rows):
    return [dict(r) for r in rows]


def login_required(fn):
    @wraps(fn)
    def wrapper(*args, **kwargs):
        if not session.get("user"):
            flash("Daraxt qo‘shish va boshqaruv uchun tizimga kiring.", "info")
            return redirect(url_for("kirish", next=request.path))
        return fn(*args, **kwargs)

    return wrapper


def safe_next(value, fallback):
    if value and value.startswith("/") and not value.startswith("//"):
        return value
    return fallback


def init_db():
    os.makedirs(QR_DIR, exist_ok=True)
    os.makedirs(UPLOAD_DIR, exist_ok=True)
    db = sqlite3.connect(DB_PATH)
    db.executescript(
        """
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password_hash TEXT NOT NULL,
            full_name TEXT NOT NULL,
            role TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS zones (
            id INTEGER PRIMARY KEY,
            name TEXT NOT NULL,
            zone_type TEXT NOT NULL,
            area_m2 REAL NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            status TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS trees (
            id INTEGER PRIMARY KEY,
            public_code TEXT UNIQUE NOT NULL,
            species_name TEXT NOT NULL,
            planted_year INTEGER NOT NULL,
            latitude REAL NOT NULL,
            longitude REAL NOT NULL,
            health_status TEXT NOT NULL,
            height_m REAL NOT NULL,
            trunk_diameter REAL,
            photo_key TEXT NOT NULL,
            oxygen_kg REAL NOT NULL,
            last_updated TEXT NOT NULL,
            zone_id INTEGER,
            notes TEXT
        );
        CREATE TABLE IF NOT EXISTS reports (
            id INTEGER PRIMARY KEY,
            title TEXT NOT NULL,
            description TEXT NOT NULL,
            status TEXT NOT NULL,
            created_at TEXT NOT NULL,
            reporter TEXT,
            tree_id INTEGER,
            latitude REAL,
            longitude REAL,
            photo_url TEXT
        );
        """
    )
    cols = [r[1] for r in db.execute("PRAGMA table_info(reports)").fetchall()]
    if "photo_url" not in cols:
        db.execute("ALTER TABLE reports ADD COLUMN photo_url TEXT")
    if db.execute("SELECT COUNT(*) FROM users").fetchone()[0] == 0:
        db.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?,?,?,?)",
            (
                "admin",
                generate_password_hash("ecomap2026", method="pbkdf2:sha256"),
                "Eko-patrul administratori",
                "admin",
            ),
        )
        db.execute(
            "INSERT INTO users (username, password_hash, full_name, role) VALUES (?,?,?,?)",
            (
                "oquvchi",
                generate_password_hash("237maktab", method="pbkdf2:sha256"),
                "237-maktab o‘quvchisi",
                "student",
            ),
        )
    if db.execute("SELECT COUNT(*) FROM trees").fetchone()[0] == 0:
        seed_data(db)
    db.commit()
    db.close()


def seed_data(db):
    rng = random.Random(237)
    zone_names = [
        "Maktab hovlisi — asosiy",
        "Futbol maydoni atrofi",
        "Kirish darvozasi xiyoboni",
        "1-sektor chinorlar",
        "2-sektor archazor",
        "Mahalla guzari bog‘i",
        "Stadion yashil halqasi",
        "O‘qituvchilar hovlisi",
        "Boshlang‘ich sinflar hovlisi",
        "Kitobxona oldi",
        "Sport zal orqasi",
        "Mahalla 12-uy ko‘chasi",
        "Mahalla 8-tor ko‘cha",
        "Ichki hovuz atrofi",
        "Avtoturargoh yashil lentasi",
        "Yosh nihollar maydoni",
        "Eman xiyoboni",
        "Kashtan yo‘lakchasi",
    ]
    zones = []
    for i, name in enumerate(zone_names, start=1):
        lat = SCHOOL["lat"] + rng.uniform(-0.0045, 0.0045)
        lng = SCHOOL["lng"] + rng.uniform(-0.006, 0.006)
        status = "Sog‘lom" if i % 7 else "Parvarish talab"
        zones.append((name, "Yashil hudud", rng.randint(420, 3800), lat, lng, status))
    db.executemany(
        "INSERT INTO zones (name, zone_type, area_m2, latitude, longitude, status) VALUES (?,?,?,?,?,?)",
        zones,
    )

    species_pool = []
    for spec in SPECIES:
        species_pool.extend([spec] * int(round(spec["share"] * 1248)))
    while len(species_pool) < 1248:
        species_pool.append(SPECIES[0])
    species_pool = species_pool[:1248]
    rng.shuffle(species_pool)

    # 1102 sog'lom, 120 parvarish, 26 xavfli
    statuses = ["Sog‘lom"] * 1102 + ["Parvarish talab"] * 120 + ["Xavfli"] * 26
    rng.shuffle(statuses)

    trees = []
    for i in range(1248):
        spec = species_pool[i]
        planted = rng.randint(1978, 2025)
        age = 2026 - planted
        height = round(max(1.6, min(28.0, age * rng.uniform(0.28, 0.55))), 1)
        diameter = round(max(4.0, height * rng.uniform(1.8, 3.4)), 1)
        # Maktab atrofi + mahalla tarqalishi
        cluster = rng.random()
        if cluster < 0.45:
            lat = SCHOOL["lat"] + rng.uniform(-0.0018, 0.0018)
            lng = SCHOOL["lng"] + rng.uniform(-0.0024, 0.0024)
        else:
            lat = SCHOOL["lat"] + rng.uniform(-0.0075, 0.0075)
            lng = SCHOOL["lng"] + rng.uniform(-0.010, 0.010)
        code = f"UZ-237-{i+1:04d}"
        updated = datetime(2026, rng.randint(1, 10), rng.randint(1, 28)).strftime("%Y-%m-%d")
        trees.append(
            (
                code,
                spec["name"],
                planted,
                lat,
                lng,
                statuses[i],
                height,
                diameter,
                spec["photo"],
                spec["oxygen"] + rng.randint(-12, 12),
                updated,
                rng.randint(1, 18),
                "",
            )
        )
    db.executemany(
        """
        INSERT INTO trees (
            public_code, species_name, planted_year, latitude, longitude,
            health_status, height_m, trunk_diameter, photo_key, oxygen_kg,
            last_updated, zone_id, notes
        ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
        """,
        trees,
    )

    reports = [
        (
            "Chinor sug‘orishni talab qiladi",
            "Maktab stadioni yonidagi katta chinor barglari so‘lg‘in, tuproq qurigan. Zudlik bilan sug‘orish kerak.",
            "Yangi",
            "2026-05-12",
            "Malika N.",
            1,
            SCHOOL["lat"] + 0.0004,
            SCHOOL["lng"] - 0.0003,
        ),
        (
            "Archa holati tekshirilsin",
            "Kirish darvozasi yonidagi archada sarg‘aygan shoxlar ko‘rindi. Fitopatolog ko‘rigi so‘raladi.",
            "Jarayonda",
            "2026-05-11",
            "Jasur T.",
            3,
            SCHOOL["lat"] - 0.0006,
            SCHOOL["lng"] + 0.0005,
        ),
        (
            "Yashil zona tozalansin",
            "Mahalla guzari bog‘ida qurigan novdalar va axlat to‘plangan. Tozalash ishlari kerak.",
            "Ko‘rib chiqildi",
            "2026-05-10",
            "Dilnoza R.",
            None,
            SCHOOL["lat"] + 0.002,
            SCHOOL["lng"] + 0.001,
        ),
        (
            "Eman shoxi sinishi xavfi",
            "Katta emaning pastki shoxi yorilgan, o‘quvchilar yo‘li ustida. Kesish yoki mahkamlash kerak.",
            "Yangi",
            "2026-05-08",
            "Sardor Q.",
            2,
            SCHOOL["lat"] + 0.0009,
            SCHOOL["lng"] + 0.0002,
        ),
        (
            "Noqonuniy kesish ogohlantiruvi",
            "Mahalla 8-tor ko‘chada daraxt kesishga tayyorgarlik belgilari kuzatildi. Tezkor tekshiruv so‘raladi.",
            "Jarayonda",
            "2026-05-06",
            "Eko-patrul",
            None,
            SCHOOL["lat"] - 0.003,
            SCHOOL["lng"] - 0.004,
        ),
        (
            "Yosh nihollar suvsiz qolgan",
            "Yosh nihollar maydonidagi 14 ta ko‘chat so‘liyapti. Navbatma-navbat sug‘orish jadvallash kerak.",
            "Yangi",
            "2026-05-04",
            "3-sinf faollari",
            None,
            SCHOOL["lat"] - 0.001,
            SCHOOL["lng"] + 0.0015,
        ),
    ]
    db.executemany(
        """
        INSERT INTO reports (title, description, status, created_at, reporter, tree_id, latitude, longitude)
        VALUES (?,?,?,?,?,?,?,?)
        """,
        reports,
    )


def tree_age(planted_year):
    return max(0, 2026 - int(planted_year))


def status_class(status):
    mapping = {
        "Sog‘lom": "ok",
        "Parvarish talab": "warn",
        "Xavfli": "danger",
    }
    return mapping.get(status, "ok")


@app.context_processor
def inject_globals():
    return {
        "current_user": session.get("user"),
        "school": SCHOOL,
        "now_year": 2026,
        "status_class": status_class,
    }


def stats_dict():
    db = get_db()
    total = db.execute("SELECT COUNT(*) c FROM trees").fetchone()["c"]
    healthy = db.execute(
        "SELECT COUNT(*) c FROM trees WHERE health_status = 'Sog‘lom'"
    ).fetchone()["c"]
    care = db.execute(
        "SELECT COUNT(*) c FROM trees WHERE health_status != 'Sog‘lom'"
    ).fetchone()["c"]
    zones = db.execute("SELECT COUNT(*) c FROM zones").fetchone()["c"]
    oxygen = db.execute("SELECT SUM(oxygen_kg) s FROM trees").fetchone()["s"] or 0
    return {
        "total": total,
        "healthy": healthy,
        "care": care,
        "zones": zones,
        "oxygen": int(oxygen),
    }


@app.route("/")
def index():
    featured = query_all(
        """
        SELECT * FROM trees
        WHERE species_name IN ('Chinor','Eman','Archa')
        ORDER BY height_m DESC
        """
    )
    picks = {}
    for row in featured:
        if row["species_name"] not in picks:
            picks[row["species_name"]] = row
    catalog = [picks.get("Chinor"), picks.get("Eman"), picks.get("Archa")]
    reports = query_all("SELECT * FROM reports ORDER BY created_at DESC LIMIT 3")
    map_sample = as_dicts(query_all(
        "SELECT id, species_name, latitude, longitude, health_status, public_code, height_m, planted_year FROM trees ORDER BY id LIMIT 80"
    ))
    return render_template(
        "index.html",
        stats=stats_dict(),
        catalog=catalog,
        reports=reports,
        map_sample=map_sample,
        tree_age=tree_age,
    )


def apply_tree_filters(sql, args, status=None, species=None, q=None):
    status = status if status is not None else request.args.get("holat", "")
    species = species if species is not None else request.args.get("tur", "")
    q = q if q is not None else request.args.get("q", "").strip()
    if status == "muammo":
        sql += " AND health_status != ?"
        args.append("Sog‘lom")
    elif status:
        sql += " AND health_status = ?"
        args.append(status)
    if species:
        sql += " AND species_name = ?"
        args.append(species)
    if q:
        sql += " AND (species_name LIKE ? OR public_code LIKE ? OR notes LIKE ?)"
        args.extend([f"%{q}%", f"%{q}%", f"%{q}%"])
    return sql, args, status, species, q


@app.route("/xarita")
def xarita():
    sql = "SELECT id, public_code, species_name, planted_year, latitude, longitude, health_status, height_m, photo_key FROM trees WHERE 1=1"
    sql, args, status, species, _q = apply_tree_filters(sql, [])
    trees = as_dicts(query_all(sql, args))
    zones = as_dicts(query_all("SELECT * FROM zones"))
    types = [r["species_name"] for r in query_all("SELECT DISTINCT species_name FROM trees ORDER BY species_name")]
    focus_id = request.args.get("daraxt", type=int)
    return render_template(
        "map.html",
        trees=trees,
        zones=zones,
        types=types,
        selected_status=status or "",
        selected_species=species or "",
        stats=stats_dict(),
        tree_age=tree_age,
        focus_id=focus_id,
    )


@app.route("/daraxtlar")
def daraxtlar():
    sql = "SELECT * FROM trees WHERE 1=1"
    sql, args, status, species, q = apply_tree_filters(sql, [])
    total = query_one(sql.replace("SELECT *", "SELECT COUNT(*) c", 1), args)["c"]
    page = max(1, request.args.get("sahifa", default=1, type=int) or 1)
    pages = max(1, (total + PER_PAGE - 1) // PER_PAGE)
    page = min(page, pages)
    sql += " ORDER BY id LIMIT ? OFFSET ?"
    trees = query_all(sql, args + [PER_PAGE, (page - 1) * PER_PAGE])
    types = [r["species_name"] for r in query_all("SELECT DISTINCT species_name FROM trees ORDER BY species_name")]
    counts = query_all(
        "SELECT species_name, COUNT(*) c FROM trees GROUP BY species_name ORDER BY c DESC"
    )
    return render_template(
        "trees.html",
        trees=trees,
        types=types,
        counts=counts,
        q=q,
        selected_status=status,
        selected_species=species,
        stats=stats_dict(),
        tree_age=tree_age,
        page=page,
        pages=pages,
        total=total,
    )


@app.route("/daraxt/<int:tree_id>")
def daraxt_pasport(tree_id):
    tree = query_one("SELECT * FROM trees WHERE id = ?", (tree_id,))
    if not tree:
        flash("Daraxt topilmadi.", "error")
        return redirect(url_for("daraxtlar"))
    zone = None
    if tree["zone_id"]:
        zone = query_one("SELECT * FROM zones WHERE id = ?", (tree["zone_id"],))
    nearby = query_all(
        "SELECT * FROM trees WHERE species_name = ? AND id != ? ORDER BY id LIMIT 3",
        (tree["species_name"], tree_id),
    )
    reports = query_all(
        "SELECT * FROM reports WHERE tree_id = ? ORDER BY created_at DESC", (tree_id,)
    )
    return render_template(
        "passport.html",
        tree=tree,
        zone=zone,
        nearby=nearby,
        reports=reports,
        age=tree_age(tree["planted_year"]),
    )


def save_report_photo(file_storage):
    if not file_storage or not file_storage.filename:
        return None
    ext = os.path.splitext(file_storage.filename)[1].lower()
    if ext not in ALLOWED_PHOTOS:
        return None
    name = secure_filename(f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{file_storage.filename}")
    path = os.path.join(UPLOAD_DIR, name)
    file_storage.save(path)
    return f"uploads/{name}"


@app.route("/eco-signal")
def eco_signal():
    reports = query_all("SELECT * FROM reports ORDER BY id DESC")
    trees = query_all("SELECT id, public_code, species_name FROM trees ORDER BY id LIMIT 80")
    selected_tree = request.args.get("tree_id", type=int)
    return render_template(
        "eco_signal.html",
        reports=reports,
        trees=trees,
        selected_tree=selected_tree,
    )


@app.route("/eco-signal/yuborish", methods=["POST"])
def eco_signal_send():
    title = request.form.get("title", "").strip()
    description = request.form.get("description", "").strip()
    reporter = request.form.get("reporter", "").strip() or "Mehmon"
    tree_id = request.form.get("tree_id") or None
    if not title or not description:
        flash("Sarlavha va tavsif majburiy.", "error")
        return redirect(url_for("eco_signal"))
    lat = request.form.get("latitude") or SCHOOL["lat"]
    lng = request.form.get("longitude") or SCHOOL["lng"]
    try:
        lat = float(lat)
        lng = float(lng)
    except (TypeError, ValueError):
        lat, lng = SCHOOL["lat"], SCHOOL["lng"]
    if tree_id:
        t = query_one("SELECT latitude, longitude FROM trees WHERE id = ?", (tree_id,))
        if t:
            lat, lng = t["latitude"], t["longitude"]
    photo_url = save_report_photo(request.files.get("photo"))
    db = get_db()
    db.execute(
        """
        INSERT INTO reports (title, description, status, created_at, reporter, tree_id, latitude, longitude, photo_url)
        VALUES (?,?,?,?,?,?,?,?,?)
        """,
        (
            title,
            description,
            "Yangi",
            datetime.now().strftime("%Y-%m-%d"),
            reporter,
            tree_id,
            lat,
            lng,
            photo_url,
        ),
    )
    db.commit()
    flash("Eco-Signal qabul qilindi. Eko-patrul tez orada ko‘rib chiqadi.", "success")
    return redirect(url_for("eco_signal"))


@app.route("/loyiha")
def loyiha():
    return render_template("about.html", stats=stats_dict())


@app.route("/kirish", methods=["GET", "POST"])
def kirish():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user = query_one("SELECT * FROM users WHERE username = ?", (username,))
        if user and check_password_hash(user["password_hash"], password):
            session["user"] = {
                "id": user["id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "role": user["role"],
            }
            flash(f"Xush kelibsiz, {user['full_name']}!", "success")
            nxt = safe_next(
                request.form.get("next") or request.args.get("next"),
                url_for("admin"),
            )
            return redirect(nxt)
        flash("Login yoki parol noto‘g‘ri.", "error")
    return render_template("login.html", next=request.args.get("next", ""))


@app.route("/chiqish")
def chiqish():
    session.clear()
    flash("Tizimdan chiqdingiz.", "info")
    return redirect(url_for("index"))


@app.route("/admin")
@login_required
def admin():
    reports = query_all("SELECT * FROM reports ORDER BY id DESC LIMIT 12")
    latest_trees = query_all("SELECT * FROM trees ORDER BY id DESC LIMIT 8")
    species = query_all(
        "SELECT species_name, COUNT(*) c FROM trees GROUP BY species_name ORDER BY c DESC"
    )
    return render_template(
        "admin.html",
        stats=stats_dict(),
        reports=reports,
        latest_trees=latest_trees,
        species=species,
        tree_age=tree_age,
    )


@app.route("/daraxt/qoshish", methods=["GET", "POST"])
@login_required
def daraxt_qoshish():
    if request.method == "POST":
        species_name = request.form.get("species_name", "Chinor").strip()
        planted_year = int(request.form.get("planted_year") or 2026)
        lat = float(request.form.get("latitude") or SCHOOL["lat"])
        lng = float(request.form.get("longitude") or SCHOOL["lng"])
        health = request.form.get("health_status") or "Sog‘lom"
        height = float(request.form.get("height_m") or 2)
        diameter = float(request.form.get("trunk_diameter") or 8)
        notes = request.form.get("notes", "").strip()
        spec = next((s for s in SPECIES if s["name"] == species_name), SPECIES[0])
        db = get_db()
        last = db.execute("SELECT MAX(id) m FROM trees").fetchone()["m"] or 0
        code = f"UZ-237-{last+1:04d}"
        db.execute(
            """
            INSERT INTO trees (
                public_code, species_name, planted_year, latitude, longitude,
                health_status, height_m, trunk_diameter, photo_key, oxygen_kg,
                last_updated, zone_id, notes
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?)
            """,
            (
                code,
                species_name,
                planted_year,
                lat,
                lng,
                health,
                height,
                diameter,
                spec["photo"],
                spec["oxygen"],
                datetime.now().strftime("%Y-%m-%d"),
                1,
                notes,
            ),
        )
        db.commit()
        new_id = db.execute("SELECT last_insert_rowid() i").fetchone()["i"]
        flash(f"Yangi daraxt qo‘shildi: {code}", "success")
        return redirect(url_for("daraxt_pasport", tree_id=new_id))
    return render_template("add_tree.html", species=SPECIES)


@app.route("/report/<int:report_id>/holat", methods=["POST"])
@login_required
def report_status(report_id):
    status = request.form.get("status")
    if status in ("Yangi", "Jarayonda", "Ko‘rib chiqildi"):
        db = get_db()
        db.execute("UPDATE reports SET status = ? WHERE id = ?", (status, report_id))
        db.commit()
        flash("Murojaat holati yangilandi.", "success")
    return redirect(request.referrer or url_for("admin"))


@app.route("/daraxt/<int:tree_id>/holat", methods=["POST"])
@login_required
def tree_status(tree_id):
    status = request.form.get("health_status")
    if status in ("Sog‘lom", "Parvarish talab", "Xavfli"):
        db = get_db()
        db.execute(
            "UPDATE trees SET health_status = ?, last_updated = ? WHERE id = ?",
            (status, datetime.now().strftime("%Y-%m-%d"), tree_id),
        )
        db.commit()
        flash("Daraxt holati yangilandi.", "success")
    return redirect(url_for("daraxt_pasport", tree_id=tree_id))


@app.route("/api/trees")
def api_trees():
    rows = query_all(
        "SELECT id, public_code, species_name, planted_year, latitude, longitude, health_status, height_m FROM trees"
    )
    return jsonify([dict(r) for r in rows])


@app.route("/qr/<int:tree_id>.png")
def tree_qr(tree_id):
    tree = query_one("SELECT id, public_code FROM trees WHERE id = ?", (tree_id,))
    if not tree:
        return "Not found", 404
    url = request.url_root.rstrip("/") + url_for("daraxt_pasport", tree_id=tree_id)
    img = qrcode.make(url)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    buf.seek(0)
    download = request.args.get("yuklab") == "1"
    return send_file(
        buf,
        mimetype="image/png",
        as_attachment=download,
        download_name=f"{tree['public_code']}-qr.png",
    )


@app.route("/admin/hisobot.csv")
@login_required
def admin_export():
    trees = query_all(
        "SELECT public_code, species_name, planted_year, latitude, longitude, health_status, height_m, trunk_diameter, oxygen_kg, last_updated FROM trees ORDER BY id"
    )
    buf = io.StringIO()
    writer = csv.writer(buf)
    writer.writerow(
        [
            "kod",
            "tur",
            "yil",
            "lat",
            "lng",
            "holat",
            "boy_m",
            "diametr_sm",
            "kislorod_kg",
            "yangilangan",
        ]
    )
    for t in trees:
        writer.writerow(list(t))
    data = buf.getvalue().encode("utf-8-sig")
    return Response(
        data,
        mimetype="text/csv",
        headers={"Content-Disposition": "attachment; filename=eco-map-hisobot.csv"},
    )


init_db()

if __name__ == "__main__":
    app.run(debug=True, host="127.0.0.1", port=5000)
