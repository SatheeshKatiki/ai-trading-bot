(function() {
  try {
    var theme = localStorage.getItem('theme');
    if (theme === 'light') {
      document.documentElement.classList.add('light');
    } else {
      document.documentElement.classList.remove('light');
    }

    var accent = localStorage.getItem('accentColor');
    if (accent) {
      document.documentElement.style.setProperty('--primary', accent);
    }

    var density = localStorage.getItem('density');
    if (density === 'spacious') {
      document.documentElement.classList.add('spacious-mode');
    }

    var glass = localStorage.getItem('glassEnabled');
    if (glass === 'false') {
      document.documentElement.classList.add('no-glass');
    }
  } catch (e) {}
})();
