CREATE TABLE `discovery_cache` (
	`key` text PRIMARY KEY NOT NULL,
	`payload` text NOT NULL,
	`fetched_at` integer NOT NULL
);
--> statement-breakpoint
CREATE TABLE `tracked_startups` (
	`id` text PRIMARY KEY NOT NULL,
	`owner` text NOT NULL,
	`identity` text NOT NULL,
	`record` text NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `tracked_owner_identity` ON `tracked_startups` (`owner`,`identity`);