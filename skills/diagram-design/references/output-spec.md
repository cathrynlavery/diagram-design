# Output specification

## 1. Screen presets

| Preset | viewBox | Aspect | PNG | Type ramp | Use |
|---|---|---|---|---|---|
| `screen-wide` | `0 0 1920 1080` | 16:9 | @2 → 3840×2160 | screen | 1080p presentation slide |
| `screen-4k` | `0 0 3840 2160` | 16:9 | @2 → 7680×4320 | screen | 4K presentation slide |
| `screen-2k` | `0 0 2560 1440` | 16:9 | @2 → 5120×2880 | screen | 2K presentation slide |

## 2. Print presets

| Preset | viewBox | Aspect | PNG | Type ramp | Use |
|---|---|---|---|---|---|
| `print-a4-landscape` | `0 0 1120 792` | ~1.41:1 | @3 → 3360×2376 | print | A4 landscape, ~10mm margins at 96dpi |
| `print-a3-landscape` | `0 0 1584 1120` | ~1.41:1 | @3 → 4752×3360 | print | A3 landscape, ~10mm margins at 96dpi |
| `print-letter-landscape` | `0 0 1056 816` | ~1.29:1 | @3 → 3168×2448 | print | US Letter landscape, ~10mm margins at 96dpi |

## 3. Square presets

| Preset | viewBox | Aspect | PNG | Type ramp | Use |
|---|---|---|---|---|---|
| `square` | `0 0 800 800` | 1:1 | @2 → 1600×1600 | screen | Social media square |
| `square-print` | `0 0 1120 1120` | 1:1 | @3 → 3360×3360 | print | Print square |

## 4. Type ramps

### Screen

```html
<text style="font-family: 'Inter', sans-serif; font-size: 48px; font-weight: 700;">Heading 1</text>
<text style="font-family: 'Inter', sans-serif; font-size: 32px; font-weight: 600;">Heading 2</text>
<text style="font-family: 'Inter', sans-serif; font-size: 24px; font-weight: 500;">Heading 3</text>
<text style="font-family: 'Inter', sans-serif; font-size: 18px; font-weight: 400;">Body text</text>
<text style="font-family: 'Inter', sans-serif; font-size: 14px; font-weight: 400;">Caption</text>
```

### Print

```html
<text style="font-family: 'Inter', sans-serif; font-size: 36pt; font-weight: 700;">Heading 1</text>
<text style="font-family: 'Inter', sans-serif; font-size: 24pt; font-weight: 600;">Heading 2</text>
<text style="font-family: 'Inter', sans-serif; font-size: 18pt; font-weight: 500;">Heading 3</text>
<text style="font-family: 'Inter', sans-serif; font-size: 12pt; font-weight: 400;">Body text</text>
<text style="font-family: 'Inter', sans-serif; font-size: 10pt; font-weight: 400;">Caption</text>
```

## 5. Margins

All presets assume ~10mm margins (0.5 inch) from the viewBox edge to the content area.

## 6. Color tokens

### Light skin

| Token | Value | Use |
|---|---|---|
| `--bg` | `#ffffff` | Background |
| `--fg` | `#1a1a1a` | Primary text |
| `--muted` | `#6b7280` | Secondary text |
| `--border` | `#e5e7eb` | Borders and dividers |
| `--accent` | `#3b82f6` | Interactive elements |
| `--success` | `#10b981` | Positive state |
| `--warning` | `#f59e0b` | Caution state |
| `--error` | `#ef4444` | Negative state |

### Dark skin

| Token | Value | Use |
|---|---|---|
| `--bg` | `#111827` | Background |
| `--fg` | `#f9fafb` | Primary text |
| `--muted` | `#9ca3af` | Secondary text |
| `--border` | `#374151` | Borders and dividers |
| `--accent` | `#60a5fa` | Interactive elements |
| `--success` | `#34d399` | Positive state |
| `--warning` | `#fbbf24` | Caution state |
| `--error` | `#f87171` | Negative state |