from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import traceback
import os
import uuid

from flask import (
    Blueprint,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    current_app,
    send_from_directory,
    abort
)

from flask_login import login_required, current_user
from werkzeug.utils import secure_filename

from .extensions import db
from .models import Expense, ExpenseSplit, group_members
from .utils import (
    money,
    require_group_member,
    require_group_access,
    log_activity,
)


bp = Blueprint("expenses", __name__)

ALLOWED_EXTENSIONS = {
    "jpg",
    "jpeg",
    "png",
    "webp",
    "pdf"
}


# ==========================================
# VALIDATE RECEIPT
# ==========================================

def validate_receipt(file):

    if not file or not file.filename:
        return None

    original_name = secure_filename(file.filename)

    if not original_name:
        raise ValueError("Invalid bill filename.")

    extension = original_name.rsplit(".", 1)[-1].lower()

    if extension not in ALLOWED_EXTENSIONS:
        raise ValueError(
            "Only JPG, JPEG, PNG, WEBP and PDF files are allowed."
        )

    # Check actual file content
    header = file.stream.read(12)
    file.stream.seek(0)

    valid = False

    if extension in {"jpg", "jpeg"}:
        valid = header.startswith(b"\xff\xd8\xff")

    elif extension == "png":
        valid = header.startswith(b"\x89PNG\r\n\x1a\n")

    elif extension == "webp":
        valid = (
            len(header) >= 12
            and header[:4] == b"RIFF"
            and header[8:12] == b"WEBP"
        )

    elif extension == "pdf":
        valid = header.startswith(b"%PDF-")

    if not valid:
        raise ValueError(
            "Uploaded file is not a valid image or PDF."
        )

    return {
        "file": file,
        "original_name": original_name,
        "extension": extension
    }


# ==========================================
# ADD EXPENSE
# ==========================================

@bp.route("/group/<int:group_id>/add", methods=["GET", "POST"])
@login_required
def add(group_id):

    print("\n========== EXPENSE ROUTE HIT ==========")
    print("METHOD:", request.method)
    print("GROUP ID:", group_id)
    print("USER ID:", current_user.id)

    group = require_group_member(group_id)

    # Only currently active members can be selected for new expenses.
    active_member_ids = set(
        db.session.execute(
            db.select(group_members.c.user_id).where(
                group_members.c.group_id == group.id,
                group_members.c.is_active.is_(True)
            )
        ).scalars().all()
    )
    active_members = [
        member for member in group.members
        if member.id in active_member_ids
    ]

    if request.method == "GET":
        return render_template(
            "expenses/add.html",
            group=group,
            active_members=active_members
        )

    saved_receipt_path = None

    try:

        # --------------------------------
        # 1. GET FORM DATA
        # --------------------------------

        print("\n========== FORM DATA ==========")
        print(request.form.to_dict(flat=False))

        title = request.form.get("title", "").strip()
        category = request.form.get("category", "Other")
        notes = request.form.get("notes", "").strip()
        split_type = request.form.get("split_type", "equal")

        amount = money(request.form.get("amount", "0"))

        paid_by_id = int(request.form.get("paid_by_id"))

        participant_ids = list(
            dict.fromkeys(
                int(uid)
                for uid in request.form.getlist("participants")
            )
        )

        # --------------------------------
        # 2. VALIDATION
        # --------------------------------

        # Validate payer and participants against active members only.
        member_ids = active_member_ids

        if not title:
            raise ValueError("Expense name is required.")

        if amount <= 0:
            raise ValueError("Amount must be greater than zero.")

        if paid_by_id not in member_ids:
            raise ValueError("Invalid payer selected.")

        if not participant_ids:
            raise ValueError("Select at least one participant.")

        if not set(participant_ids).issubset(member_ids):
            raise ValueError("Invalid participant selected.")

        # --------------------------------
        # 3. VALIDATE RECEIPT
        # --------------------------------

        receipt = validate_receipt(
            request.files.get("receipt")
        )

        # --------------------------------
        # 4. CALCULATE SPLITS
        # --------------------------------

        shares = {}

        if split_type == "equal":

            base = (
                amount / len(participant_ids)
            ).quantize(
                Decimal("0.01"),
                rounding=ROUND_HALF_UP
            )

            remaining = amount

            for uid in participant_ids[:-1]:
                shares[uid] = base
                remaining -= base

            shares[participant_ids[-1]] = remaining

        elif split_type == "exact":

            for uid in participant_ids:

                shares[uid] = money(
                    request.form.get(
                        f"share_{uid}", "0"
                    )
                )

            if any(value < 0 for value in shares.values()):
                raise ValueError("Amounts cannot be negative.")

            if sum(
                shares.values(),
                Decimal("0.00")
            ) != amount:

                raise ValueError(
                    "Exact amounts must equal total expense."
                )

        elif split_type == "percentage":

            percentages = {
                uid: Decimal(
                    request.form.get(
                        f"share_{uid}", "0"
                    )
                )
                for uid in participant_ids
            }

            if any(value < 0 for value in percentages.values()):
                raise ValueError("Percentages cannot be negative.")

            if sum(percentages.values()) != Decimal("100"):
                raise ValueError(
                    "Total percentage must equal 100."
                )

            remaining = amount

            for uid in participant_ids[:-1]:

                shares[uid] = money(
                    amount * percentages[uid] / Decimal("100")
                )

                remaining -= shares[uid]

            shares[participant_ids[-1]] = remaining

        elif split_type == "shares":

            weights = {
                uid: Decimal(
                    request.form.get(
                        f"share_{uid}", "0"
                    )
                )
                for uid in participant_ids
            }

            total_weight = sum(weights.values())

            if total_weight <= 0 or any(
                value < 0 for value in weights.values()
            ):
                raise ValueError("Invalid share weights.")

            remaining = amount

            for uid in participant_ids[:-1]:

                shares[uid] = money(
                    amount * weights[uid] / total_weight
                )

                remaining -= shares[uid]

            shares[participant_ids[-1]] = remaining

        else:
            raise ValueError("Invalid split method.")

        # --------------------------------
        # 5. VERIFY SPLIT TOTAL
        # --------------------------------

        if sum(
            shares.values(),
            Decimal("0.00")
        ) != amount:

            raise ValueError(
                "Split amounts do not match total expense."
            )

        print("\n========== CALCULATED SHARES ==========")
        print(shares)

        # --------------------------------
        # 6. CREATE EXPENSE
        # --------------------------------

        expense = Expense(
            group_id=group.id,

            # Who paid the money
            paid_by_id=paid_by_id,

            # Who actually created the expense
            created_by_id=current_user.id,

            title=title,
            amount=amount,
            category=category,
            notes=notes,
            split_type=split_type
        )

        db.session.add(expense)
        db.session.flush()

        print("EXPENSE CREATED. ID:", expense.id)
        print("CREATED BY USER:", current_user.id)

        # --------------------------------
        # 7. SAVE RECEIPT FILE
        # --------------------------------

        if receipt:

            upload_folder = current_app.config[
                "RECEIPT_UPLOAD_FOLDER"
            ]

            os.makedirs(
                upload_folder,
                exist_ok=True
            )

            generated_filename = (
                f"{uuid.uuid4().hex}.{receipt['extension']}"
            )

            saved_receipt_path = os.path.join(
                upload_folder,
                generated_filename
            )

            receipt["file"].save(saved_receipt_path)

            expense.receipt_filename = generated_filename
            expense.receipt_original_name = receipt["original_name"]

            print("RECEIPT SAVED:", generated_filename)

        # --------------------------------
        # 8. SAVE EXPENSE SPLITS
        # --------------------------------

        for uid, share in shares.items():

            split = ExpenseSplit(
                expense_id=expense.id,
                user_id=uid,
                share_amount=share
            )

            db.session.add(split)

        print("EXPENSE SPLITS ADDED")

        # --------------------------------
        # 9. ACTIVITY LOG
        # --------------------------------

        log_activity(
            f"Added expense '{title}' ({amount}) to {group.name}.",
            group.id
        )

        # --------------------------------
        # 10. DATABASE COMMIT
        # --------------------------------

        print("\n========== BEFORE DATABASE COMMIT ==========")

        db.session.commit()

        print("DATABASE COMMIT SUCCESSFUL")

        # --------------------------------
        # 11. SUCCESS RESPONSE
        # --------------------------------

        flash(
            "Expense added successfully!",
            "success"
        )

        return redirect(
            url_for(
                "groups.detail",
                group_id=group.id
            )
        )

    except (
        ValueError,
        InvalidOperation,
        ArithmeticError
    ) as error:

        db.session.rollback()

        if saved_receipt_path and os.path.exists(saved_receipt_path):
            os.remove(saved_receipt_path)

        print("\n========== VALIDATION ERROR ==========")
        print(type(error).__name__)
        print(str(error))

        flash(str(error), "danger")

        return render_template(
            "expenses/add.html",
            group=group,
            active_members=active_members
        )

    except Exception as error:

        db.session.rollback()

        if saved_receipt_path and os.path.exists(saved_receipt_path):
            os.remove(saved_receipt_path)

        print("\n========== EXPENSE DATABASE ERROR ==========")
        print("ERROR TYPE:", type(error).__name__)
        print("ERROR MESSAGE:", str(error))

        traceback.print_exc()

        current_app.logger.exception(
            "Expense creation failed"
        )

        flash(
            f"Expense could not be saved: {str(error)}",
            "danger"
        )

        return render_template(
            "expenses/add.html",
            group=group,
            active_members=active_members
        )


# ==========================================
# VIEW / DOWNLOAD EXPENSE RECEIPT
# ==========================================

@bp.route("/<int:expense_id>/receipt")
@login_required
def view_receipt(expense_id):

    expense = db.session.get(Expense, expense_id)

    if not expense:
        abort(404)

    # Active and inactive members can view historical receipts.
    require_group_access(expense.group_id)

    if not expense.receipt_filename:
        abort(404)

    upload_folder = current_app.config[
        "RECEIPT_UPLOAD_FOLDER"
    ]

    extension = expense.receipt_filename.rsplit(".", 1)[-1].lower()

    mimetypes = {
        "jpg": "image/jpeg",
        "jpeg": "image/jpeg",
        "png": "image/png",
        "webp": "image/webp",
        "pdf": "application/pdf"
    }

    return send_from_directory(
        upload_folder,
        expense.receipt_filename,
        mimetype=mimetypes.get(extension),
        as_attachment=False,
        download_name=expense.receipt_original_name
    )


# ==========================================
# DELETE EXPENSE
# ==========================================

@bp.route("/<int:expense_id>/delete", methods=["POST"])
@login_required
def delete(expense_id):

    expense = db.session.get(Expense, expense_id)

    if not expense:
        abort(404)

    # Check group membership
    group = require_group_member(expense.group_id)

    # Only actual expense creator can delete
    if expense.created_by_id != current_user.id:
        abort(403)

    # Store details before deletion
    expense_title = expense.title
    expense_amount = expense.amount
    group_id = group.id
    group_name = group.name
    receipt_filename = expense.receipt_filename

    try:

        # Activity log
        log_activity(
            f"Deleted expense '{expense_title}' "
            f"({expense_amount}) from {group_name}.",
            group_id
        )

        # Delete expense
        # ExpenseSplit records are deleted automatically
        db.session.delete(expense)

        db.session.commit()

        # Delete attached receipt after DB commit
        if receipt_filename:

            upload_folder = current_app.config[
                "RECEIPT_UPLOAD_FOLDER"
            ]

            safe_filename = os.path.basename(receipt_filename)

            if safe_filename == receipt_filename:

                receipt_path = os.path.join(
                    upload_folder,
                    safe_filename
                )

                if os.path.isfile(receipt_path):

                    try:
                        os.remove(receipt_path)

                    except OSError:
                        current_app.logger.exception(
                            "Could not delete expense receipt file"
                        )

        flash(
            "Expense deleted successfully!",
            "success"
        )

    except Exception as error:

        db.session.rollback()

        current_app.logger.exception(
            "Expense deletion failed"
        )

        flash(
            f"Expense could not be deleted: {str(error)}",
            "danger"
        )

    return redirect(
        url_for(
            "groups.detail",
            group_id=group_id
        )
    )

# ==========================================

# DELETE EXPENSE RECEIPT / BILL

# ==========================================

# ==========================================
# DELETE EXPENSE RECEIPT / BILL
# ==========================================

@bp.route("/<int:expense_id>/receipt/delete", methods=["POST"])
@login_required
def delete_receipt(expense_id):

    expense = db.session.get(Expense, expense_id)

    if not expense:
        abort(404)

    group = require_group_member(expense.group_id)

    # Only expense creator can delete the bill
    if expense.created_by_id != current_user.id:
        abort(403)

    if not expense.receipt_filename:
        flash("No bill is attached to this expense.", "warning")
        return redirect(
            url_for("groups.detail", group_id=group.id)
        )

    receipt_filename = expense.receipt_filename
    group_id = group.id

    try:

        # Remove bill details from database
        expense.receipt_filename = None
        expense.receipt_original_name = None

        log_activity(
            f"Deleted bill attached to expense '{expense.title}'.",
            group_id
        )

        db.session.commit()

        # Delete physical file
        upload_folder = current_app.config[
            "RECEIPT_UPLOAD_FOLDER"
        ]

        safe_filename = os.path.basename(receipt_filename)

        if safe_filename == receipt_filename:

            receipt_path = os.path.join(
                upload_folder,
                safe_filename
            )

            if os.path.isfile(receipt_path):
                try:
                    os.remove(receipt_path)

                except OSError:
                    current_app.logger.exception(
                        "Could not delete receipt file"
                    )

        flash("Bill deleted successfully!", "success")

    except Exception as error:

        db.session.rollback()

        current_app.logger.exception(
            "Bill deletion failed"
        )

        flash(
            f"Bill could not be deleted: {str(error)}",
            "danger"
        )

    return redirect(
        url_for(
            "groups.detail",
            group_id=group_id
        )
    )


