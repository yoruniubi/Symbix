# Symbix — DESIGN.md

> Companion AI agent desktop client. Warm sunset gradient identity, interlocking heart/infinity mark, sparkle accent. Built to feel personal for everyday users while staying dense and precise enough for developers.

## 1. Brand Essence

- **Keywords**: companion, warmth, intelligence, connection, competence (not childish, not corporate).
- **Logo language**: two interlocking ribbons forming a heart/infinity, even stroke width, generous negative space, a four-point sparkle at the optical center. Gradient runs amber → coral → rose, always at a consistent diagonal (top-left warm, bottom-right cool-warm).
- **Rule of thumb**: the gradient is a *signature*, not a background. Reserve it for the mark, key accents, and moments of AI activity (thinking/generating). Everyday UI stays neutral so the gradient still means something when it appears.

## 2. Color System

### 2.1 Brand Gradient (use sparingly)
```
--symbix-gradient: linear-gradient(135deg, #F7A85B 0%, #F2657A 55%, #E85C93 100%);
--symbix-gradient-soft: linear-gradient(135deg, #F7A85B 0%, #E85C93 100%); /* 2-stop, for small elements */
```
Use for: logo, primary CTA (optional, use only one gradient button per screen), active "agent is thinking" state, onboarding hero moments. Never use as a full-page background or on dense data views — it fights with content.

### 2.2 Primary Accent (solid, for everyday UI)
```
--accent-50:  #FFF3E9
--accent-100: #FFE1CC
--accent-300: #F7A85B   /* amber, warm highlights */
--accent-500: #EF6B6E   /* coral, primary buttons/links */
--accent-600: #E2515F   /* coral hover/active */
--accent-700: #C43F5C   /* text-on-light, high-contrast accent text */
```
`accent-500` is your single workhorse accent color for buttons, active states, focus rings, selected items. Pick one, not the whole gradient, for anything interactive and repeated.

### 2.3 Neutrals — Warm Gray (not cool gray)
Slightly warm-tinted neutrals keep the "companion" feeling even in dense/dark UI.
```
--gray-25:  #FBFAF9
--gray-50:  #F6F4F2
--gray-100: #EDEAE7
--gray-200: #DCD7D2
--gray-300: #BFB8B2
--gray-400: #968D86
--gray-500: #6F675F   /* secondary text */
--gray-600: #524B45
--gray-700: #3A342F   /* body text, light mode */
--gray-800: #262220
--gray-900: #1A1715   /* app background, dark mode */
--gray-950: #121010   /* deepest surface, dark mode */
```

### 2.4 Semantic (status colors — separate from brand accent)
```
--success: #4E9A6E   /* muted sage green, not neon */
--warning: #D89B3C
--error:   #D3555A
--info:    #5B8AC4
```
Keep these desaturated relative to the brand accent — they need to read as *state*, not compete with the brand gradient for attention. Use only on small surfaces: dots, badges, thin borders, toast icons.

### 2.5 Dark Mode (default)
```
--bg-app:      var(--gray-900)
--bg-surface:  #211D1B     /* cards, panels */
--bg-elevated: #2B2523     /* modals, popovers */
--border:      #362F2C
--text-primary:   #F2EEEB
--text-secondary: #A79E97
```
### 2.6 Light Mode
```
--bg-app:      var(--gray-25)
--bg-surface:  #FFFFFF
--bg-elevated: #FFFFFF
--border:      var(--gray-200)
--text-primary:   var(--gray-800)
--text-secondary: var(--gray-500)
```

## 3. Typography

- **UI / body**: a humanist grotesque, not a geometric one — e.g. Inter, or Sans-serif with slightly rounded terminals. Avoid hyper-geometric fonts (Futura-like) — they read cold, which fights the companion feel.
- **Monospace** (code blocks, tool calls, logs, file paths): JetBrains Mono or similar — must be visually distinct from UI font so users instantly know "this is a system/tool output," not agent speech.

```
--font-sans: "Inter", -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif;
--font-mono: "JetBrains Mono", "Fira Code", monospace;

--text-xs:   12px / 16px
--text-sm:   13px / 18px   /* default UI density */
--text-base: 14px / 20px   /* chat body */
--text-md:   16px / 24px   /* section headers */
--text-lg:   20px / 28px
--text-xl:   24px / 32px   /* onboarding / empty states only */

--weight-regular: 400
--weight-medium:  500   /* default for emphasis, avoid heavy bold in chat */
--weight-semibold: 600  /* headers, button labels only */
```
Keep the type scale compact — this is a high-density tool used for long sessions. Reserve `text-xl`/`text-lg` for onboarding and empty states, not everyday chrome.

## 4. Spacing & Grid

8px base unit.
```
--space-1: 4px    --space-2: 8px    --space-3: 12px
--space-4: 16px   --space-5: 20px   --space-6: 24px
--space-8: 32px   --space-10: 40px  --space-12: 48px
```
Chat/tool panels use `space-3`–`space-4` internal padding; page-level containers use `space-6`–`space-8`. Don't go below `space-2` for anything tappable/clickable.

## 5. Radius

```
--radius-sm: 6px    /* inputs, small buttons, chips */
--radius-md: 8px    /* cards, message bubbles */
--radius-lg: 12px   /* modals, large panels */
--radius-full: 999px /* avatars, status dots, pills */
```
Deliberately restrained — round enough to feel warm, not so round it looks like a consumer toy. Never exceed `radius-lg` on containers holding text or code.

## 6. Elevation

Prefer **borders + subtle shadow** over heavy drop shadows — keeps dark mode from looking muddy.
```
--shadow-sm: 0 1px 2px rgba(0,0,0,0.12)
--shadow-md: 0 4px 12px rgba(0,0,0,0.18)
--shadow-glow: 0 0 24px rgba(242,101,122,0.25)  /* reserved for active-agent states only */
```

## 7. Motion

```
--ease-standard: cubic-bezier(0.4, 0, 0.2, 1)
--duration-fast: 120ms     /* hover, toggle */
--duration-base: 180ms     /* panel open/close */
--duration-slow: 320ms     /* page/route transitions */
```
- Discrete UI actions (buttons, toggles, tabs): snappy, ≤180ms, no bounce.
- "Agent is thinking/working" indicator: the one place a soft breathing/pulse animation (gradient opacity 0.6↔1, ~2s loop) is appropriate — this is where the sparkle motif can animate. Don't reuse this animation elsewhere or it loses meaning.

## 8. The Sparkle Motif

The 4-point sparkle from the logo is your "AI presence" signifier — reserve it for:
- Loading/thinking indicator
- New-idea / suggestion callouts
- Empty state for a fresh conversation

Do not scatter it as generic decoration — it should always mean "the agent is doing something," so overuse dilutes that signal.

## 9. Component Notes (for Naive UI mapping)

- Map `accent-500` → `common.primaryColor`, `accent-600` → `primaryColorHover`, `accent-700` → `primaryColorPressed` in `GlobalThemeOverrides`.
- Map warm-gray scale → `common.textColorBase`, `bodyColor`, `cardColor`, `borderColor` per light/dark theme object.
- Only the primary CTA button (one per screen max) may use `--symbix-gradient-soft` as a background; all other buttons use solid `accent-500`.
- Tool-call / function-execution blocks: monospace font, `bg-elevated`, `radius-sm`, thin `border`, no shadow — keep these visually "quieter" than chat bubbles so the conversation stays foregrounded.
- Status dots (agent idle/thinking/error) use the semantic colors from §2.4, never the brand gradient — gradient is reserved for the "actively generating" state only, per §7.

## 10. Do / Don't

**Do**: one accent color for interactive elements, warm neutrals everywhere else, gradient reserved for brand + active-agent moments, generous negative space like the logo.
**Don't**: gradient buttons everywhere, neon/saturated status colors, cool/blue-gray neutrals, over-rounded containers, decorative sparkles outside the "agent is working" context.