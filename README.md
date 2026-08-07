# Deepwoken Carry Bot

1. Install Python 3.11+ and run `pip install -r requirements.txt`.
2. Copy `.env.example` to `.env` and add the Discord bot token.
3. In the Discord Developer Portal, enable **Message Content Intent** and invite the bot with `bot` and `applications.commands` scopes. Give it Manage Channels, Manage Roles, Send Messages, Embed Links, Read Message History, and Manage Messages.
4. Run `python bot.py`.

When the bot is added (or starts in an existing server), it creates its own **Deepwoken Bot** category, channels, roles, and ticket panel. There is deliberately no setup command.

For a single-server deployment, add `GUILD_ID=your_server_id` to `.env`. The bot then runs its setup and spam protection only in that server. The `#version` channel shows the current release: **v2.0.0 — ENMITY**.

Anti-spam locks normal messaging if one non-staff member sends 6 messages in the same channel within 10 seconds. A member with Manage Server can restore saved channel permissions with `/unlockdown`.

## v2.1.0 — REGENT

The REGENT update adds a `Gank Stages` category and gives every gank a unique six-character ID, join/leave buttons, and a private voice stage. Only the new `Lieutenant` role can use `/endgank`; everyone still joined receives one PvP point. At the end of each month, the top PvP scorer receives the custom-colour `PvPer of the Month` role and is weighted three times in giveaway drawings. The most-vouched hoster receives the custom-colour `Hoster of the Month` role. Members can use `/vouch` once per hoster per month. The `#update-log` announcement pings `Update Ping` when the release is first installed.

Commands: `/startcarry` (with `/host` as an alias), `/endcarry`, `/gank`, `/blacklist`, `/unblacklist`, `/giveaway`, `/incident`, and `/closeincident`. `/setup` has intentionally been removed because setup is automatic.

The bot removes only carries with zero joiners after 30 minutes. PvE applications are mirrored to `#application-reviews`, where only members with `Review Certified` may pass or deny them.

Every ticket receives a permanent six-character ID (for example, `P4K2QX`), shown in its channel name and application embed.

Incident reports go to `#incident-reports`. A member with `Carry Staff` can take a report into a private incident ticket, then use `/closeincident` there to log its outcome and remove the ticket.
