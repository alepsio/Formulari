import psycopg2
import os

def get_db_connection():
    return psycopg2.connect(
        host="metro.proxy.rlwy.net",
        port="40745",
        database="trasporti",  # 👈 qui il tuo database reale
        user="postgres",
        password="KXXfFuNdXhksrAPXyzMahxkfqKOYmVpZ"  # ⚠️ esatto, quello preso da Railway
    )
