---
name: tailwind-design-system
description: Build scalable design systems with Tailwind CSS, design tokens, component libraries, and responsive patterns. Use when creating component libraries, implementing design systems, or standardizing UI patterns.
---

# Tailwind Design System

Build production-ready design systems with **Tailwind CSS v3 via CDN** (`cdn.tailwindcss.com` with inline `tailwind.config`, `darkMode: 'class'`) and **Vanilla JS** in `docs/index.html` (zero-build: no bundler, npm, React, TypeScript, CVA, or Tailwind v4 `@theme`).

## Use this skill when

- Extending design tokens and `fantasy.*` / semantic colors in `docs/index.html`
- Standardizing Vanilla JS UI components and class-lookup variants
- Building responsive and accessible HTML5 patterns (`<dialog>`, cards, forms)
- Maintaining dark (`html.dark`) and ivory theme parity
- Auditing or refactoring Tailwind v3 utility patterns across `docs/index.html`

## Do not use this skill when

- The task is unrelated to Tailwind styling or UI structure
- You are editing Python generators (`dnd_summarizer.py`) or raw Markdown content unless syncing DOM hooks

## Instructions

- Clarify goals, constraints, and required inputs.
- Target `docs/index.html` directly using inline `tailwind.config` (`darkMode: 'class'`), CSS custom properties, and Vanilla JS DOM helpers.
- Preserve all `dnd-web-sync-check` contracts (`CHARACTERS_INFO`, `.char-pill`, `setCharFilter`, `renderEnhancedMarkdown`, `buildTableOfContents`, `#character-diary-view`, `#toc-sidebar`).
- Validate both dark and ivory themes plus keyboard/reduced-motion accessibility.
- Open `resources/implementation-playbook.md` for copy-ready Vanilla JS + Tailwind v3 CDN patterns.

## Resources

- `resources/implementation-playbook.md` for detailed patterns and examples.
