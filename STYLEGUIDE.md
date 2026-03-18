# CafeBox Portal Style Guide

This guide defines the visual and interaction language for the CafeBox portal landing page in Task 0.12.

## 1. Purpose And Scope

- Apply to the public portal landing page served by the nginx role.
- Support first-time hotspot users arriving through captive-portal redirects.
- Keep implementation lightweight: plain HTML, CSS, and vanilla JavaScript.
- Align with the public API contract from `GET /api/public/services/status`.

Out of scope:

- Admin UI design system
- Branding for printed assets
- Service-specific internal UI styling

## 2. Experience Goals

- Feel playful and welcoming, like a friendly 16-bit game hub.
- Make the next action obvious within 3 seconds.
- Keep load and interaction fast on low-power hardware.
- Preserve trust with clear status cues and readable text.

## 3. Visual Direction

Theme: 16-bit SNES/Genesis inspired, bright but controlled.

Style keywords:

- Pixel-art accents
- Chunky panel framing
- Cartridge-era color contrast
- Soft CRT-inspired atmosphere

Avoid:

- Realistic gradients that look modern-app glossy
- Thin, minimalist gray-on-white UI
- Neon overload that hurts readability

## 4. Design Tokens

Use CSS variables for consistency.

```css
:root {
  --bg-sky-top: #84c8ff;
  --bg-sky-bottom: #dff3ff;
  --bg-grid: #9ad2ff;

  --surface-1: #f6f1da;
  --surface-2: #ece3c5;
  --surface-3: #d7c79a;

  --ink-strong: #1d2433;
  --ink-soft: #36445e;
  --ink-inverse: #fffdf2;

  --accent-primary: #e85d44;
  --accent-secondary: #2e7dff;
  --accent-success: #2f9e44;
  --accent-warning: #d97706;
  --accent-danger: #c92a2a;

  --tile-enabled: #fff8dc;
  --tile-disabled: #d9d2b2;
  --focus-ring: #2e7dff;

  --border-strong: #1d2433;
  --shadow-pixel: 4px 4px 0 #1d2433;

  --space-1: 4px;
  --space-2: 8px;
  --space-3: 12px;
  --space-4: 16px;
  --space-5: 24px;
  --space-6: 32px;

  --radius-sm: 4px;
  --radius-md: 8px;
  --radius-lg: 12px;
}
```

Implementation notes:

- Keep border lines dark and visible; this style depends on clear silhouettes.
- Use blocky shadows (`--shadow-pixel`) rather than blurred shadows.
- Use one accent color for primary calls to action per view.

## 5. Typography

Primary text should be highly legible and available offline.

- UI body font: local, bundled sans-serif (`@font-face`) with fallback to `Verdana`, `Tahoma`, `sans-serif`.
- Display font for headings: local, bundled pixel style (`@font-face`) with fallback to body font.
- Never load web fonts from external CDNs.

Type scale:

- Hero title: 28-32px
- Section title: 20-24px
- Tile title: 18-20px
- Body text: 16px
- Meta text: 14px

## 6. Page Structure

Portal anatomy from top to bottom:

1. Hero/header area
2. Optional first-boot password banner
3. Service tile grid
4. Small status/help footer

Layout rules:

- Max content width: 1080px.
- Horizontal padding: 16px mobile, 24px tablet+, 32px desktop.
- Tile grid: 1 column on small phones, 2 on phones/tablets, 3-4 on desktop.

## 7. Components

### 7.1 Hero

- Introduce the box name and short welcome line.
- Include a subtle pixel motif (stars, clouds, checker strip, or mini sprite) as decoration.
- Keep decorative elements non-interactive.

### 7.2 First-Boot Password Banner

Purpose: clearly warn operators that a temporary password is active.

Rules:

- Place directly below hero so it is visible without scrolling.
- Strong contrast and border framing.
- Include clear label, value, and one-line action guidance.
- If API says `first_boot: false`, do not render the banner.

Copy guidance:

- Heading: "First Boot Setup"
- Body: "Temporary admin password is active. Change it after sign-in."

### 7.3 Service Tiles

Each tile must display:

- Service name
- Availability state (enabled or unavailable)
- Destination URL or disabled indicator

Enabled state:

- Full color tile (`--tile-enabled`)
- Link is clickable
- Hover/pressed states feel tactile

Disabled state:

- Muted tile (`--tile-disabled`)
- Not clickable
- Include text: "Unavailable on this box"

### 7.4 Loading, Empty, And Error States

Loading:

- Show 3-6 placeholder tiles with subtle pulse or frame shimmer.
- Do not use spinner-only loading.

Empty:

- Message: "No services are enabled yet."
- Follow-up hint: "Enable services in CafeBox config and reprovision."

Error:

- Message: "Service list unavailable right now."
- Include a retry button that re-runs the same fetch.

## 8. Motion Rules

- Keep transitions short: 120-180ms.
- Animate opacity and small translate only.
- Avoid heavy parallax or continuous motion.
- Respect `prefers-reduced-motion: reduce` by disabling non-essential animations.

## 9. Accessibility Guardrails

- Body text contrast ratio target: at least 4.5:1.
- Interactive focus indicator must be visible and at least 2px thick.
- Minimum touch target: 44x44px.
- All status changes must be available in text, not color alone.
- Tile actions must be keyboard reachable in logical order.

## 10. Implementation Constraints

- No JavaScript frameworks.
- No external CDN resources.
- No runtime downloads from third-party hosts.
- Keep JS simple: one startup fetch, render helpers, basic retry path.
- Prefer inline SVG or local assets for icons.
- Avoid linking to admin endpoints from the portal UI.

Performance guidance:

- Keep portal HTML/CSS/JS payload lean.
- Prefer system-level caching and static asset delivery from nginx.
- Avoid large background images; use CSS patterns where possible.

## 11. Responsive Behavior

Mobile first is required.

- Small screens: prioritize readability and thumb-friendly spacing.
- Mid screens: grow tile columns before increasing decorative density.
- Desktop: allow richer decoration but preserve information hierarchy.

## 12. Content Tone

Voice should be:

- Warm
- Clear
- Brief
- Non-technical for first-time visitors

Good examples:

- "Welcome to CafeBox"
- "Pick a service to get started"
- "Unavailable on this box"

Avoid:

- Dense operational jargon
- Alarmist warning language
- Debug details in user-facing copy

## 13. Definition Of Done For UX

A portal implementation is style-guide compliant when:

- It visually matches the 16-bit playful direction.
- It handles all required API states (`first_boot` true/false, service list success/failure).
- It is keyboard usable and readable on mobile.
- It uses no framework and no CDN-hosted assets.
- It keeps admin surfaces undisclosed from the portal navigation.
