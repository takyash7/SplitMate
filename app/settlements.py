from decimal import InvalidOperation
from flask import Blueprint, render_template, request, redirect, url_for, flash
from flask_login import login_required, current_user
from .extensions import db
from .models import Settlement
from .utils import require_group_member, money, log_activity, calculate_balances

bp = Blueprint("settlements", __name__)

@bp.route("/group/<int:group_id>", methods=["GET", "POST"])
@login_required
def group(group_id):
    group = require_group_member(group_id)
    if request.method == "POST":
        try:
            paid_to_id = int(request.form.get("paid_to_id"))
            amount = money(request.form.get("amount", "0"))
        except (ValueError, InvalidOperation):
            flash("Enter a valid settlement amount and recipient.", "danger")
            return redirect(url_for("settlements.group", group_id=group.id))
        member_ids = {m.id for m in group.members}
        if paid_to_id not in member_ids or paid_to_id == current_user.id or amount <= 0:
            flash("Choose another group member and a positive amount.", "danger")
        else:
            settlement = Settlement(group_id=group.id, paid_by_id=current_user.id,
                                    paid_to_id=paid_to_id, amount=amount,
                                    note=request.form.get("note", "").strip())
            db.session.add(settlement)
            log_activity(f"Recorded settlement of {amount} in {group.name}.", group.id)
            db.session.commit()
            flash("Settlement recorded.", "success")
        return redirect(url_for("settlements.group", group_id=group.id))
    balances = calculate_balances(group)
    return render_template("settlements/group.html", group=group, balances=balances)
