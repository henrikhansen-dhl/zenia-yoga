# Yoga Studio Platform

Mobile-first yoga class booking system built with Django.

## What is included

- Instructor workflow through Django admin for creating classes, setting schedules, and controlling capacity.
- Public booking pages where clients can reserve their own place in a class.
- Capacity protection and duplicate email protection per class.
- Responsive, app-like interface with a calm, mindfulness-inspired visual style.
- Static file setup ready for PythonAnywhere-style deployment with WhiteNoise.

## Local setup

1. Copy .env.example to .env and adjust values if needed.
2. Activate the virtual environment in .venv.
3. Run migrations.
4. Create an admin user.
5. Start the development server.

## Useful commands

Windows PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
Copy-Item .env.example .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

## PythonAnywhere notes

- Set environment variables from .env.example in the PythonAnywhere dashboard.
- Point the WSGI file to this project and virtual environment.
- Run collectstatic during deployment.
- Replace the default secret key and allowed hosts before going live.

### Static files on PythonAnywhere

If the Django admin login page looks unstyled in production, the static files are not being served correctly.

Run this on PythonAnywhere inside your virtual environment:

```bash
python manage.py collectstatic --noinput
```

Then in the PythonAnywhere web app configuration, add static mappings:

- URL: /static/  Directory: /home/your-pythonanywhere-user/your-project-folder/staticfiles
- URL: /media/   Directory: /home/your-pythonanywhere-user/your-project-folder/media

After that, reload the web app.

## Main app structure

- booking.models defines classes and bookings.
- booking.admin provides the instructor management interface.
- booking.views and templates render the public booking flow.

## SMS reminder gateway

- The instructor clients page now supports direct SMS sending via CPSMS.
- Configure gateway credentials in `.env` (see `.env.example`).
- Required values:

```env
SMS_GATEWAY_ENABLED=True
SMS_GATEWAY_USERNAME=your-cpsms-username
SMS_GATEWAY_API_KEY=your-cpsms-api-key
SMS_GATEWAY_FROM=YogaStudioPlatform
```

- Optional values:

```env
SMS_GATEWAY_URL=https://api.cpsms.dk/v2/send
SMS_GATEWAY_LANGUAGE=da
SMS_GATEWAY_DEFAULT_COUNTRY_CODE=45
SMS_GATEWAY_TIMEOUT_SECONDS=15
```

- Use the "Send SMS reminders" button on the instructor clients page to send immediately.
- Use "Export SMS reminders" if you want CSV output instead of direct send.