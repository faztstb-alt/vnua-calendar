var CONFIG = {
  SCHEDULE_URL: 'https://faztstb-alt.github.io/vnua-calendar/schedule.ics',
  EXAM_URL: 'https://faztstb-alt.github.io/vnua-calendar/exams.ics',
  SCHEDULE_CALENDAR_ID: 'YOUR_SCHEDULE_CALENDAR_ID',
  EXAM_CALENDAR_ID: 'YOUR_EXAM_CALENDAR_ID',
  TAG_UID: 'vnua-uid'
};

function sync() {
  checkCalendar(CONFIG.SCHEDULE_CALENDAR_ID, 'Schedule');
  checkCalendar(CONFIG.EXAM_CALENDAR_ID, 'Exam');

  syncICS(CONFIG.SCHEDULE_CALENDAR_ID, CONFIG.SCHEDULE_URL, 'schedule');
  syncICS(CONFIG.EXAM_CALENDAR_ID, CONFIG.EXAM_URL, 'exam');
}

function checkCalendar(calId, label) {
  try {
    Calendar.Calendars.get(calId);
  } catch (e) {
    throw new Error(label + ' calendar not found: ' + e.message);
  }
}

function syncICS(calId, url, prefix) {
  var rawText = fetchICS(url);
  Logger.log(prefix + ' raw length ' + rawText.length);

  var icsEvents = parseICS(rawText);
  if (icsEvents.length === 0) {
    Logger.log(prefix + ' ICS has 0 events - check scraper');
    return;
  }
  Logger.log(prefix + ' ICS has ' + icsEvents.length + ' events');

  var first = icsEvents[0];
  Logger.log('First ' + prefix + ' ' + first.summary + ' ' + first.start + ' ' + first.end);

  var now = new Date();
  var start = new Date(now.getFullYear() - 1, 0, 1);
  var end = new Date(now.getFullYear() + 1, 11, 31);
  var existing = listEvents(calId, start, end);
  var existingMap = {};
  var lockedUids = {};

  var i;
  for (i = 0; i < existing.length; i++) {
    var ev = existing[i];
    var uid = getTagValue(ev);
    if (uid) {
      existingMap[uid] = ev;
      if (ev.summary && ev.summary.indexOf('!') !== -1) {
        lockedUids[uid] = true;
      }
    }
  }

  Logger.log('Existing VNUA events ' + Object.keys(existingMap).length);

  var created = 0;
  var updated = 0;
  var kept = 0;
  var locked = 0;

  var j;
  for (j = 0; j < icsEvents.length; j++) {
    var ice = icsEvents[j];
    var ev = existingMap[ice.uid];

    if (!ev) {
      var resource = {
        summary: ice.summary,
        location: ice.location,
        description: ice.description,
        start: { dateTime: ice.start.toISOString() },
        end: { dateTime: ice.end.toISOString() },
        extendedProperties: { private: {} }
      };
      resource.extendedProperties.private[CONFIG.TAG_UID] = ice.uid;

      Calendar.Events.insert(resource, calId);
      created = created + 1;
      Utilities.sleep(200);
      if (created % 30 === 0) {
        Utilities.sleep(3000);
        Logger.log('Pause after ' + created);
      }
    } else if (lockedUids[ice.uid]) {
      Logger.log('LOCKED ' + ev.summary);
      locked = locked + 1;
    } else {
      var changed = false;
      var evStart = new Date(ev.start.dateTime || ev.start.date);
      var evEnd = new Date(ev.end.dateTime || ev.end.date);

      if (ev.summary !== ice.summary) changed = true;
      if ((ev.location || '') !== ice.location) changed = true;
      if (evStart.getTime() !== ice.start.getTime()) changed = true;
      if (evEnd.getTime() !== ice.end.getTime()) changed = true;

      if (changed) {
        var patchResource = {
          summary: ice.summary,
          location: ice.location,
          description: ice.description,
          start: { dateTime: ice.start.toISOString() },
          end: { dateTime: ice.end.toISOString() }
        };
        Calendar.Events.patch(patchResource, calId, ev.id);
        updated = updated + 1;
        Utilities.sleep(200);
        if (updated % 30 === 0) {
          Utilities.sleep(3000);
        }
      } else {
        kept = kept + 1;
      }
    }
  }

  Logger.log(prefix + ' done ' + created + ' created ' + updated + ' updated ' + kept + ' kept ' + locked + ' locked');
}

function getTagValue(ev) {
  if (ev.extendedProperties && ev.extendedProperties.private) {
    return ev.extendedProperties.private[CONFIG.TAG_UID];
  }
  return null;
}

function listEvents(calId, start, end) {
  var events = [];
  var pageToken = null;
  do {
    var resp = Calendar.Events.list(calId, {
      timeMin: start.toISOString(),
      timeMax: end.toISOString(),
      maxResults: 2500,
      singleEvents: true,
      pageToken: pageToken
    });
    if (resp.items) events = events.concat(resp.items);
    pageToken = resp.nextPageToken;
  } while (pageToken);
  return events;
}

function fetchICS(url) {
  var fullUrl = url + '?v=' + new Date().getTime();
  var resp = UrlFetchApp.fetch(fullUrl, {muteHttpExceptions: true});
  if (resp.getResponseCode() !== 200) {
    Logger.log('Fetch error HTTP ' + resp.getResponseCode());
    return '';
  }
  return resp.getContentText();
}

function parseICS(text) {
  var rawLines = text.split(String.fromCharCode(10));
  var lines = [];
  var i;
  for (i = 0; i < rawLines.length; i++) {
    var line = rawLines[i];
    if (line.charAt(0) === String.fromCharCode(13)) {
      line = line.substring(1);
    }
    if (line.charAt(line.length - 1) === String.fromCharCode(13)) {
      line = line.substring(0, line.length - 1);
    }

    if (line.length > 0 && (line.charAt(0) === ' ' || line.charAt(0) === String.fromCharCode(9))) {
      if (lines.length > 0) {
        lines[lines.length - 1] = lines[lines.length - 1] + line.substring(1);
      }
    } else {
      lines.push(line);
    }
  }

  var events = [];
  var cur = null;

  for (i = 0; i < lines.length; i++) {
    var line = lines[i].trim();

    if (line === 'BEGIN:VEVENT') {
      cur = {};
      cur.summary = '';
      cur.start = null;
      cur.end = null;
      cur.location = '';
      cur.description = '';
      cur.uid = '';
    } else if (line === 'END:VEVENT') {
      if (cur && cur.uid && cur.start && cur.end) {
        events.push(cur);
      }
      cur = null;
    } else if (cur) {
      if (line.indexOf('UID:') === 0) {
        cur.uid = line.substring(4).trim();
      } else if (line.indexOf('SUMMARY:') === 0) {
        cur.summary = line.substring(8).trim();
      } else if (line.indexOf('LOCATION:') === 0) {
        cur.location = line.substring(9).trim();
      } else if (line.indexOf('DESCRIPTION:') === 0) {
        cur.description = line.substring(12).trim();
      } else if (line.indexOf('DTSTART') === 0) {
        cur.start = parseDT(line);
      } else if (line.indexOf('DTEND') === 0) {
        cur.end = parseDT(line);
      }
    }
  }
  return events;
}

function parseDT(line) {
  var lastColon = line.lastIndexOf(':');
  var val = line.substring(lastColon + 1);
  val = val.trim();
  var y = parseInt(val.substr(0, 4), 10);
  var m = parseInt(val.substr(4, 2), 10) - 1;
  var d = parseInt(val.substr(6, 2), 10);
  var h = parseInt(val.substr(9, 2), 10);
  var min = parseInt(val.substr(11, 2), 10);
  var secStr = val.substr(13, 2);
  var s;
  if (secStr && secStr.length > 0) {
    s = parseInt(secStr, 10);
  } else {
    s = 0;
  }
  return new Date(Date.UTC(y, m, d, h - 7, min, s));
}

function setup() {
  checkCalendar(CONFIG.SCHEDULE_CALENDAR_ID, 'Schedule');
  checkCalendar(CONFIG.EXAM_CALENDAR_ID, 'Exam');
  Logger.log('Schedule OK');
  Logger.log('Exam OK');
}

function deleteAllTagged() {
  var now = new Date();
  var start = new Date(now.getFullYear() - 1, 0, 1);
  var end = new Date(now.getFullYear() + 1, 11, 31);

  var ev1 = listEvents(CONFIG.SCHEDULE_CALENDAR_ID, start, end);
  var ev2 = listEvents(CONFIG.EXAM_CALENDAR_ID, start, end);

  var toDelete = [];
  var i;
  for (i = 0; i < ev1.length; i++) {
    if (getTagValue(ev1[i])) toDelete.push({ calId: CONFIG.SCHEDULE_CALENDAR_ID, id: ev1[i].id });
  }
  for (i = 0; i < ev2.length; i++) {
    if (getTagValue(ev2[i])) toDelete.push({ calId: CONFIG.EXAM_CALENDAR_ID, id: ev2[i].id });
  }

  Logger.log('Found ' + toDelete.length + ' VNUA events to delete');

  var deleted = 0;
  for (i = 0; i < toDelete.length; i++) {
    Calendar.Events.remove(toDelete[i].calId, toDelete[i].id);
    deleted = deleted + 1;
    Utilities.sleep(200);
    if (deleted % 30 === 0) {
      Utilities.sleep(3000);
      Logger.log('Pause cleanup after ' + deleted);
    }
  }

  Logger.log('Cleaned ' + deleted + ' events');
}

function cleanup() {
  deleteAllTagged();
}

function cleanOld() {
  deleteAllTagged();
}
