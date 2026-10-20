# Vigilance-PK Design System Specifications
**Project ID**: 17382771392857080164
**Theme**: Vigilance Terminal (Futuristic Command Center)

> **Status: aspirational, not implemented.** The shipped dashboard in
> `lite-web/index.html` uses a different palette (background `#0A0E1A`, not
> `#19120a`), a fixed two-panel layout rather than a 12-column fluid grid, and
> no 1440px container. Treat this document as the target design, not a
> description of the current UI. Reconcile the two before relying on it.

## 🎨 Color Palette
The aesthetic is built on a "Deep Space" foundation to minimize eye strain.

| Token | Value | Role |
| :--- | :--- | :--- |
| **Primary (Amber)** | `#f59e0b` | Active interaction, warnings, primary CTAs |
| **Secondary (Cyan)** | `#06b6d4` | Data visualization, telemetry, normal status |
| **Danger (Red)** | `#ffb4ab` | Critical failures, high-threat alerts |
| **Background** | `#19120a` | The digital "floor" |
| **Surface** | `#19120a` | Primary containers and cards |
| **Outline** | `#a08e7a` | Technical linework and borders |

## Typography
Dual-font approach balancing technical precision with readability.

| Typeface | Usage |
| :--- | :--- |
| **JetBrains Mono** | Headlines, data points, labels, and technical data |
| **Inter** | Body copy and long-form descriptions |

### Type Scales
- **Headline LG**: 32px / Bold / Monospace
- **Headline MD**: 24px / Semi-Bold / Monospace
- **Body LG**: 16px / Regular / Inter
- **Label MD**: 12px / Medium / Monospace (0.05em spacing)

## 📐 Spacing & Layout
- **Baseline Unit**: 4px
- **Margins**: 24px (Desktop)
- **Gutters**: 16px
- **Grid**: 12-column fluid grid
- **Max Container**: 1440px

## 💠 Component Specifications

### Buttons
- **Primary**: Amber background, Black text. Subtle amber outer glow (8px) on hover.
- **Secondary**: Transparent, 1px Cyan border, Cyan text.
- **Ghost**: No background, Muted Gray text, White on hover.

### Cards & Modules
- **Border**: 1px solid (`#a08e7a`).
- **Radius**: Soft (0.25rem / 4px).
- **Critical Status**: 2px thick top border in Amber or Red.

### Data Chips
- Small rectangular tags (`label-sm`). 
- 10% opacity background of the status color with 100% opacity text.

---
*Generated via Stitch MCP from the Vigilance-PK Pro Dashboard project.*
