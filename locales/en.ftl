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

# Referral arrival (Sprint 2.4.D, GDD §13.1).
# Parameters:
# - `$bonus_cm` — how many cm the newcomer got on top of the starting
#   length (`balance.referral.on_signup.newbie_bonus_cm`, default 5).
start-registered-with-referral = 🍆 Done! You are registered in Pipirik Wars.

    Starting length is 2 cm + <b>{ $bonus_cm } cm bonus for arriving via a referral link</b>. Thickness is level 1. Your name and title will appear later — on your first forest run.

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

## /clantop (Sprint 2.2.A)

clantop-header = 🛡 <b>Clan Top</b>

clantop-empty = 🛡 No clans in the top yet. Add the bot to a group — and register your clan!

# Single row in the clan top: "<rank>. ClanTitle — N cm (M 👥)".
clantop-entry = { $rank }. { $clan_title } — { $total_length_cm } cm ({ $member_count } 👥)

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

# Public result card (Sprint 2.1.H, GDD §15) — shareable summary.
# `$winner` / `$loser` — formatted `@username` / «—». In the draw variant —
# `$p1` / `$p2` (no winner).
duel-result-card-victory = ⚔️ Duel over: { $winner } crushed { $loser } (+{ NUMBER($delta_cm, useGrouping: 0) } cm).
duel-result-card-draw = ⚔️ Duel ended in a draw: { $p1 } and { $p2 } traded zero-damage blows.
duel-share-button = 📢 Share

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

# === Mass PvP clan×clan (Sprint 2.2.F, GDD §7.2) ===

# /clan_attack — usage and base errors.
pvp-mass-needs-group-chat = ⚔️The `/clan_attack` command only works in clan group chats. Run it from the chat of the clan you want to attack.
pvp-mass-not-registered = 🍆Register first via `/start` in the bot's DM.
pvp-mass-attacker-not-found = ❌This chat is not linked to a registered clan.
pvp-mass-attacker-not-member = 🚫Only members of this clan can attack other clans.
pvp-mass-target-not-found = ❌Target chat not found or not linked to a registered clan.
pvp-mass-target-needed = Usage: `/clan_attack <chat_id>` or reply to a message from the defender clan's chat.
pvp-mass-self-attack = 🤝You cannot attack your own clan.
pvp-mass-clan-frozen = 🧊One of the clans is frozen — mass duel is impossible.
pvp-mass-cooldown = ⏳Cooldown is still active: next attack possible in { NUMBER($cooldown_hours, useGrouping: 0) } h.
pvp-mass-no-participants = 🪶One side has no participants meeting the requirements (length ≥ { NUMBER($min_length_cm, useGrouping: 0) } cm, thickness ≥ { NUMBER($min_thickness_level, useGrouping: 0) }).
pvp-mass-lock-already-held = 🔒Some participants are busy with another activity. Try again in a minute.

# Start card in the group chat.
pvp-mass-started = ⚔️Clan battle: <b>{ $attacker }</b> × <b>{ $defender }</b>! Lineup: { NUMBER($attacker_size, useGrouping: 0) } × { NUMBER($defender_size, useGrouping: 0) }. All participants got instructions in DM. Move timer — { NUMBER($timer_seconds, useGrouping: 0) } sec.

# DM prompts.
pvp-mass-prompt-attack = ⚔️Clan × clan battle. Where do you strike?
pvp-mass-prompt-block = 🛡Attack chosen: { $attack }. What do you block?
pvp-mass-waiting = ⏳Your move is accepted. Waiting for others…

# Final result in DM to each participant.
pvp-mass-result-victory = 🏆Victory! Clan <b>{ $clan }</b> won and took { NUMBER($total_dealt, useGrouping: 0) } cm. Your delta: { $delta_sign }{ NUMBER($delta_cm, useGrouping: 0) } cm.
pvp-mass-result-defeat = 💀Defeat. Clan <b>{ $clan }</b> lost, { NUMBER($total_lost, useGrouping: 0) } cm went to the enemy. Your delta: { $delta_sign }{ NUMBER($delta_cm, useGrouping: 0) } cm.
pvp-mass-result-draw = 🤝Draw. Nobody won by more. Your delta: { $delta_sign }{ NUMBER($delta_cm, useGrouping: 0) } cm.

# Final card in chat.
pvp-mass-result-chat-victory = 🏆Clan × clan battle is over! Clan <b>{ $clan }</b> won and took { NUMBER($total_dealt, useGrouping: 0) } cm.
pvp-mass-result-chat-draw = 🤝Clan × clan battle ended in a draw ({ NUMBER($total_dealt, useGrouping: 0) } cm dealt by each side).

# Buttons.
pvp-mass-button-attack-high = ⬆️ Head
pvp-mass-button-attack-mid = ↔ Body
pvp-mass-button-attack-low = ⬇️ Legs
pvp-mass-button-block-high = 🛡⬆ Head
pvp-mass-button-block-mid = 🛡↔ Body
pvp-mass-button-block-low = 🛡⬇ Legs

# Toast notifications.
pvp-mass-toast-not-found = This battle is no longer active.
pvp-mass-toast-not-participant = You are not a participant in this battle.
pvp-mass-toast-foreign-button = This button is not for you.
pvp-mass-toast-invalid-state = The battle is already over.
pvp-mass-toast-already-submitted = You already made your move.
pvp-mass-toast-outdated = This button is outdated.
pvp-mass-toast-attack-selected = Attack chosen. Now pick a block.
pvp-mass-toast-move-accepted = Move accepted!

## /clan_history (Sprint 2.2.G — clan attack journal)

clan-history-needs-group-chat = 📜 The `/clan_history` command only works in a clan group chat.
clan-history-not-registered = 📜 This chat is not registered as a clan. Use /start to register.
clan-history-header = 📜 <b>Clan attack journal</b> ({ $clan_title })
clan-history-empty = 📜 Clan <b>{ $clan_title }</b> has no completed mass battles yet.
# One journal row: "<idx>. ⚔ Opponent — victory +20 cm (3×3)".
clan-history-entry-victory = { $idx }. ⚔ { $opponent_clan_title } — 🏆 victory +{ NUMBER($our_delta_cm, useGrouping: 0) } cm ({ NUMBER($our_count, useGrouping: 0) }×{ NUMBER($opponent_count, useGrouping: 0) }, { $when })
clan-history-entry-defeat = { $idx }. ⚔ { $opponent_clan_title } — 💀 defeat { NUMBER($our_delta_cm, useGrouping: 0) } cm ({ NUMBER($our_count, useGrouping: 0) }×{ NUMBER($opponent_count, useGrouping: 0) }, { $when })
clan-history-entry-draw = { $idx }. ⚔ { $opponent_clan_title } — 🤝 draw ({ NUMBER($our_count, useGrouping: 0) }×{ NUMBER($opponent_count, useGrouping: 0) }, { $when })
clan-history-entry-cancelled = { $idx }. ⚔ { $opponent_clan_title } — ⛔ cancelled ({ $when })

## /clan_head (Sprint 2.3.E — daily clan head)

clan-head-needs-group-chat = 👑 The /clan_head command only works in a clan group chat.
clan-head-not-registered = 👑 This chat is not linked to a registered clan. Use /start to register.
clan-head-frozen-clan = 👑 The clan is temporarily frozen. Cannot assign a head.
clan-head-not-enough-active = 👑 Too few active members in the clan over the last 7 days (need at least { NUMBER($required, useGrouping: 0) }, active: { NUMBER($active_count, useGrouping: 0) }).
clan-head-success = 👑 <b>Clan head of the day</b> — { $head_display_name }!
  +{ NUMBER($bonus_cm, useGrouping: 0) } cm to length (now { NUMBER($new_length_cm, useGrouping: 0) } cm).

  💬 <i>{ $quote_text }</i>
clan-head-already-assigned = 👑 The clan head for today is already assigned — { $head_display_name } (+{ NUMBER($bonus_cm, useGrouping: 0) } cm).

  💬 <i>{ $quote_text }</i>

## Referral-share button (Sprint 2.4.D-b, GDD §13.2)
# Button label under duel / forest results — shares result with referral link.
referral-share-button = 🔗 Share

# Text posted to chat when user clicks "Share" after a duel (victory).
# Parameters: $winner, $loser, $delta_cm, $winner_length_cm, $deeplink.
referral-share-duel-victory = ⚔️ PIPIRIK WARS — Battle Result!
    { $winner } 🏆 won!
    Stole { NUMBER($delta_cm, useGrouping: 0) } cm from { $loser }!
    📏 New length: { NUMBER($winner_length_cm, useGrouping: 0) } cm

    🎮 Play too → { $deeplink }

# Text for a draw.
# Parameters: $p1, $p2, $deeplink.
referral-share-duel-draw = ⚔️ PIPIRIK WARS — Battle Result!
    Draw: { $p1 } and { $p2 } parted on equal terms.

    🎮 Play too → { $deeplink }

# Text posted to chat when user clicks "Share" after a forest run.
# Parameters: $player, $delta_cm, $length_cm, $deeplink.
referral-share-forest = 🌲 PIPIRIK WARS — Forest Run!
    { $player } returned from the forest with { NUMBER($delta_cm, useGrouping: 0) } cm!
    📏 New length: { NUMBER($length_cm, useGrouping: 0) } cm

    🎮 Play too → { $deeplink }


## Weekly clan referral summary (Sprint 2.4.E, GDD §13.3)
# Card is posted to the clan chat on Sunday 18:00 UTC by cron.
# Parameters: $clan_title.
weekly-referral-summary-title = 📊 WEEKLY REPORT — Clan "{ $clan_title }"
# Parameters: $total — total number of new clan referrals in the past week.
weekly-referral-summary-total = 👥 New referrals this week: { NUMBER($total, useGrouping: 0) }
# Parameters: $rank (1..3), $referrer_display_name, $count.
weekly-referral-summary-line = 🏆 { NUMBER($rank, useGrouping: 0) }. { $referrer_display_name } — brought { NUMBER($count, useGrouping: 0) }
weekly-referral-summary-footer = Invite your friends — everyone grows together!


## Admin — TOTP confirmation of dangerous commands (Sprint 2.5-A.3, GDD §18.6)
# Used in Sprints 2.5-B/C/D by /ban, /grant_*, /balance_set, /announce handlers.
# Flow: command emits `admin-confirm-prompt` (with token + TTL), admin sends
# 6-digit code, bot responds with `admin-confirm-success` or one of the errors.
# Parameters: $token — short id (so admin knows which of multiple pending
#   confirms this code is for), $ttl_seconds — seconds to enter the code.
admin-confirm-prompt = 🔐Dangerous command confirmation.

    Enter the 6-digit code from your authenticator app within { NUMBER($ttl_seconds, useGrouping: 0) } seconds.
    Operation id: <code>{ $token }</code>
admin-confirm-success = ✅Command confirmed. Executing.
admin-confirm-totp-not-configured = ⚠️You have not configured 2FA. Contact super-admin to set it up.
admin-confirm-token-not-found = ⚠️Token not found. It may have already been used — repeat the command.
admin-confirm-token-expired = ⏰Time to enter the code has run out. Repeat the command.
admin-confirm-code-invalid = ❌Invalid code. For safety the token has been burned — repeat the command from scratch.
admin-confirm-admin-mismatch = 🚫This token belongs to another admin. Each confirmation is bound to its initiator.


## Admin — support commands (Sprint 2.5-B, GDD §18.6.5)
# Used by `/find_player`, `/player`, `/freeze`, `/unfreeze`, `/ban` and the
# shared `/confirm` handler.

# /find_player <text>
admin-find-player-usage = ⚠️ Usage: <code>/find_player &lt;tg_id | @username | substring&gt;</code>. The query is required.
admin-find-player-not-authorized = ❌ Only active admins may search for players.
admin-find-player-empty = 🔍 No players found for query <code>{ $query }</code>.
admin-find-player-header = 🔍 Found { $count } player(s) for query <code>{ $query }</code>.
# Single row. Parameters: $tg_id, $username (or "—"), $name (or "—"),
#  $title (or "—"), $length_cm, $thickness_level, $status.
admin-find-player-row = • <code>{ $tg_id }</code> · @{ $username } · «{ $name }» · { $title } · L{ $length_cm }/T{ $thickness_level } · { $status }

# /player <tg_id>
admin-player-usage = ⚠️ Usage: <code>/player &lt;tg_id&gt;</code>. The argument is required.
admin-player-not-authorized = ❌ Only active admins may view player cards.
admin-player-bad-id = ⚠️ <code>{ $value }</code> is not a valid tg_id (integer). Try again.
admin-player-not-found = 🔍 No player with tg_id <code>{ $tg_id }</code>.
admin-player-card-summary = • <code>{ $tg_id }</code> · @{ $username } · «{ $name }» · { $title } · L{ $length_cm }/T{ $thickness_level } · { $status }
admin-player-card-clan = 🏰 Clan: <code>{ $title }</code> ({ $clan_status }) · role { $role } · since { $joined_at }
admin-player-card-no-clan = 🏰 Clan: —
admin-player-card-forest-active = 🌲 Active forest run #{ $run_id }: from { $started_at } to { $ends_at }.
admin-player-card-no-forest = 🌲 No active forest run.
admin-player-card-anticheat = 🛡️ Anti-cheat ban until: { $until }.
admin-player-card-no-anticheat = 🛡️ Anti-cheat ban: not active.

# /freeze
admin-freeze-usage = ⚠️ Usage: <code>/freeze &lt;tg_id&gt; [reason]</code>.
admin-freeze-not-authorized = ❌ Only active admins may freeze players.
admin-freeze-bad-id = ⚠️ <code>{ $value }</code> is not a valid tg_id (integer).
admin-freeze-not-found = 🔍 No player with tg_id <code>{ $tg_id }</code>.
admin-freeze-already = ❄️ Player <code>{ $tg_id }</code> is already frozen.
admin-freeze-ok = 🥶 Player <code>{ $tg_id }</code> has been frozen.{ $reason_suffix }
admin-freeze-reason-suffix = Reason: { $reason }.

# /unfreeze
admin-unfreeze-usage = ⚠️ Usage: <code>/unfreeze &lt;tg_id&gt; [reason]</code>.
admin-unfreeze-not-authorized = ❌ Only active admins may unfreeze players.
admin-unfreeze-bad-id = ⚠️ <code>{ $value }</code> is not a valid tg_id (integer).
admin-unfreeze-not-found = 🔍 No player with tg_id <code>{ $tg_id }</code>.
admin-unfreeze-already = ▶️ Player <code>{ $tg_id }</code> is already active.
admin-unfreeze-ok = ☀️ Player <code>{ $tg_id }</code> has been unfrozen.{ $reason_suffix }
admin-unfreeze-reason-suffix = Reason: { $reason }.

# /ban — necessitates TOTP (B.4)
admin-ban-usage = ⚠️ Usage: <code>/ban &lt;tg_id&gt; &lt;reason&gt;</code>. Reason is required.
admin-ban-not-authorized = ❌ Only active admins may ban players.
admin-ban-totp-not-configured = ❌ Your TOTP is not configured. `/ban` is unavailable.
admin-ban-bad-id = ⚠️ <code>{ $value }</code> is not a valid tg_id (integer).
admin-ban-no-reason = ⚠️ Reason is required. Usage: <code>/ban &lt;tg_id&gt; &lt;reason&gt;</code>.
admin-ban-not-found = 🔍 No player with tg_id <code>{ $tg_id }</code>.
admin-ban-already = 🛑 Player <code>{ $tg_id }</code> is already banned.
admin-ban-confirm-issued = 🛡️ Confirm this operation. Send: <code>/confirm { $token } &lt;6-digit code&gt;</code>. Token TTL: { $ttl_seconds } sec.

# /confirm (B.5)
admin-confirm-usage = ⚠️ Usage: <code>/confirm &lt;token&gt; &lt;6-digit code&gt;</code>.
admin-confirm-not-authorized = ❌ Only active admins may confirm operations.
admin-confirm-totp-not-configured = ❌ Your TOTP is not configured. Confirmation impossible.
admin-confirm-token-not-found = ❌ Token <code>{ $token }</code> is already used or does not exist.
admin-confirm-token-expired = ⌛ Token expired. Rerun the command.
admin-confirm-admin-mismatch = ❌ This token belongs to another admin.
admin-confirm-code-invalid = ❌ Invalid 6-digit code.
admin-confirm-success-ban = ✅ Player <code>{ $tg_id }</code> has been banned.
admin-confirm-success-ban-already = 🛑 Player <code>{ $tg_id }</code> was already banned.
admin-confirm-unknown-command-kind = ⚠️ Unknown command kind <code>{ $command_kind }</code> — please update the bot.

# ─────────────────────────────────────────────────────────────────────────────
# Sprint 2.5-C — economy commands (TOTP-protected except /balance_get)
# ─────────────────────────────────────────────────────────────────────────────

# /grant_length <tg_id> <±delta_cm> <reason>
admin-grant-length-usage = ⚠️ Usage: <code>/grant_length &lt;tg_id&gt; &lt;±delta_cm&gt; &lt;reason&gt;</code>. All three are required.
admin-grant-length-not-authorized = ❌ Only active admins may modify length.
admin-grant-length-totp-not-configured = ❌ Your TOTP is not configured. `/grant_length` is unavailable.
admin-grant-length-bad-id = ⚠️ <code>{ $value }</code> is not a valid tg_id (integer).
admin-grant-length-bad-delta = ⚠️ <code>{ $value }</code> is not ±integer or equals 0.
admin-grant-length-no-reason = ⚠️ Reason is required. Usage: <code>/grant_length &lt;tg_id&gt; &lt;±delta_cm&gt; &lt;reason&gt;</code>.
admin-grant-length-not-found = 🔍 No player with tg_id <code>{ $tg_id }</code>.
admin-grant-length-blocked = 🚫 Cannot modify length of player <code>{ $tg_id }</code>: { $reason }.
admin-grant-length-confirm-issued = 🛡️ Confirm this operation. Send: <code>/confirm { $token } &lt;6-digit code&gt;</code>. Token TTL: { $ttl_seconds } sec.
admin-grant-length-success = ✅ Player <code>{ $tg_id }</code>: applied { $delta } cm. New length: { $new_length_cm } cm.
admin-grant-length-success-clamped = ⚠️ Player <code>{ $tg_id }</code>: requested { $requested } cm, applied { $applied } cm (24h cap). New length: { $new_length_cm } cm.
admin-grant-length-soft-ban = 🚫 Player <code>{ $tg_id }</code> is in anti-cheat soft-ban — operation rejected.

# /grant_thickness <tg_id> <new_level> <reason>
admin-grant-thickness-usage = ⚠️ Usage: <code>/grant_thickness &lt;tg_id&gt; &lt;new_level&gt; &lt;reason&gt;</code>.
admin-grant-thickness-not-authorized = ❌ Only active admins may modify thickness.
admin-grant-thickness-totp-not-configured = ❌ Your TOTP is not configured. `/grant_thickness` is unavailable.
admin-grant-thickness-bad-id = ⚠️ <code>{ $value }</code> is not a valid tg_id (integer).
admin-grant-thickness-bad-level = ⚠️ <code>{ $value }</code> is not a level (integer ≥ 1).
admin-grant-thickness-no-reason = ⚠️ Reason is required. Usage: <code>/grant_thickness &lt;tg_id&gt; &lt;new_level&gt; &lt;reason&gt;</code>.
admin-grant-thickness-not-found = 🔍 No player with tg_id <code>{ $tg_id }</code>.
admin-grant-thickness-blocked = 🚫 Cannot modify thickness of player <code>{ $tg_id }</code>: { $reason }.
admin-grant-thickness-level-invalid = ⚠️ Level <code>{ $level }</code> out of range [1, { $max_level }] ({ $reason_code }).
admin-grant-thickness-confirm-issued = 🛡️ Confirm this operation. Send: <code>/confirm { $token } &lt;6-digit code&gt;</code>. Token TTL: { $ttl_seconds } sec.
admin-grant-thickness-success = ✅ Player <code>{ $tg_id }</code>: thickness level set to { $new_level } (was { $previous_level }).
admin-grant-thickness-already-at-level = ℹ️ Player <code>{ $tg_id }</code> is already at thickness level { $level }.

# /balance_get <key>
admin-balance-get-usage = ⚠️ Usage: <code>/balance_get &lt;dotted.key&gt;</code>.
admin-balance-get-not-authorized = ❌ Only active admins may read balance values.
admin-balance-get-key-not-found = ⚠️ Key <code>{ $path }</code> not found ({ $reason } at segment <code>{ $segment }</code>).
admin-balance-get-result = 📦 <code>{ $path }</code> = <code>{ $value }</code> (balance v{ $version }).

# /balance_set <key> <value> <reason>
admin-balance-set-usage = ⚠️ Usage: <code>/balance_set &lt;dotted.key&gt; &lt;json_value&gt; &lt;reason&gt;</code>.
admin-balance-set-not-authorized = ❌ Only active admins may modify balance values.
admin-balance-set-totp-not-configured = ❌ Your TOTP is not configured. `/balance_set` is unavailable.
admin-balance-set-no-reason = ⚠️ Reason is required.
admin-balance-set-bad-value = ⚠️ <code>{ $value }</code> is not a valid JSON fragment.
admin-balance-set-key-not-found = ⚠️ Key <code>{ $path }</code> not found ({ $reason } at segment <code>{ $segment }</code>).
admin-balance-set-validation-error = ❌ Value for <code>{ $path }</code> failed validation: { $error }.
admin-balance-set-confirm-issued = 🛡️ Confirm this operation. Send: <code>/confirm { $token } &lt;6-digit code&gt;</code>. Token TTL: { $ttl_seconds } sec.
admin-balance-set-success = ✅ Key <code>{ $path }</code>: <code>{ $previous }</code> → <code>{ $new }</code> (balance v{ $version }).
admin-balance-set-already-at-value = ℹ️ Key <code>{ $path }</code> is already <code>{ $value }</code>.

# Shared /confirm idempotency-replay
admin-idempotency-replay = ℹ️ This command (<code>{ $command_kind }</code>) was already executed within the last minute — replay skipped.
