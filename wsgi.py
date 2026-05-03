# TutorPay — WSGI Configuration for PythonAnywhere
#
# สร้างไฟล์นี้ไว้เป็นตัวอย่าง
# ให้คัดลอกเนื้อหาไปวางในหน้า WSGI configuration ของ PythonAnywhere
# แก้ username เป็นชื่อ PythonAnywhere ของคุณ

import sys
import os

# แก้ 'yourusername' เป็น username ของคุณบน PythonAnywhere
project_home = '/home/Nichzako/TutorPay'

if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.chdir(project_home)

from app import app as application  # noqa
