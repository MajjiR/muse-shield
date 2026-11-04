# Connections: Gmail, Calendar, Contacts, Telegram and your documents folder

People connect their own accounts from **Connections** in the app's sidebar. No keys, files or terminal. Until a service is connected, its tools use the bundled sample data, so the app works and demos either way.

As the developer you set up two app keys **once**. They ship with the app, and users never see them.

## 1. Google: one sign-in for Gmail, Calendar and Contacts (about 10 minutes)

1. Open <https://console.cloud.google.com/> and create a project, e.g. **Muse Shield**.
2. Turn on the APIs (**APIs & Services → Library**): **Gmail API**, **Google Calendar API**, **People API**.
3. Set up the **OAuth consent screen** (**APIs & Services → OAuth consent screen**, or **Google Auth Platform → Branding**):
   - User type: **External**. App name: Muse Shield. Add your support email.
   - **Data access / Scopes:** add `.../auth/gmail.readonly`, `.../auth/gmail.send`, `.../auth/calendar.events`,
     `.../auth/contacts.readonly`, `openid` and `email`.
   - **Audience / Test users:** add every Google account that will sign in: yours, a demo account, the judges.
     While the app is in **Testing**, only these accounts (up to 100) can connect, and they see an "unverified
     app" notice. Opening it to everyone needs Google's verification, because Gmail access is a restricted scope.
4. Create the client (**Credentials → Create credentials → OAuth client ID**):
   - Application type: **Desktop app**. Name: Muse Shield desktop.
   - Download the JSON.
5. Give the engine the client, in the gitignored `.env`:
   ```
   MUSE_SHIELD_GOOGLE_CLIENT_FILE=/absolute/path/to/client_secret_....json
   ```
   or `MUSE_SHIELD_GOOGLE_CLIENT_ID=...` and `MUSE_SHIELD_GOOGLE_CLIENT_SECRET=...`. A Desktop client's secret
   isn't confidential (Google's own docs say so). The flow also uses PKCE.

Google sends people back to the engine on its own address (`http://localhost:<port>/connections/google/callback`).
A Desktop client accepts any local port, so there's nothing to register.

## 2. Telegram (about 5 minutes)

1. Sign in at <https://my.telegram.org> with the developer's phone number, then open **API development tools**.
2. Create an application (title: Muse Shield, platform: Desktop). Copy **api_id** and **api_hash**.
3. Put them in `.env`:
   ```
   MUSE_SHIELD_TELEGRAM_API_ID=1234567
   MUSE_SHIELD_TELEGRAM_API_HASH=0123456789abcdef0123456789abcdef
   ```
4. Install the Telegram client library: `pip install 'muse-shield[connectors]'`.

Each person then signs in with their own phone number, the code Telegram sends them, and their two-step password if they use one.

## 3. Documents folder

Nothing to set up. People pick a folder in Connections. It's read by id, masked when read, and its tables are totalled on the device.

## What each connection can do

| Service | Read (always masked before Muse Spark sees it) | Act (only after you confirm, with the real values shown) |
|---|---|---|
| Gmail | your inbox, newest first, without quoted replies | send an email |
| Calendar | upcoming events | create an event (invites go out), move an event |
| Contacts | your address book; its addresses count as yours, so they can be recipients | none |
| Telegram | your recent chats and a chat's latest messages | send a message to one of *your* chats, never to a username a message suggests |
| Documents | browse, read any file, totals over tables | none |

## Where sign-ins live

Refresh tokens, the Telegram session and the chosen folder are encrypted in the vault, the same as every other private value. **Disconnect** deletes them, and also asks Google to revoke the token, or logs the Telegram session out. Muse Shield never writes them to a file.

## Privacy note while prototyping

To find what to hide, the text of what a connector reads goes to your masking model's deployment (our fine-tuned Muse Glimmer on Fireworks). Use test accounts with made-up content until masking runs where you fully control it.
