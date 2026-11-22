"""Database layer (SQLite) - ported from the original MySQL/Streamlit database.py.
Same function names, same business rules; no external packages needed."""
import os, sqlite3, hmac, hashlib, secrets
from datetime import date, timedelta

DB_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "library.db")

# ---- Library rules (change here) -------------------------------------------
LOAN_DAYS = 14            # default loan period
MAX_ACTIVE_LOANS = 3      # books a member can hold at once
BLACKLIST_AFTER_LATE = 4  # late returns before auto-blacklist (as in original code)
BLACKLIST_DAYS = 30

# ---- Functions that replace the T-SQL user-defined functions ----------------
def calculate_late_fee(due_date, return_date=None):
    """fn_CalculateOverdueFees: 1/day up to 30 days, then 3/day beyond."""
    if return_date is None:
        return_date = date.today()
    if isinstance(due_date, str):
        due_date = date.fromisoformat(due_date)
    if isinstance(return_date, str):
        return_date = date.fromisoformat(return_date)
    d = (return_date - due_date).days
    if d <= 0:
        return 0.0
    return float(d) if d <= 30 else float(d + (d - 30) * 2)

def _fee_sql(due, returned):
    return calculate_late_fee(due, returned) if due else 0.0

def _age_group(dob):
    """fn_GetAgeGroup"""
    if not dob:
        return "Unknown"
    b, t = date.fromisoformat(dob), date.today()
    age = t.year - b.year - ((t.month, t.day) < (b.month, b.day))
    for lo, hi in ((0, 10), (11, 20), (21, 30), (31, 40), (41, 50), (51, 60)):
        if lo <= age <= hi:
            return f"[{lo}, {hi}]"
    return "60+"

def get_conn():
    con = sqlite3.connect(DB_PATH)
    con.row_factory = sqlite3.Row
    con.execute("PRAGMA foreign_keys = ON")
    con.create_function("fn_CalculateOverdueFees", 2, _fee_sql)
    con.create_function("fn_GetAgeGroup", 1, _age_group)
    return con

def run_query(sql, params=None, fetch=True):
    con = get_conn()
    try:
        cur = con.execute(sql, params or ())
        if fetch:
            return [dict(r) for r in cur.fetchall()]
        con.commit()
        return cur.lastrowid
    finally:
        con.close()

# ---- Passwords (PBKDF2 from the standard library instead of bcrypt) ---------
def hash_password(password, iters=100_000):
    salt = secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), iters).hex()
    return f"pbkdf2${iters}${salt}${h}"

def check_password(password, stored):
    try:
        _, iters, salt, h = stored.split("$")
        calc = hashlib.pbkdf2_hmac("sha256", password.encode(), salt.encode(), int(iters)).hex()
        return hmac.compare_digest(calc, h)
    except Exception:
        return False

def login_admin(username, password):
    rows = run_query("SELECT * FROM Admins WHERE Username=?", (username,))
    return rows[0] if rows and check_password(password, rows[0]["PasswordHash"]) else None

def login_borrower(email, password):
    rows = run_query("SELECT * FROM Borrowers WHERE Email=?", (email,))
    if rows and rows[0]["PasswordHash"] and check_password(password, rows[0]["PasswordHash"]):
        check_and_lift_blacklist(rows[0]["BorrowerID"])
        return run_query("SELECT * FROM Borrowers WHERE BorrowerID=?", (rows[0]["BorrowerID"],))[0]
    return None

def register_borrower(first, last, email, phone, dob, password):
    """sp_AddNewBorrower (+ password): rejects duplicate e-mail."""
    if run_query("SELECT 1 FROM Borrowers WHERE Email=?", (email,)):
        raise ValueError("Email already exists")
    return run_query(
        "INSERT INTO Borrowers (FirstName,LastName,Email,Phone,DateOfBirth,PasswordHash,MembershipDate) "
        "VALUES (?,?,?,?,?,?,?)",
        (first, last, email, phone, dob or None, hash_password(password), date.today().isoformat()), fetch=False)

# ---- Books -----------------------------------------------------------------
def search_books(q="", genre="", only_available=False, limit=25, offset=0):
    where, p = ["1=1"], []
    if q:
        where.append("(b.Title LIKE ? OR b.Author LIKE ? OR b.ISBN LIKE ?)")
        p += [f"%{q}%"] * 3
    if genre:
        where.append("b.Genre LIKE ?"); p.append(f"%{genre}%")
    if only_available:
        where.append("b.AvailableCopies > 0")
    w = " AND ".join(where)
    total = run_query(f"SELECT COUNT(*) c FROM Books b WHERE {w}", p)[0]["c"]
    rows = run_query(
        f"""SELECT b.*, (SELECT MIN(DueDate) FROM Loans l WHERE l.BookID=b.BookID AND l.DateReturned IS NULL) AS EarliestReturn
            FROM Books b WHERE {w} ORDER BY b.Subject, b.Author, b.Title LIMIT ? OFFSET ?""", p + [limit, offset])
    return {"total": total, "rows": rows}

def get_genres():
    seen = set()
    for r in run_query("SELECT DISTINCT Genre FROM Books WHERE Genre IS NOT NULL"):
        seen.update(g for g in r["Genre"].split("|") if g)
    return sorted(seen)

def get_all_books():
    return run_query("SELECT * FROM Books ORDER BY Subject, Author")

def get_book_availability(subject=None):
    sql = """SELECT b.Subject, b.Author, b.Title, b.AvailableCopies, MIN(l.DueDate) AS EarliestReturn
             FROM Books b LEFT JOIN Loans l ON b.BookID=l.BookID AND l.DateReturned IS NULL
             WHERE b.AvailableCopies=0 {w} GROUP BY b.BookID"""
    return run_query(sql.format(w="AND b.Subject=?" if subject else ""), (subject,) if subject else ())

def add_book(title, author, isbn, genre, subject, shelf, total, pub_date=None):
    total = int(total or 1)
    return run_query(
        "INSERT INTO Books (Title,Author,ISBN,Genre,Subject,ShelfLocation,TotalCopies,AvailableCopies,"
        "PublishedDate,CurrentStatus) VALUES (?,?,?,?,?,?,?,?,?,?)",
        (title, author, isbn, genre, subject or (genre or "Other").split("|")[0], shelf, total, total,
         pub_date or None, "Available" if total > 0 else "Borrowed"), fetch=False)

def remove_book(book_id):
    if run_query("SELECT 1 FROM Loans WHERE BookID=? AND DateReturned IS NULL", (book_id,)):
        raise ValueError("Book has active loans and cannot be removed")
    if run_query("SELECT 1 FROM Loans WHERE BookID=?", (book_id,)):
        raise ValueError("Book has loan history and cannot be deleted (keeps records intact)")
    run_query("DELETE FROM Books WHERE BookID=?", (book_id,), fetch=False)

# ---- Loans -----------------------------------------------------------------
def issue_book(book_id, borrower_id, due_date=None):
    check_and_lift_blacklist(borrower_id)
    con = get_conn()
    try:
        b = con.execute("SELECT * FROM Books WHERE BookID=?", (book_id,)).fetchone()
        m = con.execute("SELECT * FROM Borrowers WHERE BorrowerID=?", (borrower_id,)).fetchone()
        if not b: raise ValueError("Book not found")
        if not m: raise ValueError("Borrower not found")
        if m["IsBlacklisted"]:
            raise ValueError(f"Borrower is blacklisted until {m['BlacklistedUntil']}")
        if b["AvailableCopies"] <= 0: raise ValueError("No copies available")
        if get_active_loan_count(borrower_id) >= MAX_ACTIVE_LOANS:
            raise ValueError(f"Borrower already has {MAX_ACTIVE_LOANS} active loans")
        if con.execute("SELECT 1 FROM Loans WHERE BookID=? AND BorrowerID=? AND DateReturned IS NULL",
                       (book_id, borrower_id)).fetchone():
            raise ValueError("Borrower already has this book")
        today = date.today()
        due = date.fromisoformat(due_date) if due_date else today + timedelta(days=LOAN_DAYS)
        if due < today: raise ValueError("Due date cannot be in the past")
        con.execute("UPDATE Books SET AvailableCopies=AvailableCopies-1 WHERE BookID=?", (book_id,))
        con.execute("UPDATE Books SET CurrentStatus='Borrowed' WHERE BookID=? AND AvailableCopies=0", (book_id,))
        cur = con.execute("INSERT INTO Loans (BookID,BorrowerID,DateBorrowed,DueDate) VALUES (?,?,?,?)",
                          (book_id, borrower_id, today.isoformat(), due.isoformat()))
        con.commit()
        return cur.lastrowid
    finally:
        con.close()

def return_book(loan_id):
    con = get_conn()
    try:
        loan = con.execute("SELECT * FROM Loans WHERE LoanID=?", (loan_id,)).fetchone()
        if not loan: raise ValueError("Loan not found")
        if loan["DateReturned"]: raise ValueError("Book already returned")
        today = date.today()
        fee = calculate_late_fee(loan["DueDate"], today)
        late = 1 if today > date.fromisoformat(loan["DueDate"]) else 0
        con.execute("UPDATE Loans SET DateReturned=?, LateFeeAmount=?, IsLate=? WHERE LoanID=?",
                    (today.isoformat(), fee, late, loan_id))
        con.execute("UPDATE Books SET AvailableCopies=MIN(AvailableCopies+1,TotalCopies), CurrentStatus='Available' "
                    "WHERE BookID=?", (loan["BookID"],))
        if late:
            con.execute("UPDATE Borrowers SET LateSubmissionCount=LateSubmissionCount+1 WHERE BorrowerID=?",
                        (loan["BorrowerID"],))
            cnt = con.execute("SELECT LateSubmissionCount FROM Borrowers WHERE BorrowerID=?",
                              (loan["BorrowerID"],)).fetchone()[0]
            if cnt >= BLACKLIST_AFTER_LATE:
                con.execute("UPDATE Borrowers SET IsBlacklisted=1, BlacklistedUntil=? WHERE BorrowerID=?",
                            ((today + timedelta(days=BLACKLIST_DAYS)).isoformat(), loan["BorrowerID"]))
        con.commit()
        return fee
    finally:
        con.close()

def get_active_loans_for_borrower(borrower_id):
    return run_query(
        """SELECT l.LoanID, b.Title, b.Author, b.Subject, l.DateBorrowed, l.DueDate,
                  CAST(julianday('now','localtime')-julianday(l.DueDate) AS INT) AS DaysOverdue,
                  fn_CalculateOverdueFees(l.DueDate, NULL) AS CurrentFee
           FROM Loans l JOIN Books b ON l.BookID=b.BookID
           WHERE l.BorrowerID=? AND l.DateReturned IS NULL ORDER BY l.DueDate""", (borrower_id,))

def get_loan_history_for_borrower(borrower_id):
    return run_query(
        """SELECT l.LoanID, b.Title, b.Author, l.DateBorrowed, l.DueDate, l.DateReturned,
                  l.LateFeeAmount, l.FeePaid, l.IsLate
           FROM Loans l JOIN Books b ON l.BookID=b.BookID
           WHERE l.BorrowerID=? ORDER BY l.DateBorrowed DESC, l.LoanID DESC""", (borrower_id,))

def get_active_loan_count(borrower_id):
    return run_query("SELECT COUNT(*) cnt FROM Loans WHERE BorrowerID=? AND DateReturned IS NULL",
                     (borrower_id,))[0]["cnt"]

def _loan_list(where="1=1", params=(), limit=200, offset=0):
    base = f"""FROM Loans l JOIN Books b ON l.BookID=b.BookID JOIN Borrowers br ON l.BorrowerID=br.BorrowerID
               WHERE {where}"""
    total = run_query(f"SELECT COUNT(*) c {base}", params)[0]["c"]
    rows = run_query(
        f"""SELECT l.LoanID, l.BookID, l.BorrowerID, br.FirstName||' '||br.LastName AS BorrowerName, br.Email,
                   b.Title, b.Author, l.DateBorrowed, l.DueDate, l.DateReturned,
                   CASE WHEN l.DateReturned IS NULL THEN CAST(julianday('now','localtime')-julianday(l.DueDate) AS INT) END AS DaysOverdue,
                   CASE WHEN l.DateReturned IS NULL THEN fn_CalculateOverdueFees(l.DueDate, NULL) ELSE l.LateFeeAmount END AS Fee,
                   l.FeePaid, l.IsLate
            {base} ORDER BY l.DateReturned IS NOT NULL, l.DueDate, l.LoanID LIMIT ? OFFSET ?""",
        tuple(params) + (limit, offset))
    return {"total": total, "rows": rows}

def get_all_active_loans(**kw):
    return _loan_list("l.DateReturned IS NULL", **kw)

def get_all_loans_with_status(status="all", q="", limit=25, offset=0):
    where, p = ["1=1"], []
    if status == "active": where.append("l.DateReturned IS NULL")
    elif status == "overdue": where.append("l.DateReturned IS NULL AND l.DueDate < date('now','localtime')")
    elif status == "returned": where.append("l.DateReturned IS NOT NULL")
    elif status == "unpaid": where.append("COALESCE(l.LateFeeAmount,0) > 0 AND l.FeePaid=0")
    if q:
        where.append("(b.Title LIKE ? OR br.FirstName||' '||br.LastName LIKE ? OR br.Email LIKE ?)"); p += [f"%{q}%"] * 3
    return _loan_list(" AND ".join(where), tuple(p), limit, offset)

def get_due_tomorrow():
    t = (date.today() + timedelta(days=1)).isoformat()
    return run_query(
        """SELECT l.LoanID, br.BorrowerID, br.Email, br.FirstName||' '||br.LastName AS BorrowerName, b.Title, l.DueDate
           FROM Loans l JOIN Books b ON l.BookID=b.BookID JOIN Borrowers br ON l.BorrowerID=br.BorrowerID
           WHERE l.DueDate=? AND l.DateReturned IS NULL""", (t,))

def mark_fee_paid(loan_id, admin_id, amount=None):
    loan = run_query("SELECT * FROM Loans WHERE LoanID=?", (loan_id,))
    if not loan: raise ValueError("Loan not found")
    loan = loan[0]
    if loan["FeePaid"]: raise ValueError("Fee already paid")
    amount = amount if amount is not None else loan["LateFeeAmount"]
    if not amount or amount <= 0: raise ValueError("No fee to collect")
    run_query("UPDATE Loans SET FeePaid=1 WHERE LoanID=?", (loan_id,), fetch=False)
    run_query("INSERT INTO FeeCollections (LoanID,BorrowerID,AmountPaid,CollectedBy) VALUES (?,?,?,?)",
              (loan_id, loan["BorrowerID"], amount, admin_id), fetch=False)

# ---- Borrowers -------------------------------------------------------------
def get_borrowers(q="", limit=25, offset=0):
    w, p = "1=1", []
    if q:
        w = "(FirstName||' '||LastName LIKE ? OR Email LIKE ?)"; p = [f"%{q}%"] * 2
    total = run_query(f"SELECT COUNT(*) c FROM Borrowers WHERE {w}", p)[0]["c"]
    rows = run_query(
        f"""SELECT BorrowerID, FirstName, LastName, Email, Phone, DateOfBirth, MembershipDate,
                   LateSubmissionCount, IsBlacklisted, BlacklistedUntil,
                   (SELECT COUNT(*) FROM Loans l WHERE l.BorrowerID=Borrowers.BorrowerID AND l.DateReturned IS NULL) AS ActiveLoans
            FROM Borrowers WHERE {w} ORDER BY FirstName, LastName LIMIT ? OFFSET ?""", p + [limit, offset])
    return {"total": total, "rows": rows}

def get_all_borrowers():
    return run_query("SELECT * FROM Borrowers ORDER BY FirstName")

def blacklist_borrower(borrower_id, until_date):
    run_query("UPDATE Borrowers SET IsBlacklisted=1, BlacklistedUntil=? WHERE BorrowerID=?",
              (until_date, borrower_id), fetch=False)

def unblacklist_borrower(borrower_id):
    run_query("UPDATE Borrowers SET IsBlacklisted=0, BlacklistedUntil=NULL WHERE BorrowerID=?",
              (borrower_id,), fetch=False)

def check_and_lift_blacklist(borrower_id):
    rows = run_query("SELECT IsBlacklisted, BlacklistedUntil FROM Borrowers WHERE BorrowerID=?", (borrower_id,))
    if rows and rows[0]["IsBlacklisted"] and rows[0]["BlacklistedUntil"]:
        if date.fromisoformat(rows[0]["BlacklistedUntil"]) <= date.today():
            unblacklist_borrower(borrower_id)

# ---- Admin / misc ----------------------------------------------------------
def get_inventory_summary():
    return run_query("SELECT Subject, Author, COUNT(*) Titles, SUM(TotalCopies) TotalCopies, "
                     "SUM(AvailableCopies) Available FROM Books GROUP BY Subject, Author ORDER BY Subject, Author")

def get_all_admins():
    return run_query("SELECT AdminID, Username, Email, CreatedAt FROM Admins")

def add_admin(username, email, password, created_by):
    return run_query("INSERT INTO Admins (Username,Email,PasswordHash,CreatedBy) VALUES (?,?,?,?)",
                     (username, email, hash_password(password), created_by), fetch=False)

def log_notification(borrower_id, loan_id, message, notif_type="due_reminder"):
    run_query("INSERT INTO Notifications (BorrowerID,LoanID,Message,NotifType) VALUES (?,?,?,?)",
              (borrower_id, loan_id, message, notif_type), fetch=False)

def send_due_reminders():
    """Logs a reminder for every loan due tomorrow (the 'email' is stored in Notifications)."""
    n = 0
    for r in get_due_tomorrow():
        log_notification(r["BorrowerID"], r["LoanID"],
                         f"Reminder: '{r['Title']}' is due tomorrow ({r['DueDate']}).")
        n += 1
    return n

def get_notifications(borrower_id=None, limit=100):
    if borrower_id:
        return run_query("SELECT * FROM Notifications WHERE BorrowerID=? ORDER BY NotificationID DESC LIMIT ?",
                         (borrower_id, limit))
    return run_query("""SELECT n.*, br.FirstName||' '||br.LastName AS BorrowerName, br.Email
                        FROM Notifications n JOIN Borrowers br ON n.BorrowerID=br.BorrowerID
                        ORDER BY NotificationID DESC LIMIT ?""", (limit,))

def get_audit_log(limit=100):
    return run_query("""SELECT a.AuditID, a.BookID, b.Title, a.StatusChange, a.ChangeDate
                        FROM AuditLog a LEFT JOIN Books b ON a.BookID=b.BookID ORDER BY AuditID DESC LIMIT ?""", (limit,))

def get_dashboard():
    one = lambda s: run_query(s)[0]["v"]
    return {
        "books": one("SELECT COUNT(*) v FROM Books"),
        "borrowers": one("SELECT COUNT(*) v FROM Borrowers"),
        "activeLoans": one("SELECT COUNT(*) v FROM Loans WHERE DateReturned IS NULL"),
        "overdue": one("SELECT COUNT(*) v FROM Loans WHERE DateReturned IS NULL AND DueDate < date('now','localtime')"),
        "available": one("SELECT COALESCE(SUM(AvailableCopies),0) v FROM Books"),
        "blacklisted": one("SELECT COUNT(*) v FROM Borrowers WHERE IsBlacklisted=1"),
        "feesCollected": one("SELECT COALESCE(SUM(AmountPaid),0) v FROM FeeCollections"),
        "feesPending": one("SELECT COALESCE(SUM(LateFeeAmount),0) v FROM Loans WHERE FeePaid=0 AND DateReturned IS NOT NULL"),
        "dueTomorrow": len(get_due_tomorrow()),
    }
