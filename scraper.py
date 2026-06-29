"""
VNUA Schedule → Google Calendar (.ics)
pip install requests icalendar
"""

import os, json, base64, uuid, hashlib
import requests
from datetime import datetime, timezone, timedelta
from icalendar import Calendar, Event

BASE_URL    = "https://daotao.vnua.edu.vn"
USERNAME    = os.environ.get("SCHOOL_USER", "")
PASSWORD    = os.environ.get("SCHOOL_PASS", "")
OUTPUT_TKB  = "docs/schedule.ics"
OUTPUT_EXAM = "docs/exams.ics"

# Giờ bắt đầu mỗi tiết
TIET_BAT_DAU = {
    1: "07:00",  2: "07:55",  3: "08:50",  4: "09:55",  5: "10:50",
    6: "12:45",  7: "13:40",  8: "14:35",  9: "15:40", 10: "16:35",
    11: "18:00", 12: "18:55", 13: "19:50",
}

# Giờ kết thúc mỗi tiết
TIET_KET_THUC = {
    1: "07:50",  2: "08:45",  3: "09:40",  4: "10:45",  5: "11:40",
    6: "13:35",  7: "14:30",  8: "15:25",  9: "16:30", 10: "17:25",
    11: "18:50", 12: "19:45", 13: "20:40",
}

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

# ── Lấy danh sách học kỳ ────────────────────────────────────────────────────
def get_hocky_list():
    resp = S.post(f"{BASE_URL}/api/sch/w-locdshockytkbuser", json={
        "filter": {"is_tieng_anh": None},
        "additional": {
            "paging": {"limit": 100, "page": 1},
            "ordering": [{"name": "hoc_ky", "order_type": 1}]
        }
    })
    return resp.json()["data"]["ds_hoc_ky"]

# ── Lấy TKB dạng học kỳ (bitmap) ──────────────────────────────────────────────
def get_tkb_hocky(hoc_ky_id):
    resp = S.post(f"{BASE_URL}/api/sch/w-locdstkbhockytheodoituong", json={
        "hoc_ky": hoc_ky_id,
        "loai_doi_tuong": 1,
        "id_du_lieu": None,
    })
    data = resp.json().get("data", {})
    ds = data.get("ds_nhom_to", []) if isinstance(data, dict) else []
    print(f"  HK {hoc_ky_id}: {len(ds)} TKB items")
    return ds

# ── Lấy lịch thi ─────────────────────────────────────────────────────────────
def get_exams(hoc_ky_id):
    resp = S.post(f"{BASE_URL}/api/epm/w-locdslichthisvtheohocky", json={
        "filter": {"hoc_ky": hoc_ky_id, "is_giua_ky": False},
        "additional": {
            "paging": {"limit": 100, "page": 1},
            "ordering": [{"name": None, "order_type": None}]
        }
    })
    data = resp.json().get("data", {})
    ds = data.get("ds_lich_thi") if isinstance(data, dict) else data
    if isinstance(ds, int): ds = []
    elif isinstance(ds, dict): ds = list(ds.values())
    elif not isinstance(ds, list): ds = []
    print(f"  HK {hoc_ky_id}: {len(ds)} exam items")
    return ds

# ── Build TKB .ics ──────────────────────────────────────────────────────────
def build_ics(all_entries, cal_name):
    cal = Calendar()
    cal.add("prodid", "-//VNUA Schedule//VN")
    cal.add("version", "2.0")
    cal.add("X-WR-CALNAME", cal_name)
    cal.add("X-WR-TIMEZONE", "Asia/Ho_Chi_Minh")
    cal.add("METHOD", "PUBLISH")

    now_utc = datetime.now(tz=timezone.utc)
    total_count = 0
    per_hk = {}

    for entry in all_entries:
        try:
            tkb_list = entry.get("tkb_list", [])
            hk_info  = entry.get("hk_info", {})
            start_str = hk_info.get("ngay_bat_dau_hk", "")
            if not start_str:
                continue

            start_date = datetime.strptime(start_str, "%d/%m/%Y").date()
            monday_w1 = start_date - timedelta(days=start_date.weekday())
            hk_id = hk_info.get("hoc_ky", "unknown")
            per_hk[hk_id] = 0

            for tkb in tkb_list:
                bitmap = str(tkb.get("tkb", "")).strip()
                if not bitmap:
                    continue

                thu = int(tkb.get("thu", 0))
                if thu < 2 or thu > 8:
                    continue

                tbd_raw = tkb.get("tbd", 0)
                so_tiet_raw = tkb.get("so_tiet", 0)
                try:
                    tbd = int(str(tbd_raw).strip())
                    so_tiet = int(str(so_tiet_raw).strip())
                except (ValueError, TypeError):
                    continue

                if tbd <= 0 or so_tiet <= 0:
                    continue

                tiet_kt = tbd + so_tiet - 1

                if tbd not in TIET_BAT_DAU or tiet_kt not in TIET_KET_THUC:
                    print(f"DEBUG SKIP: tbd={tbd} tiet_kt={tiet_kt} out of range")
                    continue

                tu_gio = TIET_BAT_DAU[tbd]
                den_gio = TIET_KET_THUC[tiet_kt]

                ten_mon = tkb.get("ten_mon", "Môn học")
                phong = str(tkb.get("phong", "")).strip()
                gv = tkb.get("gv", "") or tkb.get("ten_giang_vien", "")
                nhom = tkb.get("nhom_to", "")
                ma_mon = tkb.get("ma_mon", "")

                dow_offset = thu - 2

                for week_idx, char in enumerate(bitmap):
                    if char == "-":
                        continue

                    week_num = week_idx + 1
                    event_date = monday_w1 + timedelta(weeks=week_idx, days=dow_offset)

                    dt_start = datetime.strptime(f"{event_date} {tu_gio}", "%Y-%m-%d %H:%M")
                    dt_end   = datetime.strptime(f"{event_date} {den_gio}", "%Y-%m-%d %H:%M")

                    uid_seed = f"{ma_mon}|{nhom}|{thu}|{tbd}|{week_num}|{hk_id}"
                    uid = hashlib.md5(uid_seed.encode()).hexdigest() + "@vnua.edu.vn"

                    ev = Event()
                    ev.add("dtstamp", now_utc)
                    ev.add("uid", uid)
                    ev.add("summary", ten_mon)
                    ev.add("dtstart", dt_start)
                    ev.add("dtend", dt_end)
                    ev.add("location", phong)
                    ev.add("description", (
                        f"GV: {gv}\n"
                        f"{phong}\n"
                        f"Tiết {tbd}–{tiet_kt} | Nhóm {nhom}\n"
                        f"Tuần {week_num} | HK {hk_id}"
                    ))
                    ev.add("sequence", 0)
                    cal.add_component(ev)
                    total_count += 1
                    per_hk[hk_id] += 1

        except Exception as e:
            print(f"Skip entry: {e}")
            continue

    print(f"DEBUG TKB per HK: {per_hk}")
    print(f"Total TKB: {total_count} sự kiện")
    return cal.to_ical()

# ── Build Exam .ics ───────────────────────────────────────────────────────────
def build_exam_ics(all_exams):
    cal = Calendar()
    cal.add("prodid", "-//VNUA Exams//VN")
    cal.add("version", "2.0")
    cal.add("X-WR-CALNAME", "Lịch thi VNUA")
    cal.add("X-WR-TIMEZONE", "Asia/Ho_Chi_Minh")
    cal.add("METHOD", "PUBLISH")

    now_utc = datetime.now(tz=timezone.utc)
    count = 0
    per_hk = {}

    for thi in all_exams:
        try:
            ngay_thi  = thi.get("ngay_thi") or thi.get("ngay")
            gio_bd    = thi.get("gio_bat_dau") or thi.get("gio_thi") or "00:00"
            ten_mon   = thi.get("ten_mon") or thi.get("mon_hoc") or "Thi"
            phong_thi = thi.get("phong_thi") or thi.get("ma_phong") or ""
            phong_str = phong_thi.split("-")[0].strip() if phong_thi else ""
            hk_id     = thi.get("hoc_ky", "unknown")

            if hk_id not in per_hk:
                per_hk[hk_id] = 0

            if not ngay_thi:
                continue

            ngay     = datetime.strptime(ngay_thi, "%d/%m/%Y").date()
            dt_start = datetime.strptime(f"{ngay} {gio_bd[:5]}", "%Y-%m-%d %H:%M")
            dt_end   = dt_start + timedelta(minutes=int(thi.get("so_phut", 60)))

            uid_seed = f"EXAM|{ten_mon}|{ngay_thi}|{gio_bd}|{hk_id}"
            uid = hashlib.md5(uid_seed.encode()).hexdigest() + "@vnua.edu.vn"

            desc_parts = []
            if thi.get("hinh_thuc_thi"): desc_parts.append(f"Hình thức: {thi['hinh_thuc_thi']}")
            if phong_str:                desc_parts.append(phong_str)

            ev = Event()
            ev.add("dtstamp", now_utc)
            ev.add("uid", uid)
            ev.add("summary", f"🔴 THI: {ten_mon}")
            ev.add("dtstart", dt_start)
            ev.add("dtend", dt_end)
            ev.add("location", phong_str)
            ev.add("description", "\n".join(desc_parts))
            ev.add("sequence", 0)
            cal.add_component(ev)
            count += 1
            per_hk[hk_id] += 1
        except Exception as e:
            print(f"Skip exam entry: {e}")

    print(f"DEBUG Exam per HK: {per_hk}")
    print(f"Total Lịch thi: {count} sự kiện")
    return cal.to_ical()

# ── Main ──────────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    user_data = login()
    if not user_data:
        raise SystemExit("Login thất bại")

    ds_hk = get_hocky_list()
    print(f"Found {len(ds_hk)} học kỳ: {[h['hoc_ky'] for h in ds_hk]}")

    all_tkb_entries = []
    all_exams = []

    for hk in ds_hk:
        hk_id = hk["hoc_ky"]
        print(f"\nFetching HK {hk_id} ({hk.get('ten_hoc_ky','')})...")

        tkb_list = get_tkb_hocky(hk_id)
        if tkb_list:
            all_tkb_entries.append({"hk_info": hk, "tkb_list": tkb_list})

        exams = get_exams(hk_id)
        all_exams.extend(exams)

    os.makedirs("docs", exist_ok=True)

    with open(OUTPUT_TKB, "wb") as f:
        f.write(build_ics(all_tkb_entries, "Lịch học VNUA"))
    print(f"\nSaved: {OUTPUT_TKB}")

    with open(OUTPUT_EXAM, "wb") as f:
        f.write(build_exam_ics(all_exams))
    print(f"Saved: {OUTPUT_EXAM}")
