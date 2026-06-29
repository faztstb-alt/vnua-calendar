"""
VNUA Schedule → Google Calendar (.ics)
pip install requests icalendar
"""

import os, json, base64, uuid
import requests
from datetime import datetime, timezone, timedelta
from icalendar import Calendar, Event

BASE_URL    = "https://daotao.vnua.edu.vn"
USERNAME    = os.environ.get("SCHOOL_USER", "")
PASSWORD    = os.environ.get("SCHOOL_PASS", "")
OUTPUT_TKB  = "docs/schedule.ics"
OUTPUT_EXAM = "docs/exams.ics"

S = requests.Session()
S.headers.update({"User-Agent": "Mozilla/5.0", "Referer": BASE_URL})

# ── Login ─────────────────────────────────────────────────────────────────────
def login():
    from urllib.parse import parse_qs

    code = base64.b64encode(json.dumps({
        "username": USERNAME,
        "password": PASSWORD,
        "uri": f"{BASE_URL}/#/home"
    }).encode()).decode()

    resp = S.get(f"{BASE_URL}/api/pn-signin", params={
        "code": code, "gopage": "", "mgr": "1"
    }, allow_redirects=False)

    location = resp.headers.get("Location", "")
    fragment = location.split("#")[-1]
    query    = fragment.split("?")[-1]
    params   = parse_qs(query)
    curr_b64 = params.get("CurrUser", [""])[0]

    curr_b64 += "=" * (-len(curr_b64) % 4)
    user_data    = json.loads(base64.b64decode(curr_b64))
    access_token = user_data["access_token"]

    S.headers.update({
        "Authorization":    f"Bearer {access_token}",
        "Accept":           "application/json, text/plain, */*",
        "Idpc":             "0",
        "X-Requested-With": "XMLHttpRequest",
    })
    print("Login OK | Token:", access_token[:30], "...")
    return user_data

# ── Lấy danh sách học kỳ (có ngày bắt đầu) ───────────────────────────────────
def get_hocky_list():
    resp = S.post(f"{BASE_URL}/api/sch/w-locdshockytkbuser", json={})
    return resp.json()["data"]["ds_hoc_ky"]

def get_latest_hocky():
    ds = get_hocky_list()
    latest = max(ds, key=lambda hk: hk["hoc_ky"])
    print(f"Mới nhất trên web: {latest['hoc_ky']} - {latest['ten_hoc_ky']} "
          f"({latest['ngay_bat_dau_hk']} → {latest['ngay_ket_thuc_hk']})")
    return latest

# ── Lấy khung giờ tiết (fallback từ API tuần cũ) ───────────────────────────────
def get_tiet_map():
    resp = S.post(f"{BASE_URL}/api/sch/w-locdstkbtuanusertheohocky", json={
        "filter": {"hoc_ky": "20261", "ten_hoc_ky": ""},
        "additional": {
            "paging": {"limit": 1, "page": 1},
            "ordering": [{"name": None, "order_type": None}]
        }
    })
    data = resp.json().get("data", {})
    tiet_map = {t["tiet"]: (t["gio_bat_dau"], t["gio_ket_thuc"])
                for t in data.get("ds_tiet_trong_ngay", [])}
    if tiet_map:
        print(f"Loaded {len(tiet_map)} time slots from fallback API")
    else:
        print("Warning: Không lấy được ds_tiet_trong_ngay")
    return tiet_map

# ── Lấy TKB dạng học kỳ (bitmap) ──────────────────────────────────────────────
def get_tkb_hocky(hoc_ky_id):
    # loai_doi_tuong: 1 = TKB cá nhân, ma_doi_tuong = mã sinh viên
    body = {
        "filter": {
            "hoc_ky": hoc_ky_id,
            "loai_doi_tuong": 1,
            "ma_doi_tuong": USERNAME,
        },
        "additional": {
            "paging": {"limit": 100, "page": 1},
            "ordering": [{"name": None, "order_type": None}]
        }
    }

    resp = S.post(f"{BASE_URL}/api/sch/w-locdstkbhockytheodoituong", json=body)
    raw = resp.json()
    print(f"DEBUG w-locdstkbhockytheodoituong keys: {list(raw.keys())}")
    data = raw.get("data", {})
    if isinstance(data, dict):
        print(f"DEBUG data keys: {list(data.keys())}")
    elif isinstance(data, list):
        print(f"DEBUG data is list, len={len(data)}")
    return data

# ── Lấy lịch thi ─────────────────────────────────────────────────────────────
def get_exams(hoc_ky_id):
    resp = S.post(f"{BASE_URL}/api/epm/w-locdslichthisvtheohocky", json={
        "filter": {"hoc_ky": hoc_ky_id, "is_giua_ky": False},
        "additional": {
            "paging": {"limit": 100, "page": 1},
            "ordering": [{"name": None, "order_type": None}]
        }
    })
    return resp.json().get("data", {})

# ── Build TKB .ics từ dạng học kỳ (bitmap) ───────────────────────────────────
def build_ics(data, hoc_ky_info, tiet_map):
    cal = Calendar()
    cal.add("prodid", "-//VNUA Schedule//VN")
    cal.add("version", "2.0")
    cal.add("X-WR-CALNAME", "Lịch học VNUA")
    cal.add("X-WR-TIMEZONE", "Asia/Ho_Chi_Minh")

    now_utc = datetime.now(tz=timezone.utc)
    count = 0

    # Ngày bắt đầu học kỳ → tìm Thứ 2 tuần 1
    start_str = hoc_ky_info.get("ngay_bat_dau_hk", "")
    if not start_str:
        print("Warning: Không có ngày bắt đầu học kỳ")
        return cal.to_ical()

    start_date = datetime.strptime(start_str, "%d/%m/%Y").date()
    monday_w1 = start_date - timedelta(days=start_date.weekday())  # Monday=0

    # Trích danh sách TKB — thử nhiều key
    ds = None
    if isinstance(data, dict):
        for key in ["ds_tkb_hoc_ky", "ds_thoi_khoa_bieu", "ds_tkb", "data", "items", "rows", "result"]:
            if key in data:
                ds = data[key]
                print(f"DEBUG using data['{key}']")
                break
    if ds is None:
        ds = data

    if isinstance(ds, dict):
        ds = list(ds.values())
        print(f"DEBUG flattened dict values, len={len(ds)}")
    if not isinstance(ds, list):
        print(f"Warning: ds_tkb kiểu {type(ds)} — cannot iterate")
        return cal.to_ical()

    print(f"DEBUG total entries before filter: {len(ds)}")
    if ds and isinstance(ds[0], dict):
        print(f"DEBUG first entry keys: {list(ds[0].keys())}")
        print(f"DEBUG first entry sample: {json.dumps(ds[0], ensure_ascii=False, default=str)[:400]}")

    for tkb in ds:
        try:
            # Bitmap tuần
            bitmap = str(tkb.get("thoi_gian_hoc") or tkb.get("tuan_hoc") or tkb.get("thoi_gian") or "").strip()
            if not bitmap:
                continue

            thu_raw = tkb.get("thu") or tkb.get("thu_trong_tuan") or tkb.get("ngay_hoc")
            thu = int(thu_raw) if thu_raw is not None else 0
            if thu < 2 or thu > 8:
                continue

            tiet_bd = int(tkb.get("tiet_bat_dau") or tkb.get("tiet_bd") or 0)
            so_tiet = int(tkb.get("so_tiet") or tkb.get("so_tiet_hoc") or 0)
            if tiet_bd <= 0 or so_tiet <= 0:
                continue
            tiet_kt = tiet_bd + so_tiet - 1

            if not tiet_map or tiet_bd not in tiet_map:
                continue
            tiet_kt = min(tiet_kt, max(tiet_map.keys()))

            dow_offset = thu - 2  # thu=2 (Mon) → 0

            ten_mon = tkb.get("ten_mon") or tkb.get("ten_mon_hoc") or tkb.get("mon_hoc") or "Môn học"
            phong_raw = str(tkb.get("phong") or tkb.get("ma_phong") or tkb.get("phong_hoc") or "")
            phong = phong_raw.split("-")[0].strip()
            gv = tkb.get("ten_giang_vien") or tkb.get("giang_vien") or tkb.get("gv") or ""
            nhom = tkb.get("nhom_to") or tkb.get("ma_nhom") or tkb.get("nhom") or ""

            for week_idx, char in enumerate(bitmap):
                if char == "-":
                    continue

                week_num = week_idx + 1
                event_date = monday_w1 + timedelta(weeks=week_idx, days=dow_offset)

                dt_start = datetime.strptime(
                    f"{event_date} {tiet_map[tiet_bd][0]}", "%Y-%m-%d %H:%M")
                dt_end = datetime.strptime(
                    f"{event_date} {tiet_map[tiet_kt][1]}", "%Y-%m-%d %H:%M")

                ev = Event()
                ev.add("dtstamp", now_utc)
                ev.add("uid", str(uuid.uuid4()))
                ev.add("summary", ten_mon)
                ev.add("dtstart", dt_start)
                ev.add("dtend", dt_end)
                ev.add("location", phong)
                ev.add("description", (
                    f"GV: {gv}\n"
                    f"{phong}\n"
                    f"Tiết {tiet_bd}–{tiet_kt} | Nhóm {nhom}\n"
                    f"Tuần {week_num}"
                ))
                cal.add_component(ev)
                count += 1

        except Exception as e:
            print(f"Skip TKB entry: {e} | data: {tkb}")
            continue

    print(f"TKB: {count} sự kiện")
    return cal.to_ical()

# ── Build Exam .ics ───────────────────────────────────────────────────────────
def build_exam_ics(data):
    cal = Calendar()
    cal.add("prodid", "-//VNUA Exams//VN")
    cal.add("version", "2.0")
    cal.add("X-WR-CALNAME", "Lịch thi VNUA")
    cal.add("X-WR-TIMEZONE", "Asia/Ho_Chi_Minh")

    now_utc = datetime.now(tz=timezone.utc)
    count = 0

    ds = None
    if isinstance(data, dict):
        ds = data.get("ds_lich_thi")
        if ds is None:
            ds = data.get("data")
    if ds is None:
        ds = data

    if isinstance(ds, dict):
        vals = list(ds.values())
        ds = vals[0] if vals else []
    if isinstance(ds, int):
        print(f"Warning: Exam data là số ({ds}), bỏ qua lịch thi.")
        ds = []
    elif not isinstance(ds, (list, tuple)):
        print(f"Warning: Exam data kiểu {type(ds)}, bỏ qua lịch thi.")
        ds = []

    for thi in ds:
        try:
            ngay_thi  = thi.get("ngay_thi") or thi.get("ngay")
            gio_bd    = thi.get("gio_bat_dau") or thi.get("gio_thi") or "00:00"
            ten_mon   = thi.get("ten_mon") or thi.get("mon_hoc") or "Thi"
            phong_thi = thi.get("phong_thi") or thi.get("ma_phong") or ""
            phong_str = phong_thi.split("-")[0].strip() if phong_thi else ""

            ngay     = datetime.strptime(ngay_thi, "%d/%m/%Y").date()
            dt_start = datetime.strptime(f"{ngay} {gio_bd[:5]}", "%Y-%m-%d %H:%M")
            dt_end   = dt_start + timedelta(minutes=int(thi.get("so_phut", 60)))

            desc_parts = []
            if thi.get("hinh_thuc_thi"): desc_parts.append(f"Hình thức: {thi['hinh_thuc_thi']}")
            if phong_str:                desc_parts.append(phong_str)

            ev = Event()
            ev.add("dtstamp", now_utc)
            ev.add("uid", str(uuid.uuid4()))
            ev.add("summary", f"🔴 THI: {ten_mon}")
            ev.add("dtstart", dt_start)
            ev.add("dtend", dt_end)
            ev.add("location", phong_str)
            ev.add("description", "\n".join(desc_parts))
            cal.add_component(ev)
            count += 1
        except Exception as e:
            print(f"Skip exam entry: {e} | data: {thi}")

    print(f"Lịch thi: {count} sự kiện")
    return cal.to_ical()

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    user_data = login()
    if not user_data:
        raise SystemExit("Login thất bại")

    # Luôn lấy học kỳ mới nhất từ web
    hk_info = get_latest_hocky()
    hk_id = hk_info["hoc_ky"]
    print(f"Học kì: {hk_id} ({hk_info.get('ten_hoc_ky', '')})")

    # Lấy khung giờ tiết trước
    tiet_map = get_tiet_map()

    # Lấy TKB dạng học kỳ (loai_doi_tuong=1 = cá nhân)
    tkb_data = get_tkb_hocky(hk_id)

    os.makedirs("docs", exist_ok=True)

    with open(OUTPUT_TKB, "wb") as f:
        f.write(build_ics(tkb_data, hk_info, tiet_map))
    print(f"Saved: {OUTPUT_TKB}")

    exam_data = get_exams(hk_id)
    with open(OUTPUT_EXAM, "wb") as f:
        f.write(build_exam_ics(exam_data))
    print(f"Saved: {OUTPUT_EXAM}")
