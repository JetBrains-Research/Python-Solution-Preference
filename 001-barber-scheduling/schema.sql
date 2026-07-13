CREATE TABLE appointments (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT NOT NULL,
    start_time TEXT NOT NULL,
    end_time TEXT NOT NULL,
    barber TEXT NOT NULL,
    customer_name TEXT NOT NULL,
    notes TEXT,
    UNIQUE(date, start_time, barber)
);
