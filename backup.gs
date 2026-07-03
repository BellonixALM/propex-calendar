// backup.gs – автоматичне резервне копіювання Google Sheets та діагностичні ендпоінти

/**
 * Створює щоденну резервну копію поточної Google‑таблиці у форматі XLSX.
 * Файл зберігається у вказаній папці Google Drive (BackupFolderId).
 */
function dailySheetBackup() {
  const srcSpreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const srcId = srcSpreadsheet.getId();
  const today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');
  const backupFolderId = '1BDYJdlZHbMll1VMHuIUCnUasLTgTLLSt'; // folder for daily backups

  const exportUrl = `https://docs.google.com/spreadsheets/d/${srcId}/export?format=xlsx`;
  const token = ScriptApp.getOAuthToken();
  const response = UrlFetchApp.fetch(exportUrl, {
    headers: { Authorization: 'Bearer ' + token },
    muteHttpExceptions: true
  });

  if (response.getResponseCode() === 200) {
    const blob = response.getBlob().setName(`CRM_backup_${today}.xlsx`);
    const folder = DriveApp.getFolderById(backupFolderId);
    folder.createFile(blob);
    Logger.log('Backup saved for ' + today);
    return 'Backup saved successfully';
  } else {
    Logger.log('Backup failed, code: ' + response.getResponseCode());
    return 'Backup failed: ' + response.getResponseCode();
  }
}

// Public endpoint to trigger backup or inspect Odometer Sheet
function doGet(e) {
  var action = e && e.parameter ? e.parameter.action : '';
  
  if (action === 'inspect') {
    return ContentService.createTextOutput(testInspectOdometer())
      .setMimeType(ContentService.MimeType.TEXT);
  }
  
  var res = dailySheetBackup();
  return ContentService.createTextOutput('Backup triggered: ' + res);
}

// Temporary test function to inspect columns of odometer spreadsheet
function testInspectOdometer() {
  try {
    var ss = SpreadsheetApp.openById('17r2oSP52TFIAiGegGTWlHsxRmHN7iEX2W5M4aYUKM54');
    var sheets = ss.getSheets();
    var log = [];
    sheets.forEach(function(s) {
      log.push('Sheet name: ' + s.getName());
      var range = s.getDataRange();
      var values = range.getValues();
      if (values.length > 0) {
        log.push('Headers: ' + JSON.stringify(values[0]));
        log.push('First data row: ' + JSON.stringify(values[1] || 'None'));
      }
    });
    return log.join('\n');
  } catch(e) {
    return 'Error inspecting odometer sheet: ' + e.toString();
  }
}

/**
 * Додає щоденний тригер для функції dailySheetBackup.
 */
function createDailyBackupTrigger() {
  const existing = ScriptApp.getProjectTriggers();
  existing.forEach(t => {
    if (t.getHandlerFunction() === 'dailySheetBackup') {
      ScriptApp.deleteTrigger(t);
    }
  });

  ScriptApp.newTrigger('dailySheetBackup')
    .timeBased()
    .atHour(2)
    .everyDays(1)
    .create();
  Logger.log('Daily backup trigger created at 02:00');
}
