import os
from dotenv import load_dotenv
from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, sessionmaker

load_dotenv()

# Format : postgresql+psycopg://<utilisateur>:<mot_de_passe>@<hôte>:<port>/<base>
DATABASE_URL = os.environ["DATABASE_URL"]

# pool_pre_ping : vérifie qu'une connexion est toujours ouverte avant de la réutiliser
engine = create_engine(DATABASE_URL, pool_pre_ping=True)
SessionLocal = sessionmaker(engine)


class Base(DeclarativeBase):
    pass


def get_db():
    # FastAPI dependency: one session per request, closed once the response is sent.
    with SessionLocal() as db:
        yield db