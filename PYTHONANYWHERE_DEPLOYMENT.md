# PythonAnywhere Deployment Guide

This guide is customized for PythonAnywhere user: **henrikhansen**.

## 1) Create a web app

1. Log in to PythonAnywhere.
2. Open the **Web** tab.
3. Click **Add a new web app**.
4. Choose:
   - **Manual configuration**
   - **Python 3.11**

## 2) Get project code on PythonAnywhere

Open a **Bash** console and run:

```bash
cd /home/henrikhansen
git clone https://github.com/YOUR_ORG/YOUR_REPO.git yoga-platforms
cd /home/henrikhansen/yoga-platforms
```

If you are not using Git, upload the project folder with the **Files** tab to:

`/home/henrikhansen/yoga-platforms`

## 3) Create virtual environment and install requirements

```bash
cd /home/henrikhansen/yoga-platforms
python3.12 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements.txt
```

## 4) Configure production environment variables

Create/update:

`/home/henrikhansen/yoga-platforms/.env`

Use values like this (MySQL on PythonAnywhere):

```env
DJANGO_SECRET_KEY=replace-with-a-long-random-secret
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=henrikhansen.pythonanywhere.com
DJANGO_TIME_ZONE=Europe/Copenhagen

DJANGO_DB_ENGINE=mysql
DJANGO_DB_NAME=henrikhansen$YOUR_DB_NAME
DJANGO_DB_USER=henrikhansen
DJANGO_DB_PASSWORD=your-pythonanywhere-mysql-password
DJANGO_DB_HOST=henrikhansen.mysql.pythonanywhere-services.com
DJANGO_DB_PORT=3306

STUDIO_AUTO_PROVISION_ON_CREATE=True

SMS_GATEWAY_ENABLED=Trud
SMS_GATEWAY_URL=https://api.cpsms.dk/v2/send
SMS_GATEWAY_USERNAME=hehan
SMS_GATEWAY_API_KEY=d7860255-6954-413d-b5db-209a274301bf
SMS_GATEWAY_FROM=ZeniaYoga
SMS_GATEWAY_LANGUAGE=da
SMS_GATEWAY_DEFAULT_COUNTRY_CODE=45
SMS_GATEWAY_TIMEOUT_SECONDS=15

# Full public URL of the site — included in SMS booking links.
# Must be set for the scheduled reminder task to build correct links.
SITE_URL=https://henrikhansen.pythonanywhere.com
```

## 5) Prepare data and media

Because default DB is MySQL, platform data should be migrated into MySQL (not copied as `db.sqlite3`).

If you need existing data from local SQLite, export/import it:

```bash
cd /home/henrikhansen/yoga-platforms
source .venv/bin/activate
python manage.py dumpdata --exclude contenttypes --exclude auth.permission > data.json
python manage.py loaddata data.json
```

For studio-specific databases in this project, copy/upload these SQLite files if you want to keep existing studio data:

- `db_studio_karin-meditation.sqlite3`
- `db_studio_zenia-yoga.sqlite3`

Also copy/upload media files to:

- `/home/henrikhansen/yoga-platforms/media/`

## 6) Run migrations and collect static files

```bash
cd /home/henrikhansen/yoga-platforms
source .venv/bin/activate
python manage.py migrate
python manage.py collectstatic --noinput
```

If needed, create admin user:

```bash
python manage.py createsuperuser
```

## 7) Configure WSGI file

In the **Web** tab, open your WSGI configuration file and ensure it includes:

```python
import os
import sys

path = '/home/henrikhansen/yoga-platforms'
if path not in sys.path:
    sys.path.append(path)

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'config.settings')

from django.core.wsgi import get_wsgi_application
application = get_wsgi_application()
```

## 8) Configure static/media mappings in Web tab

Add static mapping:

- URL: `/static/`
- Directory: `/home/henrikhansen/yoga-platforms/staticfiles`

Add media mapping:

- URL: `/media/`
- Directory: `/home/henrikhansen/yoga-platforms/media`

## 9) Reload and verify

1. Click **Reload** in the Web tab.
2. Open:
   - `https://henrikhansen.pythonanywhere.com/`
   - `https://henrikhansen.pythonanywhere.com/admin/`
3. Confirm:
   - CSS is loaded
   - admin login works
   - booking pages load

## 10) Pre-flight checks before first reload

Run these commands in a Bash console on PythonAnywhere before you press **Reload**:

```bash
cd /home/henrikhansen/yoga-platforms
source .venv/bin/activate
python manage.py check
python manage.py showmigrations
python manage.py shell -c "from django.conf import settings; print(settings.DATABASES['default']['ENGINE']); print(settings.DATABASES['default']['NAME']); print(settings.ALLOWED_HOSTS)"
python manage.py collectstatic --noinput
python manage.py shell -c "from django.db import connections; connections['default'].cursor(); print('MySQL connection OK')"
```

Expected results:

- `python manage.py check` finishes without critical errors.
- `showmigrations` shows applied migrations after `python manage.py migrate`.
- Database engine prints `django.db.backends.mysql`.
- Allowed hosts includes `henrikhansen.pythonanywhere.com`.
- Final command prints `MySQL connection OK`.

## 11) Troubleshooting quick checks

- **Module not found**:
  - Activate venv and reinstall requirements.
  - `source /home/henrikhansen/yoga-platforms/.venv/bin/activate`
  - `pip install -r /home/henrikhansen/yoga-platforms/requirements.txt`

- **DisallowedHost error**:
  - Verify `.env` contains: `DJANGO_ALLOWED_HOSTS=henrikhansen.pythonanywhere.com`

- **MySQL connection error**:
  - Verify `.env` has the correct `DJANGO_DB_*` values from PythonAnywhere Databases tab.
  - Check MySQL password and host format.

- **Admin page without CSS**:
  - Run: `python manage.py collectstatic --noinput`
  - Verify Web tab static mapping `/static/` -> `/home/henrikhansen/yoga-platforms/staticfiles`

- **500 error after changes**:
  - Check error log in the Web tab.
  - Reload web app after fixes.

## Optional fallback: use SQLite for default DB

If you intentionally want SQLite as default DB instead of MySQL, set:

```env
DJANGO_DB_ENGINE=sqlite
```

Then ensure `db.sqlite3` exists in `/home/henrikhansen/yoga-platforms/` and run:

```bash
cd /home/henrikhansen/yoga-platforms
source .venv/bin/activate
python manage.py migrate
```

## 12) Scheduled task: daily SMS reminders

The management command `send_daily_reminders` sends class reminders automatically.
It is designed to run as a **PythonAnywhere Scheduled Task** — one task per studio.

### Prerequisites

- `SMS_GATEWAY_ENABLED=True` in `.env`
- `SITE_URL` set to your full public URL in `.env` (see step 4)
- Studio database exists and is provisioned (see `provision_studio_db`)

### Test it first (dry run)

Open a Bash console and verify who would receive a reminder:

```bash
cd /home/henrikhansen/yoga-platforms
source .venv/bin/activate
python manage.py send_daily_reminders --studio zenia-yoga --dry-run
python manage.py send_daily_reminders --studio karin-meditation --dry-run
```

Send manually once to confirm gateway works:

```bash
python manage.py send_daily_reminders --studio zenia-yoga
```

### Set up scheduled tasks

1. Open the **Tasks** tab on PythonAnywhere.
2. For each studio add a **Daily** task at your chosen time (e.g. 07:00).
3. Use the command exactly as shown:

**Studio: zenia-yoga — runs at 07:00**
```
/home/henrikhansen/yoga-platforms/.venv/bin/python /home/henrikhansen/yoga-platforms/manage.py send_daily_reminders --studio zenia-yoga
```

**Studio: karin-meditation — runs at 07:00**
```
/home/henrikhansen/yoga-platforms/.venv/bin/python /home/henrikhansen/yoga-platforms/manage.py send_daily_reminders --studio karin-meditation
```

Both tasks can run at the same time — they work independently and use separate database connections.

### What the task does each day

1. Finds clients on the `reminder_classes` list (class-interest reminders) for upcoming published classes.
2. Finds clients in a weekly series (`series_participants`) whose class is **today** and who have **not yet booked a spot**.
3. Sends an SMS to each person with a direct booking link.
4. Logs every attempt to `SmsReminderLog` (viewable in the SMS log popup in the instructor interface).

### Changing the SMS language

Default language is set by `SMS_GATEWAY_LANGUAGE` in `.env`. Override per task with `--lang`:

```
... send_daily_reminders --studio zenia-yoga --lang en
```


SMS Gateway return number: (+45)93759829
