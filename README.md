# Doctor Dev Panel — Login Foundation

این نسخه فقط پایه تمیز پروژه است:

- لاگین قشنگ و مدرن برای ادمین
- FastAPI backend
- session cookie امضاشده
- password hash با PBKDF2
- CLI رنگی: `doctor-dev`
- installer: `scripts/doctor_dev.sh`
- systemd ready
- TLS direct mode اختیاری با مسیر certificate/key یا certbot

## نصب سریع روی سرور

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh install-panel
```

## آپدیت

```bash
curl -fsSL https://github.com/alirezarohollahi/doctor_dev/raw/refs/heads/master/scripts/doctor_dev.sh -o /tmp/doctor_dev.sh \
  && sudo bash /tmp/doctor_dev.sh update-panel
```

## CLI

```bash
doctor-dev help
doctor-dev config edit
doctor-dev restart
doctor-dev status
doctor-dev logs
```

## اجرای لوکال

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python - <<'PY'
from doctor_dev_panel.security import create_password_hash, generate_secret
print('APP_SECRET=' + generate_secret())
print('ADMIN_PASSWORD_HASH=' + create_password_hash('admin123456'))
PY
cp .env.example .env
# مقدارهای APP_SECRET و ADMIN_PASSWORD_HASH را در .env جایگزین کن
python main.py --env .env
```

آدرس: `http://127.0.0.1:8080`
