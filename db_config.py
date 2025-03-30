import psycopg2

def get_db_connection():
    return psycopg2.connect(
        dbname="trasporti",
        user="postgres",
        password="postgres",
        host="localhost",
        port="5432"
    )
