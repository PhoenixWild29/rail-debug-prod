-- Migration: 036_rail036_webhooks
-- Add webhook notification support for Slack and Discord

ALTER TABLE users ADD COLUMN slack_webhook_url TEXT;
ALTER TABLE users ADD COLUMN discord_webhook_url TEXT;