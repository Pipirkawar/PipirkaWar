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
