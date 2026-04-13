CREATE TABLE `profiles` (
	`profile_id` text PRIMARY KEY NOT NULL,
	`yaml_blob` text NOT NULL,
	`parsed_json` text NOT NULL,
	`version` integer NOT NULL,
	`schema_version` integer NOT NULL,
	`created_at` text NOT NULL,
	`updated_at` text NOT NULL
);
--> statement-breakpoint
CREATE TABLE `runs` (
	`run_id` text PRIMARY KEY NOT NULL,
	`parent_run_id` text,
	`agent_name` text NOT NULL,
	`mode` text NOT NULL,
	`input_hash` text,
	`input_json` text,
	`model_id` text,
	`fallback_used` integer DEFAULT 0,
	`started_at` text NOT NULL,
	`ended_at` text,
	`status` text NOT NULL,
	`result_json` text,
	`total_cost_usd` real,
	`total_tokens` integer,
	`iterations_used` integer,
	`eval_suite_id` text,
	FOREIGN KEY (`parent_run_id`) REFERENCES `runs`(`run_id`) ON UPDATE no action ON DELETE set null
);
--> statement-breakpoint
CREATE INDEX `runs_agent_name_idx` ON `runs` (`agent_name`);--> statement-breakpoint
CREATE INDEX `runs_status_idx` ON `runs` (`status`);--> statement-breakpoint
CREATE INDEX `runs_started_at_idx` ON `runs` (`started_at`);--> statement-breakpoint
CREATE TABLE `trace_events` (
	`event_id` text PRIMARY KEY NOT NULL,
	`run_id` text NOT NULL,
	`parent_event_id` text,
	`step_index` integer NOT NULL,
	`timestamp` text NOT NULL,
	`type` text NOT NULL,
	`actor` text,
	`payload_json` text,
	`cost_usd` real,
	`duration_ms` integer,
	FOREIGN KEY (`run_id`) REFERENCES `runs`(`run_id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`parent_event_id`) REFERENCES `trace_events`(`event_id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `trace_events_run_id_idx` ON `trace_events` (`run_id`);--> statement-breakpoint
CREATE INDEX `trace_events_run_id_step_index_idx` ON `trace_events` (`run_id`,`step_index`);--> statement-breakpoint
CREATE INDEX `trace_events_type_idx` ON `trace_events` (`type`);--> statement-breakpoint
CREATE TABLE `approvals` (
	`approval_id` text PRIMARY KEY NOT NULL,
	`run_id` text NOT NULL,
	`scope` text NOT NULL,
	`title` text NOT NULL,
	`description` text NOT NULL,
	`screenshot_path` text,
	`options_json` text NOT NULL,
	`status` text NOT NULL,
	`user_response_json` text,
	`requested_at` text NOT NULL,
	`responded_at` text,
	`timeout_at` text NOT NULL,
	FOREIGN KEY (`run_id`) REFERENCES `runs`(`run_id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `approvals_status_idx` ON `approvals` (`status`);--> statement-breakpoint
CREATE INDEX `approvals_run_id_idx` ON `approvals` (`run_id`);--> statement-breakpoint
CREATE TABLE `costs` (
	`cost_id` text PRIMARY KEY NOT NULL,
	`run_id` text NOT NULL,
	`event_id` text NOT NULL,
	`model_id` text NOT NULL,
	`prompt_tokens` integer NOT NULL,
	`output_tokens` integer NOT NULL,
	`cost_usd` real NOT NULL,
	`timestamp` text NOT NULL,
	FOREIGN KEY (`run_id`) REFERENCES `runs`(`run_id`) ON UPDATE no action ON DELETE cascade,
	FOREIGN KEY (`event_id`) REFERENCES `trace_events`(`event_id`) ON UPDATE no action ON DELETE cascade
);
--> statement-breakpoint
CREATE INDEX `costs_run_id_idx` ON `costs` (`run_id`);--> statement-breakpoint
CREATE INDEX `costs_timestamp_idx` ON `costs` (`timestamp`);--> statement-breakpoint
CREATE INDEX `costs_model_id_idx` ON `costs` (`model_id`);--> statement-breakpoint
CREATE TABLE `model_pricing` (
	`model_id` text PRIMARY KEY NOT NULL,
	`prompt_token_cost_usd_per_million` real NOT NULL,
	`output_token_cost_usd_per_million` real NOT NULL,
	`effective_from` text,
	`effective_to` text
);
--> statement-breakpoint
CREATE TABLE `audit_log` (
	`log_id` text PRIMARY KEY NOT NULL,
	`timestamp` text NOT NULL,
	`actor` text NOT NULL,
	`action` text NOT NULL,
	`target_kind` text,
	`target_id` text,
	`details_json` text
);
