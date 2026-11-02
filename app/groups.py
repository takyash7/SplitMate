import os

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    jsonify,
)

from flask_login import login_required, current_user

from .extensions import db
from .models import (
    Group,
    User,
    Expense,
    ActivityLog,
    group_members,
)

from .utils import (
    require_group_member,
    require_group_access,
    log_activity,
    calculate_balances,
    simplify_debts,
)

from urllib.parse import quote, urlencode


bp = Blueprint("groups", __name__)


# --------------------------------------------------
# PHONE HELPERS
# --------------------------------------------------

def _normalize_phone(phone):
    """Keep digits only."""
    return "".join(
        ch for ch in str(phone or "")
        if ch.isdigit()
    )



def _get_membership_status(group_id, user_id):
    """Return True, False or None for membership status."""
    return db.session.execute(
        db.select(group_members.c.is_active).where(
            group_members.c.group_id == group_id,
            group_members.c.user_id == user_id,
        )
    ).scalar_one_or_none()


def _add_or_reactivate_member(group, user):
    """Add a new member or reactivate an existing member."""

    membership = _get_membership_status(group.id, user.id)

    if membership is True:
        return "already_active"

    if membership is False:

        db.session.execute(
            db.update(group_members)
            .where(
                group_members.c.group_id == group.id,
                group_members.c.user_id == user.id,
            )
            .values(is_active=True)
        )

        log_activity(
            f"{user.name} rejoined the group {group.name}.",
            group.id,
        )

        db.session.commit()

        return "reactivated"

    group.members.append(user)

    log_activity(
        f"Added {user.name} to {group.name}.",
        group.id,
    )

    db.session.commit()

    return "added"


# --------------------------------------------------
# GROUP INDEX
# --------------------------------------------------

@bp.route("/")
@login_required
def index():

    return render_template(
        "groups/index.html",
        groups=current_user.groups,
    )


# --------------------------------------------------
# CREATE GROUP
# --------------------------------------------------

@bp.route("/create", methods=["GET", "POST"])
@login_required
def create():

    if request.method == "POST":

        name = request.form.get("name", "").strip()

        group_type = request.form.get(
            "group_type",
            "Friends"
        )

        description = request.form.get(
            "description",
            ""
        ).strip()

        if not name or len(name) > 120:

            flash(
                "Please enter a valid group name.",
                "danger",
            )

        else:

            group = Group(
                name=name,
                group_type=group_type,
                description=description,
                created_by_id=current_user.id,
            )

            group.members.append(current_user)

            db.session.add(group)

            log_activity(
                f"Created group {name}.",
                None,
            )

            db.session.commit()

            flash(
                "Group created successfully.",
                "success",
            )

            return redirect(
                url_for(
                    "groups.detail",
                    group_id=group.id
                )
            )

    return render_template("groups/create.html")


# --------------------------------------------------
# GROUP DETAIL
# --------------------------------------------------

@bp.route("/<int:group_id>")
@login_required
def detail(group_id):

    group = require_group_access(group_id)

    membership_rows = db.session.execute(
        db.select(
            group_members.c.user_id,
            group_members.c.is_active,
        ).where(
            group_members.c.group_id == group_id
        )
    ).all()

    member_statuses = {
        user_id: bool(is_active)
        for user_id, is_active in membership_rows
    }

    is_active = member_statuses.get(current_user.id, False)

    balances = calculate_balances(group)
    suggestions = simplify_debts(group)


    for item in suggestions:
        print(
            "From ID:", item["from_id"],
        "| To ID:", item["to_id"],
            "| Current User:", current_user.id,
            "| Reminder URL Generated:", bool(item.get("reminder_mailto"))
        )
    
    print("====================================\n")
    

    # Prepare manual email reminders
    for item in suggestions:

        item["reminder_mailto"] = None

        # Only the person who should receive money can send a reminder.
        # Sender must also be an active group member.
        if is_active and item["to_id"] == current_user.id:

            debtor = db.session.get(User, item["from_id"])

            
            if debtor and debtor.email:

                subject = f"Payment Reminder - {group.name}"

                body = (
                    f"Hi {debtor.name},\n\n"
                    f"This is a friendly reminder about your pending "
                    f"payment in the group '{group.name}'.\n\n"
                    f"Pending Amount: Rs. {item['amount']:.2f}\n"
                    f"Payment Due To: {current_user.name}\n\n"
                    f"Please settle the amount when possible.\n\n"
                    f"Thanks,\n"
                    f"{current_user.name}"
                )

                query = urlencode({
                    "subject": subject,
                    "body": body
                }, quote_via=quote)

                recipient_email = quote(
                    debtor.email,
                    safe="@.+-_"
                )

                item["reminder_mailto"] = (
                    f"https://mail.google.com/mail/?view=cm&fs=1"
                    f"&to={recipient_email}&{query}"
             )

    return render_template(
        "groups/detail.html",
        group=group,
        balances=balances,
        suggestions=suggestions,
        is_active=is_active,
        member_statuses=member_statuses,
    )


# --------------------------------------------------
# ADD MEMBER USING EMAIL
# --------------------------------------------------

@bp.post("/<int:group_id>/members")
@login_required
def add_member(group_id):

    group = require_group_member(group_id)

    email = request.form.get(
        "email",
        ""
    ).strip().lower()

    user = User.query.filter_by(
        email=email
    ).first()

    if not user:

        flash(
            "No registered user found with that email. Ask them to register first.",
            "warning",
        )

    else:

        result = _add_or_reactivate_member(
            group,
            user
        )

        if result == "already_active":

            flash(
                "That user is already an active member.",
                "info",
            )

        elif result == "reactivated":

            flash(
                f"{user.name} has rejoined the group.",
                "success",
            )

        else:

            flash(
                f"{user.name} added to the group.",
                "success",
            )

    return redirect(
        url_for(
            "groups.detail",
            group_id=group.id
        )
    )


# --------------------------------------------------
# LEAVE GROUP
# --------------------------------------------------

@bp.post("/<int:group_id>/leave")
@login_required
def leave_group(group_id):

    group = require_group_member(group_id)

    if group.created_by_id == current_user.id:

        flash(
            "The group creator cannot leave the group.",
            "warning",
        )

        return redirect(
            url_for(
                "groups.detail",
                group_id=group.id
            )
        )

    choice = request.form.get("choice")

    if choice not in [
        "delete_entries",
        "keep_entries"
    ]:

        flash(
            "Invalid leave option.",
            "danger",
        )

        return redirect(
            url_for(
                "groups.detail",
                group_id=group.id
            )
        )

    expenses_to_delete = []

    receipt_filenames = []

    if choice == "delete_entries":

        expenses_to_delete = Expense.query.filter_by(
            group_id=group.id,
            created_by_id=current_user.id,
        ).all()

        receipt_filenames = [
            expense.receipt_filename
            for expense in expenses_to_delete
            if expense.receipt_filename
        ]

        for expense in expenses_to_delete:

            db.session.delete(expense)

    db.session.execute(
        db.update(group_members)
        .where(
            group_members.c.group_id == group.id,
            group_members.c.user_id == current_user.id,
        )
        .values(is_active=False)
    )

    log_activity(
        f"{current_user.name} left the group {group.name}.",
        group.id,
    )

    try:

        db.session.commit()

        if choice == "delete_entries":

            upload_folder = current_app.config.get(
                "RECEIPT_UPLOAD_FOLDER"
            )

            if upload_folder:

                for filename in receipt_filenames:

                    if os.path.basename(filename) != filename:
                        continue

                    file_path = os.path.join(
                        upload_folder,
                        filename,
                    )

                    if os.path.isfile(file_path):

                        try:
                            os.remove(file_path)

                        except OSError:

                            current_app.logger.exception(
                                "Could not delete receipt file"
                            )

        flash(
            "You have left the group successfully.",
            "success",
        )

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Leave group failed"
        )

        flash(
            "Could not leave the group. Please try again.",
            "danger",
        )

        return redirect(
            url_for(
                "groups.detail",
                group_id=group.id
            )
        )

    return redirect(
        url_for("groups.index")
    )


# --------------------------------------------------
# DELETE GROUP
# --------------------------------------------------

@bp.post("/<int:group_id>/delete")
@login_required
def delete_group(group_id):

    group = Group.query.get_or_404(group_id)

    # Only the group creator can delete the group.
    if group.created_by_id != current_user.id:

        flash(
            "Only the group creator can delete this group.",
            "danger",
        )

        return redirect(
            url_for("groups.index")
        )

    # Collect receipt filenames before deleting expenses.
    receipt_filenames = [
        expense.receipt_filename
        for expense in group.expenses
        if expense.receipt_filename
    ]

    try:

        # Delete group-specific activity logs.
        ActivityLog.query.filter_by(
            group_id=group.id
        ).delete(synchronize_session=False)

        # Delete group membership records.
        db.session.execute(
            db.delete(group_members).where(
                group_members.c.group_id == group.id
            )
        )

        # Group relationships already have cascade delete.
        # This deletes expenses, expense splits and settlements.
        db.session.delete(group)

        db.session.commit()

        # Delete receipt files after successful database commit.
        upload_folder = current_app.config.get(
            "RECEIPT_UPLOAD_FOLDER"
        )

        if upload_folder:

            for filename in receipt_filenames:

                # Prevent path traversal.
                if os.path.basename(filename) != filename:
                    continue

                file_path = os.path.join(
                    upload_folder,
                    filename
                )

                if os.path.isfile(file_path):

                    try:

                        os.remove(file_path)

                    except OSError:

                        current_app.logger.exception(
                            "Could not delete group receipt: %s",
                            filename,
                        )

        flash(
            "Group and all its associated data have been deleted successfully.",
            "success",
        )

        return redirect(
            url_for("groups.index")
        )

    except Exception:

        db.session.rollback()

        current_app.logger.exception(
            "Group deletion failed"
        )

        flash(
            "Could not delete the group. Please try again.",
            "danger",
        )

        return redirect(
            url_for(
                "groups.detail",
                group_id=group.id
            )
        )