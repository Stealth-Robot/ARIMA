# A.R.I.M.A. UI/UX Specification

> Aligning the web app to the spreadsheet layout. This document describes how each page should look, feel, and behave — with exact colours, measurements, and interaction patterns extracted from the source spreadsheet.

---

## Colour System

### Rating Cell Backgrounds (Artist Page — individual scores)

Each rating value (0-5) has a distinct, vibrant background colour. These are the signature visual of the app.

| Score | Colour | Hex (Classic) | Text | CSS Variable |
|-------|--------|-------------|------|-------------|
| 5 | Red | `#FF0016` | White (`--rating-text-light`) | `--rating-5-bg` |
| 4 | Orange | `#FF8E1E` | Black (`--rating-text-dark`) | `--rating-4-bg` |
| 3 | Yellow | `#FEFF2A` | Black (`--rating-text-dark`) | `--rating-3-bg` |
| 2 | Light Green | `#9EFFA4` | Black (`--rating-text-dark`) | `--rating-2-bg` |
| 1 | Light Blue | `#8AB5FC` | Black (`--rating-text-dark`) | `--rating-1-bg` |
| 0 | Purple | `#9200FC` | White (`--rating-text-light`) | `--rating-0-bg` |
| Unrated | White | `#FFFFFF` | — | (none) |

> **All colours are theme-driven.** Per the whitepaper: "Every colour used in the app is a column in the Themes table. No hardcoded colours." These are stored as 19 new columns in the Themes table. See `architecture.md` §14 for the full column list.

### Stats Heat Map Gradient (STATS page — average scores)

Average scores on the STATS page use a continuous gradient. These are the anchor points:

| Range | Colour | Hex |
|-------|--------|-----|
| 4.0–5.0 | Pink/Magenta | `#FFB7FE` |
| 3.0–3.9 | Orange | `#FF8E1E` |
| 2.0–2.9 | Yellow | `#FEFF2A` |
| 1.0–1.9 | Light Green | `#9EFFA4` |
| 0.1–0.9 | Light Blue | `#8AB5FC` |
| 0 (no rating) | White | `#FFFFFF` |

For intermediate values, interpolate between adjacent colours. For example, 3.5 would be between orange and pink.

### Completion Heat Map (STATS 2.0 — percentages)

| Range | Colour | Hex |
|-------|--------|-----|
| 100% | Pink/Magenta | `#FFB7FE` |
| 80–99% | Orange | `#FCA644` |
| 50–79% | Gradient (orange→blue) | interpolated |
| 1–49% | Light Blue | `#8AB5FC` |
| 0% | White | `#FFFFFF` |

### Structural Colours

All structural colours are in the Theme table (new columns):

| Element | Hex (Classic) | Theme Column | CSS Variable |
|---------|-------------|-------------|-------------|
| Header row bg | `#EEF2F8` | `header_row` (existing) | `--header-row` |
| Album header row | `#E6EBF4` | `album_header_bg` (new) | `--album-header-bg` |
| Alternating row | `#F7F9FD` | `row_alternate` (new) | `--row-alternate` |
| Grid lines | `#C0C0C0` | `grid_line` (new) | `--grid-line` |
| Key column bg (Standard) | `#FF8E1E` | `key_bg_standard` (new) | `--key-bg-standard` |
| Key column bg (Stealth) | `#FEFF2A` | `key_bg_stealth` (new) | `--key-bg-stealth` |

### Gender Text Colours

These are already in the theme system but documented here for reference:

| Gender | Colour | Current CSS Variable |
|--------|--------|---------------------|
| Female | Pink | `--gender-female` |
| Male | Blue | `--gender-male` |
| Mixed | Purple | `--gender-mixed` |

---

## Rating Key Legend

The spreadsheet displays a repeating Key column alongside song/artist rows. It cycles through **two versions**, each 7 rows:

### Standard Key

| Score | Label |
|-------|-------|
| 5 | Fucking banger |
| 4 | Great song |
| 3 | A vibe |
| 2 | Eh / Mid / No opinion |
| 1 | This isn't great |
| 0 | Absolute shit |

### Stealth Key

| Score | Label |
|-------|-------|
| 5 | Fucking banger |
| 4 | Bit of a Bop |
| 3 | Decent/Lacking Pop |
| 2 | Mid / kinda bad |
| 1 | Bad |
| 0 | I feel Offended |

The Key column shows `Key (Standard)` or `Key (Stealth Ver)` as a header, then cycles through score 5→0, then repeats with the alternate version. This creates a continuous reference alongside the data.

**Implementation:** The Key column shows the score number on the left and the label text on the right. The background colour matches the score colour from the rating cell colours above.

---

## Page 1: Artist Page (Discography)

### Layout (from example4.png)

```
┌─────────────────────────────────────────────────────────────────────────┐
│ [Top Navbar]                                                             │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  ┌────────────────┬──────┬──────┬──────┬──────┬───┬──────┬─────────────┐ │
│  │ DIRECTORY       │ Assy │Steal │Deren │ Diam │...│ Toki │Key(Standard)│ │
│  ├────────────────┼──────┼──────┼──────┼──────┼───┼──────┼─────────────┤ │
│  │ $10 (PRIMIster) │      │      │      │      │   │      │             │ │  ← album header (grey bg)
│  │ 1,2,3 (B.I.G)   │  3   │      │      │  3   │   │      │ 4 Great song│ │  ← song row
│  │ 2MYX (Junk)     │  5   │  3   │      │  5   │   │  3   │ 3 A vibe    │ │  ← song row
│  │ Angel (Berry)   │  5   │  5   │      │  5   │   │  1   │ 2 Eh / Mid  │ │
│  │ ...             │      │      │      │      │   │      │             │ │
│  └────────────────┴──────┴──────┴──────┴──────┴───┴──────┴─────────────┘ │
│                                                                          │
│  ┌──────────────────────────────────────────────────────────────────────┐ │
│  │ Artist1 │ Artist2 │ Artist3 │ ...                   [bottom navbar]  │ │
│  └──────────────────────────────────────────────────────────────────────┘ │
└─────────────────────────────────────────────────────────────────────────┘
```

### Column Structure

| Column | Width | Content |
|--------|-------|---------|
| DIRECTORY (col A) | 350px | Album headers (bold, grey bg) and song names |
| User columns | 60-70px each | Rating value (0-5) with coloured background |
| Empty separator | 10px | Visual gap before Key column |
| Key column | 140px | Score number + label text, coloured background |

### Visual Rules

1. **Album header rows:**
   - Full-width, spanning all columns
   - Background: `#E6EBF4` (light blue-grey)
   - Text: Bold, shows album name + year in parentheses: `"The Story Begins (2015)"`
   - No rating values in user columns

2. **Song rows:**
   - Background: alternating white `#FFFFFF` / `#F7F9FD`
   - Song name in DIRECTORY column (no track numbers)
   - Rating cells: coloured background based on score (see Rating Cell Backgrounds)
   - Unrated cells: white/blank (NOT "-")
   - Grid lines: `#C0C0C0` borders between all cells

3. **Key column:**
   - Repeats alongside every song row
   - Shows: `[score] [label]` e.g. `5 Fucking banger`
   - Background colour matches the score colour
   - Cycles: Standard (7 rows) → Stealth (7 rows) → repeat
   - Album header rows show the Key version header: `Key (Standard)` or `Key (Stealth Ver)`

4. **Header row:**
   - Background: `#EEF2F8`
   - First column header: `DIRECTORY`
   - User names as column headers
   - Key column header: `Key (Standard)`
   - Pinned/frozen at top

5. **Locked user indicator:**
   - Some users have `🔒` prefix: e.g. `🔒Assy`, `🔒Stealth`
   - Column width slightly wider (70px vs 60px) for locked users
   - This indicates their data is protected — display the lock emoji in the header

### Differences from Current Implementation

| Current | Should Be | Priority |
|---------|-----------|----------|
| Shows "-" for unrated | Blank/empty cell | **High** |
| Shows "1. Song Name" with track number | Just "Song Name" (no number) | **High** |
| Album headers are separate divs | Full-width table rows with grey bg | **High** |
| No Key column | Add repeating Key column | **High** |
| No cell background colours | Add coloured backgrounds per rating value | **Critical** |
| P column for promoted | Remove P column (not in spreadsheet) | **Medium** |
| hx-prompt dialog for rating | Click to cycle or dropdown (see Interactions) | **Medium** |
| Auto column widths | Fixed widths (350/60-70/140px) | **Medium** |

---

## Page 2: STATS Page (Global Stats — Average Scores)

### Layout (from example2.png)

```
┌──────┬───────────────┬──────┬──────┬──────┬──────┬───┬──────┬───┬──────────────┐
│Global│ Group          │ Assy │Steal │Deren │ Diam │...│ Toki │   │Key (Standard)│
├──────┼───────────────┼──────┼──────┼──────┼──────┼───┼──────┼───┼──────────────┤
│3.518 │ Misc. Artists  │3.878 │3.509 │3.839 │3.971 │   │3.173 │5.0│Fckn banger   │
│3.612 │ &TEAM          │3.571 │2.667 │  0   │4.116 │   │2.273 │4.0│Great song    │
│3.747 │ (G)I-DLE       │4.296 │3.914 │3.221 │3.889 │   │4.185 │3.0│A vibe        │
│3.578 │ 100%           │4.100 │3.000 │3.333 │3.912 │   │3.500 │2.0│Eh / Mid      │
│3.797 │ 15&            │4.091 │2.364 │4.545 │3.727 │   │4.273 │1.0│This isn't... │
│3.091 │ 2NE1           │3.651 │3.349 │3.125 │2.907 │   │2.628 │0.0│Absolute shit │
│3.213 │ 2AM            │3.625 │2.533 │  0   │4.000 │   │3.750 │   │Key (Stealth) │
```

### Visual Rules

1. **Cell background colours:**
   - Each user cell is coloured based on the average score using the heat map gradient
   - 0 values (no ratings) shown as `0` with white background (NOT blank, NOT "-")
   - Global column also coloured

2. **Group column:**
   - Artist name coloured by gender (pink/blue/purple)
   - Alphabetically sorted

3. **Key column:**
   - Same cycling pattern as artist page
   - Score number on the left, label on the right
   - Coloured background per score

4. **Number format:**
   - Show up to 3 decimal places for averages (not rounded to 1 or 2)
   - `0` for users with no ratings for an artist (not blank)

### Differences from Current Implementation

| Current | Should Be | Priority |
|---------|-----------|----------|
| Shows "-" for no rating | Shows "0" | **High** |
| No cell background colours | Heat map gradient colours | **Critical** |
| 2 decimal places | Up to 3 decimal places | **Medium** |
| Key column shows "0-5" | Full repeating key legend | **High** |
| No colour on Global column | Coloured like user cells | **Medium** |

---

## Page 3: STATS 2.0 Page (Artist Stats — Completion)

### Layout (from example3.png)

This is the most complex page with **three sets of user columns:**

```
Set 1: % rated           │     │Set 2: Unrated count     │     │Set 3: Rated count
Global│Group    │Assy│Stea│...│SC   │Assy│Log│Stea│...  │     │Assy│Stea│...
──────┼─────────┼────┼────┼───┼─────┼────┼───┼────┼─────┼─────┼────┼────┼───
19.7% │Overall  │61.5│35.0│   │     │    │   │    │     │     │    │    │
3919  │TotalRate│1309│7450│   │21292│    │   │    │     │     │    │    │
X     │         │  2 │  4 │   │     │    │   │    │     │     │    │    │
245   │SGC(any%)│ 349│ 325│   │     │    │   │    │     │     │    │    │
69.5  │SGC(80%) │ 174│ 120│   │     │    │   │    │     │     │    │    │
──────┼─────────┼────┼────┼───┼─────┼────┼───┼────┼─────┼─────┼────┼────┼───
41.5  │Misc.Art │89.8│77.4│   │ 137 │ 14 │ ✓ │ 31 │     │     │ 123│ 106│
24.5  │&TEAM    │97.7│14.0│   │  43 │  1 │   │ 37 │     │     │  42│   6│
76.2  │(G)I-DLE │100 │100 │   │  81 │  0 │ ✓ │  0 │     │     │  81│  81│
```

### Column Groups

**Set 1 (Percentage rated):** `Global | Group | [users...] | (gap)`
- Values are percentages (0-100) shown as numbers without % symbol
- Cell backgrounds coloured by percentage (heat map)
- 0% = white, 100% = pink

**Song Count column:** Between Set 1 and Set 2
- Total songs for that artist

**Set 2 (Unrated count):** `[users...] | (gap)`
- Number of songs the user has NOT rated for that artist
- Also includes a **"Log" column** (checkboxes: True/False)
- Checkboxes rendered as filled/empty squares

**Set 3 (Rated count):** `[users...]`
- Number of songs the user HAS rated for that artist

### Summary Rows (Top 5)

| Row | Global Value | Label |
|-----|-------------|-------|
| 1 | Avg % rated (weighted) | Overall Average (weighted) |
| 2 | Avg total rated | Total Rated Songs |
| 3 | "X" | (Rank row — users show rank number) |
| 4 | Avg SGC (any) | Scored Group Count (any%) |
| 5 | Avg SGC (80%) | Scored Group Count (80%+ scored songs) |

Row 6: **"Macro-Stats (DO NOT EDIT THIS ROW OR ABOVE)"** — separator between summary and per-artist data. In the web app, render this as a visual divider/gap.

### Visual Rules

1. **Set 1 cells:** Coloured by percentage using completion heat map
2. **Set 2 cells:** Plain numbers (unrated count), no colouring
3. **Set 3 cells:** Plain numbers (rated count), no colouring
4. **Log column:** Checkboxes (✓ / empty) — appears between users in Set 2
5. **Song Count:** Centered, bold, acts as a visual anchor
6. **Gap columns:** Empty columns between sets for visual separation

### Differences from Current Implementation

| Current | Should Be | Priority |
|---------|-----------|----------|
| 2 column groups | 3 column groups (add rated count) | **High** |
| No cell colouring | Percentage heat map on Set 1 | **Critical** |
| No SGC (any%) row | Add row for any-percentage scored groups | **Medium** |
| No Log column | Add Log checkboxes | **Low** (investigate purpose) |
| Simple gap | Proper visual separator between sets | **Medium** |
| Shows "%" suffix | Numbers without % symbol | **Low** |

---

## Page 4: Changelog

### Layout (from example1.png)

```
┌──────┬─────────────────────────────────────────────┬────────────┐
│ Name │ Desc                                         │ Date       │
├──────┼─────────────────────────────────────────────┼────────────┤
│ Toki │ Added Irene album "Biggest Fan"              │ 2026-03-29 │
│ Diam │ Added Scream Records release "RUDE! Remixes" │ 2026-03-27 │
│ Toki │ Added LATENCY tab and mini album "LATE..."   │ 2026-03-27 │
│ Diam │ Added Minnie single "CARRY YOU"              │ 2026-03-27 │
```

### Visual Rules

1. **Only 3 columns:** Name, Desc(ription), Date
2. **Date format:** `YYYY-MM-DD` (date only, no time)
3. **Green header row** background (matches spreadsheet tab colour)
4. **Newest entries at top**
5. **Description format:** Consistent pattern: `Added [artist] [type] "[name]"`
6. **No "Approved By" column** — not in spreadsheet
7. **No "Justification" column** — not in spreadsheet

### Differences from Current Implementation

| Current | Should Be | Priority |
|---------|-----------|----------|
| 5 columns (Date, User, Approved By, Desc, Justification) | 3 columns (Name, Desc, Date) | **High** |
| "User" column header | "Name" column header | **Low** |
| ISO datetime shown | Date only (YYYY-MM-DD) | **Medium** |
| Has "Approved By" column | Remove | **High** |
| Has "Justification" column | Remove | **High** |

---

## Interaction Design

### Rating a Song (Artist Page)

**Current:** `hx-prompt` browser dialog asking "Rate Song Name (0-5):" — clunky, breaks flow.

**Proposed:** Click-to-rate inline interaction:
1. User clicks a rating cell
2. A small popover appears with 6 coloured buttons (0-5), each with the rating colour
3. Clicking a button sets the rating and closes the popover
4. The cell immediately updates with the number and colour
5. Clicking outside closes without change
6. If cell already has a rating, clicking it opens the popover with current value highlighted

**Alternative (simpler):** Click cycles through 0→1→2→3→4→5→clear. Each click advances the rating and updates the colour. Simple, fast, no popover needed. Good for power users who rate many songs quickly.

### Navigating Between Artists

**Current:** Bottom navbar with HTMX — good. Keep this.

**Enhancement:** The spreadsheet uses tabs along the bottom. The bottom navbar should feel like spreadsheet tabs:
- Horizontal scroll
- Active artist highlighted/underlined
- Artist names coloured by gender
- Compact, tab-like styling

---

## Implementation Priority

### Phase 1: Foundation + Critical Visual Changes
1. Add 19 new colour columns to Theme model + update seed data for Classic and Dark
2. Create `app/constants.py` with rating key labels (text content, not colours)
3. Add `score_to_colour()` helper in `services/theme.py` for heat map interpolation
4. Add rating cell background colours to Artist page using theme CSS variables (the #1 most impactful visual change)
5. Add heat map colouring to STATS and STATS 2.0 pages

### Phase 2: Layout Alignment
6. Change unrated from "-" to blank on artist page
7. Remove track numbers from song names
8. Make album headers full-width table rows with themed `album_header_bg`
9. Add Key column to artist page and STATS page (cycling Standard/Stealth)
10. Simplify Changelog to 3 columns (Name, Desc, Date)
11. Add third column group to STATS 2.0 (rated count)
12. Set fixed column widths (350px song, 60-70px user, 140px key)

### Phase 3: Interaction Polish
13. Replace hx-prompt with click-to-rate popover or click-to-cycle
14. Add proper separator columns between Stats column groups
15. Number formatting (3 decimals on STATS, no % on STATS 2.0)

### Phase 4: Details
16. Add SGC (any%) row to STATS 2.0
17. Investigate and implement Log column
18. Locked user (🔒) indicator in headers
