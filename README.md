# Draftly — Backend

Django + Django REST Framework API for the Draftly collaborative document workspace.

## Stack

| Concern    | Choice                              |
| ---------- | ----------------------------------- |
| Framework  | Django 6.1                          |
| API        | Django REST Framework (function based views) |
| Auth       | Token authentication (`rest_framework.authtoken`) |
| Live       | Django Channels (WebSockets)         |
| Database   | SQLite (local) / PostgreSQL (env)   |
| Imports    | `python-docx` for `.docx` files     |

## Getting started

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py seed_demo_users     # creates the demo accounts + sample documents
python manage.py runserver
```

The API is served on http://127.0.0.1:8000/api/.

### Running with an ASGI server (required for the live updates)

`daphne` is in `INSTALLED_APPS`, so `python manage.py runserver` already starts
**Daphne (ASGI)** — WebSockets work and Django's auto-reloader restarts the server
when a `.py` file changes:

```bash
python manage.py runserver
```

Without `daphne` in `INSTALLED_APPS` the same command would serve WSGI and the live
updates would not work. To start the server explicitly:

```bash
# development — auto-reload + WebSockets (alternative to runserver)
uvicorn draftly_backend.asgi:application --reload --port 8000

# production
daphne -b 0.0.0.0 -p 8000 --proxy-headers draftly_backend.asgi:application
```

| Flag | Why |
| ---- | --- |
| `--reload` (uvicorn) | Restarts the server when a `.py` file changes. |
| `--proxy-headers` | Behind Render / Railway / nginx the TLS is terminated there — this tells the server to believe `X-Forwarded-Proto` and `X-Forwarded-For` (needed for HTTPS and the correct host). |
| `--ping-interval 30 --ping-timeout 60` | Keeps the WebSocket alive through proxies that drop idle connections. |
| `-b 0.0.0.0` | Bind to every interface — required inside a container. |
| `-p ${PORT:-8000}` | Render and Railway inject the port as `PORT`. |

> **After changing backend code, restart the server.** A stale process keeps the old
> routes — the symptom is a `404` for an endpoint that clearly exists in the code.

### Environment

The settings read a `.env` file (`python-dotenv`) — copy `.env.example` to `.env`.
Variables set by the platform (Render, Railway, Docker …) always win over the file:

```bash
cp .env.example .env
```

| Variable | Purpose |
| -------- | ------- |
| `DJANGO_SECRET_KEY` | the secret key |
| `DJANGO_DEBUG` | `0` in production |
| `DJANGO_ALLOWED_HOSTS` | comma separated host names |
| `CORS_ALLOWED_ORIGINS` | comma separated frontend origins |
| `DATABASE_URL` | PostgreSQL URL — **empty means local SQLite** |
| `REDIS_URL` | Redis for the channel layer (empty = in-memory, single process) |

## Demo accounts

| Account            | Password   | Role                          |
| ------------------ | ---------- | ----------------------------- |
| alice@draftly.demo | draftly123 | Owner — creates and shares    |
| bob@draftly.demo   | draftly123 | Collaborator — receives shares |

## Endpoints

| Method   | Path                                        | Description                              |
| -------- | ------------------------------------------- | ---------------------------------------- |
| POST     | `/api/auth/register/`                       | Create an account → token               |
| POST     | `/api/auth/login/`                          | `{ email, password }` → `{ token, user }` |
| POST     | `/api/auth/logout/`                         | Invalidates the token                    |
| GET      | `/api/auth/me/`                             | The signed in user                       |
| GET      | `/api/users/?search=`                       | People that a document can be shared with |
| GET      | `/api/documents/?scope=&search=`            | List documents (scope: all/mine/shared/recent/trash) |
| POST     | `/api/documents/`                           | Create a document                        |
| GET      | `/api/documents/<id>/`                      | Read a document                          |
| PATCH    | `/api/documents/<id>/`                      | Update title/content (owner or editor)   |
| DELETE   | `/api/documents/<id>/`                      | Move the document to the trash (owner)   |
| GET      | `/api/documents/<id>/version/`              | The current version (no content)         |
| GET      | `/api/documents/<id>/download/`            | Download as docx / original / md / html / txt / json |
| POST     | `/api/documents/<id>/restore/`              | Restore from the trash (owner)           |
| DELETE   | `/api/documents/<id>/purge/`                | Delete permanently (owner)               |
| POST     | `/api/documents/import/`                    | Import a `.txt`, `.md` or `.docx` file   |
| GET      | `/api/documents/<id>/permissions/`          | List who has access                      |
| POST     | `/api/documents/<id>/share/`                | Share the document (owner)               |
| PATCH    | `/api/documents/<id>/permissions/<pid>/`    | Change a role (owner)                    |
| DELETE   | `/api/documents/<id>/share/<user_id>/`      | Revoke access (owner)                    |

All endpoints except the login and the registration require the
`Authorization: Token <token>` header.

---

## Live updates (WebSockets)

The REST API stays the only place where a document is written — it owns the permission
checks and the validation. After a successful save the new state is fanned out through
the channel layer, so the other editors see the change immediately.

```
ws://127.0.0.1:8000/ws/documents/<uuid>/?token=<api-token>
```

| Direction | Message |
| --------- | ------- |
| server → client | `{"type": "hello", "version": 7, "role": "editor", "user_id": 3}` |
| server → client | `{"type": "update", "content": {…}, "title": "…", "version": 8, "author_id": 3, "author_name": "Bob"}` |
| server → client | `{"type": "presence", "users": [{"id": 3, "name": "Bob"}]}` |
| client → server | `{"type": "collab", "kind": "content", "content": {…}}` — the live stream of the editor |
| client → server | `{"type": "collab", "kind": "selection", "anchor": 12, "head": 40}` — the live selection |
| client → server | `{"type": "ping"}` → `{"type": "pong"}` |

The `collab` messages are **relayed, never stored** — they carry the live editing data
(what somebody is typing, where they have selected something). The database is written
through the REST API only.

Close codes: `4401` (no/invalid token), `4403` (no access to the document), `4404`
(unknown document).

**Django must be started with an ASGI server** — `python manage.py runserver` does that
automatically once `channels` is installed (it switches to Daphne). In production:

```bash
daphne -b 0.0.0.0 -p 8000 draftly_backend.asgi:application
```

The channel layer is in-memory by default. With more than one worker or several
instances, set `REDIS_URL` to switch to `channels_redis`:

```
REDIS_URL=redis://localhost:6379/0
```

## Files on disk

Every document is stored twice:

| Where | What |
| ----- | ---- |
| the database (`Document.content`) | the TipTap JSON — the editable source of truth |
| `media/documents/<year>/<month>/<slug>.docx` | the Word file, rewritten on every save |

An imported document additionally keeps its **original upload** in
`media/imports/<year>/<month>/` — that is what the download serves with
`?format=original`.

The `media/` folder is served at `/media/` in development. In production it has to be
served by the platform (or nginx) and it has to live on a **persistent disk** — a free
host with an ephemeral filesystem would lose the files.

## Access rules

The rules are enforced on the server, not in the frontend:

| Action                | Owner | Editor | Viewer | Not shared |
| --------------------- | ----- | ------ | ------ | ---------- |
| Read the document     | yes   | yes    | yes    | no         |
| Edit title / content  | yes   | yes    | no     | no         |
| Download the document | yes   | yes    | yes    | no         |
| Share / revoke access | yes   | no     | no     | no         |
| Delete / restore      | yes   | no     | no     | no         |

The helper functions live in `documents/permissions.py` and are used by every view.

## Project layout

```
draftly_backend/
├── draftly_backend/     # project package (settings, urls, ASGI, CORS middleware)
├── accounts/             # login/logout/me + user lookup + seed command
├── documents/            # models, permissions, services, views, importer, consumer
│   ├── tiptap.py         # helpers for the TipTap JSON format
│   ├── importers.py      # .txt / .md / .docx  ->  editable document
│   ├── exports.py        # editable document  ->  .md / .html / .txt / .json
│   ├── docx_export.py    # editable document  ->  the stored .docx file
│   ├── realtime.py       # channel layer fan-out after a save
│   ├── consumers.py      # the WebSocket (a plain ASGI function)
│   └── tests.py          # API + permission tests
├── media/                # the generated .docx files and the original uploads
├── manage.py
└── requirements.txt
```

## Tests

```bash
python manage.py test
```

The test suite focuses on the permission rules (owner, editor, viewer and
unrelated users), on content persistence and on the file import.

## CORS

`draftly_backend/cors.py` is a ~40 line middleware that adds the CORS headers
for the frontend origin, so the project needs no extra dependency. Configure the
allowed origins with the `CORS_ALLOWED_ORIGINS` environment variable:

```
CORS_ALLOWED_ORIGINS=http://localhost:5173,https://your-frontend.example.com
```
