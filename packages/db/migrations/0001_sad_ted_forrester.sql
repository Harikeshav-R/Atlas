CREATE TABLE `listings` (
	`listing_id` text PRIMARY KEY NOT NULL,
	`canonical_url` text NOT NULL,
	`company_name` text NOT NULL,
	`role_title` text NOT NULL,
	`location` text,
	`remote_model` text DEFAULT 'unknown' NOT NULL,
	`description_markdown` text,
	`description_hash` text,
	`first_seen_at` text NOT NULL,
	`last_seen_at` text NOT NULL,
	`removed_at` text,
	`status` text DEFAULT 'active' NOT NULL
);
--> statement-breakpoint
CREATE UNIQUE INDEX `listings_canonical_url_idx` ON `listings` (`canonical_url`);--> statement-breakpoint
CREATE INDEX `listings_company_name_idx` ON `listings` (`company_name`);--> statement-breakpoint
CREATE INDEX `listings_first_seen_at_idx` ON `listings` (`first_seen_at`);--> statement-breakpoint
CREATE INDEX `listings_status_idx` ON `listings` (`status`);--> statement-breakpoint
CREATE TABLE `listing_snapshots` (
	`snapshot_id` text PRIMARY KEY NOT NULL,
	`listing_id` text NOT NULL,
	`captured_at` text NOT NULL,
	`raw_html_path` text,
	`extracted_text` text,
	`content_hash` text,
	FOREIGN KEY (`listing_id`) REFERENCES `listings`(`listing_id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `listing_snapshots_listing_id_idx` ON `listing_snapshots` (`listing_id`);--> statement-breakpoint
CREATE TABLE `evaluations` (
	`evaluation_id` text PRIMARY KEY NOT NULL,
	`listing_id` text NOT NULL,
	`profile_version` integer NOT NULL,
	`agent_run_id` text,
	`grade` text NOT NULL,
	`score` real NOT NULL,
	`six_blocks_json` text NOT NULL,
	`summary_text` text NOT NULL,
	`created_at` text NOT NULL,
	FOREIGN KEY (`listing_id`) REFERENCES `listings`(`listing_id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`agent_run_id`) REFERENCES `runs`(`run_id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE UNIQUE INDEX `evaluations_listing_profile_idx` ON `evaluations` (`listing_id`,`profile_version`);--> statement-breakpoint
CREATE TABLE `scorecards` (
	`scorecard_id` text PRIMARY KEY NOT NULL,
	`evaluation_id` text NOT NULL,
	`dimensions_json` text NOT NULL,
	`weighted_total` real NOT NULL,
	FOREIGN KEY (`evaluation_id`) REFERENCES `evaluations`(`evaluation_id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE UNIQUE INDEX `scorecards_evaluation_id_idx` ON `scorecards` (`evaluation_id`);--> statement-breakpoint
CREATE TABLE `preferences` (
	`preferences_id` text PRIMARY KEY NOT NULL,
	`profile_id` text NOT NULL,
	`scoring_weights_json` text,
	`grade_thresholds_json` text,
	`model_routing_json` text,
	`budgets_json` text,
	`notification_prefs_json` text,
	`updated_at` text NOT NULL,
	FOREIGN KEY (`profile_id`) REFERENCES `profiles`(`profile_id`) ON UPDATE no action ON DELETE cascade
);
