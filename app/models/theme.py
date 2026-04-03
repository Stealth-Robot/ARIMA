from app.extensions import db


class Theme(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))

    # UI chrome colours (existing 17)
    bg_primary = db.Column(db.Text)
    bg_secondary = db.Column(db.Text)
    text_primary = db.Column(db.Text)
    text_secondary = db.Column(db.Text)
    navbar_bg = db.Column(db.Text)
    navbar_text = db.Column(db.Text)
    header_row = db.Column(db.Text)
    promoted_song = db.Column(db.Text)
    gender_female = db.Column(db.Text)
    gender_male = db.Column(db.Text)
    gender_mixed = db.Column(db.Text)
    gender_anime = db.Column(db.Text)
    album_name = db.Column(db.Text)
    link = db.Column(db.Text)
    button_primary = db.Column(db.Text)
    button_secondary = db.Column(db.Text)
    border = db.Column(db.Text)

    # Rating cell backgrounds (6)
    rating_5_bg = db.Column(db.Text)
    rating_4_bg = db.Column(db.Text)
    rating_3_bg = db.Column(db.Text)
    rating_2_bg = db.Column(db.Text)
    rating_1_bg = db.Column(db.Text)
    rating_0_bg = db.Column(db.Text)

    # Rating text colours (6) — per-score text for readability
    rating_5_text = db.Column(db.Text)
    rating_4_text = db.Column(db.Text)
    rating_3_text = db.Column(db.Text)
    rating_2_text = db.Column(db.Text)
    rating_1_text = db.Column(db.Text)
    rating_0_text = db.Column(db.Text)

    # Heat map anchors — average scores (3)
    heatmap_high = db.Column(db.Text)
    heatmap_mid = db.Column(db.Text)
    heatmap_low = db.Column(db.Text)

    # Completion heat map anchors — percentages (3)
    pct_high = db.Column(db.Text)
    pct_mid = db.Column(db.Text)
    pct_low = db.Column(db.Text)

    # Structural colours (5)
    album_header_bg = db.Column(db.Text)
    row_alternate = db.Column(db.Text)
    grid_line = db.Column(db.Text)
    key_bg_standard = db.Column(db.Text)
    key_bg_stealth = db.Column(db.Text)
    header_user_bg = db.Column(db.Text)

    # Artist navbar
    artist_button_text = db.Column(db.Text)

    # Top navbar active indicator
    navbar_active = db.Column(db.Text)

    # Songs remaining to rate colours
    unrated_0_bg = db.Column(db.Text)
    unrated_low_bg = db.Column(db.Text)
    unrated_mid_bg = db.Column(db.Text)
    unrated_high_bg = db.Column(db.Text)
    unrated_text = db.Column(db.Text)

    # Search overlay section headers
    search_section_bg = db.Column(db.Text)
    search_section_text = db.Column(db.Text)

    # Action button colours
    delete_button = db.Column(db.Text)
    edit_on_button = db.Column(db.Text)
    edit_off_button = db.Column(db.Text)
    button_text = db.Column(db.Text)

    # Discography header
    discography_background = db.Column(db.Text)
    discography_text = db.Column(db.Text)

    owner = db.relationship('User', foreign_keys=[user_id])
