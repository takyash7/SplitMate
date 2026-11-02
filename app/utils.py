from decimal import Decimal, ROUND_HALF_UP
from flask import abort
from flask_login import current_user
from .models import Group, ActivityLog, group_members
from .extensions import db

CENT = Decimal("0.01")

def money(value):
    return Decimal(str(value)).quantize(CENT, rounding=ROUND_HALF_UP)


def require_group_member(group_id):
    group = db.session.get(Group, group_id)

    if not group:
        abort(404)

    membership = db.session.execute(
        db.select(group_members).where(
            group_members.c.group_id == group_id,
            group_members.c.user_id == current_user.id,
            group_members.c.is_active.is_(True)
        )
    ).first()

    if not membership:
        abort(404)

    return group


def require_group_access(group_id):
    group = db.session.get(Group, group_id)

    if not group:
        abort(404)

    membership = db.session.execute(
        db.select(group_members).where(
            group_members.c.group_id == group_id,
            group_members.c.user_id == current_user.id
        )
    ).first()

    if not membership:
        abort(404)

    return group



def log_activity(message, group_id=None):
    db.session.add(ActivityLog(user_id=current_user.id, group_id=group_id, message=message))

def calculate_balances(group):
    # Positive means the member should receive money; negative means they owe money.
    balances = {member.id: Decimal("0.00") for member in group.members}
    for expense in group.expenses:
        balances[expense.paid_by_id] += Decimal(expense.amount)
        for split in expense.splits:
            balances[split.user_id] -= Decimal(split.share_amount)
    for settlement in group.settlements:
        balances[settlement.paid_by_id] += Decimal(settlement.amount)
        balances[settlement.paid_to_id] -= Decimal(settlement.amount)
    return {uid: value.quantize(CENT) for uid, value in balances.items()}

def simplify_debts(group):
    balances = calculate_balances(group)
    people = {m.id: m.name for m in group.members}
    creditors = [[uid, value] for uid, value in balances.items() if value > 0]
    debtors = [[uid, -value] for uid, value in balances.items() if value < 0]
    creditors.sort(key=lambda x: x[1], reverse=True)
    debtors.sort(key=lambda x: x[1], reverse=True)
    result = []
    i = j = 0
    while i < len(debtors) and j < len(creditors):
        amount = min(debtors[i][1], creditors[j][1]).quantize(CENT)
        if amount > 0:
            result.append({"from_id": debtors[i][0], "from": people[debtors[i][0]],
                           "to_id": creditors[j][0], "to": people[creditors[j][0]],
                           "amount": amount})
        debtors[i][1] -= amount
        creditors[j][1] -= amount
        if debtors[i][1] == 0: i += 1
        if creditors[j][1] == 0: j += 1
    return result
