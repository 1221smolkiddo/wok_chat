# WokChat

Two-person realtime chat built with FastAPI, PostgreSQL, JWT auth, WebSockets, client-side encrypted message text, and encrypted-at-rest media storage.

## Repo Status

This repo is ready for:

- GitHub push
- Render deployment via `render.yaml`
- Railway deployment via `railway.json`

Keeping both files is fine. Render ignores `railway.json`, and Railway ignores `render.yaml`.

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

## Important Env Vars

- `DATABASE_URL`
- `SECRET_KEY`
- `ENVIRONMENT`
- `FORCE_HTTPS`
- `CORS_ORIGINS`
- `TRUSTED_HOSTS`
- `USER_ONE_USERNAME`
- `USER_ONE_PASSWORD`
- `USER_TWO_USERNAME`
- `USER_TWO_PASSWORD`
- `UPLOAD_DIR`

## Render Deploy

This repo includes [`render.yaml`](./render.yaml), so Render can create the web service and database from the repo.

### Render steps

1. Push the repo to GitHub.
2. Go to Render.
3. Open `Blueprints`.
4. Create a new Blueprint instance from this repository.
5. Render will detect `render.yaml`.
6. Review the generated services:
   - web service: `wok-chat`
   - database: `wok-chat-db`
7. Fill in the missing environment variables in Render:
   - `SECRET_KEY`
   - `USER_ONE_USERNAME`
   - `USER_ONE_PASSWORD`
   - `USER_TWO_USERNAME`
   - `USER_TWO_PASSWORD`
   - `CORS_ORIGINS`
   - `TRUSTED_HOSTS`
8. Deploy.

### Render production values

Use values like:

```env
ENVIRONMENT=production
FORCE_HTTPS=true
DB_ECHO=false
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=1440
MESSAGE_TTL_HOURS=48
CLEANUP_INTERVAL_SECONDS=300
LOGIN_MAX_ATTEMPTS=5
LOGIN_WINDOW_SECONDS=900
UPLOAD_DIR=uploads
```

After Render gives you a live domain, set:

```env
CORS_ORIGINS=["https://your-app.onrender.com"]
TRUSTED_HOSTS=["your-app.onrender.com"]
```

If you later attach a custom domain, replace those values with the custom domain.

## Railway Deploy

This repo also includes [`railway.json`](./railway.json) if you still want to deploy there later.

## Git Ignore

Do not commit:

- `.env`
- `uploads/`
- `venv/` or `.venv/`
- temp log files

## Security Notes

- Both users must use the same `Chat key` on login to read encrypted text messages.
- Message text and captions are client-side encrypted when a chat key is used.
- Attachments are not full end-to-end encrypted yet.
- Realtime messaging, typing indicators, and presence require both users to have the app open.

## Platform Notes

- Render supports WebSockets, so it fits this app's realtime behavior.
- The current `UPLOAD_DIR=uploads` setting stores uploaded media on the service filesystem.
- If you redeploy or restart on a platform with ephemeral storage, uploaded attachments may not persist unless you use a persistent disk or external object storage later.
