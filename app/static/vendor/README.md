# Vendored Dependencies

Local copies of third-party libraries. No external CDN requests at runtime.

| Library | Version | Source |
|---------|---------|--------|
| HTMX | 2.0.4 | https://unpkg.com/htmx.org@2.0.4/dist/htmx.min.js |
| Tailwind CSS | 2.2.19 | https://cdn.jsdelivr.net/npm/tailwindcss@2.2.19/dist/tailwind.min.css |

Note: Tailwind v3+ does not ship a pre-built CSS file. The v2.2.19 build contains
all utility classes used by this app. If new Tailwind classes are needed, verify
they exist in this version first.

## Tailwind CSS

The config file [tailwind.config.js](../../../tailwind.config.js) can be used to extend or override Tailwind default styling. It still needs to be manually minified.