# Vigilance-PK Dashboard Design

Describes the dashboard as built in `lite-web/index.html` (ADR-026).
The earlier "Vigilance Terminal" spec (amber/cyan command-centre look) was
never built and has been retired.

## Principles
- **A tool for analysts, not a film prop.** Plain labels ("Sync now", "Latest reports"), sentence case, no fake terminal jargon.
- **Readable.** 14px body text, nothing under 12px.
- **No third-party requests.** No CDN scripts, icon fonts or web fonts. Icons are inline SVG.
- **Severity owns the warm colours.** Red/orange/yellow mean severity only. The interactive accent is blue so the two never get confused.
- **Never colour alone.** Severity is always written as a label too.

## Colour tokens
Defined on `:root`. Dark is the default; light follows `prefers-color-scheme`.

| Token | Dark | Light | Use |
|---|---|---|---|
| `--bg` | `#0f1216` | `#f5f6f8` | Page background |
| `--surface` | `#161a20` | `#ffffff` | Cards, bars, dialogs |
| `--surface-2` | `#1d232b` | `#f0f2f5` | Hover, user messages, notices |
| `--border` | `#2a313b` | `#dce0e5` | All borders |
| `--text` / `--text-2` / `--text-3` | `#e7e9ec` / `#aab2bd` / `#808a97` | `#15181c` / `#48505c` / `#687280` | Primary / secondary / meta text |
| `--accent` | `#6ea8fe` | `#1d4ed8` | Primary buttons, focus ring |
| `--critical` | `#f87171` | `#b91c1c` | Severity: critical |
| `--high` | `#fb923c` | `#c2410c` | Severity: high |
| `--medium` | `#facc15` | `#a16207` | Severity: medium |
| `--low` | `#8b95a3` | `#5f6875` | Severity: low |

## Type
- UI: the system font stack (`system-ui`, Segoe UI, Roboto, Noto Sans).
- Urdu: Noto Nastaliq Urdu / Jameel Noori Nastaleeq if installed, otherwise Segoe UI. Line height 1.9 for Nastaliq.
- Sizes: 16px headings in dialogs, 14px body and card titles, 13px secondary, 12px meta.

## Layout
- Top bar: name, connection state, Status, Sync now.
- Two panels: report feed (320–440px) and chat. Below 860px they stack and the page scrolls.
- Radius 8px everywhere; 1px borders; no shadows, blur or glow.

## Components
- **Report card:** severity pill + source + date; linked title; two-line summary; categories and tags; "Why this rating" disclosure. Left border in the severity colour.
- **Notice:** inline message above the feed for sync progress, results and errors. Dismissible.
- **Dialogs:** native `<dialog>` for status and the admin key (Esc closes, focus is managed by the browser).
- **Answer:** escaped text with minimal Markdown (paragraphs, bullets, bold), followed by the list of reports searched.
