const fs = require('fs');
const path = require('path');
function walk(dir) {
  let results = [];
  const list = fs.readdirSync(dir);
  list.forEach(file => {
    file = path.join(dir, file);
    const stat = fs.statSync(file);
    if (stat && stat.isDirectory()) {
      results = results.concat(walk(file));
    } else if(file.endsWith('.tsx')) {
      results.push(file);
    }
  });
  return results;
}
const files = walk('d:/Projects/AI trading Bot/frontend/app');
files.forEach(f => {
  let c = fs.readFileSync(f, 'utf8');
  let original = c;

  // Generic patterns mapped to unified button style
  c = c.replace(/className=\"flex-1 py-3 bg-muted\/50 rounded-xl text-sm font-bold hover:bg-muted transition-all\"/g, 'className=\"flex-1 py-3 bg-muted/50 text-foreground hover:bg-muted rounded-xl text-sm font-bold transition-all\"');

  // Let's replace button variants like 'text-red-500' to primary if needed, but the user specifically mentioned "button color should be updated".
  // Specifically let's target buttons in Journal
  c = c.replace(/className=\"w-full py-2 text-xs font-bold text-muted-foreground hover:text-foreground transition-all\"/g, 'className=\"w-full py-2 text-xs font-bold text-primary hover:opacity-80 transition-all\"');
  
  c = c.replace(/className=\"px-4 py-2 bg-muted\/50 rounded-lg text-sm border border-border\/50 flex items-center gap-2\"/g, 'className=\"px-4 py-2 bg-primary text-white hover:bg-primary/90 rounded-lg text-sm transition-colors flex items-center gap-2\"');
  
  c = c.replace(/className=\"flex-1 py-3 bg-primary text-white rounded-xl text-sm font-bold shadow-lg hover:bg-primary\/90 transition-all\"/g, 'className=\"flex-1 py-3 bg-primary text-white rounded-xl text-sm font-bold shadow-lg hover:bg-primary/90 transition-all\"');
  
  // Strategy page Add rule buttons
  c = c.replace(/className=\"w-full py-2\.5 bg-background hover:bg-muted border border-border rounded-lg text-xs font-bold text-red-500 transition-colors\"/g, 'className=\"w-full py-2.5 bg-primary/10 hover:bg-primary/20 border border-primary/20 rounded-lg text-xs font-bold text-primary transition-colors\"');
  
  c = c.replace(/className=\"w-full py-2\.5 bg-background hover:bg-muted border border-border rounded-lg text-xs font-bold text-foreground transition-colors\"/g, 'className=\"w-full py-2.5 bg-primary/10 hover:bg-primary/20 border border-primary/20 rounded-lg text-xs font-bold text-primary transition-colors\"');

  c = c.replace(/className=\"w-full py-2\.5 bg-background hover:bg-muted border border-border rounded-lg text-xs font-bold text-success transition-colors\"/g, 'className=\"w-full py-2.5 bg-primary/10 hover:bg-primary/20 border border-primary/20 rounded-lg text-xs font-bold text-primary transition-colors\"');

  c = c.replace(/className=\"px-4 py-2 bg-muted\/50 hover:bg-muted rounded-lg text-xs font-bold transition-all\"/g, 'className=\"px-4 py-2 bg-primary text-white hover:bg-primary/90 rounded-lg text-xs font-bold transition-all\"');

  // Broker page buttons
  c = c.replace(/className=\"w-full py-2 bg-primary\/10 hover:bg-primary\/20 text-primary text-sm font-bold rounded-lg transition-colors border border-primary\/20\"/g, 'className=\"w-full py-2 bg-primary text-white hover:bg-primary/90 text-sm font-bold rounded-lg transition-colors\"');

  // Backtest Export/Cancel
  c = c.replace(/className=\"px-6 py-2 bg-muted hover:bg-muted\/80 rounded-lg text-sm font-medium transition-colors border border-border\"/g, 'className=\"px-6 py-2 bg-muted/50 hover:bg-muted rounded-lg text-sm font-medium transition-colors border border-border text-foreground\"');

  if (c !== original) {
    fs.writeFileSync(f, c);
    console.log('Updated ' + f);
  }
});
console.log('Done');
