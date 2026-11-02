from flask import Blueprint, render_template
from flask_login import login_required, current_user
from .models import Group, ActivityLog
from .utils import calculate_balances

bp = Blueprint("main", __name__)

@bp.route("/")
def home():
    return render_template("home.html")

@bp.route("/dashboard")
@login_required
def dashboard():
    groups = current_user.groups
    group_cards = []
    total_owed = 0
    total_owing = 0
    for group in groups:
        balances = calculate_balances(group)
        balance = balances.get(current_user.id, 0)
        total_owed += max(balance, 0)
        total_owing += max(-balance, 0)
        group_cards.append({"group": group, "balance": balance, "members": len(group.members),
                            "expenses": len(group.expenses)})
    activities = ActivityLog.query.filter_by(user_id=current_user.id).order_by(ActivityLog.created_at.desc()).limit(10).all()
    return render_template("dashboard.html", group_cards=group_cards, total_owed=total_owed,
                           total_owing=total_owing, activities=activities)
