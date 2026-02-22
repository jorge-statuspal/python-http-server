import os

import pydev

os.environ.setdefault('PYDEV_SETTINGS_MODULE', 'settings')

application = pydev.get_wsgi_application()