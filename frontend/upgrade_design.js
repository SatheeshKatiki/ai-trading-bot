/* eslint-disable @typescript-eslint/no-require-imports */
const fs = require('fs');
const path = require('path');

const tabsDir = path.join(__dirname, 'app', 'strategy', 'tabs');
const pageFile = path.join(__dirname, 'app', 'strategy', 'page.tsx');

const filesToUpdate = [pageFile];

if (fs.existsSync(tabsDir)) {
  const tabs = fs.readdirSync(tabsDir).filter(f => f.endsWith('.tsx'));
  for (const tab of tabs) {
    filesToUpdate.push(path.join(tabsDir, tab));
  }
}

for (const file of filesToUpdate) {
  if (!fs.existsSync(file)) continue;
  let code = fs.readFileSync(file, 'utf8');

  // Hard match the exact string since regexes can be tricky with formatting
  // Card 1 pattern:
  code = code.replace(/bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl border border-[^\s]+ space-y-5 h-\[([^\]]+)\] flex flex-col justify-between shadow-xl hover:shadow-[^\s]+ transition-all duration-300/g, 
    'glass-card p-6 rounded-2xl space-y-5 h-[$1] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300');

  // Card 2 pattern:
  code = code.replace(/bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl border border-[^\s]+ space-y-5 flex flex-col justify-between shadow-xl hover:shadow-[^\s]+ transition-all duration-300/g, 
    'glass-card p-6 rounded-2xl space-y-5 flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300');

  // Text colors
  code = code.replace(/text-gray-400/g, 'text-muted-foreground');
  code = code.replace(/text-gray-500/g, 'text-muted-foreground');

  fs.writeFileSync(file, code);
}
console.log('Design upgraded successfully');
