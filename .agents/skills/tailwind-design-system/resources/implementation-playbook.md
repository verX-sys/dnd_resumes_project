# Tailwind v3 CDN + Vanilla JS Implementation Playbook

Zero-build patterns for single-file HTML5 + Vanilla JS + Tailwind CSS v3 CDN (`cdn.tailwindcss.com`) apps such as `docs/index.html`. No bundler, npm, React, TypeScript, CVA, or Tailwind v4 `@theme` required.

---

## 1. Design Token Hierarchy (CSS Variables + Inline `tailwind.config`)

Define raw palette tokens and semantic surface variables in `<style>`, then expose them through the inline `tailwind.config` script with `darkMode: 'class'`.

```html
<script src="https://cdn.tailwindcss.com"></script>
<script>
  tailwind.config = {
    darkMode: 'class',
    theme: {
      extend: {
        colors: {
          fantasy: {
            gold: '#d4af37',
            dark: '#0f1117',
            card: '#181b26',
            border: '#282d3f',
            ivoryBg: '#f7f4ed',
            ivoryCard: '#ffffff',
            ivoryBorder: '#e6dfd1',
            ivoryText: '#1f1b16',
          },
          surface: 'var(--surface)',
          ink: 'var(--ink)',
        },
        borderRadius: {
          card: 'var(--radius-card)',
        },
      },
    },
  };
</script>

<style>
  :root {
    --surface: #f7f4ed;
    --ink: #1f1b16;
    --accent: #d4af37;
    --radius-card: 0.75rem;
  }
  html.dark {
    --surface: #0f1117;
    --ink: #e5e7eb;
  }
</style>
```

---

## 2. Plain-JS Variant Helper (`VARIANT_CLASSES` + `cn`)

Replace external variant libraries with a flat lookup table and a lightweight `cn(...)` string joiner.

```javascript
function cn(...parts) {
  return parts.flat().filter(Boolean).join(' ');
}

const BUTTON_BASE =
  'inline-flex items-center justify-center gap-2 rounded-lg text-sm font-medium transition-colors ' +
  'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fantasy-gold disabled:opacity-50 disabled:pointer-events-none';

const VARIANT_CLASSES = {
  primary: 'bg-fantasy-gold text-fantasy-dark hover:brightness-110',
  surface:
    'border border-fantasy-ivoryBorder bg-fantasy-ivoryCard text-fantasy-ivoryText ' +
    'dark:border-fantasy-border dark:bg-fantasy-card dark:text-slate-100 hover:border-fantasy-gold',
  ghost: 'text-slate-600 hover:bg-black/5 dark:text-slate-300 dark:hover:bg-white/5',
};

const SIZE_CLASSES = {
  sm: 'h-8 px-3 text-xs',
  md: 'h-10 px-4',
  icon: 'h-9 w-9',
};

function buttonClasses({ variant = 'surface', size = 'md', extra = '' } = {}) {
  return cn(BUTTON_BASE, VARIANT_CLASSES[variant], SIZE_CLASSES[size], extra);
}
```

---

## 3. Semantic HTML Card, Form & Native `<dialog>` Patterns

Prefer native HTML5 elements (`<article>`, `<label>`, `<dialog>`) over generic `<div>` stacks or third-party modal wrappers.

```html
<!-- Card -->
<article class="rounded-card border border-fantasy-ivoryBorder bg-fantasy-ivoryCard p-5 text-fantasy-ivoryText shadow-sm dark:border-fantasy-border dark:bg-fantasy-card dark:text-slate-100">
  <header class="mb-2 flex items-baseline justify-between gap-3">
    <h3 class="text-base font-semibold tracking-tight">Sessione 42</h3>
    <time datetime="2026-03-14" class="text-xs text-slate-500 dark:text-slate-400">2026-03-14</time>
  </header>
  <p class="text-sm leading-relaxed text-slate-600 dark:text-slate-300">Riassunto della puntata.</p>
</article>

<!-- Accessible Form Field -->
<form id="filter-form" class="space-y-3" novalidate>
  <div>
    <label for="search-input" class="mb-1 block text-xs font-semibold uppercase tracking-wide">
      Cerca nelle cronache
    </label>
    <input
      id="search-input"
      type="search"
      aria-describedby="search-error"
      class="w-full rounded-lg border border-fantasy-ivoryBorder bg-fantasy-ivoryCard px-3 py-2 text-sm text-fantasy-ivoryText focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-fantasy-gold dark:border-fantasy-border dark:bg-fantasy-dark dark:text-slate-100"
    />
    <p id="search-error" role="alert" class="mt-1 hidden text-xs text-red-500"></p>
  </div>
</form>

<!-- Native Modal Dialog -->
<dialog id="detail-dialog" class="m-auto w-full max-w-lg rounded-card border border-fantasy-ivoryBorder bg-fantasy-ivoryCard p-6 text-fantasy-ivoryText backdrop:bg-black/70 dark:border-fantasy-border dark:bg-fantasy-card dark:text-slate-100">
  <div class="flex items-start justify-between gap-4">
    <h2 id="dialog-title" class="text-lg font-semibold">Dettagli</h2>
    <button type="button" data-dialog-close aria-label="Chiudi" class="rounded p-1 hover:bg-black/5 dark:hover:bg-white/10">✕</button>
  </div>
  <div id="dialog-body" class="mt-4 text-sm"></div>
</dialog>
```

```javascript
const dialog = document.getElementById('detail-dialog');
dialog?.querySelector('[data-dialog-close]')?.addEventListener('click', () => dialog.close());
dialog?.addEventListener('click', (e) => {
  if (e.target === dialog) dialog.close(); // backdrop click
});
// Open with: dialog.showModal();
```

---

## 4. Responsive Grid & Container Utilities

Use standard Tailwind v3 breakpoint prefixes (`sm:`, `md:`, `lg:`, `xl:`) and map presets via plain objects when generating cards dynamically.

```javascript
const GRID_COLS = {
  2: 'grid grid-cols-1 sm:grid-cols-2 gap-4',
  3: 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-3 gap-4',
  4: 'grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-5',
};

const CONTAINER_CLASSES = 'mx-auto w-full max-w-screen-xl px-4 sm:px-6 lg:px-8';
```

---

## 5. CSS-First Animation Utilities (`prefers-reduced-motion`)

Keep motion lightweight in `<style>` using CSS transitions and `@keyframes`, and always respect `prefers-reduced-motion`.

```css
@keyframes fadeSlideUp {
  from {
    opacity: 0;
    transform: translateY(6px);
  }
  to {
    opacity: 1;
    transform: translateY(0);
  }
}

.animate-reveal {
  animation: fadeSlideUp 220ms cubic-bezier(0.16, 1, 0.3, 1) both;
}

@media (prefers-reduced-motion: reduce) {
  .animate-reveal,
  .transition-colors,
  .transition-all {
    animation-duration: 0.01ms !important;
    transition-duration: 0.01ms !important;
  }
}
```

---

## 6. `html.dark` / Ivory Class-Based Theme Toggle

Match `darkMode: 'class'` on `<html>` (`html.dark` for dark obsidian, default `:root` for ivory parchment) with `localStorage` persistence and `matchMedia` fallback.

```javascript
const THEME_KEY = 'dnd-theme';

function resolveTheme() {
  const saved = localStorage.getItem(THEME_KEY);
  if (saved === 'dark' || saved === 'ivory') return saved;
  return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'ivory';
}

function applyTheme(theme) {
  const root = document.documentElement;
  root.classList.toggle('dark', theme === 'dark');
  root.dataset.theme = theme;
  localStorage.setItem(THEME_KEY, theme);
  const btn = document.getElementById('theme-toggle');
  if (btn) btn.setAttribute('aria-pressed', String(theme === 'dark'));
}

applyTheme(resolveTheme());

document.getElementById('theme-toggle')?.addEventListener('click', () => {
  const isDark = document.documentElement.classList.contains('dark');
  applyTheme(isDark ? 'ivory' : 'dark');
});
```

---

## Checklist

- Extend `tailwind.config` in `docs/index.html` instead of scattering arbitrary hex values.
- Use `cn(...)` + lookup maps (`VARIANT_CLASSES`) for repeatable Vanilla JS UI states.
- Test every new UI block in both `html.dark` and ivory mode, with keyboard navigation and `prefers-reduced-motion`.
- After editing `docs/index.html`, run the `dnd-web-sync-check` verifications.
