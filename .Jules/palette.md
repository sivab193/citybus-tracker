## 2024-05-18 - Dynamically loaded data and ARIA
**Learning:** Added `aria-live="polite"` to dynamically updating DOM elements in vanilla JS apps ensures screen readers notify users when new data arrives asynchronously.
**Action:** Always add `aria-live` regions when setting `.innerHTML` or `.textContent` asynchronously in dashboards.
