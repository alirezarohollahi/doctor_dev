#!/usr/bin/env python3
from doctor_dev_panel.security import create_password_hash
import getpass

password = getpass.getpass("Password: ")
print(create_password_hash(password))
