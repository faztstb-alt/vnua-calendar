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
S.headers.update({
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/148.0.0.0 Safari/537.36",
    "Referer": f"{BASE_URL}/public/",
    "Origin": BASE_URL,
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "vi,en;q=0.9",
    "DNT": "1",
    "Idpc": "0",
    "Priority": "u=1, i",
    "Sec-Ch-Ua": '"Chromium";v="148", "Google Chrome";v="148", "Not/A)Brand";v="99"',
    "Sec-Ch-Ua-Mobile": "?0",
    "Sec-Ch-Ua-Platform": '"Windows"',
    "Sec-Fetch-Dest": "empty",
    "Sec-Fetch-Mode": "cors",
    "Sec-Fetch-Site": "same-origin",
})

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
        "Authorization": f"Bearer {access_token}",
        "X-Requested-With": "XMLHttpRequest",
    })
    print("Login OK | Token:", access_token[:30], "...")
    return user_data

# ── Lấy danh sách học kỳ (có ngày bắt đầu) ───────────────────────────────────
def get_hocky_list():
    resp = S.post(f"{BASE_URL}/api/sch/w-locdshockytkbuser", json={
        "filter": {"is_tieng_anh": None},
        "additional": {
            "paging": {"limit": 100, "page": 1},
            "ordering": [{"name": "hoc_ky", "order_type": 1}]
        }
    })
    return resp.json()["data"]["ds_hoc_ky"]

def get_latest_hocky():
    ds = get_hocky_list()
    latest = max(ds, key=lambda hk: hk["hoc_ky"])
    print(f"Mới nhất trên web: {latest['hoc_ky']} - {latest['ten_hoc_ky']} "
          f"({latest['ngay_bat_dau_hk']} → {latest['ngay_ket_thuc_hk']})")
    return latest

# ── Lấy TKB dạng học kỳ (bitmap) ──────────────────────────────────────────────
def get_tkb_hocky(hoc_ky_id):
    # Body FLAT — không có "filter" wrapper, giống cURL thật
    body = {
        "hoc_ky": hoc_ky_id,
        "loai_doi_tuong": 1,
        "id_du_lieu": None,
    }

    resp = S.post(f"{BASE_URL}/api/sch/w-locdstkbhockytheodoituong", json=body)
    raw = resp.json()
    print(f"DEBUG w-locdstkbhockytheodoituong keys: {list(raw.keys())}")
    data = raw.get("data", {})
    if isinstance(data, dict):
        ds = data.get("ds_nhom_to", [])
        print(f"DEBUG ds_nhom_to: {len(ds)} items")
        if ds and isinstance(ds[0], dict):
            print(f"DEBUG first keys: {list(ds[0].keys())}")
        return ds
    else:
        print(f"DEBUG data type: {type(data)}")
        return []

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
def build_ics(ds_nhom_to, hoc_ky_info):
    cal = Calendar()
    cal.add("prodid", "-//VNUA Schedule//VN")
    cal.add("version", "2.0")
    cal.add("X-WR-CALNAME", "Lịch học VNUA")
    cal.add("X-WR-TIMEZONE", "Asia/Ho_Chi_Minh")

    now_utc = datetime.now(tz=timezone.utc)
    count = 0

    start_str = hoc_ky_info.get("ngay_bat_dau_hk", "")
    if not start_str:
        print("Warning: Không có ngày bắt đầu học kỳ")
        return cal.to_ical()

    start_date = datetime.strptime(start_str, "%d/%m/%Y").date()
    monday_w1 = start_date - timedelta(days=start_date.weekday())

    for tkb in ds_nhom_to:
        try:
            bitmap = str(tkb.get("tkb", "")).strip()
            if not bitmap:
                continue

            thu = int(tkb.get("thu", 0))
            if thu < 2 or thu > 8:
                continue

            tu_gio = tkb.get("tu_gio", "")
            den_gio = tkb.get("den_gio", "")
            if not tu_gio or not den_gio:
                continue

            ten_mon = tkb.get("ten_mon", "Môn học")
            phong = str(tkb.get("phong", "")).strip()
            gv = tkb.get("gv", "") or tkb.get("ten_giang_vien", "")
            nhom = tkb.get("nhom_to", "")
            tbd = int(tkb.get("tbd", 0))
            so_tiet = int(tkb.get("so_tiet", 0))

            dow_offset = thu - 2

            for week_idx, char in enumerate(bitmap):
                if char == "-":
                    continue

                week_num = week_idx + 1
                event_date = monday_w1 + timedelta(weeks=week_idx, days=dow_offset)

                dt_start = datetime.strptime(f"{event_date} {tu_gio}", "%Y-%m-%d %H:%M")
                dt_end   = datetime.strptime(f"{event_date} {den_gio}", "%Y-%m-%d %H:%M")

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
                    f"Tiết {tbd}–{tbd + so_tiet - 1} | Nhóm {nhom}\n"
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

    hk_info = get_latest_hocky()
    hk_id = hk_info["hoc_ky"]
    print(f"Học kì: {hk_id} ({hk_info.get('ten_hoc_ky', '')})")

    ds_nhom_to = get_tkb_hocky(hk_id)

    os.makedirs("docs", exist_ok=True)

    with open(OUTPUT_TKB, "wb") as f:
        f.write(build_ics(ds_nhom_to, hk_info))
    print(f"Saved: {OUTPUT_TKB}")

    exam_data = get_exams(hk_id)
    with open(OUTPUT_EXAM, "wb") as f:
        f.write(build_exam_ics(exam_data))
    print(f"Saved: {OUTPUT_EXAM}")
