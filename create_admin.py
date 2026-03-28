import sys
import os

# Add the current directory to Python path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from app import app, db, bcrypt
from models import User

def create_admin_user():
    with app.app_context():
        # Check if admin already exists
        admin_exists = User.query.filter_by(role='admin').first()
        if admin_exists:
            print("⚠️ Admin user already exists!")
            return
        
        # Create admin user
        admin = User(
            username="admin",  # Change this as needed
            phone="+251912345678",  # Change this as needed
            role="admin"
        )
        admin.set_password("admin123")  # Change this password!
        admin.is_approved = True
        
        db.session.add(admin)
        db.session.commit()
        print("✅ Admin user created successfully!")
        print(f"Username: admin")
        print(f"Password: admin123")  # Remember to change this!
        print("⚠️ IMPORTANT: Change the default password immediately!")

if __name__ == "__main__":
    create_admin_user()