-- SQLite version of the original SQL Server schema (SchemaCreation.sql),
-- extended with the extra tables/columns used by database.py
-- (admins, passwords, copies, late fees, blacklist, notifications).
PRAGMA foreign_keys = ON;

CREATE TABLE IF NOT EXISTS Books (
  BookID          INTEGER PRIMARY KEY AUTOINCREMENT,
  Title           TEXT NOT NULL,
  Author          TEXT NOT NULL,
  ISBN            TEXT NOT NULL UNIQUE,
  PublishedDate   DATE,
  Genre           TEXT,
  Subject         TEXT,                       -- main genre (first one listed)
  ShelfLocation   TEXT,
  TotalCopies     INTEGER NOT NULL DEFAULT 1 CHECK (TotalCopies >= 0),
  AvailableCopies INTEGER NOT NULL DEFAULT 1 CHECK (AvailableCopies >= 0),
  CurrentStatus   TEXT NOT NULL CHECK (CurrentStatus IN ('Available','Borrowed'))
);

CREATE TABLE IF NOT EXISTS Borrowers (
  BorrowerID          INTEGER PRIMARY KEY AUTOINCREMENT,
  FirstName           TEXT NOT NULL,
  LastName            TEXT NOT NULL,
  Email               TEXT NOT NULL UNIQUE,
  Phone               TEXT,
  DateOfBirth         DATE,
  MembershipDate      DATE NOT NULL,
  PasswordHash        TEXT,
  LateSubmissionCount INTEGER NOT NULL DEFAULT 0,
  IsBlacklisted       INTEGER NOT NULL DEFAULT 0,
  BlacklistedUntil    DATE
);

CREATE TABLE IF NOT EXISTS Loans (
  LoanID        INTEGER PRIMARY KEY AUTOINCREMENT,
  BookID        INTEGER NOT NULL REFERENCES Books(BookID),
  BorrowerID    INTEGER NOT NULL REFERENCES Borrowers(BorrowerID),
  DateBorrowed  DATE NOT NULL,
  DueDate       DATE NOT NULL,
  DateReturned  DATE,
  LateFeeAmount REAL NOT NULL DEFAULT 0,
  IsLate        INTEGER NOT NULL DEFAULT 0,
  FeePaid       INTEGER NOT NULL DEFAULT 0,
  CONSTRAINT CHK_DueDate      CHECK (DueDate >= DateBorrowed),
  CONSTRAINT CHK_DateReturned CHECK (DateReturned IS NULL OR DateReturned >= DateBorrowed)
);

CREATE TABLE IF NOT EXISTS Admins (
  AdminID      INTEGER PRIMARY KEY AUTOINCREMENT,
  Username     TEXT NOT NULL UNIQUE,
  Email        TEXT,
  PasswordHash TEXT NOT NULL,
  CreatedBy    INTEGER,
  CreatedAt    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS FeeCollections (
  CollectionID INTEGER PRIMARY KEY AUTOINCREMENT,
  LoanID       INTEGER NOT NULL REFERENCES Loans(LoanID),
  BorrowerID   INTEGER NOT NULL REFERENCES Borrowers(BorrowerID),
  AmountPaid   REAL NOT NULL,
  CollectedBy  INTEGER REFERENCES Admins(AdminID),
  CollectedAt  DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS Notifications (
  NotificationID INTEGER PRIMARY KEY AUTOINCREMENT,
  BorrowerID     INTEGER NOT NULL REFERENCES Borrowers(BorrowerID),
  LoanID         INTEGER REFERENCES Loans(LoanID),
  Message        TEXT NOT NULL,
  NotifType      TEXT NOT NULL DEFAULT 'due_reminder',
  CreatedAt      DATETIME DEFAULT CURRENT_TIMESTAMP
);

-- Original trg_BookStatusChange (T-SQL trigger) -> SQLite trigger
CREATE TABLE IF NOT EXISTS AuditLog (
  AuditID      INTEGER PRIMARY KEY AUTOINCREMENT,
  BookID       INTEGER NOT NULL,
  StatusChange TEXT NOT NULL,
  ChangeDate   DATETIME NOT NULL DEFAULT CURRENT_TIMESTAMP
);

CREATE TRIGGER IF NOT EXISTS trg_BookStatusChange
AFTER UPDATE OF CurrentStatus ON Books
WHEN OLD.CurrentStatus <> NEW.CurrentStatus
BEGIN
  INSERT INTO AuditLog (BookID, StatusChange)
  VALUES (NEW.BookID, 'Changed from ' || OLD.CurrentStatus || ' to ' || NEW.CurrentStatus);
END;

-- Original Indexes.sql
CREATE INDEX IF NOT EXISTS Loans_BorrowerID_BookID_Idx    ON Loans (BorrowerID, BookID);
CREATE INDEX IF NOT EXISTS Loans_BookID_DateBorrowed_Idx  ON Loans (BookID, DateBorrowed);
CREATE INDEX IF NOT EXISTS Books_BookID_Genre_Idx         ON Books (BookID, Genre);
CREATE INDEX IF NOT EXISTS Loans_BookID_DateReturned_Idx  ON Loans (BookID, DateReturned);
CREATE INDEX IF NOT EXISTS Loans_DueDate_DateReturned_Idx ON Loans (DueDate, DateReturned);
