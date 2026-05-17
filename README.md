# ANIZONEFLIX - Telegram Management Bot & Web Server

A high-performance FastAPI web server integrated with a Pyrogram Telegram bot, designed for seamless deployment on Render.

## Features

- **FastAPI + Pyrogram**: Optimized integration using async lifecycles.
- **Render Deployment Ready**: Pre-configured for Render with healthcheck support.
- **Long Polling**: Automatic update receiving without the need for webhooks.
- **Async Startup**: Proper handling of bot and web server lifecycles.
- **Plugin Handler System**: Modular bot commands and message handling.
- **Healthcheck Support**: Handles Render's HEAD requests to keep the service live.
- **MongoDB Support**: Integrated database management for anime metadata.

## Deployment Guide

### Render Deployment

#### Step-by-step:

1. **Fork/Upload**: Fork this repository or upload it to your GitHub/GitLab.
2. **Create Web Service**: On Render, create a new "Web Service".
3. **Build Command**: Set the build command to `pip install -r requirements.txt`.
4. **Start Command**: Set the start command to `python main.py`.
5. **Environment Variables**: Add the required environment variables (see below).
6. **Deploy**: Trigger the deployment.

### Start Command

You can use either:
```bash
python main.py
```
or:
```bash
uvicorn app:app --host 0.0.0.0 --port 10000
```

### Required Environment Variables

Ensure the following variables are set in your Render environment:

- `API_ID`: Your Telegram API ID.
- `API_HASH`: Your Telegram API Hash.
- `BOT_TOKEN`: Your Telegram Bot Token.
- `MONGO_URI`: Your MongoDB connection string.
- `PORT`: Set to `10000` (or as per your configuration).

## Healthcheck

The application supports automatic healthchecks via Render:

```python
@app.api_route("/", methods=["GET", "HEAD"])
async def root():
    return {"status": "running"}
```

## Project Structure

- `app.py`: Main FastAPI application logic and lifecycle events.
- `bot/`: Package containing Pyrogram bot initialization and handlers.
- `config/`: Configuration management for environment variables.
- `database/`: Database interaction logic (MongoDB).
- `requirements.txt`: Project dependencies.
- `main.py`: Entry point for starting the web server.

## Troubleshooting

### Bot not responding
- Check `BOT_TOKEN` correctness.
- Ensure the bot is not running elsewhere (multiple sessions cause conflicts).
- Verify all handlers are correctly imported.
- Test the `/ping` command.

### Render sleeping issue
Free instances on Render may sleep after inactivity. To avoid this, consider using a paid instance or an external pinger service to keep the healthcheck endpoint active.

### MongoDB connection errors
- Verify your `MONGO_URI`.
- Ensure your IP is whitelisted in MongoDB Atlas or your database provider.
