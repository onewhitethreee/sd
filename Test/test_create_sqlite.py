import sqlite3

# 直接测试创建表
conn = sqlite3.connect("ev_central.db")
conn.executescript(
    """
CREATE TABLE IF NOT EXISTS ChargingPoints (
    cp_id text PRIMARY KEY,
    location varchar(255),
    price_per_kwh decimal(10, 4),
    status TEXT NOT NULL DEFAULT 'unknown',
    last_connection_time DATETIME
);

CREATE TABLE IF NOT EXISTS Drivers (
    driver_id text PRIMARY KEY,
    username varchar(255),
    created_at DATETIME
);

CREATE TABLE IF NOT EXISTS ChargingSessions (
    session_id text PRIMARY KEY,
    cp_id text,
    driver_id text,
    start_time DATETIME,
    end_time DATETIME,
    energy_consumed_kwh decimal(12, 2),
    total_cost decimal(12, 2),
    status TEXT NOT NULL DEFAULT 'requested',
    FOREIGN KEY (cp_id) REFERENCES ChargingPoints (cp_id),
    FOREIGN KEY (driver_id) REFERENCES Drivers (driver_id)
);
"""
)
conn.commit()
conn.close()
