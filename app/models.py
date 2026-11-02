from datetime import datetime
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash
from .extensions import db, login_manager


group_members = db.Table(
    "group_members",
    db.Column("group_id", db.Integer, db.ForeignKey("groups.id"), primary_key=True),
    db.Column("user_id", db.Integer, db.ForeignKey("users.id"), primary_key=True),
    db.Column("joined_at", db.DateTime, default=datetime.utcnow, nullable=False),
    db.Column("is_active", db.Boolean, default=True, nullable=False),
)


class User(UserMixin, db.Model):
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    email = db.Column(db.String(160), unique=True, nullable=False, index=True)

    # Stored as digits only, including country code.
    phone_number = db.Column(
        db.String(15),
        unique=True,
        nullable=True,
        index=True
    )

    password_hash = db.Column(db.String(255), nullable=False)
    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    groups = db.relationship(
        "Group",
        secondary=group_members,
        back_populates="members"
    )

    expenses_paid = db.relationship(
        "Expense",
        back_populates="payer",
        foreign_keys="Expense.paid_by_id"
    )

    expenses_created = db.relationship(
        "Expense",
        back_populates="creator",
        foreign_keys="Expense.created_by_id"
    )

    splits = db.relationship("ExpenseSplit", back_populates="user")

    settlements_sent = db.relationship(
        "Settlement",
        back_populates="payer",
        foreign_keys="Settlement.paid_by_id"
    )

    settlements_received = db.relationship(
        "Settlement",
        back_populates="payee",
        foreign_keys="Settlement.paid_to_id"
    )

    password_reset_otps = db.relationship(
        "PasswordResetOTP",
        back_populates="user",
        cascade="all, delete-orphan"
    )

    def set_password(self, password):
        self.password_hash = generate_password_hash(password)

    def check_password(self, password):
        return check_password_hash(self.password_hash, password)

    def __repr__(self):
        return f"<User {self.email}>"


class PasswordResetOTP(db.Model):
    __tablename__ = "password_reset_otps"

    id = db.Column(db.Integer, primary_key=True)

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    # Store hashed OTP, never plain OTP.
    otp_hash = db.Column(db.String(255), nullable=False)

    expires_at = db.Column(db.DateTime, nullable=False)

    attempts = db.Column(
        db.Integer,
        default=0,
        server_default="0",
        nullable=False
    )

    used_at = db.Column(db.DateTime, nullable=True)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        server_default=db.func.current_timestamp(),
        nullable=False
    )

    user = db.relationship(
        "User",
        back_populates="password_reset_otps"
    )


class Group(db.Model):
    __tablename__ = "groups"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    group_type = db.Column(db.String(30), default="Friends", nullable=False)
    description = db.Column(db.String(500))

    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    creator = db.relationship("User", foreign_keys=[created_by_id])

    members = db.relationship(
        "User",
        secondary=group_members,
        back_populates="groups"
    )

    expenses = db.relationship(
        "Expense",
        back_populates="group",
        cascade="all, delete-orphan"
    )

    settlements = db.relationship(
        "Settlement",
        back_populates="group",
        cascade="all, delete-orphan"
    )


class Expense(db.Model):
    __tablename__ = "expenses"

    id = db.Column(db.Integer, primary_key=True)

    group_id = db.Column(
        db.Integer,
        db.ForeignKey("groups.id"),
        nullable=False,
        index=True
    )

    paid_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    created_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=True,
        index=True
    )

    title = db.Column(db.String(160), nullable=False)
    amount = db.Column(db.Numeric(12, 2), nullable=False)
    category = db.Column(db.String(50), default="Other", nullable=False)
    notes = db.Column(db.String(500))
    split_type = db.Column(db.String(20), default="equal", nullable=False)

    receipt_filename = db.Column(db.String(255), nullable=True)
    receipt_original_name = db.Column(db.String(255), nullable=True)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False,
        index=True
    )

    group = db.relationship("Group", back_populates="expenses")

    payer = db.relationship(
        "User",
        back_populates="expenses_paid",
        foreign_keys=[paid_by_id]
    )

    creator = db.relationship(
        "User",
        back_populates="expenses_created",
        foreign_keys=[created_by_id]
    )

    splits = db.relationship(
        "ExpenseSplit",
        back_populates="expense",
        cascade="all, delete-orphan"
    )


class ExpenseSplit(db.Model):
    __tablename__ = "expense_splits"

    id = db.Column(db.Integer, primary_key=True)

    expense_id = db.Column(
        db.Integer,
        db.ForeignKey("expenses.id"),
        nullable=False,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False,
        index=True
    )

    share_amount = db.Column(db.Numeric(12, 2), nullable=False)

    expense = db.relationship("Expense", back_populates="splits")
    user = db.relationship("User", back_populates="splits")

    __table_args__ = (
        db.UniqueConstraint(
            "expense_id",
            "user_id",
            name="uq_expense_split_user"
        ),
    )


class Settlement(db.Model):
    __tablename__ = "settlements"

    id = db.Column(db.Integer, primary_key=True)

    group_id = db.Column(
        db.Integer,
        db.ForeignKey("groups.id"),
        nullable=False,
        index=True
    )

    paid_by_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    paid_to_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    amount = db.Column(db.Numeric(12, 2), nullable=False)
    note = db.Column(db.String(300))

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    group = db.relationship("Group", back_populates="settlements")

    payer = db.relationship(
        "User",
        back_populates="settlements_sent",
        foreign_keys=[paid_by_id]
    )

    payee = db.relationship(
        "User",
        back_populates="settlements_received",
        foreign_keys=[paid_to_id]
    )


class ActivityLog(db.Model):
    __tablename__ = "activity_logs"

    id = db.Column(db.Integer, primary_key=True)

    group_id = db.Column(
        db.Integer,
        db.ForeignKey("groups.id"),
        nullable=True,
        index=True
    )

    user_id = db.Column(
        db.Integer,
        db.ForeignKey("users.id"),
        nullable=False
    )

    message = db.Column(db.String(300), nullable=False)

    created_at = db.Column(
        db.DateTime,
        default=datetime.utcnow,
        nullable=False
    )

    user = db.relationship("User")


@login_manager.user_loader
def load_user(user_id):
    try:
        return db.session.get(User, int(user_id))
    except (TypeError, ValueError):
        return None