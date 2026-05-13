# Agent Handoff — Sprint 4.9: Announcement Channel

## Branch
`devin/1778711591-sprint-4-9-announcements`

## Status
All implementation complete. CI checks: lint ✓, typecheck ✓, imports ✓, tests ✓ (45 new tests, pre-existing dashboard integration failures only).

## What was done
- Domain layer: `domain/announcements/` (IAnnouncementPublisher port, WeeklyDigest/LeaderboardSnapshot entities)
- Application layer: `application/announcements/` (PublishWeeklyDigest, PublishLeaderboard use-cases, IAnnouncementStatsQuery)
- Infrastructure: `infrastructure/announcements/` (AiogramAnnouncementPublisher, SqlAlchemyAnnouncementStatsQuery)
- Settings: announcement_channel_id, announcement_weekly_enabled, announcement_weekly_cron in BotSettings
- Bot integration: background scheduler with cron matching, admin commands with TOTP flow
- Web panel: POST endpoints for digest/leaderboard publishing
- Localization: 3 keys in 8 locale files
- Tests: 45 unit tests across all layers

## Next steps
- Delete this file before opening PR
- Create PR via git_pr tools
