# AviScreen Backend

Django REST API backend for the AviScreen Flutter application. Features user authentication via Firebase, bird flock diagnosis using AI/ML, and comprehensive API endpoints for the mobile app.

## 🚀 Quick Start

### Prerequisites
- Python 3.11+ (Recommended: 3.12.10)
- PostgreSQL 12+
- Git
- Firebase account (for credentials)

### 5-Minute Setup

```powershell
# Clone repository
git clone https://github.com/Farukhthegreat/fyp-backend.git
cd fyp-backend

# Create virtual environment
python -m venv venv
venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt
pip install psycopg2-binary firebase-admin

# Create .env file (copy from .env.example, update config)
# Set up PostgreSQL database
# Add firebase-credentials.json to root folder

# Run migrations
python manage.py migrate

# Start server
python manage.py runserver
```

Visit: http://127.0.0.1:8000/api/health/

---

## 📖 Complete Setup Guide

**For detailed instructions on setting up PostgreSQL, Firebase, environment variables, and more, see:**

### 👉 **[SETUP_GUIDE.md](./SETUP_GUIDE.md)** ← Read this for complete setup

This guide includes:
- ✅ PostgreSQL installation & configuration
- ✅ Firebase setup & credentials
- ✅ Environment variables configuration
- ✅ Database migrations
- ✅ Testing & verification
- ✅ Connecting Flutter app
- ✅ Troubleshooting
- ✅ Deployment checklist

---

## 📁 Project Structure

```
fyp-backend/
├── api/                          # Main application
│   ├── models.py                # Database models (Flock, Diagnosis, etc.)
│   ├── views.py                 # API endpoints
│   ├── serializers.py           # Data serialization
│   ├── authentication.py        # Firebase authentication
│   ├── ai_engine.py             # AI/ML diagnosis logic
│   ├── urls.py                  # API routes
│   └── migrations/              # Database migrations
├── fyp_backend/                  # Project configuration
│   ├── settings.py              # Django settings
│   ├── urls.py                  # URL configuration
│   └── wsgi.py                  # WSGI config
├── manage.py                     # Django CLI
├── requirements.txt              # Dependencies
├── .env.example                  # Environment template (copy to .env)
├── firebase-credentials.json    # Firebase credentials (not in repo)
├── README.md                     # This file
└── SETUP_GUIDE.md               # Detailed setup instructions
```

---

## 🔌 API Endpoints

### Health Check
```
GET /api/health/
```

### Authentication (Firebase)
```
POST   /api/auth/register/
POST   /api/auth/login/
POST   /api/auth/logout/
GET    /api/auth/user/
```

### Flocks Management
```
GET    /api/flocks/              # List all flocks
POST   /api/flocks/              # Create flock
GET    /api/flocks/{id}/         # Get flock details
PUT    /api/flocks/{id}/         # Update flock
DELETE /api/flocks/{id}/         # Delete flock
```

### Diagnosis
```
POST   /api/diagnose/            # Run diagnosis
GET    /api/diagnoses/           # List diagnoses
GET    /api/diagnoses/{id}/      # Get diagnosis details
```

### Admin Panel
```
http://127.0.0.1:8000/admin/
(Login with superuser credentials)
```

---

## 🛠️ Common Commands

### Development
```powershell
# Start development server
python manage.py runserver

# Create migrations after model changes
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Create superuser (admin)
python manage.py createsuperuser

# Run tests
python manage.py test
```

### Database
```powershell
# Access PostgreSQL
psql -U aviansense_user -d aviansense_db

# Reset database
python manage.py migrate api zero
python manage.py migrate
```

### Virtual Environment
```powershell
# Activate (Windows)
venv\Scripts\Activate.ps1

# Deactivate
deactivate
```

---

## 🔐 Security Notes

- ✅ Firebase credentials are git-ignored (never committed)
- ✅ `.env` file is git-ignored (never commit secrets)
- ⚠️ Change `SECRET_KEY` in production
- ⚠️ Set `DEBUG=False` in production
- ⚠️ Use strong database passwords
- ⚠️ Configure `ALLOWED_HOSTS` for your domain

---

## 🔗 Connecting Flutter App

Update your Flutter app's API base URL:

```dart
const String API_BASE_URL = 'http://192.168.100.12:8000/api/';
// Replace 192.168.100.12 with your server's IP address
```

---

## 📝 Tech Stack

- **Framework:** Django 6.0.2
- **API:** Django REST Framework 3.16.1
- **Database:** PostgreSQL
- **Authentication:** Firebase Admin SDK
- **AI/ML:** (Integrated in ai_engine.py)
- **CORS:** django-cors-headers

---

## 🚨 Troubleshooting

Common issues and solutions are documented in [SETUP_GUIDE.md - Troubleshooting Section](./SETUP_GUIDE.md#-troubleshooting)

---

## 📞 Getting Help

1. Check [SETUP_GUIDE.md](./SETUP_GUIDE.md)
2. Review Django documentation: [docs.djangoproject.com](https://docs.djangoproject.com)
3. Check GitHub Issues: [Issues](https://github.com/Farukhthegreat/fyp-backend/issues)
4. Review code comments and docstrings

---

## 📄 License

This project is part of the FYP (Final Year Project).

---

**Ready to get started?** → Follow [SETUP_GUIDE.md](./SETUP_GUIDE.md)

Last Updated: February 2026
