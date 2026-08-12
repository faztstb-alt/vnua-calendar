# VNUA Calendar Sync

Đồng bộ lịch học & lịch thi từ hệ thống đào tạo VNUA (daotao.vnua.edu.vn) sang Google Calendar.

## Cách 1: Subscribe .ics (đơn giản, không cần code)

1. Fork repo này
2. Thêm GitHub Secrets: `SCHOOL_USER` và `SCHOOL_PASS` (tài khoản VNUA)
3. GitHub Actions tự chạy → tạo `docs/schedule.ics` và `docs/exams.ics`
4. Google Calendar → Add calendar → From URL → dán:

```
https://YOUR_USERNAME.github.io/vnua-calendar/schedule.ics
https://YOUR_USERNAME.github.io/vnua-calendar/exams.ics
```

**Ưu điểm:** không cần deploy gì thêm. **Nhược điểm:** Google tự refresh chậm (12–24h), không tuỳ biến được.

## Cách 2: Google Apps Script (chủ động sync, tô màu phòng)

### Bước 1: Fork repo & bật GitHub Actions

Giống Cách 1. Đảm bảo Actions chạy xanh, `.ics` đã lên GitHub Pages.

### Bước 2: Tạo calendar con

Google Calendar → `+` → Create new calendar → tạo 2 cái (TKB, lịch thi) → Settings từng cái → copy Calendar ID (`...@group.calendar.google.com`).

### Bước 3: Bật Google Calendar API cho project Apps Script

script.google.com → New project → Extensions → Google Calendar API → toggle ON (hoặc qua Google Cloud Console như bình thường).

### Bước 4: Deploy

1. Copy toàn bộ `sync-vnua.gs` vào script.google.com
2. Sửa trong `CONFIG`:

```js
SCHEDULE_CALENDAR_ID: 'your-schedule-calendar-id@group.calendar.google.com',
EXAM_CALENDAR_ID: 'your-exam-calendar-id@group.calendar.google.com',
```

3. Chọn hàm `setup` trong dropdown Run → chạy → cấp quyền
4. Chọn hàm `sync` → chạy lần đầu

### Bước 5: Đặt trigger tự động (tuỳ chọn)

Apps Script → đồng hồ bên trái (Triggers) → Add Trigger → chọn hàm `sync`, loại time-driven, tần suất tuỳ ý (script tự gate theo học kỳ nên chạy thường xuyên cũng không tạo trùng).

## Cơ chế sync

- **1 lần / học kỳ:** mỗi file `.ics` có `X-HOCKY:<mã kỳ>` ở đầu. `sync()` so mã này với lần sync trước (lưu trong Script Properties) — trùng thì bỏ qua toàn bộ, không gọi Calendar API.
- **Chỉ thêm, không sửa:** event đã tồn tại (theo UID) thì giữ nguyên. Kỳ mới chỉ thêm event mới, không đụng event kỳ cũ.
- **Lặp thật, không chép tay:** buổi học liên tiếp cùng lớp/phòng/tiết gộp thành 1 event Calendar có recurrence (`RRULE`), không tạo N event rời.
- **Tô màu phòng THT:** phòng chứa chữ `THT` tự động lên màu đỏ cà chua.

## Reset / debug

Nút Run trên script.google.com không cho nhập tham số, nên đừng chạy thẳng `resetSyncedHistory(prefix)` — dùng 2 hàm không tham số:

- `resetScheduleHistory` — xoá dấu đã-sync của lịch học
- `resetExamHistory` — xoá dấu đã-sync của lịch thi
- `checkSyncedHistory` — xem log đang lưu mã kỳ nào cho mỗi loại, dùng để kiểm tra trước khi nghi ngờ có bug

Reset không đụng gì tới event đã tạo trên Calendar, chỉ xoá cái "nhớ" để lần `sync()` kế tiếp chạy lại từ đầu.

## Build lại từ đầu

`cleanup()` xoá **mọi** event có gắn tag UID trên cả 2 calendar. Chạy xong nhớ `resetScheduleHistory` + `resetExamHistory` rồi mới `sync()` lại — không thì bị gate chặn, sync xong Calendar vẫn trống.

## File trong repo

| File | Mô tả |
|---|---|
| `scraper.py` | Fetch TKB + lịch thi từ VNUA, build `.ics` |
| `sync-vnua.gs` | Google Apps Script — dán tay vào script.google.com, không tự chạy từ repo |
| `.github/workflows/sync.yml` | GitHub Actions cron chạy `scraper.py` |
| `docs/schedule.ics`, `docs/exams.ics` | Output cho cả 2 cách dùng |

## Lưu ý

- Không share `SCHOOL_PASS` hoặc Calendar ID công khai
- GAS quota: ~20,000 Calendar API write/ngày — dư dả cho quy mô 1 sinh viên
