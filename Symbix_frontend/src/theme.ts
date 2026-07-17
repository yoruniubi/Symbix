/**
 * Symbix Theme — single source of truth from DESIGN.md
 *
 * Default: light (warm companion feel)
 * Also supports dark mode via setThemeMode()
 *
 * Usage:
 *   import { themeOverrides, injectCssVariables } from '@/theme'
 *   injectCssVariables('light')
 *   <n-config-provider :theme="null" :theme-overrides="themeOverrides">
 */

import type { GlobalThemeOverrides } from 'naive-ui'

// ─────────────────────────────────────────────
// 1. Design Tokens
// ─────────────────────────────────────────────

export const tokens = {
  /** Brand gradient — logo, active-agent moments, one CTA max per screen */
  gradient: 'linear-gradient(135deg, #F7A85B 0%, #F2657A 55%, #E85C93 100%)',
  gradientSoft: 'linear-gradient(135deg, #F7A85B 0%, #E85C93 100%)',

  /** Accent scale (solid, everyday interactive) */
  accent: {
    50: '#FFF3E9',
    100: '#FFE1CC',
    300: '#F7A85B',
    500: '#EF6B6E', // primary workhorse
    600: '#E2515F', // hover / active
    700: '#C43F5C', // high-contrast accent text
  },

  /** Warm gray neutrals */
  gray: {
    25: '#FBFAF9',
    50: '#F6F4F2',
    100: '#EDEAE7',
    200: '#DCD7D2',
    300: '#BFB8B2',
    400: '#968D86',
    500: '#6F675F',
    600: '#524B45',
    700: '#3A342F',
    800: '#262220',
    900: '#1A1715',
    950: '#121010',
  },

  /** Semantic status (desaturated — state, not brand) */
  semantic: {
    success: '#4E9A6E',
    warning: '#D89B3C',
    error: '#D3555A',
    info: '#5B8AC4',
  },

  /**
   * Dark mode surfaces — warm charcoal with amber undertone
   * so the coral/amber brand still feels present at night.
   */
  dark: {
    bgApp: '#161210',       // deep warm charcoal
    bgSurface: '#1E1916',   // slightly lifted panel
    bgElevated: '#2A221E',  // cards / elevated
    border: '#3D322C',      // warm brown border
    textPrimary: '#F7F0EA', // soft warm white
    textSecondary: '#B8A99C',
    textMuted: '#8A7B70',
  },

  /** Light mode surfaces (default) */
  light: {
    bgApp: '#FBFAF9',
    bgSurface: '#FFFFFF',
    bgElevated: '#FFFFFF',
    border: '#DCD7D2',
    textPrimary: '#262220',
    textSecondary: '#6F675F',
    textMuted: '#968D86',
  },

  /** Typography */
  font: {
    sans: '"Inter", -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif',
    mono: '"JetBrains Mono", "Fira Code", "Cascadia Code", monospace',
  },

  /** Type scale (px) */
  text: {
    xs: '12px',
    sm: '13px', // default UI density
    base: '14px', // chat body
    md: '16px',
    lg: '20px',
    xl: '24px',
  },

  /** Spacing (8px base) */
  space: {
    1: '4px',
    2: '8px',
    3: '12px',
    4: '16px',
    5: '20px',
    6: '24px',
    8: '32px',
    10: '40px',
    12: '48px',
  },

  /** Radius */
  radius: {
    sm: '6px',
    md: '8px',
    lg: '12px',
    full: '999px',
  },

  /** Elevation */
  shadow: {
    sm: '0 1px 2px rgba(0,0,0,0.06)',
    md: '0 4px 12px rgba(0,0,0,0.08)',
    glow: '0 0 24px rgba(242,101,122,0.20)',
  },

  /** Motion */
  ease: 'cubic-bezier(0.4, 0, 0.2, 1)',
  duration: {
    fast: '120ms',
    base: '180ms',
    slow: '320ms',
  },
} as const

export type ThemeMode = 'light' | 'dark'

/** App default — light feels warmer with the coral/amber accent */
export const DEFAULT_THEME_MODE: ThemeMode = 'light'

// ─────────────────────────────────────────────
// 2. CSS custom properties
// ─────────────────────────────────────────────

function derivedHelpers(mode: ThemeMode) {
  if (mode === 'light') {
    return {
      accentSoft: 'rgba(239, 107, 110, 0.10)',
      accentSoftHover: 'rgba(239, 107, 110, 0.16)',
      accentBorder: 'rgba(239, 107, 110, 0.28)',
      accentGlow: 'rgba(239, 107, 110, 0.14)',
      surfaceHover: 'rgba(38, 34, 32, 0.04)',
      surfaceActive: 'rgba(38, 34, 32, 0.07)',
      scrollbar: 'rgba(38, 34, 32, 0.12)',
      scrollbarHover: 'rgba(38, 34, 32, 0.20)',
      activityBarBg: 'rgba(255, 255, 255, 0.92)',
      panelBg: 'rgba(255, 255, 255, 0.98)',
      shadowSm: '0 1px 2px rgba(0,0,0,0.06)',
      shadowMd: '0 4px 12px rgba(0,0,0,0.08)',
    }
  }
  // Dark: keep coral glow stronger so brand shows through the charcoal
  return {
    accentSoft: 'rgba(239, 107, 110, 0.16)',
    accentSoftHover: 'rgba(239, 107, 110, 0.24)',
    accentBorder: 'rgba(247, 168, 91, 0.38)',
    accentGlow: 'rgba(242, 101, 122, 0.28)',
    surfaceHover: 'rgba(247, 168, 91, 0.08)',
    surfaceActive: 'rgba(247, 168, 91, 0.12)',
    scrollbar: 'rgba(247, 168, 91, 0.18)',
    scrollbarHover: 'rgba(247, 168, 91, 0.30)',
    activityBarBg: 'rgba(22, 18, 16, 0.92)',
    panelBg: 'rgba(30, 25, 22, 0.97)',
    shadowSm: '0 1px 2px rgba(0,0,0,0.28)',
    shadowMd: '0 6px 18px rgba(0,0,0,0.36)',
  }
}

/** Build a CSS string that sets :root variables from tokens */
export function buildCssVariables(mode: ThemeMode = DEFAULT_THEME_MODE): string {
  const surface = mode === 'dark' ? tokens.dark : tokens.light
  const h = derivedHelpers(mode)
  return `
:root {
  color-scheme: ${mode};

  --symbix-gradient: ${tokens.gradient};
  --symbix-gradient-soft: ${tokens.gradientSoft};

  --accent-50: ${tokens.accent[50]};
  --accent-100: ${tokens.accent[100]};
  --accent-300: ${tokens.accent[300]};
  --accent-500: ${tokens.accent[500]};
  --accent-600: ${tokens.accent[600]};
  --accent-700: ${tokens.accent[700]};

  --gray-25: ${tokens.gray[25]};
  --gray-50: ${tokens.gray[50]};
  --gray-100: ${tokens.gray[100]};
  --gray-200: ${tokens.gray[200]};
  --gray-300: ${tokens.gray[300]};
  --gray-400: ${tokens.gray[400]};
  --gray-500: ${tokens.gray[500]};
  --gray-600: ${tokens.gray[600]};
  --gray-700: ${tokens.gray[700]};
  --gray-800: ${tokens.gray[800]};
  --gray-900: ${tokens.gray[900]};
  --gray-950: ${tokens.gray[950]};

  --success: ${tokens.semantic.success};
  --warning: ${tokens.semantic.warning};
  --error: ${tokens.semantic.error};
  --info: ${tokens.semantic.info};

  --bg-app: ${surface.bgApp};
  --bg-surface: ${surface.bgSurface};
  --bg-elevated: ${surface.bgElevated};
  --border: ${surface.border};
  --text-primary: ${surface.textPrimary};
  --text-secondary: ${surface.textSecondary};
  --text-muted: ${surface.textMuted};

  --font-sans: ${tokens.font.sans};
  --font-mono: ${tokens.font.mono};

  --radius-sm: ${tokens.radius.sm};
  --radius-md: ${tokens.radius.md};
  --radius-lg: ${tokens.radius.lg};
  --radius-full: ${tokens.radius.full};

  --shadow-sm: ${h.shadowSm};
  --shadow-md: ${h.shadowMd};
  --shadow-glow: ${tokens.shadow.glow};

  --ease-standard: ${tokens.ease};
  --duration-fast: ${tokens.duration.fast};
  --duration-base: ${tokens.duration.base};
  --duration-slow: ${tokens.duration.slow};

  --accent-soft: ${h.accentSoft};
  --accent-soft-hover: ${h.accentSoftHover};
  --accent-border: ${h.accentBorder};
  --accent-glow: ${h.accentGlow};
  --surface-hover: ${h.surfaceHover};
  --surface-active: ${h.surfaceActive};
  --scrollbar: ${h.scrollbar};
  --scrollbar-hover: ${h.scrollbarHover};
  --activity-bar-bg: ${h.activityBarBg};
  --panel-bg: ${h.panelBg};
}
`.trim()
}

/** Inject CSS variables into <head> (call once in main.js) */
export function injectCssVariables(mode: ThemeMode = DEFAULT_THEME_MODE) {
  const id = 'symbix-theme-vars'
  let el = document.getElementById(id) as HTMLStyleElement | null
  if (!el) {
    el = document.createElement('style')
    el.id = id
    document.head.appendChild(el)
  }
  el.textContent = buildCssVariables(mode)
  document.documentElement.setAttribute('data-theme', mode)
}

// ─────────────────────────────────────────────
// 3. Naive UI GlobalThemeOverrides
// ─────────────────────────────────────────────

export function buildThemeOverrides(mode: ThemeMode = DEFAULT_THEME_MODE): GlobalThemeOverrides {
  const surface = mode === 'dark' ? tokens.dark : tokens.light
  const a = tokens.accent
  const s = tokens.semantic
  const h = derivedHelpers(mode)
  const isLight = mode === 'light'

  return {
    common: {
      fontFamily: tokens.font.sans,
      fontFamilyMono: tokens.font.mono,
      fontSize: tokens.text.sm,
      fontSizeMini: tokens.text.xs,
      fontSizeTiny: tokens.text.xs,
      fontSizeSmall: tokens.text.sm,
      fontSizeMedium: tokens.text.base,
      fontSizeLarge: '15px',
      fontSizeHuge: tokens.text.md,
      borderRadius: tokens.radius.md,
      borderRadiusSmall: tokens.radius.sm,

      primaryColor: a[500],
      primaryColorHover: a[600],
      primaryColorPressed: a[700],
      primaryColorSuppl: a[300],

      infoColor: s.info,
      successColor: s.success,
      warningColor: s.warning,
      errorColor: s.error,

      bodyColor: surface.bgApp,
      cardColor: surface.bgSurface,
      modalColor: surface.bgElevated,
      popoverColor: surface.bgElevated,
      tableColor: surface.bgSurface,
      invertedColor: isLight ? tokens.gray[900] : surface.textPrimary,

      borderColor: surface.border,
      dividerColor: surface.border,

      textColorBase: surface.textPrimary,
      textColor1: surface.textPrimary,
      textColor2: surface.textSecondary,
      textColor3: surface.textMuted,
      textColorDisabled: isLight ? tokens.gray[400] : tokens.gray[600],

      placeholderColor: isLight ? tokens.gray[400] : tokens.gray[500],
      placeholderColorDisabled: isLight ? tokens.gray[300] : tokens.gray[600],

      iconColor: surface.textSecondary,
      iconColorHover: surface.textPrimary,
      iconColorPressed: a[500],
      iconColorDisabled: isLight ? tokens.gray[400] : tokens.gray[600],

      hoverColor: h.surfaceHover,
      pressedColor: h.surfaceActive,

      opacityDisabled: '0.45',
      boxShadow1: h.shadowSm,
      boxShadow2: h.shadowMd,
      boxShadow3: isLight
        ? '0 8px 24px rgba(0,0,0,0.10)'
        : '0 8px 24px rgba(0,0,0,0.22)',
    },

    Button: {
      borderRadiusMedium: tokens.radius.md,
      borderRadiusLarge: tokens.radius.md,
      borderRadiusSmall: tokens.radius.sm,
      borderRadiusTiny: tokens.radius.sm,
      fontWeightStrong: '600',
      textColorPrimary: '#FFFFFF',
      colorPrimary: a[500],
      colorHoverPrimary: a[600],
      colorPressedPrimary: a[700],
      colorFocusPrimary: a[500],
      borderPrimary: `1px solid ${a[500]}`,
      borderHoverPrimary: `1px solid ${a[600]}`,
      borderPressedPrimary: `1px solid ${a[700]}`,
      borderFocusPrimary: `1px solid ${a[500]}`,
      rippleColorPrimary: a[500],
    },

    Input: {
      borderRadius: tokens.radius.sm,
      color: isLight ? tokens.gray[25] : surface.bgSurface,
      colorFocus: surface.bgSurface,
      border: `1px solid ${surface.border}`,
      borderHover: `1px solid ${isLight ? tokens.gray[300] : tokens.gray[600]}`,
      borderFocus: `1px solid ${a[500]}`,
      boxShadowFocus: '0 0 0 2px rgba(239, 107, 110, 0.16)',
      caretColor: a[500],
      textColor: surface.textPrimary,
      placeholderColor: isLight ? tokens.gray[400] : tokens.gray[500],
    },

    Card: {
      borderRadius: tokens.radius.lg,
      color: surface.bgSurface,
      borderColor: surface.border,
      titleTextColor: surface.textPrimary,
      textColor: surface.textSecondary,
    },

    Select: {
      peers: {
        InternalSelection: {
          borderRadius: tokens.radius.sm,
          color: isLight ? tokens.gray[25] : surface.bgSurface,
          border: `1px solid ${surface.border}`,
          borderHover: `1px solid ${isLight ? tokens.gray[300] : tokens.gray[600]}`,
          borderActive: `1px solid ${a[500]}`,
          borderFocus: `1px solid ${a[500]}`,
          boxShadowActive: '0 0 0 2px rgba(239, 107, 110, 0.16)',
          boxShadowFocus: '0 0 0 2px rgba(239, 107, 110, 0.16)',
          textColor: surface.textPrimary,
          placeholderColor: isLight ? tokens.gray[400] : tokens.gray[500],
        },
        InternalSelectMenu: {
          borderRadius: tokens.radius.md,
          color: surface.bgElevated,
          optionTextColor: surface.textSecondary,
          optionTextColorActive: surface.textPrimary,
          optionColorPending: h.accentSoft,
          optionColorActive: h.accentSoftHover,
          optionCheckColor: a[500],
        },
      },
    },

    Dropdown: {
      borderRadius: tokens.radius.md,
      color: surface.bgElevated,
      optionTextColor: surface.textSecondary,
      optionTextColorHover: surface.textPrimary,
      optionTextColorActive: surface.textPrimary,
      optionColorHover: h.accentSoft,
      optionColorActive: h.accentSoftHover,
    },

    Tooltip: {
      borderRadius: tokens.radius.sm,
      color: isLight ? tokens.gray[800] : surface.bgElevated,
      textColor: isLight ? tokens.gray[25] : surface.textPrimary,
    },

    Message: {
      borderRadius: tokens.radius.md,
    },

    Tag: {
      borderRadius: tokens.radius.sm,
    },

    Modal: {
      borderRadius: tokens.radius.lg,
      color: surface.bgElevated,
      textColor: surface.textPrimary,
    },

    Dialog: {
      borderRadius: tokens.radius.lg,
      color: surface.bgElevated,
      titleTextColor: surface.textPrimary,
      textColor: surface.textSecondary,
    },

    Popover: {
      borderRadius: tokens.radius.md,
      color: surface.bgElevated,
      textColor: surface.textPrimary,
    },

    Empty: {
      textColor: surface.textMuted,
      iconColor: isLight ? tokens.gray[400] : tokens.gray[500],
    },

    Slider: {
      fillColor: a[500],
      fillColorHover: a[600],
      handleColor: a[500],
    },

    Switch: {
      railColorActive: a[500],
    },

    Checkbox: {
      colorChecked: a[500],
      borderChecked: `1px solid ${a[500]}`,
      borderFocus: `1px solid ${a[500]}`,
    },

    Radio: {
      colorActive: a[500],
      boxShadowActive: `inset 0 0 0 1px ${a[500]}`,
      boxShadowFocus: `inset 0 0 0 1px ${a[500]}`,
    },

    Scrollbar: {
      color: h.scrollbar,
      colorHover: h.scrollbarHover,
    },
  }
}

/** Default Naive overrides for current default mode (light) */
export const themeOverrides: GlobalThemeOverrides = buildThemeOverrides(DEFAULT_THEME_MODE)

// ─────────────────────────────────────────────
// 4. Convenience re-exports for component CSS
// ─────────────────────────────────────────────

export const css = {
  bgApp: 'var(--bg-app)',
  bgSurface: 'var(--bg-surface)',
  bgElevated: 'var(--bg-elevated)',
  border: 'var(--border)',
  textPrimary: 'var(--text-primary)',
  textSecondary: 'var(--text-secondary)',
  textMuted: 'var(--text-muted)',
  accent: 'var(--accent-500)',
  accentHover: 'var(--accent-600)',
  accentSoft: 'var(--accent-soft)',
  accentBorder: 'var(--accent-border)',
  gradient: 'var(--symbix-gradient)',
  gradientSoft: 'var(--symbix-gradient-soft)',
  radiusSm: 'var(--radius-sm)',
  radiusMd: 'var(--radius-md)',
  radiusLg: 'var(--radius-lg)',
  fontSans: 'var(--font-sans)',
  fontMono: 'var(--font-mono)',
  success: 'var(--success)',
  warning: 'var(--warning)',
  error: 'var(--error)',
  info: 'var(--info)',
} as const
