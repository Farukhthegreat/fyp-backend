# AviScreen Backend - Complete Setup Guide

This guide will walk you through setting up the FYP backend on a **new/different computer** with all dependencies including PostgreSQL, Firebase, and environment configuration.

---

## 📋 Prerequisites

Before you start, ensure you have:

- **Python 3.11+** (Recommended: Python 3.12.10) - [Download](https://www.python.org/downloads/)
- **Git** - [Download](https://git-scm.com/)
- **PostgreSQL 12+** - [Download](https://www.postgresql.org/download/)
- A **Firebase Project** (with credentials JSON file)
- A code editor (VS Code recommended)

### Verify Installations

```powershell
python --version
git --version
psql --version
```

---

## 🚀 Step 1: Clone the Repository

Open PowerShell or Command Prompt and run:

```powershell
# Navigate to your desired projects folder
cd C:\Users\YourUsername\Documents

# Clone the repository
git clone https://github.com/Farukhthegreat/fyp-backend.git

# Navigate to the project
cd fyp-backend
```

---

## 💾 Step 2: Set Up PostgreSQL Database

### 2.1 Install & Start PostgreSQL

1. **Download** PostgreSQL from [postgresql.org](https://www.postgresql.org/download/)
2. **Run installer** and follow the setup wizard
3. **Remember your password** for the `postgres` user (you'll need it later)
4. **Verify installation**:
   ```powershell
   psql --version
   ```

### 2.2 Create Database & User

Open PowerShell as Administrator and connect to PostgreSQL:

```powershell
# Connect to PostgreSQL with the default superuser
psql -U postgres
```

You'll see the PostgreSQL prompt (`postgres=#`). Run these commands:

```sql
-- Create a new user (replace password with something secure)
CREATE USER aviansense_user WITH PASSWORD 'your_secure_password_here';

-- Create database owned by the user
CREATE DATABASE aviansense_db OWNER aviansense_user;

-- Grant privileges
GRANT ALL PRIVILEGES ON DATABASE aviansense_db TO aviansense_user;

-- Verify (list databases)
\l

-- Exit
\q
```

**Save these credentials:**
- Database Name: `aviansense_db`
- Database User: `aviansense_user`
- Database Password: `your_secure_password_here`
- Database Host: `localhost`
- Database Port: `5432`

---

## 🔥 Step 3: Set Up Firebase

### 3.1 Create a Firebase Project

1. Go to [Firebase Console](https://console.firebase.google.com/)
2. Click **"Create Project"**
3. Enter project name (e.g., "AviScreen-Backend")
4. Accept terms and click **"Create Project"**
5. Wait for project creation to complete

### 3.2 Generate Service Account Key

1. In Firebase Console, click **⚙️ Project Settings** (top-left corner)
2. Go to **"Service Accounts"** tab
3. Click **"Generate New Private Key"**
4. A JSON file will download - this is your `firebase-credentials.json`

### 3.3 Save Credentials to Project

1. Copy the downloaded `firebase-credentials.json` file
2. Paste it into your project root folder: `fyp-backend/firebase-credentials.json`

**⚠️ WARNING:** This file contains sensitive credentials. Keep it secure and never commit it to public repositories (it's already in `.gitignore`).

---

## 🛠️ Step 4: Set Up Python Virtual Environment

```powershell
# Navigate to project folder (if not already there)
cd C:\path\to\fyp-backend

# Create virtual environment
python -m venv venv

# Activate virtual environment
# On Windows:
venv\Scripts\Activate.ps1

# You should see (venv) at the beginning of your terminal line
```

**If you get a permission error:**

```powershell
# Run PowerShell as Administrator, then:
Set-ExecutionPolicy -ExecutionPolicy RemoteSigned -Scope CurrentUser

# Then try activating again
venv\Scripts\Activate.ps1
```

---

## 📦 Step 5: Install Dependencies

With virtual environment activated:

```powershell
# Upgrade pip
python -m pip install --upgrade pip

# Install required packages
pip install -r requirements.txt

# Install PostgreSQL Python adapter
pip install psycopg2-binary

# Install Firebase Admin SDK (if not in requirements.txt)
pip install firebase-admin
```

Verify installation:

```powershell
pip list
```

---

## 🔐 Step 6: Configure Environment Variables

### 6.1 Create `.env` File

In your project root (`fyp-backend/`), create a file named `.env`:

```
# Django Settings
DEBUG=True
SECRET_KEY=your-secret-key-here-change-in-production

# Database Configuration
DB_ENGINE=django.db.backends.postgresql
DB_NAME=aviansense_db
DB_USER=aviansense_user
DB_PASSWORD=your_secure_password_here
DB_HOST=localhost
DB_PORT=5432

# Firebase Configuration
FIREBASE_CREDENTIALS_PATH=firebase-credentials.json

# CORS Settings (for development)
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.100.12

# Server Configuration
SERVER_PORT=8000
SERVER_HOST=0.0.0.0
```

### 6.2 Important Security Notes

- **Never commit `.env` file** to Git (it's in `.gitignore`)
- **Change `SECRET_KEY`** in production
- **Use strong `DB_PASSWORD`** in production
- **Set `DEBUG=False`** in production

---

## 🗄️ Step 7: Run Database Migrations

With virtual environment activated:

```powershell
# Apply migrations to create database tables
python manage.py migrate

# Create superuser (admin account)
python manage.py createsuperuser
```

When prompted:
- **Username:** admin (or your preferred name)
- **Email:** your-email@example.com
- **Password:** create a strong password

---

## ✅ Step 8: Verify Setup

### 8.1 Run the Development Server

```powershell
# Start the backend server
python manage.py runserver
```

You should see:
```
System check identified no issues (0 silenced).
Django version 6.0.2, using settings 'fyp_backend.settings'
Starting development server at http://127.0.0.1:8000/
Quit the server with CTRL-BREAK.
```

### 8.2 Test the Endpoints

In your browser or Postman, visit:

```
http://127.0.0.1:8000/api/health/
```

You should see a JSON response:
```json
{
    "status": "ok",
    "message": "Backend is running"
}
```

### 8.3 Access Admin Panel

Visit: `http://127.0.0.1:8000/admin/`

Login with your superuser credentials.

---

## 🌐 Step 9: Allow External Connections (Optional)

To connect from other devices on your network:

### 9.1 Update `.env`

```
ALLOWED_HOSTS=localhost,127.0.0.1,192.168.x.x,0.0.0.0
```

Replace `192.168.x.x` with your computer's IP address.

### 9.2 Find Your IP Address

```powershell
ipconfig
```

Look for "IPv4 Address" under your active network (e.g., `192.168.100.12`)

### 9.3 Run Server on Network

```powershell
python manage.py runserver 0.0.0.0:8000
```

Now accessible from other devices:
```
http://192.168.100.12:8000/
```

---

## 🔧 Common Commands Reference

### Database

```powershell
# Create migrations (after model changes)
python manage.py makemigrations

# Apply migrations
python manage.py migrate

# Reset database (deletes all data!)
python manage.py migrate api zero  # Revert to initial
python manage.py migrate           # Reapply
```

### Admin & Users

```powershell
# Create another superuser
python manage.py createsuperuser

# Change superuser password
python manage.py changepassword admin
```

### Server

```powershell
# Run on specific port
python manage.py runserver 8080

# Run on all network interfaces
python manage.py runserver 0.0.0.0:8000
```

### Testing

```powershell
# Run all tests
python manage.py test

# Run specific app tests
python manage.py test api
```

### Cleanup

```powershell
# Clear Python cache
python manage.py clean_pyc

# Deactivate virtual environment
deactivate
```

---

## 🚨 Troubleshooting

### Issue: "psycopg2 connection error"

**Solution:**
```powershell
# Install PostgreSQL adapter
pip install psycopg2-binary

# Verify PostgreSQL is running
# (Check PostgreSQL in Services on Windows)
```

### Issue: "ModuleNotFoundError: No module named 'firebase_admin'"

**Solution:**
```powershell
pip install firebase-admin
```

### Issue: "Port 8000 already in use"

**Solution:**
```powershell
# Use different port
python manage.py runserver 8001
```

### Issue: "django.core.exceptions.ImproperlyConfigured"

**Solution:**
- Check `.env` file exists in project root
- Verify all environment variables are set correctly
- Check PostgreSQL is running and credentials are correct

### Issue: "Can't connect to PostgreSQL"

**Solution:**
```powershell
# Check PostgreSQL service is running
# On Windows: Services > PostgreSQL

# Test connection
psql -U aviansense_user -d aviansense_db -h localhost

# Verify credentials in .env match what you created
```

### Issue: "Firebase credentials not found"

**Solution:**
1. Verify `firebase-credentials.json` exists in project root
2. Check `FIREBASE_CREDENTIALS_PATH` in `.env` is correct
3. Ensure file has proper JSON format

---

## 📱 Connecting Flutter App

Once backend is running, update your Flutter app:

### 1. Update API Base URL

In `lib/services/api_service.dart` (or wherever API calls are):

```dart
const String API_BASE_URL = 'http://192.168.100.12:8000/api/';
// Replace 192.168.100.12 with your server's IP
```

### 2. Enable CORS in Browser/Device

The backend is configured with CORS enabled for development. Make sure your requests include proper headers.

### 3. Test Connection

```dart
try {
  final response = await http.get(
    Uri.parse('$API_BASE_URL/health/'),
  );
  print(response.body);
} catch (e) {
  print('Error: $e');
}
```

---

## 📚 Project Structure

```
fyp-backend/
├── api/                           # Main API app
│   ├── models.py                 # Database models
│   ├── views.py                  # API endpoints
│   ├── serializers.py            # Data serializers
│   ├── authentication.py         # Firebase auth
│   ├── ai_engine.py              # AI/ML logic
│   ├── migrations/               # Database migrations
│   └── urls.py                   # API routing
├── fyp_backend/                   # Project settings
│   ├── settings.py               # Django settings
│   ├── urls.py                   # URL configuration
│   └── wsgi.py                   # WSGI config
├── manage.py                      # Django management
├── requirements.txt               # Python dependencies
├── .env                           # Environment variables (not in repo)
├── firebase-credentials.json      # Firebase creds (not in repo)
├── README.md                      # Quick start
└── SETUP_GUIDE.md                # This file
```

---

## 🔒 Security Checklist

Before deploying to production:

- [ ] Change `DEBUG=False` in `.env`
- [ ] Generate a new `SECRET_KEY`
- [ ] Use a strong database password
- [ ] Consider using PostgreSQL hosted service (AWS RDS, Heroku, etc.)
- [ ] Set up HTTPS/SSL certificate
- [ ] Configure proper `ALLOWED_HOSTS`
- [ ] Use environment-specific settings
- [ ] Enable Firebase security rules
- [ ] Set up monitoring and logging
- [ ] Regular backups of database

---

## 📞 Getting Help

If you encounter issues:

1. Check the **Troubleshooting** section above
2. Review Django docs: [docs.djangoproject.com](https://docs.djangoproject.com)
3. Firebase docs: [firebase.google.com/docs](https://firebase.google.com/docs)
4. PostgreSQL docs: [postgresql.org/docs](https://www.postgresql.org/docs/)
5. Check GitHub Issues: [GitHub Issues](https://github.com/Farukhthegreat/fyp-backend/issues)

---

## ✨ Next Steps

1. ✅ **Backend Setup Complete!**
2. 🔗 **Connect Flutter app** to this backend
3. 📝 **Start developing** API endpoints
4. 🧪 **Write tests** for your endpoints
5. 🚀 **Deploy** to production when ready

---

**Happy Coding! 🚀**

Last Updated: February 2026
