from app.extensions import db


class Theme(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.Text)
    user_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))

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
    album_name = db.Column(db.Text)
    pending_item = db.Column(db.Text)
    link = db.Column(db.Text)
    button_primary = db.Column(db.Text)
    button_secondary = db.Column(db.Text)
    border = db.Column(db.Text)

    owner = db.relationship('User', foreign_keys=[user_id])
