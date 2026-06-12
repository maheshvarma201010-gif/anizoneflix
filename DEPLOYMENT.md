# MovieOTT Deployment Guide

This guide provides instructions for deploying MovieOTT.

## Environment Variables
| Variable | Description |
|---|---|
| `API_ID` | Telegram API ID |
| `API_HASH` | Telegram API Hash |
| `BOT_TOKEN` | Telegram Bot Token |
| `MONGO_URI` | MongoDB Connection String |
| `TMDB_API_KEY` | TMDB API Key |
| `OMDB_API_KEY` | OMDb API Key |
| `BASE_URL` | Your Production URL |

## Docker
```bash
docker build -t movieott .
docker run -p 10000:10000 --env-file .env movieott
```
