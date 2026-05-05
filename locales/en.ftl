# Bot localization for "Pipirik Wars" — EN.
#
# Sprint 1.5.A / dev plan 1.5.1: "All messages extracted from code".
# Foundation file: contains only keys already wired to presenters via
# `IMessageBundle`. Subsequent sprints (1.5.B+) will add the remaining
# keys and remove hardcoded strings from bot/presenters/.
#
# Conventions:
# - Keys grouped by module: `start_*`, `profile_*`, `forest_*`, etc.
# - Parameters: Fluent placeholders `{ $name }` (BCP-47 / Mozilla Fluent).
# - HTML tags allowed in values (bot uses parse_mode=HTML), but prefer
#   only `<b>`/`<i>` to keep migration to other parse_modes simple.

## /start (Sprint 1.1.C → 1.1.D → 1.2.4 DAU Gate)

start-registered = 🍆 Done! You are registered in Pipirik Wars.

    Starting length is 2 cm, thickness is level 1. Your name and title will appear later — on your first forest run.

start-already = 🍆 You are already registered. Use /profile to view your card.

start-group = 🍆 "Pipirik Wars" is here!

    1. First, register in the bot's private chat: open a DM and press /start.
    2. Then add me to a group as an admin — this turns the chat into a clan.

start-other = 🍆 "Pipirik Wars" is here. The /start command works in DM or in a group.

start-queued = 🍆 The servers are full — we've put you in the queue.

    Your position: #{ $position }.
    As soon as a slot opens up, we'll register you and send a notification.
