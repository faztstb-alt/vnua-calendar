# VNUA Calendar Sync

Đồng bộ lịch học & lịch thi từ hệ thống đào tạo VNUA (daotao.vnua.edu.vn) sang Google Calendar.

## Cách 1: Subscribe .ics (Đơn giản, không cần code)

1. Fork repo này
2. Thêm GitHub Secrets: `SCHOOL_USER` và `SCHOOL_PASS` (tài khoản VNUA)
3. GitHub Actions tự động chạy → tạo file `.ics` trong `docs/`
4. Vào Google Calendar → Add calendar → From URL
5. Dán URL:
   ```
   https://YOUR_USERNAME.github.io/vnua-calendar/schedule.ics
   https://YOUR_USERNAME.github.io/vnua-calendar/exams.ics
   ```

**Ưu điểm:** Dễ setup, không cần server
**Nhược điểm:** Google Calendar tự động refresh chậm (12-24h), không sửa event được

## Cách 2: Google Apps Script (Realtime, có thể sửa event)

### Bước 1: Fork repo & setup GitHub Actions

Giống Cách 1. Đảm bảo Actions chạy thành công, file `.ics` đã lên GitHub Pages.

### Bước 2: Tạo calendar con trong Google Calendar

1. Google Calendar web → bên trái → `+` → **Create new calendar**
2. Tạo 2 calendar:
   - `VNUA Học` (cho TKB)
   - `VNUA Thi` (cho lịch thi)
3. Vào Settings của từng calendar → copy **Calendar ID** (dạng `...@group.calendar.google.com`)

### Bước 3: Bật Google Calendar API

1. Vào [Google Cloud Console](https://console.cloud.google.com/) → project của bạn
2. APIs & Services → Library → tìm **Google Calendar API** → Enable
3. Hoặc trong GAS: Extensions → Google Calendar API → toggle ON

### Bước 4: Deploy GAS

1. Vào [script.google.com](https://script.google.com) → New project
2. Copy code từ file `sync-vnua.gs` trong repo này
3. Sửa `CONFIG`:
   ```javascript
   SCHEDULE_CALENDAR_ID: 'YOUR_SCHEDULE_CALENDAR_ID@group.calendar.google.com',
   EXAM_CALENDAR_ID: 'YOUR_EXAM_CALENDAR_ID@group.calendar.google.com',
   ```
4. Chạy `setup()` → cấp quyền Calendar API
5. Chạy `sync()` lần đầu

### Bước 5: Sync khi có TKB mới

Mỗi khi VNUA cập nhật TKB (đầu học kỳ):
1. Đợi GitHub Actions chạy xong (hoặc trigger manual)
2. Vào GAS → chạy `cleanup()` → xóa event cũ
3. Chạy `sync()` → tạo event mới

### Event Lock

Sửa title event trên Google Calendar, thêm `!` bất kỳ đâu → event đó sẽ không bị `cleanup()` xóa và không bị `sync()` ghi đè.

Ví dụ: `THI: Toán!` hoặc `!LT Nhập môn`

## File trong repo

| File | Mô tả |
|------|-------|
| `scraper.py` | Script Python fetch TKB + lịch thi từ VNUA |
| `.github/workflows/sync.yml` | GitHub Actions cron |
| `docs/schedule.ics` | TKB output |
| `docs/exams.ics` | Lịch thi output |
| `sync-vnua.gs` | Google Apps Script (để trong GAS, không chạy local) |

## Lưu ý

- GitHub Actions free tier: 2,000 phút/tháng
- GAS quota: ~50,000 URL fetch + ~20,000 Calendar API write/ngày
- Nếu bị rate limit: tăng `Utilities.sleep()` trong GAS
- Không chia sẻ `SCHOOL_PASS` hoặc Calendar ID công khai
