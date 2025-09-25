CREATE TABLE `ChargingPoints` (
  `cp_id` integer PRIMARY KEY,
  `location_address` varchar(255),
  `price_per_kwh` decimal,
  `status` enum(activado,parado,suministrando,averiado,desconectado),
  `last_connection_time` timestamp
);

CREATE TABLE `Drivers` (
  `driver_id` integer PRIMARY KEY,
  `username` varchar(255),
  `created_at` timestamp
);

CREATE TABLE `ChargingSessions` (
  `session_id` integer PRIMARY KEY,
  `cp_id` integer,
  `driver_id` integer,
  `start_time` timestamp,
  `end_time` timestamp,
  `energy_consumed_kwh` decimal,
  `total_cost` decimal,
  `status` enum(requested,authorized,in_progress,completed,cancelled,failed)
);

CREATE TABLE `CentralStatusLog` (
  `log_id` integer PRIMARY KEY,
  `creat_at` timestamp,
  `event_type` enum(request for charging,...),
  `details` text
);

ALTER TABLE `ChargingSessions` ADD FOREIGN KEY (`cp_id`) REFERENCES `ChargingPoints` (`cp_id`);

ALTER TABLE `ChargingSessions` ADD FOREIGN KEY (`driver_id`) REFERENCES `Drivers` (`driver_id`);
