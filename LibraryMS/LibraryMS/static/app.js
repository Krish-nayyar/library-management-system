/* Library Management System - single-page UI (plain JavaScript, no libraries, works offline) */
const $ = s => document.querySelector(s);
const esc = s => String(s ?? "").replace(/[&<>"']/g, c => ({"&":"&amp;","<":"&lt;",">":"&gt;",'"':"&quot;","'":"&#39;"}[c]));
const money = n => Number(n || 0).toFixed(2);
const day = d => (d ? `<span style="white-space:nowrap">${String(d).slice(0, 10)}</span>` : "-");
const SIZE = 20;
let S = { me: null, view: "", page: 1, q: "", genre: "", avail: false, status: "all", rep: null, repArgs: {} };
let toastTimer;

async function api(path, method = "GET", body) {
  const r = await fetch("/api/" + path, { method, headers: { "Content-Type": "application/json" },
                                          body: body ? JSON.stringify(body) : undefined });
  const j = await r.json().catch(() => ({}));
  if (!r.ok) throw new Error(j.error || r.statusText);
  return j;
}
function toast(msg, err) {
  const t = $("#toast"); t.textContent = msg; t.className = "show" + (err ? " err" : "");
  clearTimeout(toastTimer); toastTimer = setTimeout(() => (t.className = ""), 3500);
}
const guard = fn => async (...a) => { try { await fn(...a); } catch (e) { toast(e.message, true); } };

const table = (cols, rows, empty = "Nothing to show.") => !rows.length ? `<p class="muted">${empty}</p>` :
  `<div class="scroll"><table><thead><tr>${cols.map(c => `<th>${c[0]}</th>`).join("")}</tr></thead><tbody>${
    rows.map(r => `<tr>${cols.map(c => `<td>${c[1](r)}</td>`).join("")}</tr>`).join("")}</tbody></table></div>`;
const pager = total => { const pages = Math.max(1, Math.ceil(total / SIZE));
  return `<div class="pager"><span>${total} result${total === 1 ? "" : "s"}</span>
    <button class="btn sm sec" data-act="prev" ${S.page <= 1 ? "disabled" : ""}>&larr; Prev</button>
    <span>Page ${S.page} / ${pages}</span>
    <button class="btn sm sec" data-act="next" ${S.page >= pages ? "disabled" : ""}>Next &rarr;</button></div>`; };
const field = (label, name, type = "text", extra = "") => `<label>${label}<input name="${name}" type="${type}" ${extra}></label>`;
const stat = (n, label, cls = "") => `<div class="stat ${cls}"><b>${n}</b><span>${label}</span></div>`;
const tag = (txt, cls = "") => `<span class="tag ${cls}">${esc(txt)}</span>`;
const searchBar = (extra = "") => `<div class="bar"><input type="search" id="q" placeholder="Search..." value="${esc(S.q)}">${extra}</div>`;
const qs = () => `page=${S.page}&size=${SIZE}&q=${encodeURIComponent(S.q)}`;

/* ------------------------------------------------------------------ shell */
async function boot() { S.me = await api("me"); render(); }
function render() {
  if (!S.me.role) return loginScreen();
  const admin = S.me.role === "admin";
  const items = admin
    ? [["dashboard","Dashboard"],["books","Books"],["borrowers","Borrowers"],["loans","Loans"],["reports","Reports"],["activity","Activity"],["admins","Admins"]]
    : [["browse","Browse Books"],["myloans","My Loans"],["mynotes","Notifications"],["profile","My Profile"]];
  if (!S.view || !items.some(i => i[0] === S.view)) S.view = items[0][0];
  $("#app").innerHTML = `<header><h1>📚 Library Management System</h1>
      <span class="who">${esc(S.me.name)} (${admin ? "Admin" : "Member"})</span>
      <button class="btn sm sec" data-act="logout">Log out</button></header>
    <nav>${items.map(i => `<button class="${S.view === i[0] ? "on" : ""}" data-act="nav" data-v="${i[0]}">${i[1]}</button>`).join("")}</nav>
    <main id="main"></main>`;
  guard(V[S.view])();
}

function loginScreen(mode = "member") {
  const adm = mode === "admin", reg = mode === "register";
  $("#app").innerHTML = `<div class="card login"><h2>📚 Library Management System</h2>
    <div class="tabs">${[["member","Member"],["admin","Admin"],["register","Register"]].map(t =>
      `<button class="btn ${mode === t[0] ? "" : "sec"}" data-act="loginmode" data-m="${t[0]}">${t[1]}</button>`).join("")}</div>
    <form data-form="${reg ? "register" : "login"}" data-role="${adm ? "admin" : "member"}"><div class="form">
    ${reg ? field("First name","firstName","text","required") + field("Last name","lastName","text","required") +
            field("Email","email","email","required") + field("Phone","phone") + field("Date of birth","dob","date") +
            field("Password (min 6)","password","password","required minlength=6")
          : field(adm ? "Username" : "Email","username",adm ? "text" : "email","required") + field("Password","password","password","required")}
    <button class="btn">${reg ? "Create account" : "Log in"}</button></div></form>
    <p class="muted" style="font-size:13px">${adm ? "Demo: admin / admin123" : reg ? "New members can borrow up to 3 books at a time."
      : "Demo member: dwolters0@ft.com / library123 (all seeded members use library123)"}</p></div>`;
}

/* ------------------------------------------------------------------ views */
const V = {
  async dashboard() {
    const d = await api("dashboard");
    $("#main").innerHTML = `<div class="grid">${stat(d.books,"Book titles") + stat(d.available,"Copies available","ok") + stat(d.borrowers,"Members") +
      stat(d.activeLoans,"Active loans") + stat(d.overdue,"Overdue loans", d.overdue ? "bad" : "") + stat(d.dueTomorrow,"Due tomorrow") +
      stat(d.blacklisted,"Blacklisted members") + stat(money(d.feesCollected),"Fees collected","ok")}</div>
      <div class="card"><h3 style="margin-top:0">Quick guide</h3><p class="muted">Use <b>Loans</b> to issue and return books (late fees are calculated
      automatically), <b>Reports</b> for the SQL analytics from the project, and <b>Activity</b> for the audit trail written by the database trigger.
      The seeded loans are from 2024, so every open loan is shown as overdue today.</p></div>`;
  },

  async books() {
    const [g, r] = await Promise.all([api("genres"), api(`books?${qs()}&genre=${encodeURIComponent(S.genre)}&available=${S.avail ? 1 : 0}`)]);
    $("#main").innerHTML = `<div class="card"><h3 style="margin-top:0">Add book</h3><form data-form="addBook"><div class="form">
      ${field("Title","title","text","required") + field("Author","author","text","required") + field("ISBN","isbn","text","required maxlength=13") +
        field("Published","published","date") + field("Genre (A|B|C)","genre") + field("Shelf","shelf","text","maxlength=10") +
        field("Copies","copies","number","min=1 value=1")}<button class="btn">Add Book</button></div></form></div>
      <div class="card">${searchBar(`<select id="genre"><option value="">All genres</option>${g.map(x => `<option ${x === S.genre ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>
        <label><input type="checkbox" id="avail" ${S.avail ? "checked" : ""}> Available only</label>`)}
      ${table([["ID",b=>b.BookID],["Title",b=>`<b>${esc(b.Title)}</b>`],["Author",b=>esc(b.Author)],["ISBN",b=>esc(b.ISBN)],["Genre",b=>esc(b.Genre)],["Shelf",b=>esc(b.ShelfLocation)],
        ["Status",b=>b.AvailableCopies > 0 ? tag(`Available (${b.AvailableCopies}/${b.TotalCopies})`,"ok") : tag("Borrowed","bad") + `<div class="muted">back ~ ${day(b.EarliestReturn)}</div>`],
        ["",b=>`<button class="btn sm red" data-act="delBook" data-id="${b.BookID}">Delete</button>`]], r.rows)}${pager(r.total)}</div>`;
  },

  async borrowers() {
    const r = await api(`borrowers?${qs()}`);
    $("#main").innerHTML = `<div class="card"><h3 style="margin-top:0">Add member</h3><form data-form="addBorrower"><div class="form">
      ${field("First name","firstName","text","required") + field("Last name","lastName","text","required") + field("Email","email","email","required") +
        field("Phone","phone") + field("Date of birth","dob","date")}<button class="btn">Add Borrower</button></div></form>
      <p class="muted" style="font-size:13px;margin-bottom:0">New members get the default password <b>library123</b>.</p></div>
      <div class="card">${searchBar()}${table([["ID",b=>b.BorrowerID],["Name",b=>`<b>${esc(b.FirstName)} ${esc(b.LastName)}</b>`],["Email",b=>esc(b.Email)],
        ["Member since",b=>day(b.MembershipDate)],["Active",b=>b.ActiveLoans],["Late returns",b=>b.LateSubmissionCount],
        ["Status",b=>b.IsBlacklisted ? tag("Blacklisted until " + day(b.BlacklistedUntil),"bad") : tag("Good standing","ok")],
        ["",b=>b.IsBlacklisted ? `<button class="btn sm sec" data-act="unblack" data-id="${b.BorrowerID}">Lift</button>`
                              : `<button class="btn sm red" data-act="black" data-id="${b.BorrowerID}">Blacklist 30d</button>`]], r.rows)}${pager(r.total)}</div>`;
  },

  async loans() {
    const r = await api(`loans?${qs()}&status=${S.status}`);
    const st = [["all","All"],["active","Active"],["overdue","Overdue"],["returned","Returned"],["unpaid","Unpaid fees"]];
    $("#main").innerHTML = `<div class="card"><h3 style="margin-top:0">Issue book</h3><form data-form="addLoan"><div class="form">
      ${field("Book ID","bookId","number","required min=1") + field("Borrower ID","borrowerId","number","required min=1") +
        field("Due date (default +14 days)","dueDate","date")}<button class="btn">Create Loan</button></div></form></div>
      <div class="card">${searchBar(`<select id="status">${st.map(s => `<option value="${s[0]}" ${S.status === s[0] ? "selected" : ""}>${s[1]}</option>`).join("")}</select>`)}
      ${table([["Loan",l=>l.LoanID],["Book",l=>`<b>${esc(l.Title)}</b><div class="muted">#${l.BookID}</div>`],["Member",l=>`${esc(l.BorrowerName)}<div class="muted">#${l.BorrowerID}</div>`],
        ["Borrowed",l=>day(l.DateBorrowed)],["Due",l=>day(l.DueDate)],["Returned",l=>l.DateReturned ? day(l.DateReturned) : (l.DaysOverdue > 0 ? tag(l.DaysOverdue + " days overdue","bad") : tag("On loan","warn"))],
        ["Fee",l=>Number(l.Fee) > 0 ? money(l.Fee) + (l.DateReturned ? (l.FeePaid ? " " + tag("paid","ok") : " " + tag("unpaid","bad")) : "") : "-"],
        ["",l=>!l.DateReturned ? `<button class="btn sm" data-act="return" data-id="${l.LoanID}">Return</button>`
              : (Number(l.Fee) > 0 && !l.FeePaid ? `<button class="btn sm sec" data-act="pay" data-id="${l.LoanID}">Collect fee</button>` : "")]], r.rows)}${pager(r.total)}</div>`;
  },

  async reports() {
    const list = await api("reports");
    if (!S.rep) S.rep = list[0].key;
    const cur = list.find(x => x.key === S.rep);
    $("#main").innerHTML = `<div class="rep"><div class="list card">${list.map(x => `<button class="${x.key === S.rep ? "on" : ""}" data-act="rep" data-k="${x.key}">${esc(x.title)}</button>`).join("")}</div>
      <div class="card"><h3 style="margin-top:0">${esc(cur.title)}</h3><p class="muted">${esc(cur.desc)}<br><small>Original SQL: ${esc(cur.source)}</small></p>
      <form data-form="runReport"><div class="bar">${cur.params.map(p => field(p.label, p.name, p.type, `value="${esc(S.repArgs[p.name] ?? p.default)}"`)).join("")}
      ${cur.params.length ? `<button class="btn">Run</button>` : ""}</div></form><div id="repOut"></div></div></div>`;
    const args = new URLSearchParams(cur.params.map(p => [p.name, S.repArgs[p.name] ?? p.default]));
    const out = await api(`reports/${cur.key}?${args}`);
    $("#repOut").innerHTML = table(out.columns.map(c => [esc(c), r => esc(r[c])]), out.rows, "No rows for these parameters.");
  },

  async activity() {
    const [a, n] = await Promise.all([api("audit"), api("notifications")]);
    $("#main").innerHTML = `<div class="card"><h3 style="margin-top:0">Book status audit log <small class="muted">(written by trigger trg_BookStatusChange)</small></h3>
      ${table([["#",x=>x.AuditID],["Book",x=>esc(x.Title) + ` <span class="muted">#${x.BookID}</span>`],["Change",x=>esc(x.StatusChange)],["When",x=>esc(x.ChangeDate)]], a, "No status changes yet - issue or return a book.")}</div>
      <div class="card"><div class="bar"><h3 style="margin:0;margin-right:auto">Notifications</h3><button class="btn sm" data-act="remind">Send due-tomorrow reminders</button></div>
      ${table([["When",x=>esc(x.CreatedAt)],["To",x=>esc(x.BorrowerName) + `<div class="muted">${esc(x.Email)}</div>`],["Message",x=>esc(x.Message)]], n, "No notifications yet.")}</div>`;
  },

  async admins() {
    const a = await api("admins");
    $("#main").innerHTML = `<div class="card"><h3 style="margin-top:0">Add admin</h3><form data-form="addAdmin"><div class="form">
      ${field("Username","username","text","required") + field("Email","email","email") + field("Password (min 6)","password","password","required minlength=6")}
      <button class="btn">Add Admin</button></div></form></div>
      <div class="card">${table([["ID",x=>x.AdminID],["Username",x=>esc(x.Username)],["Email",x=>esc(x.Email)],["Created",x=>esc(x.CreatedAt)]], a)}</div>`;
  },

  /* ---- member views ---- */
  async browse() {
    const [g, r] = await Promise.all([api("genres"), api(`books?${qs()}&genre=${encodeURIComponent(S.genre)}&available=${S.avail ? 1 : 0}`)]);
    $("#main").innerHTML = `<div class="card">${searchBar(`<select id="genre"><option value="">All genres</option>${g.map(x => `<option ${x === S.genre ? "selected" : ""}>${esc(x)}</option>`).join("")}</select>
      <label><input type="checkbox" id="avail" ${S.avail ? "checked" : ""}> Available only</label>`)}
      ${table([["Title",b=>`<b>${esc(b.Title)}</b>`],["Author",b=>esc(b.Author)],["Genre",b=>esc(b.Genre)],["Shelf",b=>esc(b.ShelfLocation)],
        ["Availability",b=>b.AvailableCopies > 0 ? tag("Available","ok") : tag("On loan","bad") + `<div class="muted">back ~ ${day(b.EarliestReturn)}</div>`],
        ["",b=>`<button class="btn sm" data-act="borrow" data-id="${b.BookID}" ${b.AvailableCopies > 0 ? "" : "disabled"}>Borrow</button>`]], r.rows)}${pager(r.total)}</div>`;
  },

  async myloans() {
    const r = await api("my/loans");
    $("#main").innerHTML = `<div class="card"><h3 style="margin-top:0">Currently borrowed (${r.active.length} of ${r.limit})</h3>
      ${table([["Title",l=>`<b>${esc(l.Title)}</b>`],["Author",l=>esc(l.Author)],["Borrowed",l=>day(l.DateBorrowed)],["Due",l=>day(l.DueDate)],
        ["Status",l=>l.DaysOverdue > 0 ? tag(l.DaysOverdue + " days overdue","bad") : tag("On time","ok")],["Fee so far",l=>money(l.CurrentFee)]], r.active, "You have no books on loan. Returns are handled at the library desk.")}</div>
      <div class="card"><h3 style="margin-top:0">History</h3>
      ${table([["Title",l=>esc(l.Title)],["Borrowed",l=>day(l.DateBorrowed)],["Due",l=>day(l.DueDate)],["Returned",l=>day(l.DateReturned)],
        ["Late fee",l=>Number(l.LateFeeAmount) > 0 ? money(l.LateFeeAmount) + (l.FeePaid ? " " + tag("paid","ok") : " " + tag("unpaid","bad")) : "-"]], r.history.filter(l => l.DateReturned), "No past loans.")}</div>`;
  },

  async mynotes() {
    const n = await api("my/notifications");
    $("#main").innerHTML = `<div class="card"><h3 style="margin-top:0">Notifications</h3>${table([["When",x=>esc(x.CreatedAt)],["Message",x=>esc(x.Message)]], n, "No notifications.")}</div>`;
  },

  async profile() {
    const p = await api("my/profile");
    $("#main").innerHTML = `<div class="card"><h3 style="margin-top:0">${esc(p.FirstName)} ${esc(p.LastName)}</h3>
      <p>Email: ${esc(p.Email)}<br>Phone: ${esc(p.Phone || "-")}<br>Date of birth: ${day(p.DateOfBirth)}<br>Member since: ${day(p.MembershipDate)}<br>
      Late returns: ${p.LateSubmissionCount}<br>Status: ${p.IsBlacklisted ? tag("Blacklisted until " + day(p.BlacklistedUntil),"bad") : tag("Good standing","ok")}</p>
      <p class="muted">Members are blacklisted for 30 days after 4 late returns.</p></div>`;
  },
};

/* ------------------------------------------------------------------ events */
const go = () => guard(V[S.view])();
const reset = () => { S.page = 1; S.q = ""; S.genre = ""; S.avail = false; S.status = "all"; };

const ACT = {
  logout: async () => { await api("logout", "POST"); S = { ...S, me: { role: null }, view: "" }; reset(); render(); },
  nav: el => { S.view = el.dataset.v; reset(); render(); },
  loginmode: el => loginScreen(el.dataset.m),
  prev: () => { S.page--; go(); }, next: () => { S.page++; go(); },
  delBook: async el => { if (!confirm("Delete this book?")) return; await api("books/" + el.dataset.id, "DELETE"); toast("Book deleted"); go(); },
  black: async el => { await api(`borrowers/${el.dataset.id}/blacklist`, "POST", { days: 30 }); toast("Member blacklisted for 30 days"); go(); },
  unblack: async el => { await api(`borrowers/${el.dataset.id}/unblacklist`, "POST"); toast("Blacklist lifted"); go(); },
  return: async el => { const r = await api(`loans/${el.dataset.id}/return`, "POST"); toast(r.fee > 0 ? `Returned. Late fee: ${money(r.fee)}` : "Returned on time"); go(); },
  pay: async el => { await api(`loans/${el.dataset.id}/pay`, "POST", {}); toast("Fee collected"); go(); },
  borrow: async el => { await api("borrow", "POST", { bookId: el.dataset.id }); toast("Book borrowed - due in 14 days"); go(); },
  rep: el => { S.rep = el.dataset.k; S.repArgs = {}; go(); },
  remind: async () => { const r = await api("reminders", "POST"); toast(`${r.sent} reminder(s) created`); go(); },
};

const FORMS = {
  login: async (d, f) => { S.me = await api("login", "POST", { role: f.dataset.role, username: d.username, password: d.password }); S.view = ""; render(); },
  register: async d => { await api("register", "POST", d); toast("Account created - you can log in now"); loginScreen("member"); },
  addBook: async d => { await api("books", "POST", d); toast("Book added"); go(); },
  addBorrower: async d => { await api("borrowers", "POST", d); toast("Member added"); go(); },
  addLoan: async d => { await api("loans", "POST", d); toast("Loan created"); go(); },
  addAdmin: async d => { await api("admins", "POST", d); toast("Admin added"); go(); },
  runReport: async d => { S.repArgs = d; go(); },
};

document.addEventListener("click", e => { const el = e.target.closest("[data-act]"); if (el && ACT[el.dataset.act]) guard(ACT[el.dataset.act])(el); });
document.addEventListener("submit", e => { const f = e.target.closest("form[data-form]"); if (!f) return; e.preventDefault();
  guard(FORMS[f.dataset.form])(Object.fromEntries(new FormData(f)), f); });
let qTimer;
document.addEventListener("input", e => { if (e.target.id !== "q") return; clearTimeout(qTimer);
  qTimer = setTimeout(async () => { S.q = e.target.value; S.page = 1; await go();
    const q = $("#q"); if (q) { q.focus(); q.setSelectionRange(q.value.length, q.value.length); } }, 350); });
document.addEventListener("change", e => {
  if (e.target.id === "genre") { S.genre = e.target.value; S.page = 1; go(); }
  if (e.target.id === "avail") { S.avail = e.target.checked; S.page = 1; go(); }
  if (e.target.id === "status") { S.status = e.target.value; S.page = 1; go(); } });
boot();
