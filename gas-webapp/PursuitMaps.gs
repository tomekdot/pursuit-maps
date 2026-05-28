/**
 * Pursuit Maps - Google Apps Script Web App
 * ===========================================
 *
 * INSTALL (once):
 * 1. Open Sheet → Extensions → Apps Script
 * 2. Paste this entire code
 * 3. Save (Ctrl+S)
 * 4. Deploy → New deployment
 *    - Type: Web app
 *    - Execute as: Me
 *    - Who has access: Anyone (or Anyone with link)
 * 5. Click "Deploy"
 * 6. Copy the URL shown under "Web app URL"
 * 7. Paste URL into:
 *    - Local: write in URL=... below
 *    - GitHub: add as secret GAS_WEBAPP_URL
 *
 * USAGE:
 * - Manually: open browser and visit URL with parameter ?action=sync
 * - Local: python3 gas_webapp_runner.py
 * - GitHub Actions: automatically at 5:00 UTC
 */

var SHEET_ID = '1PwcF1PXHnYhyE23-VPqHewkD_lcNMPIg7LXDN_NaVHQ';
var SHEET_GID = 763170857;
var SHEET_NAME = '';

/**
 * Handle HTTP GET requests
 */
function doGet(e) {
  if (!e || !e.parameter) {
    return ContentService.createTextOutput(JSON.stringify({
      status: 'ok',
      message: 'Pursuit Maps GAS is alive. Use POST with JSON body.'
    })).setMimeType(ContentService.MimeType.JSON);
  }
  var action = e.parameter.action || 'ping';

  if (action === 'ping') {
    var ss = SpreadsheetApp.openById(SHEET_ID);
    var sheet = getSheet(ss);
    return ContentService.createTextOutput(JSON.stringify({
      status: 'ok',
      sheet: sheet.getName(),
      rows: sheet.getLastRow()
    })).setMimeType(ContentService.MimeType.JSON);
  }

  if (action === 'sync') {
    var payload = e.parameter.data;
    if (!payload) {
      return ContentService.createTextOutput(JSON.stringify({
        status: 'error',
        message: 'Missing data parameter'
      })).setMimeType(ContentService.MimeType.JSON);
    }
    var data;
    try {
      data = JSON.parse(decodeURIComponent(payload));
    } catch(err) {
      return ContentService.createTextOutput(JSON.stringify({
        status: 'error',
        message: 'Invalid JSON: ' + err.message
      })).setMimeType(ContentService.MimeType.JSON);
    }
    var result = performSync(data);
    return ContentService.createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON);
  }

  if (action === 'votes') {
    var payload = e.parameter.data;
    var data;
    try {
      data = JSON.parse(decodeURIComponent(payload));
    } catch(err) {
      return ContentService.createTextOutput(JSON.stringify({
        status: 'error',
        message: 'Invalid JSON: ' + err.message
      })).setMimeType(ContentService.MimeType.JSON);
    }
    var result = updateVotes(data);
    return ContentService.createTextOutput(JSON.stringify(result))
      .setMimeType(ContentService.MimeType.JSON);
  }

  return ContentService.createTextOutput(JSON.stringify({
    status: 'error',
    message: 'Unknown action: ' + action
  })).setMimeType(ContentService.MimeType.JSON);
}

/**
 * Handle HTTP POST requests (preferred for large data)
 */
function doPost(e) {
  var payload;
  try {
    if (!e || !e.postData || !e.postData.contents) {
      return ContentService.createTextOutput(JSON.stringify({
        status: 'error',
        message: 'No POST data received'
      })).setMimeType(ContentService.MimeType.JSON);
    }
    payload = JSON.parse(e.postData.contents);
  } catch(err) {
    return ContentService.createTextOutput(JSON.stringify({
      status: 'error',
      message: 'Invalid JSON: ' + err.message
    })).setMimeType(ContentService.MimeType.JSON);
  }

  var action = payload.action || 'sync';
  var result;

  if (action === 'sync') {
    result = performSync(payload);
  } else if (action === 'votes') {
    result = updateVotes(payload);
  } else if (action === 'setup') {
    result = addHeaders();
  } else {
    result = { status: 'error', message: 'Unknown action: ' + action };
  }

  return ContentService.createTextOutput(JSON.stringify(result))
    .setMimeType(ContentService.MimeType.JSON);
}

/**
 * Get the target sheet by GID
 */
function getSheet(ss) {
  var sheets = ss.getSheets();
  for (var i = 0; i < sheets.length; i++) {
    if (sheets[i].getSheetId() == SHEET_GID) {
      SHEET_NAME = sheets[i].getName();
      return sheets[i];
    }
  }
  // fallback: try by name
  try {
    SHEET_NAME = 'Pursuit Channels New';
    return ss.getSheetByName(SHEET_NAME);
  } catch(e) {
    return sheets[0];
  }
}

/**
 * Main sync: add new rows + fill empty cells
 *
 * Expected payload:
 * {
 *   "action": "sync",
 *   "maps": [
 *     {
 *       "uid": "...",
 *       "name": "...",
 *       "author": "...",
 *       "env": "...",
 *       "uploaded": "...",
 *       "maptype": "...",
 *       "notes": "..."
 *     }
 *   ],
 *   "existing": {
 *     "UID": { "row": 5, "fill": { "C": "author", "D": "Valley" } }
 *   }
 * }
 */
function performSync(payload) {
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var sheet = getSheet(ss);

  var newMaps = payload.maps || [];
  var existing = payload.existing || {};

  var lastRow = sheet.getLastRow();
  var added = 0;
  var filled = 0;
  var errors = [];

  // Column mapping: A=1(#), B=2(name), C=3(author), D=4(env), E=5(uploaded),
  //                  F=6(uid), G=7(maptype), H=8(notes), I=9(yn_rating),
  //                  J=10(yn_votes), K=11(stars_avg), L=12(stars_total)

  // 1. Add new rows
  if (newMaps.length > 0) {
    var startRow = lastRow + 1;
    var numRows = newMaps.length;
    var values = [];

    for (var i = 0; i < newMaps.length; i++) {
      var m = newMaps[i];
      values.push([
        startRow + i - lastRow,  // row number
        m.name || '',
        m.author || '',
        m.env || '',
        m.uploaded || '',
        m.uid || '',
        m.maptype || '',
        m.notes || ''
      ]);
    }

    try {
      var range = sheet.getRange(startRow, 1, numRows, 8);
      range.setValues(values);
      added = numRows;
    } catch(e) {
      errors.push('Failed to add rows: ' + e.message);
    }
  }

  // 2. Fill empty cells in existing rows
  var cellUpdates = [];
  for (var uid in existing) {
    if (!existing.hasOwnProperty(uid)) continue;
    var info = existing[uid];
    var row = info.row;
    var fill = info.fill || {};

    for (var col in fill) {
      if (!fill.hasOwnProperty(col)) continue;
      var colNum = col.charCodeAt(0) - 'A'.charCodeAt(0) + 1;
      cellUpdates.push({
        row: row,
        col: colNum,
        value: fill[col]
      });
    }
  }

  // Apply cell updates in batch
  for (var j = 0; j < cellUpdates.length; j++) {
    try {
      sheet.getRange(cellUpdates[j].row, cellUpdates[j].col)
           .setValue(cellUpdates[j].value);
      filled++;
    } catch(e) {
      errors.push('Failed to fill R' + cellUpdates[j].row +
                  'C' + cellUpdates[j].col + ': ' + e.message);
    }
  }

  return {
    status: 'ok',
    sheetName: SHEET_NAME,
    newRowsAdded: added,
    cellsFilled: filled,
    errors: errors,
    totalRows: sheet.getLastRow()
  };
}

/**
 * Update vote columns (I, J, K, L) for existing rows
 *
 * Expected payload:
 * {
 *   "action": "votes",
 *   "votes": {
 *     "UID": {
 *       "yn_rating": "3.5/5",
 *       "yn_votes": "42",
 *       "stars_avg": "4.2/5",
 *       "stars_total": "565"
 *     }
 *   },
 *   "uid_to_row": { "UID": 5 }
 * }
 */
function updateVotes(payload) {
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var sheet = getSheet(ss);

  var votes = payload.votes || {};
  var uidToRow = payload.uid_to_row || {};

  // Build UID to row mapping from current sheet if not provided
  if (Object.keys(uidToRow).length === 0) {
    var dataRange = sheet.getDataRange();
    var data = dataRange.getValues();
    for (var i = 1; i < data.length; i++) {  // skip header
      if (data[i][5]) {  // column F = UID
        uidToRow[data[i][5]] = i + 1;  // 1-based row
      }
    }
  }

  var updated = 0;
  var skipped = 0;
  var errors = [];

  for (var uid in votes) {
    if (!votes.hasOwnProperty(uid)) continue;

    var row = uidToRow[uid];
    if (!row) {
      skipped++;
      continue;
    }

    var v = votes[uid];
    try {
      // Column I (9) = YN Rating
      if (v.yn_rating) sheet.getRange(row, 9).setValue(v.yn_rating);
      // Column J (10) = YN Votes
      if (v.yn_votes !== undefined && v.yn_votes !== '') {
        sheet.getRange(row, 10).setValue(v.yn_votes);
      }
      // Column K (11) = 5-Star Avg
      if (v.stars_avg) sheet.getRange(row, 11).setValue(v.stars_avg);
      // Column L (12) = 5-Star Total
      if (v.stars_total !== undefined && v.stars_total !== '') {
        sheet.getRange(row, 12).setValue(v.stars_total);
      }
      updated++;
    } catch(e) {
      errors.push('R' + row + ': ' + e.message);
    }
  }

  return {
    status: 'ok',
    updated: updated,
    skipped: skipped,
    errors: errors
  };
}

/**
 * Add the new column headers if they don't exist
 * POST with: {"action": "setup"}
 */
function addHeaders() {
  var ss = SpreadsheetApp.openById(SHEET_ID);
  var sheet = getSheet(ss);
  var headers = sheet.getRange('A1:L1').getValues()[0];

  var colI = headers[8];  // 0-indexed: 8 = column I
  var colJ = headers[9];
  var colK = headers[10];
  var colL = headers[11];

  if (!colI) sheet.getRange('I1').setValue('YN Rating');
  if (!colJ) sheet.getRange('J1').setValue('YN Votes');
  if (!colK) sheet.getRange('K1').setValue('5-Star Avg');
  if (!colL) sheet.getRange('L1').setValue('5-Star Total');

  return { status: 'ok', message: 'Headers added/verified' };
}
