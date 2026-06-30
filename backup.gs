// backup.gs – автоматичне резервне копіювання Google Sheets

/**
 * Створює щоденну резервну копію поточної Google‑таблиці у форматі XLSX.
 * Файл зберігається у вказаній папці Google Drive (BackupFolderId).
 * Додайте тригер "Time‑driven" (наприклад, 02:00 години), щоб функція виконувалась щоденно.
 */
function dailySheetBackup() {
  const srcSpreadsheet = SpreadsheetApp.getActiveSpreadsheet();
  const srcId = srcSpreadsheet.getId();
  const today = Utilities.formatDate(new Date(), Session.getScriptTimeZone(), 'yyyy-MM-dd');

  // Public endpoint to trigger backup via HTTP GET
function doGet(e) {
  dailySheetBackup();
  return ContentService.createTextOutput('Backup triggered');
}

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
  } else {
    Logger.log('Backup failed, code: ' + response.getResponseCode());
  }
}

/**
 * Додає щоденний тригер для функції dailySheetBackup.
 * Запустіть її один раз вручну (Run > dailySheetBackup) після розгортання скрипту.
 */
function createDailyBackupTrigger() {
  // Видалити старі тригери (опційно)
  const existing = ScriptApp.getProjectTriggers();
  existing.forEach(t => {
    if (t.getHandlerFunction() === 'dailySheetBackup') {
      ScriptApp.deleteTrigger(t);
    }
  });

  // Створити новий тригер: щоденно о 02:00 за часовим поясом скрипта
  ScriptApp.newTrigger('dailySheetBackup')
    .timeBased()
    .atHour(2)
    .everyDays(1)
    .create();
  Logger.log('Daily backup trigger created at 02:00');
}
