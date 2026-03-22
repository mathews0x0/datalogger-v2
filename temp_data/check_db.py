import os
import sys
from pathlib import Path

# Add server to path
sys.path.insert(0, str(Path(__file__).parent.parent / "server"))
sys.path.insert(0, str(Path(__file__).parent.parent / "server" / "api"))

from api import create_app
from api.models import db, DeviceToken

app = create_app()

with app.app_context():
    tokens = DeviceToken.query.all()
    print("ALL DEVICE TOKENS IN DB:")
    for t in tokens:
        print(t.to_dict())
