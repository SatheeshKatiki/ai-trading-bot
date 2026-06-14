const fs = require('fs');
const path = require('path');

const tabsDir = path.join(__dirname, 'app', 'strategy', 'tabs');

if (fs.existsSync(tabsDir)) {
  const tabs = fs.readdirSync(tabsDir).filter(f => f.endsWith('.tsx'));
  for (const tab of tabs) {
    const file = path.join(tabsDir, tab);
    let code = fs.readFileSync(file, 'utf8');

    code = code.replace(/bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl border border-[^\s]+ space-y-5 h-\[([^\]]+)\] flex flex-col justify-between shadow-xl hover:shadow-[^\s]+ hover:border-[^\s]+ transition-all duration-300/g, 
      'glass-card p-6 rounded-2xl space-y-5 h-[$1] flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300');

    code = code.replace(/bg-gradient-to-br from-slate-800 to-slate-900 p-6 rounded-2xl border border-[^\s]+ space-y-5 flex flex-col justify-between shadow-xl hover:shadow-[^\s]+ hover:border-[^\s]+ transition-all duration-300/g, 
      'glass-card p-6 rounded-2xl space-y-5 flex flex-col justify-between hover:-translate-y-1 hover:shadow-xl hover:shadow-primary/10 transition-all duration-300');

    fs.writeFileSync(file, code);
  }
}
console.log('Robust design upgraded successfully');
