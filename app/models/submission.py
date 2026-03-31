from app.extensions import db


class Submission(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    submitted_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    submitted_at = db.Column(db.Text, nullable=False)
    status = db.Column(db.Text, nullable=False, default='pending')
    approved_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    approved_at = db.Column(db.Text)
    rejected_by_id = db.Column(db.Integer, db.ForeignKey('user.id', ondelete='SET NULL'))
    rejected_at = db.Column(db.Text)
    rejected_reason = db.Column(db.Text)

    submitted_by = db.relationship('User', foreign_keys=[submitted_by_id])
    approved_by = db.relationship('User', foreign_keys=[approved_by_id])
    rejected_by = db.relationship('User', foreign_keys=[rejected_by_id])
