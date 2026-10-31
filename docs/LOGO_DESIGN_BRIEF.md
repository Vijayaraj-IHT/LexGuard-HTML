# LexGuard — Brand & Logo Design Brief

**Purpose:** give the project one mark that survives a favicon at 16 px, a navbar at 36 px, a report cover, and a projector — and that matches the judicial crimson/white design system already in the CSS.

---

## 1. Brand audit (what exists today)

| Where | What is used now | Problem |
|---|---|---|
| `frontend/favicon.svg` | Crimson shield containing a hand-drawn balance scale | Conceptually right, but 14 separate paths, thin 1.2 px strings, and white-on-crimson detail that disappears below 32 px |
| Navbar (`lexguard-nav.js:32`) | Bootstrap icon `bi-shield-fill-check` inside a rounded red square | **Different mark** from the favicon — two logos for one product |
| Login / report cover | Plain text "LexGuard", Playfair Display | No lockup rules, inconsistent sizes |
| Page titles | "LexGuard — Judicial Repository & Verification Platform" | Long, inconsistent subtitles across pages |

**Brand attributes to encode:** authority, integrity (cryptographic), accessibility, Indian judiciary, modern public-interest technology.
**Metaphors available:** scales (justice), shield (guard/verification), seal (authenticity), arch/pillar (courthouse), check/hash (technical verification). Use **at most two** — more becomes a cliché and dies at small sizes.

**Constraints**

- Must read at **16 × 16 px** (favicon), 36 px (navbar), 512 px (docs).
- Must work **one-colour** (report printing, fax-quality photocopies in a court office).
- No text inside the mark (wordmark is separate).
- Palette: crimson `#991b1b`, maroon `#7f1d1d`, gold `#b45309` (text-safe), ink `#0f172a`, white.
- Must not imitate the State emblem / Ashoka Chakra or any official court seal (legal restriction on state emblems).

---

## 2. Three concepts

### Concept A — "Guardian Scales" (evolution of today's favicon) ★ recommended

A **shield whose interior is reduced to a single balanced beam and two pans**, drawn on a 4 px grid with uniform 3 px strokes; the vertical stem ends in a small checkmark notch.

```
    ╭─────────╮
   ╱  ──┬──    ╲      shield = guard
  │    ╱ ╲      │     beam  = balance
  │   ▬   ▬     │     notch = verified
   ╲           ╱
    ╰─────────╯
```

- **Pros:** keeps recognition from the current favicon; instantly "justice"; scales survive at 16 px when reduced to shield + beam only.
- **Cons:** scales are the most common legal cliché — differentiation must come from the geometric rendering and the crimson/white contrast.
- **Best if:** you want continuity with existing screenshots and the report.

### Concept B — "Seal & Cipher"

A circular court-seal ring with a **checkmark cut out of the centre**, the check formed by a gavel's diagonal. A fine ring gap suggests a hash/chain link.

- **Pros:** speaks to the *verification* half of the product; unique among legal-tech logos.
- **Cons:** busy at 16 px; harder to print one-colour; reads "security app" more than "judicial repository".

### Concept C — "Monogram Arch"

An **"L" and "G" constructed from two courthouse arches**, forming a square monogram with a crimson keystone.

- **Pros:** very legible small, modern, distinctive, excellent for an app icon.
- **Cons:** less immediately "law"; needs the wordmark to explain the product at first sight.

### Recommendation

**Concept A**, refined to 5 paths with a 16 px simplified variant, and adopt **Concept C's square container** (rounded 8 px radius) for the app icon so it sits correctly next to OS icons. This gives continuity + legibility without the 14-path clutter.

---

## 3. Recommended master mark — construction spec

**Canvas** 64 × 64, live area 56 × 56, 4 px padding, 8 px corner radius on the container.
**Grid** 4 px. **Stroke** 3 px, round caps/joins. **Minimum detail** 4 px.

```svg
<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 64 64" role="img" aria-label="LexGuard">
  <defs>
    <linearGradient id="lg-red" x1="0" y1="0" x2="1" y2="1">
      <stop offset="0" stop-color="#b91c1c"/>
      <stop offset="1" stop-color="#7f1d1d"/>
    </linearGradient>
  </defs>

  <!-- Shield (guard) -->
  <path d="M32 6 L54 15 V33 C54 45.5 44.6 54.6 32 58 C19.4 54.6 10 45.5 10 33 V15 Z"
        fill="url(#lg-red)"/>

  <!-- Beam + stem (balance) -->
  <path d="M22 26.5 H42 M32 21 V45.5 M24 45.5 H40"
        stroke="#fff" stroke-width="3" stroke-linecap="round" fill="none"/>

  <!-- Pans -->
  <path d="M17 30 L22.5 37.5 H11.5 Z" fill="#fff"/>
  <path d="M47 30 L52.5 37.5 H41.5 Z" fill="#fff"/>

  <!-- Verification notch -->
  <path d="M28.5 33.6 L31.4 36.5 L36.4 30.6"
        stroke="#fff" stroke-width="2.6" stroke-linecap="round"
        stroke-linejoin="round" fill="none"/>
</svg>
```

**16 px variant:** drop the pans and the notch → shield + beam + stem only. At 16 px the stem must be 2 px, not 3.
**One-colour variant:** solid `#991b1b` shield, white interior; no gradient.
**Inverse variant:** white shield outline on crimson, crimson interior marks.

### Lockup

```
[mark 36px]  LexGuard
             Judicial case repository
```

- Wordmark: **Playfair Display SemiBold 600**, size = mark × 0.62, `letter-spacing: -0.01em`, ink `#0f172a` on white, white on crimson.
- Descriptor: **Inter 500**, size = wordmark × 0.34, uppercase, `letter-spacing: .08em`, colour `#475569`.
- Clear space: **0.5 × mark height** on all sides; nothing enters the shield's bounding box.

---

## 4. Colour

| Token | Hex | Contrast on white | Use |
|---|---|---:|---|
| Court crimson | `#991b1b` | 8.31 : 1 | Primary brand, links, buttons |
| Maroon (gradient end) | `#7f1d1d` | 10.02 : 1 | Gradient/shadow anchor |
| Signature gold | `#b45309` | **5.02 : 1** | Accent text, focus, "verified" energy |
| Ink | `#0f172a` | 17.85 : 1 | Body text |
| Slate | `#475569` | 7.0 : 1 | Secondary text |
| Success | `#047857` | 5.48 : 1 | Verified state |
| White | `#ffffff` | — | Surface |

**Do not use `#d97706` for text** (3.19 : 1 — fails AA). The current site does; switch to `#b45309`.

---

## 5. Where the logo appears (integration checklist)

| Surface | Asset | Code change |
|---|---|---|
| Navbar (36 px) | `lexguard-mark.svg` + wordmark | Replace `<div class="brand-emblem"><i class="bi bi-shield-fill-check"></i></div>` in `lexguard-nav.js:32` with the inline SVG; keep `aria-label="LexGuard — home"` on the link |
| Favicon | `favicon.svg` (16 px variant) + `favicon.ico` 16/32/48 | Replace `frontend/favicon.svg`; regenerate `.ico`; update `backend/storage/favicon.ico` too (served by `/favicon.ico`) |
| iPhone / PWA | `apple-touch-icon.png` 180 | new `<link rel="apple-touch-icon">` on every page head |
| Login / register | Centred mark 72 px above the title | `login.html`, `register.html` |
| 404 / unauthorized | Watermark mark at 12 % opacity | `404.html`, `unauthorized.html` |
| Report cover | 512 px PNG + mono SVG | `report_builder/build_report.py` |
| Social / README | `og-image.png` 1200 × 630 | `<meta property="og:image">`, README hero |
| Certificate / seal modal | Mono mark inside the seal ring | `case-viewer.html` certified-copy modal |

---

## 6. Production checklist

- [ ] Mark reads at 16 px on light and dark backgrounds.
- [ ] Grayscale print test (no gradient reliance).
- [ ] Clear space and minimum sizes documented (16 px digital, 8 mm print).
- [ ] `aria-hidden="true"` on decorative SVGs; accessible name only on the home link.
- [ ] All assets < 8 KB each (SVG optimised with `svgo`).
- [ ] No state-emblem resemblance; no Ashoka Chakra; no national flag colours as the sole identity.
- [ ] Reused favicon in backend served byte-identically.
- [ ] Logo + wordmark lockup has fixed spacing tokens (`--lg-logo-gap: .65rem`).

---

## 7. Suggested next step

Pick a concept (A recommended, or B/C if you want a different positioning) and I will:

1. produce the **three SVG masters** (colour, mono, inverse) + 16 px favicon variant,
2. render 16/32/48/180/512 PNG exports,
3. replace the navbar emblem and favicon in the repo,
4. add a small `brand.html` preview page so you can see every size side by side.

If you prefer a different metaphor (gavel, pillar, hash chain, Devanagari-inspired form), say which and I will redraw the concept before touching the codebase.
