import os

import psycopg2
from dotenv import load_dotenv


def main():
    load_dotenv(override=True)
    database_url = os.getenv("DATABASE_URL")
    if not database_url:
        raise RuntimeError("DATABASE_URL is missing. Set it in the .env file.")
    if "[YOUR-PASSWORD]" in database_url:
        raise RuntimeError("Replace [YOUR-PASSWORD] in .env with your database password.")

    connection = psycopg2.connect(database_url)
    try:
        print("Database connection successful.")
    finally:
        connection.close()


if __name__ == "__main__":
    main()
