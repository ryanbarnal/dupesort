// Thin outline icons on a 24-unit grid with a 1.5 stroke, the same set as the desktop app.

const P = {
  music: '<circle cx="6" cy="17.5" r="2.5"/><circle cx="18" cy="15.5" r="2.5"/><path d="M8.5 17.5v-12l12-2v12M8.5 9.5l12-2"/>',
  photos: '<rect x="3" y="4" width="18" height="16" rx="2.5"/><circle cx="8.75" cy="9.25" r="1.75"/><path d="m21 15-5-5L5 20"/>',
  videos: '<rect x="2.5" y="6" width="13.5" height="12" rx="2.5"/><path d="m16 10.5 5.5-3v9l-5.5-3"/>',
  documents: '<path d="M14 2.5H6A1.5 1.5 0 0 0 4.5 4v16A1.5 1.5 0 0 0 6 21.5h12a1.5 1.5 0 0 0 1.5-1.5V8L14 2.5z"/><path d="M14 2.5V8h5.5M8.5 13h7M8.5 17H13"/>',
  all: '<rect x="3.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="3.5" width="7" height="7" rx="1.5"/><rect x="3.5" y="13.5" width="7" height="7" rx="1.5"/><rect x="13.5" y="13.5" width="7" height="7" rx="1.5"/>',
  scan: '<circle cx="10.5" cy="10.5" r="6.5"/><path d="m15.5 15.5 5 5"/>',
  'folder-plus': '<path d="M3 7v12a1.5 1.5 0 0 0 1.5 1.5h15A1.5 1.5 0 0 0 21 19V9.5A1.5 1.5 0 0 0 19.5 8h-8l-2-2.5h-5A1.5 1.5 0 0 0 3 7z"/><path d="M12 11v6.5M8.75 14.25h6.5"/>',
  move: '<path d="M3 7v12a1.5 1.5 0 0 0 1.5 1.5h15A1.5 1.5 0 0 0 21 19V9.5A1.5 1.5 0 0 0 19.5 8h-8l-2-2.5h-5A1.5 1.5 0 0 0 3 7z"/><path d="M8 14.25h8m-3-3 3 3-3 3"/>',
  close: '<path d="M6 6l12 12M18 6 6 18"/>',
  check: '<path d="m4.5 12.5 5 5 10-11"/>',
  undo: '<path d="M4 9.5h11a5 5 0 0 1 0 10H9"/><path d="m8 5.5-4 4 4 4"/>',
  download: '<path d="M12 3.5v12m-5-5 5 5 5-5M4.5 20.5h15"/>',
  report: '<path d="M14 2.5H6A1.5 1.5 0 0 0 4.5 4v16A1.5 1.5 0 0 0 6 21.5h12a1.5 1.5 0 0 0 1.5-1.5V8L14 2.5z"/><path d="M14 2.5V8h5.5M12 11.5V18m-3-3 3 3 3-3"/>',
  lock: '<rect x="4.5" y="10.5" width="15" height="10" rx="2"/><path d="M8 10.5V7.5a4 4 0 0 1 8 0v3"/>',
  sparkle: '<path d="M11 3q0 7-7 7.5 7 .5 7 7.5 0-7 7-7.5-7-.5-7-7.5zM18.5 15v6M15.5 18h6"/>',
  info: '<circle cx="12" cy="12" r="9"/><path d="M12 11v5.5M12 7.75v.01"/>',
  sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2.5v2M12 19.5v2M4.6 4.6l1.4 1.4M18 18l1.4 1.4M2.5 12h2M19.5 12h2M4.6 19.4 6 18M18 6l1.4-1.4"/>',
  moon: '<path d="M20 14.5A8 8 0 0 1 9.5 4a8 8 0 1 0 10.5 10.5z"/>',
  auto: '<circle cx="12" cy="12" r="8.5"/><path d="M12 3.5v17a8.5 8.5 0 0 0 0-17z" fill="currentColor" stroke="none"/>',
  windows: '<rect x="3.5" y="3.5" width="7.5" height="7.5" rx="1"/><rect x="13" y="3.5" width="7.5" height="7.5" rx="1"/><rect x="3.5" y="13" width="7.5" height="7.5" rx="1"/><rect x="13" y="13" width="7.5" height="7.5" rx="1"/>',
  apple: '<path d="M15.5 3.5c-1.4.1-3 1-3.4 2.7 1.6.1 3-.9 3.4-2.7zM12 7.5c-1-.6-2.2-.9-3.2-.6C6.5 7.5 5 9.8 5.3 13c.4 4 3 7.6 4.9 7.5 1-.1 1.3-.6 1.8-.6s.8.5 1.8.6c1.9.1 3.9-3 4.7-5.4-2-.9-2.8-3.7-.6-5.6-.8-1.3-2.3-2-3.7-1.9-.9 0-1.6.4-2.2.5z"/>',
  linux: '<path d="M9.5 20.5c-2 0-4-1-4-2.5 0-1 1-1.5 1.5-3s.5-3 .5-5a4.5 4.5 0 0 1 9 0c0 2 0 3.5.5 5s1.5 2 1.5 3c0 1.5-2 2.5-4 2.5"/><circle cx="10.5" cy="9" r=".6"/><circle cx="13.5" cy="9" r=".6"/><path d="M11 11.5h2l-1 1.2z"/>',
  web: '<circle cx="12" cy="12" r="9"/><ellipse cx="12" cy="12" rx="4" ry="9"/><path d="M3 12h18"/>',
  external: '<path d="M11 4.5H6A1.5 1.5 0 0 0 4.5 6v12A1.5 1.5 0 0 0 6 19.5h12a1.5 1.5 0 0 0 1.5-1.5v-5M11 13l8.5-8.5M14 4.5h5.5V10"/>',
};

export function icon(name, cls = 'i') {
  return `<svg class="${cls}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${P[name] || ''}</svg>`;
}

/** Replace every <i data-icon="name"></i> placeholder with its SVG. */
export function hydrateIcons(root = document) {
  root.querySelectorAll('i[data-icon]').forEach((el) => {
    el.outerHTML = icon(el.dataset.icon, el.className ? `i ${el.className}` : 'i');
  });
}

// Light / dark / match-system, remembered on this device.
const MODES = ['auto', 'light', 'dark'];
export function setupTheme(button) {
  let mode = 'auto';
  try {
    mode = localStorage.getItem('dupesort-theme') || 'auto';
  } catch {}
  const apply = () => {
    if (mode === 'auto') document.documentElement.removeAttribute('data-theme');
    else document.documentElement.dataset.theme = mode;
    button.innerHTML = icon(mode === 'auto' ? 'auto' : mode === 'dark' ? 'moon' : 'sun');
    const label = { auto: 'Appearance: match system', light: 'Appearance: light', dark: 'Appearance: dark' }[mode];
    button.title = label;
    button.setAttribute('aria-label', label);
  };
  button.addEventListener('click', () => {
    mode = MODES[(MODES.indexOf(mode) + 1) % MODES.length];
    try {
      localStorage.setItem('dupesort-theme', mode);
    } catch {}
    apply();
  });
  apply();
}
