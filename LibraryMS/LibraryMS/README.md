# Library Management System (Minor Project)

A complete library system built from the project files you supplied: the SQL Server schema, seed data and analytics
requirements, the `database.py` business logic, and the React front-end layout. It runs **locally in your browser**.

## How to run (30 seconds)
The only thing you need is **Python 3.8 or newer**. Nothing else to install: no pip packages, no MySQL, no Node.

* **Windows:** double-click `run.bat`
* **macOS:** double-click `run.command` (first time: right-click, then Open)
* **Any OS / terminal:** `python app.py` (or `python3 app.py`)

Your browser opens at <http://localhost:8000>. Stop the server with `Ctrl+C`.
If `library.db` is ever deleted, it is rebuilt automatically from the seed files on the next start.

## Logins
| Role | Login | Password |
|---|---|---|
| Admin (librarian) | `admin` | `admin123` |
| Member | any seeded e-mail, e.g. `dwolters0@ft.com` | `library123` |

New members can also self-register on the login screen.

## What it does
**Admin:** dashboard stats, add/search/delete books, add members, blacklist / lift blacklist, issue and return books
(late fees calculated automatically), collect fees, 12 SQL reports, audit log, due-tomorrow reminders, add admins.

**Member:** search the catalogue (title / author / ISBN / genre / available only), borrow available books, see current loans
with overdue days and fee so far, loan history, notifications, profile and blacklist status.

### Business rules (same as your `database.py`; constants are at the top of `database.py`)
* Late fee: 1 per day for the first 30 days, then 3 per day (`fn_CalculateOverdueFees`).
* 4 late returns -> automatically blacklisted for 30 days; the blacklist lifts itself when the date passes.
* Default loan period 14 days, max 3 active loans per member, no borrowing while blacklisted, no duplicate active loan of the same book.

## How your files were used
| Your file | Where it went |
|---|---|
| `SchemaCreation/SchemaCreation.sql`, `Indexes.sql` | `schema.sql` (SQLite version, extended with the tables/columns `database.py` needs) |
| `SeedingDMLs/*.sql` (1000 books, 1000 borrowers, 1000 loans) | converted by `build_db.py` into `library.db` |
| `Requirements/Triggers/trg_BookStatusChange.sql` | SQLite trigger in `schema.sql`; visible on the **Activity** page |
| `Requirements/Functions/*`, `Procedures/*`, `Queries/*` | `queries.py`, run from the **Reports** page (each report shows its original file name) |
| `database.py` (MySQL + Streamlit + bcrypt) | `database.py`: same function names, ported to SQLite; PBKDF2 (standard library) replaces bcrypt |
| React `LibraryManagementFrontend` | the Books / Borrowers / Loans forms and layout are reproduced in `static/` (plain JavaScript, so no Node/npm is needed) |
| `ERD/ERD.pdf` and the original `.sql` files | kept unchanged in `sql_server_original/` |

## Project structure
```
app.py                 web server + REST API (Python standard library)
database.py            all database operations and library rules
queries.py             the SQL analytics reports
build_db.py            builds library.db from the seed files
schema.sql             tables, trigger, indexes
library.db             ready-to-use database
static/                index.html, style.css, app.js (the user interface)
sql_server_original/   your original SQL Server files + ERD
```

## Notes
* **Why SQLite instead of SQL Server / MySQL?** SQLite ships inside Python, so nothing needs installing. T-SQL stored procedures and
  functions do not exist in SQLite, so they are implemented as Python functions / SQL queries with the same logic.
* **Seed data adjustments** (in `build_db.py`): dates converted from M/D/YYYY to ISO; each book gets 1 copy; a book is
  "Borrowed" only if it has an open loan (the original statuses were random and contradicted the loan table); late fees of past
  returns were back-filled and treated as paid.
* The seed loans are from Jan-Feb 2024, so every unreturned loan shows as overdue today with a large fee. That is the data, not a bug.
  New loans you create use today's date. The "Borrowed Books Report" defaults to January 2024 for the same reason.
* To reset everything, delete `library.db` and start the app again.
* This is a local demo: sessions are kept in memory and the server only listens on `127.0.0.1`.
