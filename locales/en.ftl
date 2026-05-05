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

## /profile (Sprint 1.1.E → 1.5.C)

profile-group = 🍆 The /profile command works only in the bot's DM. Open a private chat and try again.

profile-other = 🍆 The /profile command works only in the bot's DM.

profile-not-registered = 🍆 You don't seem to be registered yet. Tap /start in this chat and your card will appear.

# Localized title names from `domain.player.value_objects.Title`.
# Keys mirror enum values: `Title.NEWBIE = "newbie"` → `profile-title-newbie`.
profile-title-newbie = Newbie

# Player card from GDD §2.2. Parameters:
# - `$nick` — assembled "Title DisplayName Name" (built by presenter)
# - `$length_cm` — integer, cm
# - `$thickness_level` — integer, level
profile-card =
    🏷 { $nick }

    📏 Length: { $length_cm } cm
    📐 Thickness: { $thickness_level }

    🎽 Equipment: empty for now

## /top (Sprint 1.4.C → 1.5.C)

top-header = 🏆 <b>Pipirik Top</b>

top-empty = 🏆 The top is empty for now. Be the first — tap /start!

# Single row in the top: "<rank>. Title DisplayName Name — N cm".
top-entry = { $rank }. { $nick } — { $length_cm } cm

## /oracle (Sprint 1.4.B → 1.5.D)

oracle-group = 🔮 The /oracle command works only in the bot's DM. Open a private chat and try again.

oracle-other = 🔮 The /oracle command works only in the bot's DM.

oracle-not-registered = 🔮 You don't seem to be registered yet. Tap /start in this chat and the oracle will hear you.

# Success message (GDD §11). Parameters:
# - `$prediction` — prediction text, already with `{ user }` substituted
# - `$bonus_cm` — integer, length bonus
# - `$new_length_cm` — integer, new player length
oracle-success =
    🔮 Prediction of the day:
    { $prediction }

    📏 +{ NUMBER($bonus_cm, useGrouping: 0) } cm
    Now you have: { NUMBER($new_length_cm, useGrouping: 0) } cm

# "Come back tomorrow" message. Parameters:
# - `$hours` — integer, hours until 00:00 Moscow reset
# - `$minutes` — integer 0-59, minutes (`%02d` formatting done by presenter)
oracle-already-used =
    🔮 You've already visited the oracle today.
    Come back in { NUMBER($hours, useGrouping: 0) }h { $minutes }m (00:00 Moscow time).

## /upgrade (Sprint 1.4.A → 1.5.D)

upgrade-group = 🍆 The /upgrade command works only in the bot's DM. Open a private chat and try again.

upgrade-other = 🍆 The /upgrade command works only in the bot's DM.

upgrade-not-registered = 🍆 You don't seem to be registered yet. Tap /start in this chat — then you'll be able to upgrade.

# "Upgrade from N to N+1" proposal card. Parameters:
# - `$current_thickness` — integer, current level
# - `$next_thickness` — integer, target level (current+1)
# - `$cost_cm` — integer, cost in cm
# - `$current_length_cm` — integer, current player length
# - `$remaining_cm` — integer, what's left after deduction
# - `$min_after_spend_cm` — integer, lower bound from 20 cm rule
upgrade-proposal =
    📐 Thickness upgrade
    Current level: { NUMBER($current_thickness, useGrouping: 0) }
    Target level: { NUMBER($next_thickness, useGrouping: 0) }
    Cost: { NUMBER($cost_cm, useGrouping: 0) } cm
    You have: { NUMBER($current_length_cm, useGrouping: 0) } cm
    Remaining: { NUMBER($remaining_cm, useGrouping: 0) } cm (minimum by the 20 cm rule: { NUMBER($min_after_spend_cm, useGrouping: 0) })

# Success message "Thickness upgraded". Parameters:
# - `$new_thickness`, `$cost_cm`, `$new_length_cm`.
upgrade-success =
    ✅ Thickness upgraded to { NUMBER($new_thickness, useGrouping: 0) }!
    📏 Spent: { NUMBER($cost_cm, useGrouping: 0) } cm
    Remaining: { NUMBER($new_length_cm, useGrouping: 0) } cm

# "Insufficient length" rejection card. Parameters:
# - `$next_thickness`, `$cost_cm`, `$current_length_cm`,
# - `$min_after_spend_cm`, `$deficit_cm`.
upgrade-insufficient =
    ❌ Not enough length to upgrade to { NUMBER($next_thickness, useGrouping: 0) }.
    Cost: { NUMBER($cost_cm, useGrouping: 0) } cm
    You have: { NUMBER($current_length_cm, useGrouping: 0) } cm
    Minimum remaining: { NUMBER($min_after_spend_cm, useGrouping: 0) } cm
    Short by: { NUMBER($deficit_cm, useGrouping: 0) } cm

upgrade-cancelled = Upgrade cancelled.

upgrade-race = ⚠️ The upgrade cost has changed — open /upgrade again to see the current one.

# Inline button label "Confirm (X cm)". Parameter `$cost_cm`.
upgrade-button-confirm = Confirm ({ NUMBER($cost_cm, useGrouping: 0) } cm)

upgrade-button-cancel = Cancel

# Toasts for callback responses (Telegram limit ≤ 200 chars).
upgrade-toast-upgraded = Thickness upgraded.

upgrade-toast-cancelled = Upgrade cancelled.

upgrade-toast-player-not-found = Tap /start first.

upgrade-toast-insufficient = Not enough length.

upgrade-toast-race = Cost changed.

# Anti-cheat soft-ban gate on /upgrade (Sprint 1.6.E, ГДД §3.3.5).
# `$banned-until` is an ISO-8601 string of the ban-expiration moment (UTC, tz-aware).
upgrade-anticheat-blocked = Upgrade is temporarily frozen. Anti-cheat verification is active until { $banned-until }.

upgrade-toast-anticheat-blocked = Anti-cheat verification active.

# Compressed "Insufficient length" used to replace message text after a
# callback click (without the full card — handler doesn't know the
# fresh thickness without re-fetching the profile).
upgrade-insufficient-short =
    ❌ Not enough length.
    Cost: { NUMBER($cost_cm, useGrouping: 0) } cm
    You have: { NUMBER($current_length_cm, useGrouping: 0) } cm
    Minimum remaining: { NUMBER($min_after_spend_cm, useGrouping: 0) } cm
    Short by: { NUMBER($deficit_cm, useGrouping: 0) } cm

## /forest (Sprint 1.3.D → 1.5.E)

forest-group = 🍆 The /forest command is only available in the bot's private chat. Open the DM and try again.

forest-other = 🍆 The /forest command is only available in the bot's private chat.

forest-not-registered = 🍆 Looks like you're not registered yet. Tap /start in this chat — then you'll be able to go to the forest.

forest-already-in = 🌲 You're already in the forest — wait for your return. The bot will send a message when the trip ends.

# "Went to the forest" start message (GDD §8.2). Parameters:
# - `$nick` — assembled "Title Name PlayerName" (via presenter)
# - `$cooldown_minutes` — integer, minutes until return
forest-started = 🌲 { $nick } went to the forest for { NUMBER($cooldown_minutes, useGrouping: 0) } minutes...

# Fallback message when `GetProfile` couldn't find the player right after
# `StartForestRun` — parameter `$cooldown_minutes`.
forest-started-fallback = 🌲 You went to the forest for { NUMBER($cooldown_minutes, useGrouping: 0) } minutes...

# "Returned from forest" message — header and length line (GDD §8.2).
# Parameters:
# - `$nick` — full nick "Title Name PlayerName" with recomputed DisplayName
# - `$length_delta_cm` — integer, +N cm gained in the forest
# - `$length_before_cm` / `$length_after_cm` — integers, before/after
forest-finished-header = 🌲 { $nick } returned from the forest!
forest-finished-length =
    📏 Length: +{ NUMBER($length_delta_cm, useGrouping: 0) } cm (was { NUMBER($length_before_cm, useGrouping: 0) }, now { NUMBER($length_after_cm, useGrouping: 0) })

# `{delta}` substitution for forest flavour log templates (Sprint 1.5.G,
# GDD §15). `$length_delta_cm` — integer; format mirrors `+N cm` in
# `forest-finished-length`. Kept as a separate key so localizers can
# change units / sign for future languages without touching templates.
forest-flavour-delta = +{ NUMBER($length_delta_cm, useGrouping: 0) } cm

# Title "Newbie" granted (first forest return, GDD §8.2).
forest-finished-title-granted = 🎖 Title earned: Newbie

# Parameter `$item_name` — display_name of the item,
# `$rarity` — localized rarity (see forest-rarity-*).
forest-finished-item-found = 🎩 Found: { $item_name } [{ $rarity }]

# Name granted automatically (newbie without a name yet). Parameter `$name`.
forest-finished-name-granted = 🪪 Name received: { $name }

# Name offered for replacement (player already has a name). Parameter `$name`.
forest-finished-name-found = 🪪 Name found: { $name }

# Localized rarities (UI "Found: <item> [<rarity>]").
forest-rarity-common = common
forest-rarity-rare = rare
forest-rarity-epic = epic

# Inline button labels under the "returned from forest" message.
forest-button-equip = Equip
forest-button-drop-item = Drop
forest-button-replace-name = Replace
forest-button-drop-name = Drop

# Toasts for callback responses (Telegram limit ≤ 200 chars).
forest-toast-name-applied = Name replaced.
forest-toast-name-already-applied = Name was already applied.
forest-toast-name-dropped = Name dropped.
forest-toast-item-dropped = Item dropped.
forest-toast-item-equipped-placeholder = Equipment is coming later — the item is in your inventory for now.
forest-toast-foreign-button = This button isn't for you.
forest-toast-run-not-found = This forest run is no longer active.
forest-toast-drop-mismatch = Button is outdated.
forest-toast-player-not-found = Tap /start first.

# ----------------------------- /lang -----------------------------
# `/lang ru|en` — interface language switcher (Sprint 1.5.F).

# Command called outside a private chat.
lang-group = `/lang` is private-chat only. Switch to DM.

# Command called from a non-user (e.g., from a channel).
lang-other = `/lang` is for regular users only.

# Player is not registered yet.
lang-not-registered = Tap /start first, then run /lang ru|en.

# Usage hint when args are missing/invalid.
lang-usage = Usage: /lang ru or /lang en.

# Unsupported language code passed.
lang-unsupported = Language `{ $code }` is not supported. Available: ru, en.

# Locale switched successfully.
lang-set-ru = Язык интерфейса: русский. Все ответы и фоновые сообщения теперь на русском.
lang-set-en = Interface language switched to English. All replies and background messages will be in English.


# Anti-cheat hardcap (Sprint 1.6.D, GDD §3.3).
# Player attempted a length-granting action but is in a soft-ban.
# `$banned-until` — ISO string of ban expiration moment (UTC, tz-aware).
anticheat-soft-ban-active = Anti-cheat verification is active until { $banned-until }. Length growth is temporarily frozen.

# Part of the requested delta was clamped by the daily cap.
# `$applied` — actually applied cm; `$requested` — originally requested.
anticheat-cap-clamped-daily = Daily growth cap nearly reached. Applied { NUMBER($applied, useGrouping: 0) } cm out of { NUMBER($requested, useGrouping: 0) } cm.

# Part of the requested delta was clamped by the weekly cap.
anticheat-cap-clamped-weekly = Weekly growth cap nearly reached. Applied { NUMBER($applied, useGrouping: 0) } cm out of { NUMBER($requested, useGrouping: 0) } cm.


# /anticheat_unban (Sprint 1.6.G, GDD §3.3) — admin command.
# Shown when command format is invalid.
anticheat-unban-usage = ⚠️ Usage: `/anticheat_unban <tg_id> <reason>`. Reason is required.

# Not an admin (or role below super_admin).
anticheat-unban-not-authorized = ❌ You don't have permission for this command. Lifting an anti-cheat ban is available only to active super_admin.

# Target player is not registered.
anticheat-unban-player-not-found = ❌ Player with tg_id { $tg_id } is not registered.

# Ban is not active (None or already expired) — idempotent no-op.
anticheat-unban-not-banned = ℹ️ Player tg_id { $tg_id } has no active anti-cheat ban. No action needed.

# Ban successfully lifted. `$banned-until-before` — ISO string of previous ban expiration.
anticheat-unban-success = ✅ Anti-cheat ban lifted (tg_id { $tg_id }, was banned until { $banned-until-before }). Reason: { $reason }.


# ──────────────────────────────────────────────────────────────────────────
# 1×1 PvP duel (Sprint 2.1.E, GDD §7.1).
# ──────────────────────────────────────────────────────────────────────────

# /duel in private chat without reply — challenge is auto-queued to the global pool.
# Kept as fallback for compatibility; the active flow uses duel-global-enqueued.
duel-private-needs-global = 🍆 To challenge someone, reply /duel to their message in a group chat. Or wait — your `/duel` in private chat has already been sent to the global pool.

# /duel without reply in a group, or with invalid arguments.
duel-usage = 🍆 Usage: reply `/duel` to your opponent's message. Default mode is chat → global. For chat-only — `/duel chat`. In private chat, `/duel` without arguments enqueues you in the global pool.

# Player (challenger) isn't registered yet.
duel-not-registered = 🍆 You're not registered yet. Tap /start first.

# Opponent isn't registered yet.
duel-target-not-registered = 🍆 Opponent isn't registered yet — ask them to /start the bot.

# Reply on a bot message — not allowed.
duel-target-is-bot = 🍆 You can only challenge a real player, not a bot.

# Reply on own message — not allowed.
duel-self-challenge = 🍆 Challenging yourself? Find a real opponent.

# Challenge card in chat (chat_only mode). $challenger / $challenged — @username.
duel-challenge-chat = ⚔️ { $challenger } challenges { $challenged } to a duel (chat only)! Accept?

# Challenge card in chat (chat_then_global mode).
duel-challenge-chat-then-global = ⚔️ { $challenger } challenges { $challenged } to a duel! If not accepted within 3 minutes, the challenge will move to the global pool.

# Notification that challenge has been sent to the global pool (global_only).
duel-challenge-global = ⚔️ { $challenger }, your challenge has been sent to the global pool — waiting up to { NUMBER($ttl_minutes, useGrouping: 0) } min.

# Private-chat notification after `/duel` without args — enqueued in global pool.
duel-global-enqueued = ⚔️ Challenge sent to the global pool. Waiting for someone to /duel_global. Expires in { NUMBER($ttl_minutes, useGrouping: 0) } min — cancel manually with /cancel_duel { $duel_id }.

# Private-chat reply after `/duel_global` — successful match.
duel-global-matched = ⚔️ Matched with { $challenger }! Fight started — watch for round prompts in private chat.

# Private-chat reply after `/duel_global` — lobby empty (or race with self-challenge).
duel-global-empty = 🪂 Global pool is empty. Try later or send a challenge via /duel.

# `/duel_global` outside private chat — disallowed.
duel-global-only-in-private = 🤖 `/duel_global` works only in private chat — opponents shouldn't be exposed publicly.

# Replaces challenge card after accept.
duel-chat-accepted = ✅ { $challenged } accepted { $challenger }'s challenge. Fight in progress (private).

# Inline buttons.
duel-button-accept = Accept
duel-button-reject = Decline
duel-button-attack-high = Attack: ⬆ high
duel-button-attack-mid = Attack: ➡ mid
duel-button-attack-low = Attack: ⬇ low
duel-button-block-high = Block: ⬆ high
duel-button-block-mid = Block: ➡ mid
duel-button-block-low = Block: ⬇ low

# Round prompt (DM).
duel-round-attack-prompt = 🥊 Round { NUMBER($round_num, useGrouping: 0) } of 3. Where do you strike?

# Block-selection prompt (after attack).
duel-round-block-prompt = 🛡 Round { NUMBER($round_num, useGrouping: 0) } of 3. Attack: { $attack }. What do you block?

# Player has moved — waiting for opponent.
duel-round-waiting = ⏳ Round { NUMBER($round_num, useGrouping: 0) } — move accepted. Waiting for opponent…

# Final result.
duel-result-victory = 🏆 Victory! +{ NUMBER($delta_cm, useGrouping: 0) } cm. Length is now { NUMBER($new_length_cm, useGrouping: 0) } cm.
duel-result-defeat = 💀 Defeat. { NUMBER($delta_cm, useGrouping: 0) } cm. Length is now { NUMBER($new_length_cm, useGrouping: 0) } cm.
duel-result-draw = 🤝 Draw. Length unchanged — { NUMBER($length_cm, useGrouping: 0) } cm.

# /cancel_duel.
duel-cancelled = ❌ Challenge cancelled by { $challenger }.
duel-cancel-usage = Usage: `/cancel_duel <duel_id>`. ID is shown in the challenge card.

# Toast notifications (callback_query answers).
duel-toast-accepted = Challenge accepted!
duel-toast-rejected = Thanks, not interested.
duel-toast-cancelled = Challenge cancelled.
duel-toast-not-found = This duel is no longer active.
duel-toast-not-participant = This duel isn't yours.
duel-toast-foreign-button = This button isn't for you.
duel-toast-invalid-state = Duel is no longer in that phase.
duel-toast-already-submitted = You've already moved in this round.
duel-toast-outdated = Button is outdated.

# Pre-duel requirements not met.
duel-requirements-not-met = 📏 Duels require length ≥ { NUMBER($min_length_cm, useGrouping: 0) } cm and thickness ≥ { NUMBER($min_thickness_level, useGrouping: 0) }.

# Anti-cheat soft-ban active.
duel-anticheat-blocked = Anti-cheat check is active until { $banned-until }. Duels are temporarily frozen.

# Player is busy with another activity (forest etc.).
duel-lock-already-held = 🔒 You're busy (e.g., in /forest). Finish the current activity first.
