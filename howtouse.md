cd /home/doctor_dev

python3 -m venv .venv
./.venv/bin/pip install -r requirements.txt

mkdir -p logs run

+++++++++++++++++++++++++++++++++++++++++++++

sudo nano /etc/systemd/system/doctor-freedom.service

+++++++++++++++++++++++++++++++++++++++++++++

sudo systemctl daemon-reload
sudo systemctl enable --now doctor-freedom


sudo systemctl status doctor-freedom
journalctl -u doctor-freedom -f