// vnua_calendar_sync.gs
// Đọc docs/schedule.json (do scraper.py publish qua GitHub Pages), tạo event vào
// Google Calendar. Mỗi mã học kì chỉ sync 1 lần, chỉ thêm - không sửa/xoá gì cũ.

const SCHEDULE_JSON_URL = "https://<user>.github.io/vnua-calendar/schedule.json"; // TODO: điền URL Pages thật
const CALENDAR_ID = "primary"; // hoặc ID lịch riêng nếu không dùng lịch mặc định
const PROP_KEY = "synced_hocky";

function syncVNUACalendar() {
  const props = PropertiesService.getScriptProperties();
  const synced = JSON.parse(props.getProperty(PROP_KEY) || "[]");

  const res = UrlFetchApp.fetch(SCHEDULE_JSON_URL, { muteHttpExceptions: true });
  if (res.getResponseCode() !== 200) {
    Logger.log("Fetch schedule.json lỗi: HTTP " + res.getResponseCode());
    return;
  }

  const data = JSON.parse(res.getContentText());
  const hocKy = data.hoc_ky;

  // trùng mã học kì cũ -> đã sync rồi, dừng, không đụng gì tới calendar
  if (synced.indexOf(hocKy) !== -1) {
    Logger.log("Học kì " + hocKy + " đã sync trước đó, bỏ qua.");
    return;
  }

  const cal = CALENDAR_ID === "primary"
    ? CalendarApp.getDefaultCalendar()
    : CalendarApp.getCalendarById(CALENDAR_ID);

  let nSeries = 0, nWeeks = 0;

  data.series.forEach(function (s) {
    const start = new Date(s.start_date + "T" + s.start_time + ":00");
    const end = new Date(s.start_date + "T" + s.end_time + ":00");
    const desc = "GV: " + s.giang_vien + "\n" + s.phong + "\nTiết " + s.tiet + " | Nhóm " + s.nhom;

    if (s.weeks > 1) {
      cal.createEventSeries(
        s.mon,
        start,
        end,
        CalendarApp.newRecurrence().addWeeklyRule().times(s.weeks),
        { location: s.phong, description: desc }
      );
    } else {
      cal.createEvent(s.mon, start, end, { location: s.phong, description: desc });
    }
    nSeries++;
    nWeeks += s.weeks;
  });

  // đánh dấu học kì này đã sync - append, không ghi đè danh sách cũ
  synced.push(hocKy);
  props.setProperty(PROP_KEY, JSON.stringify(synced));

  Logger.log("Sync xong học kì " + hocKy + ": " + nSeries + " chuỗi sự kiện (" + nWeeks + " buổi gốc).");
}

// Chạy 1 lần thủ công để tạo trigger tự động.
// Apps Script không có mốc "nửa tháng" sẵn, nên set trigger hàng tuần là đủ -
// vì hàm này tự no-op nếu hoc_ky đã sync, tần suất trigger không quan trọng.
function setupWeeklyTrigger() {
  ScriptApp.getProjectTriggers().forEach(function (t) {
    if (t.getHandlerFunction() === "syncVNUACalendar") ScriptApp.deleteTrigger(t);
  });
  ScriptApp.newTrigger("syncVNUACalendar")
    .timeBased()
    .onWeekDay(ScriptApp.WeekDay.MONDAY)
    .atHour(6)
    .create();
}

// Debug: xem đã sync học kì nào, và reset nếu cần test lại (không xoá event cũ,
// chỉ xoá cái "nhớ" để chạy lại logic thêm - cẩn thận sẽ tạo trùng event nếu chạy lại
// mà source data giữ nguyên hoc_ky cũ).
function resetSyncedHistory() {
  PropertiesService.getScriptProperties().deleteProperty(PROP_KEY);
}
