"""Create five starter seller accounts. Change names, emails and territories before running."""
import sys
sys.path.insert(0, "backend")
from app.core.database import Base, engine, SessionLocal
from app.models.entities import User, UserRole

SELLERS = [
    ("seller1@thinksmart.pt", "Seller 1", "Lisboa"),
    ("seller2@thinksmart.pt", "Seller 2", "Cascais / Sintra"),
    ("seller3@thinksmart.pt", "Seller 3", "Porto"),
    ("seller4@thinksmart.pt", "Seller 4", "Algarve"),
    ("seller5@thinksmart.pt", "Seller 5", "Other regions"),
]
Base.metadata.create_all(bind=engine)
db=SessionLocal()
try:
    for email,name,territory in SELLERS:
        if not db.query(User).filter_by(email=email).first():
            db.add(User(email=email,full_name=name,territory=territory,role=UserRole.SELLER))
    db.commit()
    print("Five seller accounts are seeded. Replace placeholder emails/names with real staff details.")
finally: db.close()
