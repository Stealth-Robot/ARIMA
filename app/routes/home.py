from flask import Blueprint
from flask_login import login_required

home_bp = Blueprint('home', __name__)


@home_bp.route('/')
@login_required
def home():
    return 'Home page placeholder', 200
