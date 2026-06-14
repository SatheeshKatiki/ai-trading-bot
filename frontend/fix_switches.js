const fs = require('fs');
const path = require('path');

function processFile(filename) {
  let code = fs.readFileSync(filename, 'utf8');
  
  // Replace:
  // <button
  //   onClick={() => updateSetting("strict_entry_mode", !settings.strict_entry_mode)}
  //   className={`w-12 h-6 rounded-full p-0.5 transition-colors shadow-lg ${settings.strict_entry_mode ? 'bg-[#4f46e5] shadow-indigo-500/30' : 'bg-muted border border-border'}`}
  // >
  //   <div className={`w-5 h-5 rounded-full bg-white transition-transform ${settings.strict_entry_mode ? 'translate-x-6' : 'translate-x-0'}`}></div>
  // </button>
  
  // Regex to match the button and extract the key (like "strict_entry_mode")
  const regex = /<button[\s\S]*?onClick=\{\(\)\s*=>\s*updateSetting\("([^"]+)",\s*!settings\.[^"}]+\)\}[\s\S]*?<\/button>/g;
  
  code = code.replace(regex, `<CustomSwitch
            checked={settings.$1 || false}
            onChange={(checked) => updateSetting("$1", checked)}
          />`);

  fs.writeFileSync(filename, code);
}

processFile(path.join(__dirname, 'app', 'strategy', 'tabs', 'strategy-tab.tsx'));
processFile(path.join(__dirname, 'app', 'strategy', 'tabs', 'notifications-tab.tsx'));

console.log('Fixed inline switches');
