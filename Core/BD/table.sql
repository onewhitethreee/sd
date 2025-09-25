CREATE TABLE IF NOT EXISTS `ChargingPoints` (
  `cp_id` integer PRIMARY KEY AUTOINCREMENT, 
  `location_address` varchar(255),
  `price_per_kwh` decimal(10,4),
  `status` TEXT NOT NULL DEFAULT 'unknown' CHECK (`status` IN ('active', 'stopped', 'supplying', 'faulty', 'disconnected')),
  `last_connection_time` DATETIME 
);

CREATE TABLE IF NOT EXISTS `Drivers` (
  `driver_id` integer PRIMARY KEY AUTOINCREMENT,
  `username` varchar(255),
  `created_at` DATETIME
);

CREATE TABLE IF NOT EXISTS `ChargingSessions` (
  `session_id` integer PRIMARY KEY AUTOINCREMENT,
  `cp_id` integer,
  `driver_id` integer,
  `start_time` DATETIME,
  `end_time` DATETIME,
  `energy_consumed_kwh` decimal(12,2),
  `total_cost` decimal(12,2),
  `status` TEXT NOT NULL DEFAULT 'requested' CHECK (`status` IN ('requested', 'authorized', 'in_progress', 'completed', 'cancelled', 'failed')),
  FOREIGN KEY (`cp_id`) REFERENCES `ChargingPoints` (`cp_id`),
  FOREIGN KEY (`driver_id`) REFERENCES `Drivers` (`driver_id`)
);

-- Removed unsupported ALTER TABLE statements; SQLite does not support adding foreign keys via ALTER


