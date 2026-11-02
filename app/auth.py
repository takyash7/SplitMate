
import secrets
import smtplib
from datetime import datetime, timedelta
from email.message import EmailMessage

from flask import (
    Blueprint,
    render_template,
    redirect,
    url_for,
    flash,
    request,
    current_app,
    session
)

from flask_login import (
    login_user,
    logout_user,
    current_user,
    login_required
)

from email_validator import validate_email, EmailNotValidError
from sqlalchemy import or_

from werkzeug.security import generate_password_hash, check_password_hash

from .extensions import db
from .models import User, PasswordResetOTP


bp = Blueprint("auth", __name__)


# --------------------------------------------------
# HELPER FUNCTIONS
# --------------------------------------------------

def _normalize_phone(phone):
    return "".join(ch for ch in phone if ch.isdigit())


def _find_user_by_identifier(identifier):

    identifier = identifier.strip()

    if "@" in identifier:
        return User.query.filter_by(
            email=identifier.lower()
        ).first()



def _send_reset_email(user, otp):

    config = current_app.config

    mail_username = config.get("MAIL_USERNAME")
    mail_password = config.get("MAIL_PASSWORD")
    mail_sender = config.get("MAIL_DEFAULT_SENDER")

    print("========== MAIL CONFIG DEBUG ==========")
    print("MAIL_USERNAME:", repr(mail_username))
    print("MAIL_PASSWORD loaded:", bool(mail_password))
    print("MAIL_DEFAULT_SENDER:", repr(mail_sender))
    print("=======================================")

    if not mail_username or not mail_password or not mail_sender:
        raise RuntimeError("Email configuration is incomplete.")

    message = EmailMessage()

    message["Subject"] = "SplitMate Password Reset OTP"
    message["From"] = mail_sender
    message["To"] = user.email

    message.set_content(
        f"""
Hello {user.name},

We received a request to reset your SplitMate password.

Your password reset OTP is:

{otp}

This OTP is valid for 5 minutes.

Do not share this OTP with anyone.

If you did not request this password reset, please ignore this email.

Regards,
SplitMate Team
"""
    )

    timeout = config.get("MAIL_TIMEOUT", 15)

    with smtplib.SMTP(
        config["MAIL_SERVER"],
        config["MAIL_PORT"],
        timeout=timeout
    ) as server:

        if config.get("MAIL_USE_TLS", True):
            server.starttls()

        server.login(mail_username, mail_password)

        server.send_message(message)


def _clear_reset_session():

    session.pop("password_reset_otp_id", None)
    session.pop("password_reset_verified_id", None)


# --------------------------------------------------
# REGISTER
# --------------------------------------------------

@bp.route("/register", methods=["GET", "POST"])
def register():

    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":

        name = request.form.get("name", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")

       

        if not name or len(name) > 100:

            flash("Please enter a valid name.", "danger")

    
        elif len(password) < 8:

            flash(
                "Password must contain at least 8 characters.",
                "danger"
            )

        else:

            try:
                email = validate_email(
                    email,
                    check_deliverability=False
                ).normalized

            except EmailNotValidError:

                flash("Please enter a valid email address.", "danger")

            else:

                existing_email = User.query.filter_by(
                    email=email
                ).first()

                existing_phone = None


                if existing_email:

                    flash(
                        "An account with this email already exists.",
                        "warning"
                    )

                elif existing_phone:

                    flash(
                        "This phone number is already linked to another account.",
                        "warning"
                    )

                else:

                    user = User(
                        name=name,
                        email=email,
                      
                    )

                    user.set_password(password)

                    db.session.add(user)
                    db.session.commit()

                    login_user(user)

                    flash("Welcome to SplitMate!", "success")

                    return redirect(url_for("main.dashboard"))

    return render_template("auth/register.html")


# --------------------------------------------------
# LOGIN
# --------------------------------------------------

@bp.route("/login", methods=["GET", "POST"])
def login():

    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":

        identifier = (
            request.form.get("identifier")
            or request.form.get("email")
            or ""
        ).strip()

        password = request.form.get("password", "")

        user = _find_user_by_identifier(identifier)

        if user and user.check_password(password):

            login_user(
                user,
                remember=bool(request.form.get("remember"))
            )

            return redirect(
                request.args.get("next")
                or url_for("main.dashboard")
            )

        flash(
            "Invalid email/phone number or password.",
            "danger"
        )

    return render_template("auth/login.html")


# --------------------------------------------------
# FORGOT PASSWORD - SEND OTP
#--------------------------------------------------


@bp.route("/forgot-password", methods=["GET", "POST"])
def forgot_password():

    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    if request.method == "POST":

        email = request.form.get("email", "").strip().lower()

        try:
            email = validate_email(
                email,
                check_deliverability=False
            ).normalized

        except EmailNotValidError:

            flash(
                "If an account exists with this email, an OTP will be sent.",
                "info"
            )

            return redirect(url_for("auth.forgot_password"))

        user = User.query.filter_by(email=email).first()

        _clear_reset_session()

        if user:

            now = datetime.utcnow()

            window_minutes = current_app.config.get(
                "OTP_RESEND_WINDOW_MINUTES", 5
            )

            resend_limit = current_app.config.get(
                "OTP_RESEND_LIMIT", 5
            )

            # Count only successfully delivered OTP records.
            recent_requests = PasswordResetOTP.query.filter(
                PasswordResetOTP.user_id == user.id,
                PasswordResetOTP.created_at >= (
                    now - timedelta(minutes=window_minutes)
                )
            ).count()

            if recent_requests >= resend_limit:

                flash(
                    "Too many OTP requests. Please try again later.",
                    "warning"
                )

                return redirect(url_for("auth.forgot_password"))

            # Generate OTP
            otp = "".join(
                str(secrets.randbelow(10))
                for _ in range(current_app.config.get(
                    "OTP_LENGTH", 6
                ))
            )

            # Create temporary OTP record
            otp_record = PasswordResetOTP(
                user_id=user.id,
                otp_hash=generate_password_hash(otp),
                expires_at=now + timedelta(
                    minutes=current_app.config.get(
                        "OTP_EXPIRY_MINUTES", 5
                    )
                )
            )

            db.session.add(otp_record)
            db.session.commit()

            # Send email first
            try:

                _send_reset_email(user, otp)

            except Exception:

                current_app.logger.exception(
                    "Password reset email could not be sent."
                )

                # Remove failed OTP record
                db.session.delete(otp_record)
                db.session.commit()

                flash(
                    "Unable to send OTP right now. Please try again later.",
                    "danger"
                )

                return redirect(url_for("auth.forgot_password"))

            # Email sent successfully.
            # Now invalidate previous unused OTPs.
            PasswordResetOTP.query.filter(
                PasswordResetOTP.user_id == user.id,
                PasswordResetOTP.used_at.is_(None),
                PasswordResetOTP.id != otp_record.id
            ).update(
                {"used_at": datetime.utcnow()},
                synchronize_session=False
            )

            db.session.commit()

            session["password_reset_otp_id"] = otp_record.id

        flash(
            "If an account exists with this email, an OTP will be sent.",
            "info"
        )

        return redirect(url_for("auth.verify_reset_otp"))

    return render_template("auth/forgot_password.html")


# --------------------------------------------------
# VERIFY OTP
# --------------------------------------------------


@bp.route("/verify-reset-otp", methods=["GET", "POST"])
def verify_reset_otp():

    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    otp_id = session.get("password_reset_otp_id")

    if not otp_id:
        flash("Please request a password reset OTP first.", "warning")
        return redirect(url_for("auth.forgot_password"))

    otp_record = db.session.get(PasswordResetOTP, otp_id)

    if (
        not otp_record
        or otp_record.used_at is not None
        or otp_record.expires_at <= datetime.utcnow()
    ):

        _clear_reset_session()

        flash(
            "OTP has expired or is invalid. Please request a new one.",
            "danger"
        )

        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":

        entered_otp = request.form.get("otp", "").strip()

        max_attempts = current_app.config.get(
            "OTP_MAX_ATTEMPTS", 5
        )

        if otp_record.attempts >= max_attempts:

            otp_record.used_at = datetime.utcnow()
            db.session.commit()

            _clear_reset_session()

            flash(
                "Maximum OTP attempts reached. Request a new OTP.",
                "danger"
            )

            return redirect(url_for("auth.forgot_password"))

        if not check_password_hash(
            otp_record.otp_hash,
            entered_otp
        ):

            otp_record.attempts += 1
            db.session.commit()

            if otp_record.attempts >= max_attempts:

                otp_record.used_at = datetime.utcnow()
                db.session.commit()

                _clear_reset_session()

                flash(
                    "Maximum OTP attempts reached. Request a new OTP.",
                    "danger"
                )

                return redirect(url_for("auth.forgot_password"))

            flash("Incorrect OTP. Please try again.", "danger")

            return redirect(url_for("auth.verify_reset_otp"))

        # OTP verified. Mark it as used immediately.
        otp_record.used_at = datetime.utcnow()
        db.session.commit()

        session.pop("password_reset_otp_id", None)
        session["password_reset_verified_id"] = otp_record.id

        return redirect(url_for("auth.reset_password"))

    return render_template("auth/verify_reset_otp.html")


# --------------------------------------------------
# RESET PASSWORD
# --------------------------------------------------

@bp.route("/reset-password", methods=["GET", "POST"])
def reset_password():

    if current_user.is_authenticated:
        return redirect(url_for("main.dashboard"))

    verified_id = session.get("password_reset_verified_id")

    if not verified_id:

        flash("Please verify your OTP first.", "warning")

        return redirect(url_for("auth.forgot_password"))

    otp_record = db.session.get(
        PasswordResetOTP,
        verified_id
    )

    if not otp_record or otp_record.used_at is None:

        _clear_reset_session()

        flash(
            "Password reset session is invalid. Please try again.",
            "danger"
        )

        return redirect(url_for("auth.forgot_password"))

    # Do not allow an old verification session to be reused.
    verification_timeout = timedelta(minutes=10)

    if datetime.utcnow() - otp_record.used_at > verification_timeout:

        _clear_reset_session()

        flash(
            "Password reset session expired. Request a new OTP.",
            "danger"
        )

        return redirect(url_for("auth.forgot_password"))

    if request.method == "POST":

        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")

        if len(password) < 8:

            flash(
                "Password must contain at least 8 characters.",
                "danger"
            )

        elif password != confirm_password:

            flash("Passwords do not match.", "danger")

        else:

            user = db.session.get(User, otp_record.user_id)

            if not user:

                _clear_reset_session()

                flash("Account not found.", "danger")

                return redirect(url_for("auth.login"))

            user.set_password(password)

            db.session.commit()

            _clear_reset_session()

            flash(
                "Password reset successfully. Please log in.",
                "success"
            )

            return redirect(url_for("auth.login"))

    return render_template("auth/reset_password.html")


# --------------------------------------------------
# LOGOUT
# --------------------------------------------------

@bp.post("/logout")
@login_required
def logout():

    logout_user()

    flash("You have been logged out.", "info")

    return redirect(url_for("auth.login"))
