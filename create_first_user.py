from app import create_app
from models import db, User

app = create_app()

with app.app_context():
    email = "admin@example.com"
    password = "adminpassword"
    name = "Admin"

    if User.query.filter_by(email=email).first():
        print("A user with that email already exists.")
    else:
        user = User(email=email, name=name, role="admin")
        user.set_password(password)
        db.session.add(user)
        db.session.commit()
        print(f"User '{email}' created successfully.")