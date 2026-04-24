from app.extensions import db


class Update(db.Model):
    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    commit_id = db.Column(db.Text, nullable=False, unique=True)
    description = db.Column(db.Text, nullable=False)
    date = db.Column(db.Text, nullable=False)
    type_id = db.Column(db.Integer, db.ForeignKey('update_type.id'))

    type = db.relationship('UpdateType')
