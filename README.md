# WokChat

Two-person realtime chat built with FastAPI, PostgreSQL, JWT auth, WebSockets, client-side encrypted message text, and encrypted-at-rest media storage.

## What To Commit

Commit the app code, `requirements.txt`, `railway.json`, `.env.example`, and this `README.md`.

Do not commit:

- `.env`
- `uploads/`
- `venv/` or `.venv/`
- temporary log files

## Local Run

1. Create a `.env` from `.env.example`
2. Install dependencies:

```bash
pip install -r requirements.txt
```

3. Start the app:

```bash
uvicorn app.main:app --reload
```

## GitHub Push

```bash
git init
git add .
git commit -m "Prepare WokChat for Railway deployment"
git branch -M main
git remote add origin <your-github-repo-url>
git push -u origin main
```

## Railway Deploy

1. Push this project to GitHub.
2. Create a new Railway project.
3. Choose `Deploy from GitHub repo`.
4. Select this repository.
5. Add a PostgreSQL database service in Railway.
6. Copy your environment variables into Railway.
7. Railway will use `railway.json` to start the app.
8. Open the generated Railway domain and test both logins.

## Railway Environment Variables

Set these in Railway:

- `DATABASE_URL`
- `SECRET_KEY`
- `ALGORITHM=HS256`
- `ACCESS_TOKEN_EXPIRE_MINUTES=1440`
- `MESSAGE_TTL_HOURS=48`
- `CLEANUP_INTERVAL_SECONDS=300`
- `DB_ECHO=false`
- `ENVIRONMENT=production`
- `FORCE_HTTPS=true`
- `LOGIN_MAX_ATTEMPTS=5`
- `LOGIN_WINDOW_SECONDS=900`
- `USER_ONE_USERNAME`
- `USER_ONE_PASSWORD`
- `USER_TWO_USERNAME`
- `USER_TWO_PASSWORD`

Then update these with your real deployed origin:

- `CORS_ORIGINS=["https://your-app.up.railway.app"]`
- `TRUSTED_HOSTS=["your-app.up.railway.app"]`

If you later attach a custom domain, replace those with your real domain and optionally keep the Railway domain too.

## Important Notes

- Both users must use the same `Chat key` on login to read encrypted messages.
- Message text/captions are client-side encrypted when a chat key is used.
- Attachments are not full end-to-end encrypted yet; they are protected in transit and encrypted at rest on the server.
- Realtime messaging, typing indicators, and online state work while both users have the app open.
- This app is a good fit for Railway because it uses WebSockets.

## Production Checklist

- Use a strong `SECRET_KEY` with at least 32 characters.
- Set final usernames and passwords in Railway variables.
- Set `ENVIRONMENT=production`.
- Set the correct `CORS_ORIGINS` and `TRUSTED_HOSTS`.
- Verify both users can log in and send messages.
- Verify WebSocket updates work from two different devices.
