import os
from pathlib import Path
from dotenv import load_dotenv


BASE_DIR = Path(__file__).resolve().parent

env_path = BASE_DIR / "venv" / ".env"

load_dotenv(env_path, override=True)



class Config:

    SECRET_KEY = os.getenv("SECRET_KEY", "dev-only-change-me")

    SQLALCHEMY_DATABASE_URI = (
        os.getenv("DATABASE_URL")
        or f"sqlite:///{BASE_DIR / 'instance' / 'splitmate.db'}"
    )

    SQLALCHEMY_TRACK_MODIFICATIONS = False

    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Lax"
    REMEMBER_COOKIE_HTTPONLY = True

    DEBUG = os.getenv("FLASK_DEBUG", "false").lower() == "true"

    # Bill upload settings
    MAX_CONTENT_LENGTH = 10 * 1024 * 1024

    RECEIPT_UPLOAD_FOLDER = os.path.join(
        str(BASE_DIR),
        "instance",
        "uploads",
        "receipts"
    )

    # Gmail SMTP settings
    MAIL_SERVER = os.getenv("MAIL_SERVER", "smtp.gmail.com")
    MAIL_PORT = int(os.getenv("MAIL_PORT", "587"))
    MAIL_USE_TLS = os.getenv("MAIL_USE_TLS", "true").lower() == "true"

    MAIL_USERNAME = os.getenv("MAIL_USERNAME")
    MAIL_PASSWORD = os.getenv("MAIL_PASSWORD")

    MAIL_DEFAULT_SENDER = (
        os.getenv("MAIL_DEFAULT_SENDER")
        or MAIL_USERNAME
    )

    MAIL_TIMEOUT = 10

    # Password reset OTP settings
    OTP_LENGTH = 6
    OTP_EXPIRY_MINUTES = 5
    OTP_MAX_ATTEMPTS = 5
    OTP_RESEND_LIMIT = 5
    OTP_RESEND_WINDOW_MINUTES = 5