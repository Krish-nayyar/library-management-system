"""The analytical requirements from the SQL Server project (Requirements/*), translated to SQLite.
Each report: key -> title, original file, description, parameters and SQL."""
from database import run_query

REPORTS = {
  "overdue_borrowers": dict(
    title="Overdue Borrowers", source="Procedures/sp_GetOverDueBorrowers.sql", params=[],
    desc="Members who still hold a book past its due date (stored procedure sp_GetOverdueBorrowers).",
    sql="""SELECT br.BorrowerID, br.FirstName||' '||br.LastName AS FullName, l.BookID, b.Title, l.DueDate,
                  CAST(julianday('now','localtime')-julianday(l.DueDate) AS INT) AS DaysOverdue
           FROM Borrowers br JOIN Loans l ON br.BorrowerID=l.BorrowerID JOIN Books b ON l.BookID=b.BookID
           WHERE l.DueDate < date('now','localtime') AND l.DateReturned IS NULL
           ORDER BY br.BorrowerID LIMIT 500"""),
  "borrowed_report": dict(
    title="Borrowed Books Report", source="Procedures/sp_BorrowedBooksReport.sql",
    params=[dict(name="start", label="From", type="date", default="2024-01-01"),
            dict(name="end", label="To", type="date", default="2024-01-31")],
    desc="Every loan started between two dates (stored procedure sp_BorrowedBooksReport).",
    sql="""SELECT b.Title, l.LoanID, l.DateBorrowed, l.DueDate, l.DateReturned,
                  br.FirstName||' '||br.LastName AS FullName
           FROM Books b JOIN Loans l ON b.BookID=l.BookID JOIN Borrowers br ON br.BorrowerID=l.BorrowerID
           WHERE l.DateBorrowed >= :start AND l.DateBorrowed <= :end ORDER BY l.DateBorrowed LIMIT 500"""),
  "overdue_analysis": dict(
    title="Overdue Analysis (> 30 days)", source="Queries/OverdueAnalysis.sql", params=[],
    desc="Loans overdue by more than 30 days (returned ones are measured up to the return date).",
    sql="""SELECT b.Title AS BookTitle,
                  CAST(julianday(COALESCE(l.DateReturned,date('now','localtime')))-julianday(l.DueDate) AS INT) AS DaysOverdue,
                  br.BorrowerID, br.FirstName, br.LastName, br.Email
           FROM Books b JOIN Loans l ON b.BookID=l.BookID JOIN Borrowers br ON br.BorrowerID=l.BorrowerID
           WHERE julianday(COALESCE(l.DateReturned,date('now','localtime')))-julianday(l.DueDate) > 30
           ORDER BY DaysOverdue DESC LIMIT 500"""),
  "active_borrowers": dict(
    title="Active Borrowers (CTE)", source="Queries/ActiveBorrowersWithCTEs.sql", params=[],
    desc="Members currently holding 2 or more books, built with a Common Table Expression.",
    sql="""WITH ActiveBorrowers AS (
             SELECT BorrowerID, COUNT(LoanID) AS BorrowCount FROM Loans WHERE DateReturned IS NULL GROUP BY BorrowerID)
           SELECT br.BorrowerID, br.FirstName, br.LastName, br.Email, ab.BorrowCount
           FROM Borrowers br JOIN ActiveBorrowers ab ON ab.BorrowerID=br.BorrowerID
           WHERE ab.BorrowCount >= 2 ORDER BY ab.BorrowCount DESC, br.BorrowerID"""),
  "borrower_ranking": dict(
    title="Borrowing Frequency Ranking (Window Function)", source="Queries/BorrowingFrequencyUsingWindowFunctions.sql",
    params=[], desc="Members ranked by number of loans using DENSE_RANK() OVER (...). Top 50 shown.",
    sql="""WITH BorrowedCounts AS (SELECT BorrowerID, COUNT(LoanID) AS BorrowCount FROM Loans GROUP BY BorrowerID)
           SELECT br.FirstName||' '||br.LastName AS FullName, bc.BorrowCount,
                  DENSE_RANK() OVER (ORDER BY bc.BorrowCount DESC) AS BorrowingRank
           FROM Borrowers br JOIN BorrowedCounts bc ON bc.BorrowerID=br.BorrowerID
           ORDER BY BorrowingRank, FullName LIMIT 50"""),
  "popular_genre": dict(
    title="Popular Genres by Month", source="Queries/PopularGenreAnalysis.sql",
    params=[dict(name="month", label="Month (1-12)", type="number", default=1)],
    desc="Genre ranking for loans started in a given month of any year. Top 50 shown.",
    sql="""WITH MonthlyGenreCount AS (
             SELECT b.Genre, COUNT(l.LoanID) AS GenreCount FROM Loans l JOIN Books b ON b.BookID=l.BookID
             WHERE CAST(strftime('%m', l.DateBorrowed) AS INT) = :month AND b.Genre <> '(no genres listed)'
             GROUP BY b.Genre)
           SELECT Genre, GenreCount, DENSE_RANK() OVER (ORDER BY GenreCount DESC) AS GenreRank
           FROM MonthlyGenreCount ORDER BY GenreRank, Genre LIMIT 50"""),
  "author_popularity": dict(
    title="Author Popularity", source="Queries/AuthorPopularity.sql + Functions/fn_BookBorrowingFrequency.sql",
    params=[], desc="Authors ranked by total times their books were borrowed. Top 50 shown.",
    sql="""WITH AuthorTotals AS (
             SELECT b.Author, COUNT(l.LoanID) AS TotalBorrowings FROM Books b LEFT JOIN Loans l ON l.BookID=b.BookID
             GROUP BY b.Author)
           SELECT Author, TotalBorrowings, DENSE_RANK() OVER (ORDER BY TotalBorrowings DESC) AS AuthorRank
           FROM AuthorTotals ORDER BY AuthorRank, Author LIMIT 50"""),
  "book_frequency": dict(
    title="Book Borrowing Frequency", source="Functions/fn_BookBorrowingFrequency.sql", params=[],
    desc="Most borrowed books. Top 50 shown.",
    sql="""SELECT b.Title, COUNT(l.LoanID) AS BookBorrowingFrequency
           FROM Books b LEFT JOIN Loans l ON l.BookID=b.BookID GROUP BY b.BookID
           ORDER BY BookBorrowingFrequency DESC, b.Title LIMIT 50"""),
  "weekly_peak": dict(
    title="Weekly Peak Days", source="Queries/WeeklyPeakDays.sql", params=[],
    desc="The 3 weekdays with the most loans and their share of all loans.",
    sql="""SELECT CASE strftime('%w', DateBorrowed) WHEN '0' THEN 'Sunday' WHEN '1' THEN 'Monday' WHEN '2' THEN 'Tuesday'
                  WHEN '3' THEN 'Wednesday' WHEN '4' THEN 'Thursday' WHEN '5' THEN 'Friday' ELSE 'Saturday' END AS LoanDay,
                  COUNT(*) AS Loans, ROUND(COUNT(*)*100.0/(SELECT COUNT(*) FROM Loans), 2) AS PercentageOfLoans
           FROM Loans GROUP BY strftime('%w', DateBorrowed) ORDER BY COUNT(*) DESC LIMIT 3"""),
  "genre_by_age": dict(
    title="Genre Preference by Age Group", source="Queries/GenrePreferenceByAge.sql", params=[],
    desc="The most borrowed genre in each age group (function fn_GetAgeGroup).",
    sql="""WITH AgeGroupGenre AS (
             SELECT b.Genre, fn_GetAgeGroup(br.DateOfBirth) AS AgeGroup
             FROM Borrowers br JOIN Loans l ON br.BorrowerID=l.BorrowerID JOIN Books b ON l.BookID=b.BookID),
           Counts AS (SELECT AgeGroup, Genre, COUNT(*) AS Borrowings FROM AgeGroupGenre GROUP BY AgeGroup, Genre)
           SELECT AgeGroup, Genre, Borrowings FROM Counts c
           WHERE Borrowings = (SELECT MAX(Borrowings) FROM Counts WHERE AgeGroup=c.AgeGroup)
           ORDER BY AgeGroup"""),
  "overdue_fees": dict(
    title="Overdue Fees per Loan", source="Functions/fn_CalculateOverdueFees.sql", params=[],
    desc="Fee for every unreturned late loan: 1 per day up to 30 days, 3 per day after that. Top 100 shown.",
    sql="""SELECT l.LoanID, l.BookID, l.BorrowerID, l.DueDate,
                  CAST(julianday('now','localtime')-julianday(l.DueDate) AS INT) AS DaysOverdue,
                  fn_CalculateOverdueFees(l.DueDate, NULL) AS OverdueFees
           FROM Loans l WHERE l.DateReturned IS NULL AND l.DueDate < date('now','localtime')
           ORDER BY OverdueFees DESC LIMIT 100"""),
  "borrower_history": dict(
    title="Books Borrowed by a Member", source="Queries/ListOfBorrowedBooks.sql",
    params=[dict(name="borrower", label="Borrower ID", type="number", default=866)],
    desc="Full borrowing history of one member.",
    sql="""SELECT b.Title, b.Author, l.DateBorrowed, l.DateReturned FROM Loans l JOIN Books b ON l.BookID=b.BookID
           WHERE l.BorrowerID = :borrower ORDER BY l.DateBorrowed"""),
}

def list_reports():
    return [dict(key=k, title=v["title"], source=v["source"], desc=v["desc"], params=v["params"])
            for k, v in REPORTS.items()]

def run_report(key, args):
    r = REPORTS.get(key)
    if not r:
        raise ValueError("Unknown report")
    p = {}
    for prm in r["params"]:
        v = args.get(prm["name"], prm["default"])
        p[prm["name"]] = int(v) if prm["type"] == "number" else str(v)
    rows = run_query(r["sql"], p)
    return {"title": r["title"], "columns": list(rows[0].keys()) if rows else [], "rows": rows}
