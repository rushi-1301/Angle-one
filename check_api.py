from django.conf import settings
import os, sys, django

# Set up Django environment
sys.path.append(os.getcwd())
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "portal.settings")
django.setup()

from backtest_runner.models import AngelOneKey
from accounts.models import User

try:
    u = User.objects.get(username='gautam_80')
    print(f"User found: {u.username}")
    if hasattr(u, "angel_api"):
        key = u.angel_api
        print(f"Client Code: {key.client_code}")
        print(f"API Key: {key.api_key[:5]}...")
        print(f"JWT Token: {'Present' if key.jwt_token else 'Missing'} (len: {len(key.jwt_token) if key.jwt_token else 0})")
        print(f"Updated At: {key.updated_at}")
    else:
        print("User has no angel_api relationship.")
except Exception as e:
    print(f"Error: {e}")
