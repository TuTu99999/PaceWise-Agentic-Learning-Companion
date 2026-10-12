import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

// Runtime is supplied by the spreadsheet skill, not a product dependency.
const runtime = process.env.ARTIFACT_TOOL_PATH;
if (!runtime) throw new Error('Set ARTIFACT_TOOL_PATH to the artifact-tool public entry point.');
const { Workbook, SpreadsheetFile } = await import(pathToFileURL(runtime).href);
const outputDir = path.resolve('outputs/teacher-course-management-20261010');
await fs.mkdir(outputDir, { recursive: true });
const workbook = Workbook.create();
const definitions = [
  { name: 'Courses', headers: ['course_code', 'course_name', 'term'],
    sample: ['CS101', 'Nhập môn lập trình', 'Học kỳ 1 · 2026–2027'], color: '#25457B' },
  { name: 'Lessons', headers: ['course_code', 'title', 'date', 'start_time', 'end_time', 'repeat_count', 'mode', 'location', 'meeting_url'],
    sample: ['CS101', 'Buổi hướng dẫn', new Date('2026-10-12T00:00:00Z'), '09:00', '10:00', 4, 'offline', 'A101', ''], color: '#4169E1' },
  { name: 'Tasks', headers: ['course_code', 'title', 'kind', 'deadline', 'points', 'published', 'chapter', 'group_name'],
    sample: ['CS101', 'Bài tập tuần', 'assignment', new Date('2026-10-16T23:59:00Z'), 10, false, 'Chương 1', 'Bài tập'], color: '#0F766E' },
  { name: 'Weights', headers: ['course_code', 'group_name', 'weight'],
    sample: ['CS101', 'Bài tập', 100], color: '#8057CC' },
];
for (const item of definitions) {
  const sheet = workbook.worksheets.add(item.name);
  sheet.showGridLines = false;
  sheet.tabColor = item.color;
  sheet.freezePanes.freezeRows(1);
  sheet.getRangeByIndexes(0, 0, 1, item.headers.length).values = [item.headers];
  sheet.getRangeByIndexes(1, 0, 1, item.sample.length).values = [item.sample];
  const head = sheet.getRangeByIndexes(0, 0, 1, item.headers.length);
  head.format.fill = item.color;
  head.format.font = { bold: true, color: '#FFFFFF' };
  head.format.rowHeight = 32;
  const body = sheet.getRangeByIndexes(1, 0, 20, item.headers.length);
  body.format.fill = '#F4F7FC';
  body.format.font = { color: '#25457B' };
  body.format.rowHeight = 26;
  body.setNumberFormat('@');
  sheet.getRangeByIndexes(0, 0, 21, item.headers.length).format.columnWidth = 22;
  sheet.getRange('B:B').format.columnWidth = 34;
  if (item.name === 'Lessons') {
    sheet.getRange('C2:C501').setNumberFormat('yyyy-mm-dd');
    sheet.getRange('F2:F501').setNumberFormat('0');
    sheet.getRange('I:I').format.columnWidth = 36;
    sheet.getRange('G2:G501').dataValidation = { rule: { type: 'list', values: ['offline', 'online'] } };
  } else if (item.name === 'Tasks') {
    sheet.getRange('D2:D501').setNumberFormat('yyyy-mm-dd hh:mm');
    sheet.getRange('D:D').format.columnWidth = 27;
    sheet.getRange('E2:E501').setNumberFormat('0.00');
    sheet.getRange('C2:C501').dataValidation = { rule: { type: 'list', values: ['assignment', 'quiz', 'midterm', 'final_exam'] } };
  } else sheet.getRange('C2:C501').setNumberFormat('0.00');
}
workbook.recalculate();
console.log((await workbook.inspect({ kind: 'region', sheetId: 'Lessons', range: 'A1:I3', maxChars: 2500 })).ndjson);
for (const item of definitions) {
  const preview = await workbook.render({ sheetName: item.name, range: `A1:${String.fromCharCode(64 + item.headers.length)}5`, scale: 1.5, format: 'png' });
  await fs.writeFile(path.join(outputDir, `${item.name}.png`), new Uint8Array(await preview.arrayBuffer()));
}
const artifact = await SpreadsheetFile.exportXlsx(workbook);
await artifact.save(path.join(outputDir, 'pacewise-schedule-template.xlsx'));
await fs.mkdir('frontend/pacewise/public/templates', { recursive: true });
await fs.copyFile(path.join(outputDir, 'pacewise-schedule-template.xlsx'), 'frontend/pacewise/public/templates/pacewise-schedule-template.xlsx');
console.log('Created and rendered four-sheet import template.');
