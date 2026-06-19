from app.extensions import db


class Rules(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    content = db.Column(db.Text, nullable=False)
    last_edited_by = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    last_edited_at = db.Column(db.Text)
    misc_owner_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    misc_maintainer_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    misc_image_url = db.Column(db.Text)

    editor = db.relationship('User', foreign_keys=[last_edited_by])
    misc_owner = db.relationship('User', foreign_keys=[misc_owner_id])
    misc_maintainer = db.relationship('User', foreign_keys=[misc_maintainer_id])
