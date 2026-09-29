# Deploying to alwaysdata (free plan)

`plan.md` §17.2 and §17.3; execution-plan step **P9**.

This is the runbook for putting this site on **alwaysdata's free plan**, served at
`https://<account>.alwaysdata.net`. It is written to be followed top to bottom once,
by someone who has the repository and the account but has never deployed this app.

Everything below was checked against alwaysdata's own documentation (sites, Python,
MySQL, quotas) and against this codebase's configuration. Where the free plan forces a
decision, the reason is stated — a runbook that only says *what* to type leaves the
person following it unable to tell a mistake from a surprise.

---

## 0. What the free plan actually gives you

| Resource | Free plan | What it means here |
|---|---|---|
| Disk | **1 GB SSD** | The repository (~30 MB), the database, the uploads, and *your own* backup archives all live in it. See §11. |
| RAM | **256 MB** | One request at a time in practice. A 6 MB photo being resized by Pillow is the peak. |
| CPU | **¼ core** | `BCRYPT_LOG_ROUNDS=12` login ≈ ¼ second. Fine. |
| Backups | **3 days**, daily | In the panel: `/home/<account>/admin/backup/<date>/`. Restorable, but only 3 days wide — see §11. |
| Address | `<account>.alwaysdata.net` | Plus free Let's Encrypt HTTPS on it. |
| Database | MySQL/MariaDB included | Host `mysql-<account>.alwaysdata.net`, 40 simultaneous connections. |
| Access | SSH + SFTP | Used for everything in §3 onwards. |

Two consequences worth internalising before starting:

* **Nothing on the free plan is fast, and the site is built for that.** Pages are
  server-rendered HTML, the SPA is pre-built and committed, the CSS is ~9 KB gzipped,
  and no build step runs on the server. A Node build on ¼ CPU is not a thing that
  would finish.
* **1 GB is the limit that will bite first.** The database and uploads are small; a
  year of uncompressed backups is not. §11 keeps them small.

---

## 1. Before you touch the server

Run these on your own machine, from `DYD-AI-SYLHET/`. All of them must pass — a deploy
is not the place to discover a failing test.

```bash
python -m pytest -q --no-cov          # the suite
npm run gates                         # CSS budget, ban-list, §9.1 tree audit
python _cms_smoke.py                  # every admin screen answers
```

**Build the front end and commit the result.** The server has no Node:

```bash
cd frontend && npm run build          # writes ../app/static/spa/
cd .. && git add app/static/spa && git commit -m "build: SPA"
```

`app/static/spa/` is committed on purpose (§17.2). A deploy that builds on the server
would need Node, 1 GB of RAM and two minutes on every push.

Generate the two secrets now — you will paste them into the panel in §5, and a
password manager is the only place they should exist afterwards:

```bash
python -c "import secrets; print(secrets.token_hex(32))"   # SECRET_KEY
python -c "import secrets; print(secrets.token_urlsafe(24))"  # database password
```

---

## 2. Create the account and the site

1. Sign up at `https://www.alwaysdata.com/` and pick the **free** plan. The account
   name you choose becomes your address (`<account>.alwaysdata.net`) and appears in
   every hostname below — call it `<account>` throughout.
2. **Web → Sites → Add a site**, with:

   | Field | Value |
   |---|---|
   | Addresses | `<account>.alwaysdata.net` |
   | Type | **Python WSGI** |
   | Application path | `/home/<account>/sylhet/wsgi.py` ← a **file**, not a directory |
   | Working directory | `/home/<account>/sylhet` |
   | Virtualenv directory | `/home/<account>/venv` (created in §4) |
   | Python version | **3.13** (this project's tested version) |

   The site type is what decides *how* the app runs: alwaysdata keeps **uWSGI** in
   front of an **Apache** that terminates HTTPS, and uWSGI imports the file you gave
   it and looks for a WSGI callable named `application`. `wsgi.py` exists for exactly
   that contract, and it is written to be the only file that has to be right.

3. Leave "Force HTTPS" for §7 — the certificate has to exist first.

> The Python version matters more than it looks. alwaysdata offers 3.5 → 3.14, and the
> panel's version and the virtualenv's version must be the same one, or every request
> fails with an import error that names a `.so` file.

---

## 3. Create the database

**Databases → MySQL → Add a database.**

| Field | Value |
|---|---|
| Name | `<account>_sylhet` |
| User | `<account>` (the account's own MySQL user) |

Then copy the host from the same screen: `mysql-<account>.alwaysdata.net`.

Your `DATABASE_URL` is therefore:

```
mysql+pymysql://<account>:<DB_PASSWORD>@mysql-<account>.alwaysdata.net/<account>_sylhet?charset=utf8mb4
```

**`?charset=utf8mb4` is not optional and is not cosmetic.** The whole site is in
Bangla. A `latin1` connection mangles it *silently* — the pages render, the data is
wrong, and nothing in any log says so (plan.md R5). Three things stand between you and
that outcome: this query string, MySQL's `utf8mb4_unicode_ci` collation, and
`ProdConfig.validate()`, which **refuses to boot** without it.

Check the collation once the schema exists (§6 does this for you):

```sql
SELECT DEFAULT_CHARACTER_SET_NAME FROM information_schema.SCHEMATA WHERE SCHEMA_NAME='<account>_sylhet';
```

---

## 4. Get the code and the virtualenv onto the server

Over SSH (`ssh <account>@ssh-<account>.alwaysdata.net`):

```bash
cd ~
git clone https://github.com/<you>/<repo>.git sylhet
cd sylhet

# The interpreter is `python` on alwaysdata — there is no `python3`.
python -m venv ~/venv
~/venv/bin/python -m pip install --upgrade pip
~/venv/bin/python -m pip install -r requirements.txt
```

Two things to know:

* **never type `python3`** on alwaysdata — the panel provides `python`, and `python3`
  is either absent or a different version than the one the panel runs your site with.
* If you would rather not clone, SFTP upload the project and then exclude the
  directories that must not go: `node_modules/`, `frontend/`, `.venv/`, `instance/`,
  `uploads/`, `var/`, `assets/`, `.env`, `.git/`. The only front-end files the server
  needs are the compiled ones already inside `app/static/`.

> `deploy.sh` (§9) updates the server with `git pull --ff-only`, so it needs the server
> to be a **clone**. If you uploaded by SFTP instead, either put the project in a
> repository now — the running site does not care either way — or deploy by uploading
> again and running `./deploy.sh --no-pull`.

---

## 5. Configure the application

**Web → Sites → (your site) → Environment variables.** These are read by the uWSGI
process and they are the authoritative configuration. At minimum:

| Variable | Value | Why |
|---|---|---|
| `APP_ENV` | `production` | `wsgi.py` defaults this, but set it anyway: it is what makes `.env` on the server ignore-able and turns on `ProdConfig`. |
| `SECRET_KEY` | 64 hex chars from §1 | Signs sessions. Under 32 characters, the app refuses to boot. |
| `DATABASE_URL` | from §3 | Must contain `charset=utf8mb4`. |
| `ALLOWED_HOSTS` | `<account>.alwaysdata.net` | Everything else gets a 400. |
| `APP_URL` | `https://<account>.alwaysdata.net` | Absolute URLs, the sitemap, and the HSTS decision. Must be https. |
| `ADMIN_URL_PREFIX` | `admin` | Where the CMS lives. |
| `TRUST_PROXY_HEADERS` | `true` | Apache speaks **http** to uWSGI. Without this, `request.is_secure` is False on an HTTPS site and the sitemap advertises `http://` URLs. |
| `UPLOAD_ROOT` | `/home/<account>/sylhet-uploads` | Outside the app directory (§13.1). |
| `BACKUP_ROOT` | `/home/<account>/sylhet-var/backups` | Where §11 writes. |
| `MAIL_PROVIDER` | `dryrun` first | Logs the contact-form email instead of sending it. Switch to `smtp` once the site is up. |
| `ADMIN_2FA_REQUIRED` | `true` | TOTP on the single admin account. |
| `ADMIN_IP_ALLOWLIST` | *(empty)* | Optional; a comma-separated CIDR list. Only fill it in if your address is static. |

### Why there is also a `.env` on the server

The panel's variables reach the **web process**. An SSH session gets none of them, so
`flask check-config`, `flask db upgrade` and `flask create-admin` would run against
defaults. Write the same values to `~/.env` in the project root for the CLI:

```bash
cp .env.example .env
nano .env          # same values as the panel
chmod 600 .env     # the SECRET_KEY lives here
```

**A stale `.env` can never override the panel**, and this is by design:
`app/config.py` skips the file *entirely* when `APP_ENV` is already `production` in the
environment, which it always is for the web process. The file exists for your shell.

**The three scripts read the same file.** `deploy.sh`, `rollback.sh` and
`cron_backup.sh` source `~/sylhet/.env` into the shell *before* exporting
`APP_ENV=production`, and that order is the reason they work: an SSH session and a
scheduled task both start with an empty environment, and the app ignores `.env` the
moment `APP_ENV` is production. Sourcing it first puts every value where the app will
actually look. The consequence is the same rule as `.env.example`'s: no spaces or `#`
in an unquoted value, and **percent-encode the database password inside
`DATABASE_URL`** — the application unquotes it, the shell does not.

---

## 6. First run

From `~/sylhet`, with `~/venv/bin/python`:

```bash
~/venv/bin/python -m flask check-config     # refuses to continue if anything is unsafe
~/venv/bin/python -m flask db upgrade       # 21 tables + the indexes
~/venv/bin/python -m flask check-db         # schema, constraints, and the consent guards
~/venv/bin/python -m flask seed             # the 21 pages and the site settings
~/venv/bin/python -m flask publish-pages    # so the site is not a 404 with good CSS
~/venv/bin/python -m flask seed-programme --yes   # the course modules and documents
~/venv/bin/python -m flask create-admin you@example.com
```

`create-admin` prints the TOTP secret and a QR-code path **once**. Put it in the
password manager before closing the terminal; `flask admin-reset-2fa <email>` is the
recovery path and is deliberately a CLI-only operation.

`check-db` deserves a sentence: it does not just look at the schema, it *proves* the
consent guards by attempting writes that must be refused, inside savepoints, and rolls
them back. If it prints a warning about the portrait probe, that is honest — there is
no media row yet to probe with.

Finally, restart the site so uWSGI picks up the new environment: **Web → Sites → your
site → Restart**, or `touch ~/sylhet/wsgi.py` from SSH.

---

## 7. HTTPS

**Web → Sites → your site → SSL.** Enable **Let's Encrypt** for
`<account>.alwaysdata.net`, then turn on **Force HTTPS**. The certificate is issued in
under a minute; a redirect from `http://` appears in the same section and is what makes
the `APP_URL=https://…` above true rather than aspirational.

Then confirm the headers, from your own machine:

```bash
curl -sI https://<account>.alwaysdata.net/ | grep -i -E 'strict-transport|cache-control'
```

You are looking for `Strict-Transport-Security` on the HTML response (production only
— by design) and `Cache-Control: public, max-age=3600` on `/static/…`.

---

## 8. Verify the deployment

Ten checks, in the order that narrows a failure fastest. The `curl` and browser checks
run from your machine; the `flask` ones run over SSH.

```bash
# 1. The app answers at all.
curl -sI https://<account>.alwaysdata.net/ | head -1                # 200

# 2. It is the production instance, not a development one.
~/venv/bin/python -m flask check-config | tail -5                   # no FAIL lines

# 3. The consent rules are enforced by the DATABASE, not just by Python.
~/venv/bin/python -m flask check-db                                 # guards report ok

# 4. The API the SPA reads answers, and answers with the right shape.
curl -s https://<account>.alwaysdata.net/api/v1/content | head -c 200

# 5. The sitemap uses https, not http.
curl -s https://<account>.alwaysdata.net/sitemap.xml | grep -c 'https://<account>'

# 6. Bangla survives the database round trip.
#    Type a Bangla name into the CMS, save, reload the page, and compare the characters.
```

In a browser:

7. Log in at `https://<account>.alwaysdata.net/admin/login` — the TOTP prompt should
   appear immediately, and a wrong code should be *rejected*.
8. **Admin → Participants**: add a participant with a portrait, tick the consent box,
   save. The portrait appears on `/participants`. Then untick consent and save: the
   portrait must disappear from the public page immediately. This is §5.1's whole rule,
   and it is the one feature whose failure is invisible until it matters.
9. **Admin → Backups**: empty until §11 runs.
10. Open `/nonexistent-page` and check you get the Bangla 404, not a Python traceback.

---

## 9. Deploys after the first one

`deploy.sh` is the only thing that should ever be run on a push, and it **never writes
configuration** — a deploy that rewrites `.env` is a deploy that can silently drop your
`SECRET_KEY`.

```bash
cd ~/sylhet && ./deploy.sh
```

It pulls, installs requirements, runs `check-config` (and stops if it fails), migrates,
runs `check-db`, creates the runtime directories from the app's own paths, renders
every page type to prove the templates still work, and touches `wsgi.py` to make uWSGI
reload. `./deploy.sh --check` does all of the checks without changing anything;
`--no-pull` is for a deploy you have already uploaded by hand.

Order matters, and it is deliberate: the schema is migrated *after* the config is
validated (a migration against a misconfigured database is a migration you cannot
re-run), and the new code only begins serving after `render-check` has proved it can.

---

## 10. Rolling back

```bash
cd ~/sylhet && ./rollback.sh --list        # the last few releases
cd ~/sylhet && ./rollback.sh <rev>         # or ./rollback.sh for the previous one
```

It refuses to run on a dirty working tree, checks out the revision as a detached HEAD,
reinstalls requirements, and re-runs the configuration and schema checks.

**It does not downgrade the database, and this is intentional.** It prints the command
(`flask db downgrade -1`) and the reason not to run it blind: a downgrade **drops
columns**, the free plan keeps only three days of automatic backups (§0), and the
column it drops may be one this site added on purpose. Reverting code is cheap;
reverting data is not.

---

## 11. The nightly backup

alwaysdata's own backups are daily and kept for **3 days**. That answers "the deploy
broke the site this morning". It does not answer "what did the register look like when
we reported the cohort in January", and it does **not** contain `UPLOAD_ROOT` at all.

```bash
chmod +x ~/sylhet/deploy.sh ~/sylhet/rollback.sh ~/sylhet/cron_backup.sh
mkdir -p ~/sylhet/var
```

Then **Web → Advanced → Scheduled tasks**, adding a task:

```
/home/<account>/sylhet/cron_backup.sh >> /home/<account>/sylhet/var/backup.log 2>&1
```

Nightly at 02:15. The command behind it is `flask backup`, which:

* dumps MySQL through `mariadb-dump --single-transaction` (consistent, and it does not
  lock the participant table while the CMS is being used);
* passes the password through `MYSQL_PWD` in the environment, **never on the command
  line** — `ps` is world-readable on a shared host, and a backup that leaks the
  database password to every other account is worse than no backup;
* tars `UPLOAD_ROOT`, which is the half of this site that cannot be regenerated;
* writes a `backups` row, so **Admin → Backups** shows whether last night actually ran
  — including a row with the error when it did not;
* deletes archives older than `--keep-days` (default 30).

**Mind the 1 GB.** On this plan, keep two weeks instead of the default thirty, and
send the archives somewhere else. Both are set on the task, because `cron_backup.sh`
reads them from the environment — it is run by cron, which never loads `.env`:

```
BACKUP_KEEP_DAYS=14 BACKUP_OFFSITE_CMD='rclone copy {src} remote:ai-sylhet' \
  /home/<account>/sylhet/cron_backup.sh >> /home/<account>/sylhet/var/backup.log 2>&1
```

`BACKUP_ROOT` is the application's setting and belongs in `.env` / the panel:
`BACKUP_ROOT=/home/<account>/sylhet-var/backups`. `BACKUP_OFFSITE_CMD` can be set in
either place; the shell one above wins for the cron run.

Restoring is a documented, tested path, not a hope:

```bash
zcat db-20260101-021500.sql.gz | mysql -h mysql-<account>.alwaysdata.net -u <account> -p <account>_sylhet
tar xzf uploads-20260101-021500.tar.gz -C /home/<account>/sylhet-uploads
```

and alwaysdata's own three days:

```bash
zstdcat /home/<account>/admin/backup/<date>/mysql/<account>_sylhet.sql.zst \
  | mysql -h mysql-<account>.alwaysdata.net -u <account> -p <account>_sylhet
```

---

## 12. Logs, and how to read a 500

| What | Where |
|---|---|
| HTTP requests (Apache) | `/home/<account>/admin/logs/http/` — also in the panel |
| **uWSGI / application** | `/home/<account>/admin/logs/uwsgi/<site-id>.log` |
| Rotating app log | `LOG_DIR` (default `var/logs/`), 5 × 10 MB |
| Audit trail | **Admin → Audit**, in the database — every admin write, with before/after |

A 500 in the browser says nothing; the reason is always in the uWSGI log, and
`wsgi.py` deliberately writes a loud banner plus the full traceback to **stderr**
before re-raising. It never swallows the error, because a blank page with a healthy
process is the hardest kind of failure to debug.

```bash
tail -n 50 /home/<account>/admin/logs/uwsgi/*.log
```

---

## 13. Troubleshooting

| Symptom | Cause, and the fix |
|---|---|
| `wsgi.py could not build the application` + `ModuleNotFoundError: No module named 'app'` | The application path or working directory is wrong, or the venv field is empty. It must be `/home/<account>/sylhet/wsgi.py` with working directory `/home/<account>/sylhet`. |
| `production configuration is invalid: SECRET_KEY — must be set and at least 32 characters` | The panel's environment variables are missing or were saved after the last restart. Add them, then restart the site. |
| `production configuration is invalid: DATABASE_URL — must contain charset=utf8mb4` | Add `?charset=utf8mb4` to the DSN. Do not work around this one. |
| Everything is 500 but `flask check-config` passes over SSH | The SSH shell is reading `.env`; the **web process** is not. Compare `~/sylhet/.env` with the panel's variable list — the panel wins. |
| `ModuleNotFoundError: No module named 'flask'` | The site's virtualenv field does not point at `~/venv`, or requirements were installed with a different interpreter. `~/venv/bin/python -m pip install -r requirements.txt`. |
| Import errors naming a `.so` file | Python version mismatch: the panel's version differs from the venv's. Recreate the venv with the panel's version. |
| Bangla text is mojibake (`à¦°`) | The DSN's charset, the column collation, or both. See §3. Fix the collation and re-run the import — do **not** re-type the data by hand. |
| Static assets 404 | `app/static/spa/` was never committed or never pulled. Run `npm run build` locally, commit, redeploy. |
| Uploads vanish after a deploy | `UPLOAD_ROOT` is inside the deploy directory, or the migration recreated it. It must be `/home/<account>/sylhet-uploads`. |
| Session lost on every request | `SECRET_KEY` is unset in the web process, so it is regenerated per worker. |
| 403 on every admin request | `ADMIN_IP_ALLOWLIST` is set to something that does not include your address — remember it is read as a CIDR list, and "empty" means off. |
| The site is slow on the first request after a quiet hour | ¼ CPU, a cold cache and a cold MySQL connection. `DB_POOL_RECYCLE` is set under MySQL's `wait_timeout`; the first request after a long quiet period is the only slow one. |

---

## 14. What this plan cannot do

Honest limits, with the smallest fix for each:

* **No `pip install` of anything needing a compiler.** Everything in
  `requirements.txt` is a wheel; adding a package with a C extension (or a
  `psycopg2`-style source build) may fail on the shared host.
* **No background workers.** Anything long-running belongs in a scheduled task.
* **No second admin at scale.** This site is built for **one** admin account (§12.1);
  the free plan's ¼ CPU would not serve a team editing at once anyway.
* **1 GB.** Watch it: `du -sh ~/sylhet ~/sylhet-uploads ~/sylhet-var`.
* **`flask backup` needs `mariadb-dump` on `PATH`** — present on alwaysdata over SSH,
  so schedule the task there and not on a machine without it.

---

## 15. Final checklist

- [ ] `npm run build` run and `app/static/spa/` committed
- [ ] Site created: type **Python WSGI**, application path **`…/wsgi.py`**, venv set
- [ ] Database created, `DATABASE_URL` ends in **`?charset=utf8mb4`**
- [ ] `SECRET_KEY` ≥ 32 characters, in the panel **and** in a `chmod 600 .env`
- [ ] `ALLOWED_HOSTS` and `APP_URL` set; `APP_URL` is **https**
- [ ] `TRUST_PROXY_HEADERS=true`
- [ ] `UPLOAD_ROOT` and `BACKUP_ROOT` outside the app directory
- [ ] `flask db upgrade` → `check-config` → `check-db` → seeds → `create-admin`, in that order
- [ ] Let's Encrypt issued, **Force HTTPS** on
- [ ] The 2FA secret is in the password manager, not only in a terminal scrollback
- [ ] A portrait's consent checkbox removes it from the public page
- [ ] The nightly backup task runs, and **Admin → Backups** shows last night's row
- [ ] `flask backup` restored once, into a throwaway database, by someone who watched
      it work

That last one is the item people skip. An untested backup is a file, not a recovery
plan — and the day you need it is the day you find out which.
