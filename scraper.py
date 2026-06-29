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
    return True

# ── Lấy học kì hiện tại ───────────────────────────────────────────────────────
def get_current_hocky():
    resp = S.post(f"{BASE_URL}/api/sch/w-locdshockytkbuser", json={})
    data = resp.json()["data"]
    return data["hoc_ky_theo_ngay_hien_tai"]

# ── Tính mã học kì theo ngày (không phụ thuộc server) ─────────────────────────
# Quy luật: HK1 = tháng 8→1 (năm bắt đầu = năm có tháng 8)
#           HK2 = tháng 2→6  (năm bắt đầu = năm trước đó)
#           HK3 = tháng 7 (hè, năm bắt đầu = năm trước đó)
def get_hocky_by_date(today=None):
    today = today or datetime.now(tz=timezone(timedelta(hours=7))).date()
    y, m = today.year, today.month
    if m == 1:
        start, sem = y - 1, 1
    elif 8 <= m <= 12:
        start, sem = y, 1
    elif 2 <= m <= 6:
        start, sem = y - 1, 2
    else:  # tháng 7
        start, sem = y - 1, 3
    return f"{start}{sem}"

# ── Lấy TKB toàn học kì ───────────────────────────────────────────────────────
def get_tkb(hoc_ky_id):
    resp = S.post(f"{BASE_URL}/api/sch/w-locdstkbtuanusertheohocky", json={
        "filter": {"hoc_ky": hoc_ky_id, "ten_hoc_ky": ""},
        "additional": {
            "paging": {"limit": 100, "page": 1},
            "ordering": [{"name": None, "order_type": None}]
        }
    })
    return resp.json()["data"]

# ── Lấy lịch thi ─────────────────────────────────────────────────────────────
def get_exams(hoc_ky_id):
    resp = S.post(f"{BASE_URL}/api/epm/w-locdslichthisvtheohocky", json={
        "filter": {"hoc_ky": hoc_ky_id, "is_giua_ky": False},
        "additional": {
            "paging": {"limit": 100, "page": 1},
            "ordering": [{"name": None, "order_type": None}]
        }
    })
    return resp.json()["data"]

# ── Build TKB .ics ────────────────────────────────────────────────────────────
def build_ics(data):
    tiet_map = {t["tiet"]: (t["gio_bat_dau"], t["gio_ket_thuc"])
                for t in data["ds_tiet_trong_ngay"]}

    cal = Calendar()
    cal.add("prodid", "-//VNUA Schedule//VN")
    cal.add("version", "2.0")
    cal.add("X-WR-CALNAME", "Lịch học VNUA")
    cal.add("X-WR-TIMEZONE", "Asia/Ho_Chi_Minh")

    now_utc = datetime.now(tz=timezone.utc)
    count   = 0

    for tuan in data["ds_tuan_tkb"]:
        for tkb in tuan["ds_thoi_khoa_bieu"]:
            if tkb.get("is_nghi_day"):
                continue

            tiet_bd = tkb["tiet_bat_dau"]
            tiet_kt = tiet_bd + tkb["so_tiet"] - 1
            tiet_kt = min(tiet_kt, max(tiet_map.keys()))

            if tiet_bd not in tiet_map:
                continue

            ngay     = datetime.fromisoformat(tkb["ngay_hoc"]).date()
            # naive datetime — Google dùng X-WR-TIMEZONE
            dt_start = datetime.strptime(f"{ngay} {tiet_map[tiet_bd][0]}", "%Y-%m-%d %H:%M")
            dt_end   = datetime.strptime(f"{ngay} {tiet_map[tiet_kt][1]}", "%Y-%m-%d %H:%M")

            phong = tkb["ma_phong"].split("-")[0].strip()

            ev = Event()
            ev.add("dtstamp",     now_utc)
            ev.add("uid",         str(uuid.uuid4()))
            ev.add("summary",     tkb["ten_mon"])
            ev.add("dtstart",     dt_start)
            ev.add("dtend",       dt_end)
            ev.add("location",    phong)
            ev.add("description", (
                f"GV: {tkb['ten_giang_vien']}\n"
                f"{phong}\n"
                f"Tiết {tiet_bd}–{tiet_kt} | Nhóm {tkb['ma_nhom']}"
            ))
            cal.add_component(ev)
            count += 1

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
    count   = 0

    ds = data.get("ds_lich_thi") or data.get("data") or data
    if isinstance(ds, dict):
        ds = list(ds.values())[0]

    for thi in ds:
        try:
            ngay_thi  = thi.get("ngay_thi") or thi.get("ngay")
            gio_bd    = thi.get("gio_bat_dau") or thi.get("gio_thi") or "00:00"
            ten_mon   = thi.get("ten_mon") or thi.get("mon_hoc") or "Thi"
            phong_thi = thi.get("phong_thi") or thi.get("ma_phong") or ""
            phong_str = phong_thi.split("-")[0].strip() if phong_thi else ""

            ngay     = datetime.strptime(ngay_thi, "%d/%m/%Y").date()
            # naive datetime — giống TKB
            dt_start = datetime.strptime(f"{ngay} {gio_bd[:5]}", "%Y-%m-%d %H:%M")
            dt_end   = dt_start + timedelta(minutes=int(thi.get("so_phut", 60)))

            desc_parts = []
            if thi.get("hinh_thuc_thi"): desc_parts.append(f"Hình thức: {thi['hinh_thuc_thi']}")
            if phong_str:                desc_parts.append(phong_str)

            ev = Event()
            ev.add("dtstamp",     now_utc)
            ev.add("uid",         str(uuid.uuid4()))
            ev.add("summary",     f"🔴 THI: {ten_mon}")
            ev.add("dtstart",     dt_start)
            ev.add("dtend",       dt_end)
            ev.add("location",    phong_str)
            ev.add("description", "\n".join(desc_parts))
            cal.add_component(ev)
            count += 1
        except Exception as e:
            print(f"Skip exam entry: {e} | data: {thi}")

    print(f"Lịch thi: {count} sự kiện")
    return cal.to_ical()

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    assert login(), "Login thất bại"

    hk_override = os.environ.get("HOC_KY_ID", "").strip()
    hk_by_date = get_hocky_by_date()

    if hk_override:
        hk_id = hk_override
        print(f"Học kì: {hk_id} (chỉ định)")
    else:
        hk_id = hk_by_date
        print(f"Học kì: {hk_id} (tính theo ngày)")
        try:
            hk_server = get_current_hocky()
            if hk_server != hk_by_date:
                print(f"⚠ Server báo hiện tại là {hk_server}, khác với tính theo ngày ({hk_by_date}). Đang dùng {hk_by_date}.")
        except Exception as e:
            print(f"(Không lấy được hoc_ky_theo_ngay_hien_tai để so sánh: {e})")

    os.makedirs("docs", exist_ok=True)

    tkb_data = get_tkb(hk_id)
    with open(OUTPUT_TKB, "wb") as f:
        f.write(build_ics(tkb_data))
    print(f"Saved: {OUTPUT_TKB}")

    exam_data = get_exams(hk_id)
    with open(OUTPUT_EXAM, "wb") as f:
        f.write(build_exam_ics(exam_data))
    print(f"Saved: {OUTPUT_EXAM}")
