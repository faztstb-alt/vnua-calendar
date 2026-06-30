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

**Ưu điểm:** dễ setup, không cần server.
**Nhược điểm:** Google Calendar tự refresh chậm (12–24h), không sửa event được, không có cơ chế khoá event.

## Cách 2: Google Apps Script (Realtime, có thể sửa event)

### Bước 1: Fork repo & setup GitHub Actions

Giống Cách 1. Đảm bảo Actions chạy thành công, file `.ics` đã lên GitHub Pages.

### Bước 2: Tạo calendar con trong Google Calendar

1. Google Calendar web → bên trái → `+` → **Create new calendar**
2. Tạo 2 calendar: `VNUA Học` (TKB), `VNUA Thi` (lịch thi)
3. Vào Settings từng calendar → copy **Calendar ID** (`...@group.calendar.google.com`)

### Bước 3: Bật Google Calendar API

1. [Google Cloud Console](https://console.cloud.google.com/) → project của bạn
2. APIs & Services → Library → tìm **Google Calendar API** → Enable
3. Hoặc trong GAS: Extensions → Google Calendar API → toggle ON

### Bước 4: Deploy GAS

1. [script.google.com](https://script.google.com) → New project
2. Copy code từ file `sync-vnua.gs` trong repo
3. Sửa `CONFIG`:

```js
SCHEDULE_CALENDAR_ID: 'YOUR_SCHEDULE_CALENDAR_ID@group.calendar.google.com',
EXAM_CALENDAR_ID: 'YOUR_EXAM_CALENDAR_ID@group.calendar.google.com',
```

4. Chạy `setup()` → cấp quyền Calendar API
5. Chạy `sync()` lần đầu

### Bước 5: Sync khi có TKB mới hoặc kỳ mới

Mỗi khi VNUA cập nhật TKB (đầu kỳ, kỳ overlap với kỳ trước):

1. Đợi GitHub Actions chạy xong (hoặc trigger manual)
2. GAS → chạy `sync()`

Đủ. **Không cần chạy `cleanup()`.**

Lý do: UID mỗi buổi học là hash deterministic từ `ma_mon|nhom|thu|tbd|week_num|hk_id`. VNUA không đổi data sau publish → UID không đổi giữa các lần sync. `sync()` tự match UID cũ → giữ nguyên (`kept`) hoặc update field đổi (`updated`), chỉ insert mới (`created`) cho buổi chưa có UID. Kỳ rớt khỏi cửa sổ 2-kỳ-gần-nhất của scraper vẫn giữ nguyên trên Calendar, không bị xoá.

### Khi nào mới cần `cleanup()`

Chỉ chạy khi cần **reset toàn bộ**: đổi format UID, đổi `TAG_UID`, hoặc data bị lỗi cần build lại từ đầu.

⚠️ **Cảnh báo:** `cleanup()` (= `deleteAllTagged()`) xoá **mọi** event có tag UID, **kể cả event đã khoá bằng `!`**. Code hiện tại không check `lockedUids` trong hàm xoá — chỉ `sync()` mới tôn trọng khoá. Sửa tay + khoá rồi chạy `cleanup()` → mất event đó vĩnh viễn.

### Event Lock

Sửa title event trên Google Calendar, thêm `!` bất kỳ đâu → event đó không bị `sync()` ghi đè nội dung.

Ví dụ: `THI: Toán!` hoặc `!LT Nhập môn`

Lưu ý: khoá chỉ chặn `sync()` patch, **không** chặn `cleanup()` xoá (xem cảnh báo trên).

## File trong repo

| File                         | Mô tả                                          |
| ----------------------------- | ----------------------------------------------- |
| `scraper.py`                  | Script Python fetch TKB + lịch thi từ VNUA      |
| `sync-vnua.gs`                | Google Apps Script — paste vào script.google.com, không tự chạy từ repo |
| `.github/workflows/sync.yml`  | GitHub Actions cron                             |
| `docs/schedule.ics`           | TKB output                                      |
| `docs/exams.ics`              | Lịch thi output                                 |

## Lưu ý

- GitHub Actions free tier: 2,000 phút/tháng
- GAS quota: ~50,000 URL fetch + ~20,000 Calendar API write/ngày
- Nếu bị rate limit: tăng `Utilities.sleep()` trong GAS
- Không chia sẻ `SCHOOL_PASS` hoặc Calendar ID công khai

Cảm ơn Claude Sonnet 4.6 và Kimi K2.6 đã tài trợ :D
