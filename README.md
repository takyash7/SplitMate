# SplitMate — Expense Sharing Platform

A Flask + MySQL-ready shared expense application. Users can create multiple groups (trips, home, office, friends), add expenses, choose only the participants for each expense, split by equal/exact/percentage/weighted shares, view balances, and record settlements.

## Included features

- Registration, login, logout and persistent user accounts (Flask-Login sessions).
- Password hashing with Werkzeug.
- Multiple groups per account; group data remains after logout/login.
- Add registered users to groups by email.
- Group-specific expense history and balances.
- Custom participants per expense (the whole group is not forced to participate).
- Equal, exact amount, percentage and weighted-share splitting.
- Decimal-based currency calculations and MySQL `DECIMAL(12,2)` columns.
- Simplified debt suggestions using a greedy settlement algorithm.
- Record settlement payments.
- Activity history.
- Responsive Bootstrap UI for phone, tablet and desktop.
- SQLAlchemy models and Flask-Migrate support.

## Requirements

- Python 3.10+
- MySQL 8+ (optional for local start; SQLite is the default)
- A modern browser

## 1. Create and activate a virtual environment

### Windows PowerShell

```powershell
py -m venv .venv
.venv\Scripts\Activate.ps1
```

### macOS / Linux

```bash
python3 -m venv .venv
source .venv/bin/activate
```

## 2. Install packages

```bash
pip install -r requirements.txt
```

## 3. Configure environment

Copy `.env.example` to `.env`.

Windows:

```powershell
Copy-Item .env.example .env
```

macOS / Linux:

```bash
cp .env.example .env
```

Change `SECRET_KEY` to a long random value. For a quick local run, leave `DATABASE_URL` blank; the app creates an SQLite database in `instance/splitmate.db`.

## 4. Optional: configure MySQL

Create a database and user in MySQL:

```sql
CREATE DATABASE splitmate CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'splitmate_user'@'localhost' IDENTIFIED BY 'use_a_strong_password';
GRANT ALL PRIVILEGES ON splitmate.* TO 'splitmate_user'@'localhost';
FLUSH PRIVILEGES;
```

Set this in `.env` (URL-encode special characters in the password):

```env
DATABASE_URL=mysql+pymysql://splitmate_user:use_a_strong_password@localhost:3306/splitmate
```

The app calls `db.create_all()` on startup for a simple first-run setup. For ongoing schema changes, use migrations:

```bash
flask --app run.py db init
flask --app run.py db migrate -m "initial schema"
flask --app run.py db upgrade
```

If you use migrations from the beginning, you can remove `db.create_all()` from `app/__init__.py` after creating the initial migration.

## 5. Run

```bash
python run.py
```

Open http://127.0.0.1:5000

## 6. Try the app

1. Register two or more accounts using different email addresses (use separate browser profiles or log out/in).
2. Create a group such as "Goa Trip".
3. Add the other registered users by email from the group page.
4. Add an expense. Select only the people who participated.
5. Try Equal, Exact, Percentage and Weighted shares.
6. Open the group page to see each member's net balance and simplified settlement suggestions.
7. Record a settlement from the settlement page.
8. Log out and back in. Your groups and expense history are stored in the database.

## Important behavior and accounting model

- Expense payer receives credit for the full amount paid.
- Each selected participant receives a debit for their assigned share.
- A user can pay an expense without being one of its participants.
- The sum of all shares must equal the expense amount.
- Balances are group-specific and are calculated from expenses, splits and recorded settlements.
- A positive balance means the member should receive money; a negative balance means the member owes money.
- A settlement is recorded as money paid by the currently logged-in user to another group member. Only record it after the payment has actually happened.

## Project layout

```text
SplitMate/
├── app/
│   ├── __init__.py
│   ├── extensions.py
│   ├── models.py
│   ├── utils.py
│   ├── auth.py
│   ├── main.py
│   ├── groups.py
│   ├── expenses.py
│   ├── settlements.py
│   ├── templates/
│   └── static/
├── instance/             # database created here at runtime
├── config.py
├── run.py
├── requirements.txt
├── .env.example
└── README.md
```

## Production checklist before public deployment

This is a complete runnable learning/MVP application, not a security-audited financial product. Before public deployment:
- Set a unique strong `SECRET_KEY`; never use the development fallback.
- Set `FLASK_DEBUG=false` and use a production WSGI server (for example Gunicorn).
- Enable HTTPS and secure session cookies (`SESSION_COOKIE_SECURE=True`).
- Add CSRF protection (Flask-WTF) to every form.
- Add rate limiting for login and registration.
- Add authorization rules for group administration and member removal.
- Add expense edit/delete with audit-safe reversal logic rather than direct destructive edits.
- Add invitation email verification, file upload validation/storage, and backups if implementing those features.
- Add automated tests for rounding, split validation, balances, and concurrent requests.
