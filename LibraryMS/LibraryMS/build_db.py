"""Builds library.db from the original SQL Server seed files (SeedingDMLs/*.sql).
Run automatically by app.py if library.db is missing:   python build_db.py
Uses only the Python standard library."""
import os, re, sqlite3, hashlib, secrets
from datetime import datetime

HERE = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(HERE, "library.db")
SEED_DIR = os.path.join(HERE, "sql_server_original", "SeedingDMLs")

DEFAULT_BORROWER_PASSWORD = "library123"
DEFAULT_ADMIN = ("admin", "admin@library.local", "admin123")

TOKEN = re.compile(r"'((?:[^']|'')*)'|(-?\d+(?:\.\d+)?)|(null)", re.I)

def hash_password(pw, iters=100_000):
    salt = secrets.token_hex(8)
    h = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt.encode(), iters).hex()
    return f"pbkdf2${iters}${salt}${h}"

def iso(d):                      # '4/8/2024' (M/D/YYYY) -> '2024-04-08'
    return None if d is None else datetime.strptime(d, "%m/%d/%Y").date().isoformat()

def parse(line):
    m = re.match(r"\s*insert into (\w+)\s*\((.*?)\)\s*values\s*\((.*)\)\s*;?\s*$", line, re.I)
    if not m:
        return None
    cols = [c.strip() for c in m.group(2).split(",")]
    vals = []
    for s, n, nul in TOKEN.findall(m.group(3)):
        if nul: vals.append(None)
        elif n and not s: vals.append(int(float(n)) if "." not in n else float(n))
        else: vals.append(s.replace("''", "'"))
    return m.group(1), dict(zip(cols, vals))

def read_rows(fname):
    with open(os.path.join(SEED_DIR, fname), encoding="utf-8", errors="replace") as f:
        for line in f:
            p = parse(line)
            if p: yield p[1]

def build(verbose=True):
    if os.path.exists(DB_PATH):
        os.remove(DB_PATH)
    con = sqlite3.connect(DB_PATH)
    con.executescript(open(os.path.join(HERE, "schema.sql"), encoding="utf-8").read())
    skipped = {"Books": 0, "Borrowers": 0, "Loans": 0}

    for r in read_rows("BooksTable.sql"):
        status = r["CurrentStatus"]
        try:
            con.execute(
                "INSERT INTO Books (Title,Author,ISBN,PublishedDate,Genre,Subject,ShelfLocation,"
                "TotalCopies,AvailableCopies,CurrentStatus) VALUES (?,?,?,?,?,?,?,?,?,?)",
                (r["Title"], r["Author"], r["ISBN"], iso(r["PublishedDate"]), r["Genre"],
                 (r["Genre"] or "Other").split("|")[0], r["ShelfLocation"], 1,
                 1 if status == "Available" else 0, status))
        except sqlite3.Error:
            skipped["Books"] += 1

    pw = hash_password(DEFAULT_BORROWER_PASSWORD)   # same demo password for seeded members
    for r in read_rows("BorrowersTable.sql"):
        try:
            con.execute(
                "INSERT INTO Borrowers (FirstName,LastName,Email,DateOfBirth,MembershipDate,PasswordHash) "
                "VALUES (?,?,?,?,?,?)",
                (r["FirstName"], r["LastName"], r["Email"], iso(r["DateOfBirth"]),
                 iso(r["MembershipDate"]), pw))
        except sqlite3.Error:
            skipped["Borrowers"] += 1

    for r in read_rows("LoansTable.sql"):
        try:
            con.execute(
                "INSERT INTO Loans (BookID,BorrowerID,DateBorrowed,DueDate,DateReturned) VALUES (?,?,?,?,?)",
                (r["BookID"], r["BorrowerID"], iso(r["DateBorrowed"]), iso(r["DueDate"]), iso(r["DateReturned"])))
        except sqlite3.Error:
            skipped["Loans"] += 1

    # Make the synthetic seed data consistent with the loan records:
    #  - a book with an open loan is 'Borrowed' (0 copies), every other book is 'Available'
    #  - returned loans get their late fee / IsLate back-filled (historic fees treated as settled)
    #  - members' late-return counters are back-filled
    con.execute("UPDATE Books SET AvailableCopies=1, CurrentStatus='Available'")
    con.execute("UPDATE Books SET AvailableCopies=0, CurrentStatus='Borrowed' WHERE BookID IN "
                "(SELECT BookID FROM Loans WHERE DateReturned IS NULL)")
    con.create_function("fee", 2, lambda d, r: __import__("database").calculate_late_fee(d, r))
    con.execute("UPDATE Loans SET LateFeeAmount=fee(DueDate,DateReturned), IsLate=(DateReturned>DueDate), "
                "FeePaid=1 WHERE DateReturned IS NOT NULL")
    con.execute("UPDATE Borrowers SET LateSubmissionCount=(SELECT COUNT(*) FROM Loans l "
                "WHERE l.BorrowerID=Borrowers.BorrowerID AND l.IsLate=1)")
    # Trigger fired while seeding? start the audit log clean.
    con.execute("DELETE FROM AuditLog")
    u, e, p = DEFAULT_ADMIN
    con.execute("INSERT INTO Admins (Username,Email,PasswordHash) VALUES (?,?,?)", (u, e, hash_password(p)))
    con.commit()
    if verbose:
        for t in ("Books", "Borrowers", "Loans"):
            n = con.execute(f"SELECT COUNT(*) FROM {t}").fetchone()[0]
            print(f"{t}: {n} rows loaded, {skipped[t]} skipped")
    con.close()

if __name__ == "__main__":
    build()
