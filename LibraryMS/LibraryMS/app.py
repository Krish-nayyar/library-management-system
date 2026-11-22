"""Library Management System - run with:  python app.py
Standard library only (http.server + sqlite3). Opens http://localhost:8000 in your browser."""
import json, os, re, secrets, sqlite3, sys, threading, webbrowser
from datetime import date, timedelta
from http.server import ThreadingHTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import build_db, database as db, queries

if not os.path.exists(db.DB_PATH):
    print("First run: building library.db from the seed files ...")
    build_db.build()

STATIC = os.path.join(HERE, "static")
SESSIONS = {}                      # token -> {"role","id","name"}
MIME = {".html": "text/html; charset=utf-8", ".css": "text/css", ".js": "application/javascript",
        ".svg": "image/svg+xml", ".png": "image/png", ".ico": "image/x-icon"}

class Handler(BaseHTTPRequestHandler):
    server_version = "LibraryMS/1.0"

    # ---- helpers -----------------------------------------------------------
    def log_message(self, fmt, *a):
        if "/api/" in (a[0] if a else ""):
            sys.stderr.write("  %s\n" % (fmt % a))

    def send_json(self, obj, status=200, headers=None):
        body = json.dumps(obj, default=str).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for k, v in (headers or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def body(self):
        n = int(self.headers.get("Content-Length") or 0)
        try:
            return json.loads(self.rfile.read(n) or b"{}")
        except ValueError:
            return {}

    def session(self):
        c = self.headers.get("Cookie", "")
        m = re.search(r"sid=([A-Za-z0-9_\-]+)", c)
        return SESSIONS.get(m.group(1)) if m else None

    def page(self, q):
        size = min(int(q.get("size", ["25"])[0]), 100)
        return size, (max(int(q.get("page", ["1"])[0]), 1) - 1) * size

    # ---- routing -----------------------------------------------------------
    def do_GET(self):    self.route("GET")
    def do_POST(self):   self.route("POST")
    def do_DELETE(self): self.route("DELETE")

    def route(self, method):
        u = urlparse(self.path)
        if not u.path.startswith("/api/"):
            return self.static(u.path)
        q, data = parse_qs(u.query), (self.body() if method == "POST" else {})
        try:
            self.api(method, u.path[5:].strip("/").split("/"), q, data)
        except (ValueError, sqlite3.IntegrityError) as e:
            msg = str(e)
            if "UNIQUE" in msg: msg = "That value already exists (duplicate email/ISBN/username)."
            elif "FOREIGN KEY" in msg: msg = "Referenced record does not exist."
            self.send_json({"error": msg}, 400)
        except Exception as e:                      # keep server alive, show message
            self.send_json({"error": f"Server error: {e}"}, 500)

    def static(self, path):
        path = "/index.html" if path == "/" else path
        f = os.path.normpath(os.path.join(STATIC, path.lstrip("/")))
        if not f.startswith(STATIC) or not os.path.isfile(f):
            self.send_response(404); self.end_headers(); return
        with open(f, "rb") as fh:
            body = fh.read()
        self.send_response(200)
        self.send_header("Content-Type", MIME.get(os.path.splitext(f)[1], "application/octet-stream"))
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    # ---- API ---------------------------------------------------------------
    def api(self, method, p, q, d):
        s, a = self.session(), p[0]
        J = self.send_json

        # --- auth ---
        if a == "login" and method == "POST":
            if d.get("role") == "admin":
                u = db.login_admin(d.get("username", "").strip(), d.get("password", ""))
                sess = u and {"role": "admin", "id": u["AdminID"], "name": u["Username"]}
            else:
                u = db.login_borrower(d.get("username", "").strip(), d.get("password", ""))
                sess = u and {"role": "borrower", "id": u["BorrowerID"], "name": u["FirstName"]}
            if not sess:
                return J({"error": "Invalid credentials"}, 401)
            tok = secrets.token_urlsafe(24); SESSIONS[tok] = sess
            return J(sess, headers={"Set-Cookie": f"sid={tok}; Path=/; HttpOnly; SameSite=Lax"})
        if a == "register" and method == "POST":
            for k in ("firstName", "lastName", "email", "password"):
                if not str(d.get(k, "")).strip(): raise ValueError(f"{k} is required")
            if len(d["password"]) < 6: raise ValueError("Password must be at least 6 characters")
            db.register_borrower(d["firstName"].strip(), d["lastName"].strip(), d["email"].strip(),
                                 d.get("phone"), d.get("dob"), d["password"])
            return J({"ok": True})
        if a == "logout":
            SESSIONS.pop(re.sub(r".*sid=([^;]+).*", r"\1", self.headers.get("Cookie", "")), None)
            return J({"ok": True}, headers={"Set-Cookie": "sid=; Path=/; Max-Age=0"})
        if a == "me":
            return J(s or {"role": None})

        if not s:
            return self.deny()

        # --- catalogue (everyone logged in) ---
        if a == "genres": return J(db.get_genres())
        if a == "books" and method == "GET":
            size, off = self.page(q)
            return J(db.search_books(q.get("q", [""])[0], q.get("genre", [""])[0],
                                     q.get("available", [""])[0] == "1", size, off))
        # --- borrower self-service ---
        if a == "borrow" and method == "POST":
            if s["role"] != "borrower": raise ValueError("Use the Loans page to issue books as admin")
            return J({"loanId": db.issue_book(int(d["bookId"]), s["id"])})
        if a == "my":
            if s["role"] != "borrower": return self.deny()
            if p[1] == "loans":
                return J({"active": db.get_active_loans_for_borrower(s["id"]),
                          "history": db.get_loan_history_for_borrower(s["id"]),
                          "limit": db.MAX_ACTIVE_LOANS})
            if p[1] == "notifications": return J(db.get_notifications(s["id"]))
            if p[1] == "profile":
                r = db.run_query("SELECT BorrowerID,FirstName,LastName,Email,Phone,DateOfBirth,MembershipDate,"
                                 "LateSubmissionCount,IsBlacklisted,BlacklistedUntil FROM Borrowers WHERE BorrowerID=?", (s["id"],))
                return J(r[0])

        # --- admin only ---
        if s["role"] != "admin": return self.deny()
        if a == "dashboard": return J(db.get_dashboard())
        if a == "books" and method == "POST":
            return J({"id": db.add_book(d["title"].strip(), d["author"].strip(), d["isbn"].strip(), d.get("genre"),
                                        d.get("subject"), d.get("shelf"), d.get("copies", 1), d.get("published"))})
        if a == "books" and method == "DELETE":
            db.remove_book(int(p[1])); return J({"ok": True})
        if a == "borrowers":
            if method == "GET":
                size, off = self.page(q); return J(db.get_borrowers(q.get("q", [""])[0], size, off))
            if len(p) == 1:   # add member (default password library123)
                for k in ("firstName", "lastName", "email"):
                    if not str(d.get(k, "")).strip(): raise ValueError(f"{k} is required")
                return J({"id": db.register_borrower(d["firstName"].strip(), d["lastName"].strip(), d["email"].strip(),
                                                      d.get("phone"), d.get("dob"), d.get("password") or "library123")})
            if p[2] == "blacklist":
                until = (date.today() + timedelta(days=int(d.get("days", 30)))).isoformat()
                db.blacklist_borrower(int(p[1]), until); return J({"until": until})
            if p[2] == "unblacklist":
                db.unblacklist_borrower(int(p[1])); return J({"ok": True})
        if a == "loans":
            if method == "GET":
                size, off = self.page(q)
                return J(db.get_all_loans_with_status(q.get("status", ["all"])[0], q.get("q", [""])[0], size, off))
            if len(p) == 1:
                return J({"loanId": db.issue_book(int(d["bookId"]), int(d["borrowerId"]), d.get("dueDate") or None)})
            if p[2] == "return": return J({"fee": db.return_book(int(p[1]))})
            if p[2] == "pay": db.mark_fee_paid(int(p[1]), s["id"], d.get("amount")); return J({"ok": True})
        if a == "reports":
            if len(p) == 1: return J(queries.list_reports())
            return J(queries.run_report(p[1], {k: v[0] for k, v in q.items()}))
        if a == "audit": return J(db.get_audit_log())
        if a == "notifications": return J(db.get_notifications())
        if a == "reminders" and method == "POST": return J({"sent": db.send_due_reminders()})
        if a == "admins":
            if method == "GET": return J(db.get_all_admins())
            if len(str(d.get("password", ""))) < 6: raise ValueError("Password must be at least 6 characters")
            return J({"id": db.add_admin(d["username"].strip(), d.get("email"), d["password"], s["id"])})
        return J({"error": "Not found"}, 404)

    def deny(self):
        self.send_json({"error": "Not allowed"}, 403)

def main():
    port = int(os.environ.get("PORT", 8000))
    for _ in range(20):
        try:
            srv = ThreadingHTTPServer(("127.0.0.1", port), Handler); break
        except OSError:
            port += 1
    else:
        sys.exit("No free port found")
    url = f"http://localhost:{port}"
    print(f"\n  Library Management System running at {url}\n  Admin login:  admin / admin123\n"
          f"  Member login: dwolters0@ft.com / library123\n  (Press Ctrl+C to stop)\n")
    threading.Timer(0.8, lambda: webbrowser.open(url)).start()
    try:
        srv.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")

if __name__ == "__main__":
    main()
