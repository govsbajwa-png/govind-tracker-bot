/**
 * Google Apps Script for Govind Tracker Bot
 *
 * SETUP:
 * 1. Open your Google Sheet
 * 2. Extensions → Apps Script
 * 3. Delete everything and paste this entire file
 * 4. Click Deploy → New deployment
 * 5. Type: Web app
 * 6. Execute as: Me
 * 7. Who has access: Anyone
 * 8. Click Deploy → Copy the URL
 * 9. Put the URL in your bot's GOOGLE_APPS_SCRIPT_URL env var
 */

function doPost(e) {
  try {
    var data = JSON.parse(e.postData.contents);
    var action = data.action;

    if (action === "write_row") {
      return writeRow(data.date, data.values);
    } else if (action === "update_cell") {
      return updateCell(data.date, data.column, data.value);
    } else {
      return jsonResponse({ error: "Unknown action: " + action });
    }
  } catch (err) {
    return jsonResponse({ error: err.toString() });
  }
}

function doGet(e) {
  return ContentService.createTextOutput("Govind Tracker API is running");
}

/**
 * Find the row for a given date string in column B.
 * Dates in the sheet look like "31-Mar", "1-Apr", etc.
 */
function findDateRow(dateStr) {
  var sheet = SpreadsheetApp.getActiveSpreadsheet().getSheetByName("Tracker");
  var dateCol = sheet.getRange("B1:B500").getValues(); // Search first 500 rows

  for (var i = 0; i < dateCol.length; i++) {
    var cellVal = dateCol[i][0];

    // Handle Date objects (Google Sheets may store dates as Date objects)
    if (cellVal instanceof Date) {
      var months = ["Jan","Feb","Mar","Apr","May","Jun","Jul","Aug","Sep","Oct","Nov","Dec"];
      cellVal = cellVal.getDate() + "-" + months[cellVal.getMonth()];
    }

    if (String(cellVal).trim() === dateStr) {
      return { row: i + 1, sheet: sheet };
    }
  }

  return null;
}

/**
 * Write a full row of values (columns C through U) for a given date.
 */
function writeRow(dateStr, values) {
  var result = findDateRow(dateStr);
  if (!result) {
    return jsonResponse({ error: "Date not found: " + dateStr });
  }

  var row = result.row;
  var sheet = result.sheet;

  // Write values to columns C through U (columns 3 to 21)
  // Only write non-empty values to avoid overwriting existing data
  for (var i = 0; i < values.length && i < 19; i++) {
    var col = i + 3; // Column C = 3
    var val = values[i];
    if (val !== "" && val !== null && val !== undefined) {
      sheet.getRange(row, col).setValue(val);
    }
  }

  return jsonResponse({ success: true, row: row, date: dateStr });
}

/**
 * Update a single cell for a given date and column letter.
 */
function updateCell(dateStr, columnLetter, value) {
  var result = findDateRow(dateStr);
  if (!result) {
    return jsonResponse({ error: "Date not found: " + dateStr });
  }

  var cell = columnLetter + result.row;
  result.sheet.getRange(cell).setValue(value);

  return jsonResponse({ success: true, cell: cell, value: value });
}

function jsonResponse(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
