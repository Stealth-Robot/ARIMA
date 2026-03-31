"""Application constants — text content, not colours (colours are in Theme table)."""

RATING_KEY_STANDARD = {
    5: 'Fucking banger',
    4: 'Great song',
    3: 'A vibe',
    2: 'Eh / Mid / No opinion',
    1: "This isn't great",
    0: 'Absolute shit',
}

RATING_KEY_STEALTH = {
    5: 'Fucking banger',
    4: 'Bit of a Bop',
    3: 'Decent/Lacking Pop',
    2: 'Mid / kinda bad',
    1: 'Bad',
    0: 'I feel Offended',
}

# Scores where text should be light (white) on the dark background
RATING_DARK_BG_SCORES = {0, 1, 5}
