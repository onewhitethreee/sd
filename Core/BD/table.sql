CREATE TABLE IF NOT EXISTS `ChargingPoints` (
  `cp_id` text PRIMARY KEY,
  `location` varchar(255),
  `price_per_kwh` decimal(10, 4),
  `max_charging_rate_kw` decimal(5, 1) DEFAULT 11.0,
  `status` TEXT NOT NULL DEFAULT 'unknown' CHECK (
    `status` IN (
      'ACTIVE',
      'STOPPED',
      'DISCONNECTED',
      'FAULTY',
      'CHARGING'
    )
  ),
  `last_connection_time` DATETIME
);

CREATE TABLE IF NOT EXISTS `Drivers` (
  `driver_id` text PRIMARY KEY,
  `username` varchar(255),
  `created_at` DATETIME
);

CREATE TABLE IF NOT EXISTS `ChargingSessions` (
  `session_id` text PRIMARY KEY,
  `cp_id` text,
  `driver_id` text,
  `start_time` DATETIME,
  `end_time` DATETIME,
  `energy_consumed_kwh` decimal(12, 2),
  `total_cost` decimal(12, 2),
  `status` TEXT NOT NULL DEFAULT 'requested' CHECK (
    `status` IN (
      'requested',
      'authorized',
      'in_progress',
      'completed',
      'cancelled',
      'failed'
    )
  ),
  FOREIGN KEY (`cp_id`) REFERENCES `ChargingPoints` (`cp_id`),
  FOREIGN KEY (`driver_id`) REFERENCES `Drivers` (`driver_id`)
);
