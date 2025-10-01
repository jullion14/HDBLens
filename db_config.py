import os
from sqlalchemy import create_engine
from pymongo import MongoClient
from dotenv import load_dotenv

# -------------------------------
# Load environment variables
# -------------------------------
load_dotenv()

# -------------------------------
# Relational DB (PostgreSQL / MySQL)
# -------------------------------
SQL_ENGINE = None

# SQL connections down here
def get_sql_engine():
    """
    Returns a SQLAlchemy engine for relational DB (PostgreSQL/MySQL).
    """
    global SQL_ENGINE
    if SQL_ENGINE is None:
        db_type = os.getenv("SQL_DB_TYPE", "postgresql")  # or 'mysql'
        user = os.getenv("SQL_USER", "user")
        password = os.getenv("SQL_PASSWORD", "password")
        host = os.getenv("SQL_HOST", "localhost")
        port = os.getenv("SQL_PORT", "5432")
        db_name = os.getenv("SQL_DB_NAME", "hdb_lens")

        if db_type == "postgresql":
            url = f"postgresql+psycopg2://{user}:{password}@{host}:{port}/{db_name}"
        else:
            raise ValueError("Unsupported SQL_DB_TYPE. Use 'postgresql' or 'mysql'.")

        SQL_ENGINE = create_engine(url, echo=False)
    return SQL_ENGINE


# -------------------------------
# NoSQL DB (MongoDB)
# -------------------------------
MONGO_CLIENT = None

def get_mongo_client():
    """
    Returns a MongoClient for MongoDB.
    """
    global MONGO_CLIENT
    if MONGO_CLIENT is None:
        mongo_uri = os.getenv("MONGO_URI", "mongodb://localhost:27017")
        MONGO_CLIENT = MongoClient(mongo_uri)
    return MONGO_CLIENT
