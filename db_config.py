import psycopg2

def get_db_connection():
    return psycopg2.connect(
        host='metro.proxy.rlwy.net',
        port='40745',
        dbname='railway',
        user='postgres',
        password='KXXfFuNdXhksrAPXyzMahxkfqKOYmVpZ'
    )
