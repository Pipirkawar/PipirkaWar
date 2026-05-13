# Bot localization for "Pipirik Wars" — PT (Portuguese, Brazilian).
#
# Sprint 4.1-K (task 4.1.14): "Catalog of locales expanded to 8 (+pt/es/tr/id/fa/uk)".
# Contentful bootstrap: 30-50 high-traffic onboarding keys (`start-*`,
# `profile-*`, `top-*`, `clantop-*`, `forest-*`, `lang-*`). Остальные
# ~1550 ключей рендерятся через `FluentMessageBundle`-fallback на EN
# (см. `infrastructure/i18n/fluent_bundle.py`).
#
# Conventions: same as `en.ftl` (Fluent placeholders `{ $name }`,
# HTML `<b>`/`<i>` allowed, indentation = 4 spaces for continuation
# lines).

## /start

start-registered = 🍆 Pronto! Você está registrado em Pipirik Wars.

    O comprimento inicial é de 2 cm, a espessura é nível 1. Seu nome e título aparecerão mais tarde — na sua primeira ida à floresta.

start-already = 🍆 Você já está registrado. Use /profile para ver seu cartão.

start-group = 🍆 "Pipirik Wars" chegou!

    1. Primeiro, registre-se no chat privado do bot: abra uma DM e aperte /start.
    2. Depois me adicione a um grupo como administrador — isso transforma o chat em um clã.

start-other = 🍆 "Pipirik Wars" está aqui. O comando /start funciona em DM ou em um grupo.

start-queued = 🍆 Os servidores estão cheios — colocamos você na fila.

    Sua posição: #{ $position }.
    Assim que uma vaga abrir, vamos registrar você e enviar uma notificação.

start-registered-with-referral = 🍆 Pronto! Você está registrado em Pipirik Wars.

    O comprimento inicial é 2 cm + <b>{ $bonus_cm } cm de bônus por chegar via link de indicação</b>. A espessura é nível 1. Seu nome e título aparecerão mais tarde — na sua primeira ida à floresta.

## /profile

profile-group = 🍆 O comando /profile funciona apenas na DM do bot. Abra um chat privado e tente novamente.

profile-other = 🍆 O comando /profile funciona apenas na DM do bot.

profile-not-registered = 🍆 Parece que você ainda não está registrado. Aperte /start neste chat e seu cartão aparecerá.

profile-title-newbie = Novato
profile-title-ataman = Atamã Bandido

profile-card =
    🏷 { $nick }

    📏 Comprimento: { $length_cm } cm
    📐 Espessura: { $thickness_level }

    🎽 Equipamento: vazio por enquanto

## /top

top-header = 🏆 <b>Top do Pipirik</b>

top-empty = 🏆 O top está vazio por enquanto. Seja o primeiro — aperte /start!

top-entry = { $rank }. { $nick } — { $length_cm } cm

## /clantop

clantop-header = 🛡 <b>Top dos Clãs</b>

clantop-empty = 🛡 Ainda não há clãs no top. Adicione o bot a um grupo — e registre seu clã!

clantop-entry = { $rank }. { $clan_title } — { $total_length_cm } cm ({ $member_count } 👥)

## /forest

forest-group = 🍆 O comando /forest está disponível apenas no chat privado do bot. Abra a DM e tente novamente.

forest-other = 🍆 O comando /forest está disponível apenas no chat privado do bot.

forest-not-registered = 🍆 Parece que você ainda não está registrado. Aperte /start neste chat — depois você poderá ir para a floresta.

forest-already-in = 🌲 Você já está na floresta — aguarde seu retorno. O bot enviará uma mensagem quando a viagem terminar.

forest-started = 🌲 { $nick } foi para a floresta por { NUMBER($cooldown_minutes, useGrouping: 0) } minutos...

forest-started-fallback = 🌲 Você foi para a floresta por { NUMBER($cooldown_minutes, useGrouping: 0) } minutos...

forest-finished-header = 🌲 { $nick } voltou da floresta!

forest-finished-length =
    📏 Comprimento: +{ NUMBER($length_delta_cm, useGrouping: 0) } cm (era { NUMBER($length_before_cm, useGrouping: 0) }, agora { NUMBER($length_after_cm, useGrouping: 0) })

forest-finished-title-granted = 🎖 Título obtido: Novato

forest-rarity-common = comum
forest-rarity-rare = raro
forest-rarity-epic = épico

## /lang

lang-group = O comando `/lang` é apenas para chat privado. Abra a DM.

lang-other = O comando `/lang` é apenas para usuários comuns.

lang-not-registered = Aperte /start primeiro, depois execute /lang ru|en|pt|es|tr|id|fa|uk|ar.

lang-usage = Uso: /lang ru|en|pt|es|tr|id|fa|uk|ar.

lang-unsupported = Idioma `{ $code }` não é suportado. Disponíveis: ru, en, pt, es, tr, id, fa, uk, ar.

lang-set-pt = Idioma da interface alterado para português. Todas as respostas e mensagens em segundo plano agora serão em português.
lang-set-ar = تم تغيير لغة الواجهة إلى العربية. جميع الردود والرسائل في الخلفية ستكون الآن باللغة العربية.

# ───────────────────────────────────────────────────────────────────────────
# Announcement Channel (Sprint 4.9)
# ───────────────────────────────────────────────────────────────────────────
announce-channel-disabled = ❌ Announcement channel not configured. Set <code>BOT_ANNOUNCEMENT_CHANNEL_ID</code>.
announce-weekly-confirm = 🛡️ Confirm publishing weekly digest. Reply: <code>/confirm { $token } &lt;6-digit code&gt;</code>.
announce-leaderboard-confirm = 🛡️ Confirm publishing leaderboard. Reply: <code>/confirm { $token } &lt;6-digit code&gt;</code>.
