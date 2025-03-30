import eventlet
eventlet.monkey_patch()
from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory, jsonify
from flask_login import LoginManager, login_user, logout_user, login_required, UserMixin, current_user
import psycopg2
from db_config import get_db_connection
from werkzeug.security import check_password_hash
from datetime import date, timedelta, datetime
from flask_socketio import SocketIO, emit, join_room




app = Flask(__name__)
socketio = SocketIO(app, cors_allowed_origins="*")
app.secret_key = 'supersecretkey'
login_manager = LoginManager()
login_manager.init_app(app)

class User(UserMixin):
    def __init__(self, id, nome, ruolo):
        self.id = id
        self.nome = nome
        self.ruolo = ruolo

@login_manager.user_loader
def load_user(user_id):
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT id, nome, ruolo FROM utenti WHERE id = %s", (int(user_id),))
    row = cur.fetchone()
    conn.close()
    if row:
        return User(row[0], row[1], row[2])
    return None

@app.route('/', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("SELECT id, nome, password_hash, ruolo FROM utenti WHERE email = %s", (email,))
        user = cur.fetchone()
        conn.close()

        if user and check_password_hash(user[2], password):
            user_obj = User(user[0], user[1], user[3])
            login_user(user_obj)
            if user[3] == 'admin':
                return redirect('/admin')
            else:
                return redirect('/autista')

    return render_template('login.html')

@socketio.on('join')
def handle_join(data):
    user_id = data.get('user_id')
    if user_id:
        join_room(f"user_{user_id}")


@app.route('/admin', methods=['GET', 'POST'])
@login_required
def admin_dashboard():
    if current_user.ruolo != 'admin':
        return redirect('/')

    conn = get_db_connection()
    cur = conn.cursor()

    # Salvataggio nuovo giro
    if request.method == 'POST':
        data = request.form['data']
        produttore_id = request.form['produttore_id']
        assegnato_a = request.form['assegnato_a']

        # Recupera i dati del produttore selezionato
        cur.execute("SELECT denominazione, indirizzo, email FROM produttori WHERE id = %s", (produttore_id,))
        p = cur.fetchone()
        cliente = p[0]
        indirizzo = p[1]
        email_cliente = p[2]

        cur.execute("""
            INSERT INTO giri_clienti (data, cliente, indirizzo, email_cliente, assegnato_a)
            VALUES (%s, %s, %s, %s, %s)
        """, (data, cliente, indirizzo, email_cliente, assegnato_a))
        conn.commit()

        # Inviare notifica in tempo reale all'autista
        socketio.emit(
            'nuovo_giro',
            {
                'cliente': cliente,
                'indirizzo': indirizzo,
                'data': data,
            },
            to=f"user_{assegnato_a}"
        )

    

    # Lista autisti
    cur.execute("SELECT id, nome FROM utenti WHERE ruolo = 'autista'")
    autisti = cur.fetchall()

    # Lista produttori
    cur.execute("SELECT id, denominazione, indirizzo, sede_operativa, email FROM produttori ORDER BY denominazione")
    produttori = cur.fetchall()

    # Filtro per data
    data_filtro = request.args.get('data')
    if data_filtro:
        cur.execute("""
            SELECT g.data, g.cliente, g.indirizzo, g.formulario_pdf, g.orario_compilazione, g.assegnato_a, g.id
            FROM giri_clienti g
            WHERE g.data = %s
            ORDER BY g.assegnato_a, g.data DESC
        """, (data_filtro,))
    else:
        cur.execute("""
            SELECT g.data, g.cliente, g.indirizzo, g.formulario_pdf, g.orario_compilazione, g.assegnato_a, g.id
            FROM giri_clienti g
            ORDER BY g.assegnato_a, g.data DESC
        """)
    giri = cur.fetchall()
    

    cur.execute("""
        SELECT a.id, a.nome FROM utenti a WHERE ruolo = 'autista'
    """)
    autisti = cur.fetchall()

    cur.execute("""
        SELECT ag.autista_id, ag.data_giornata, ag.zip_path
        FROM archivi_giornate ag
        ORDER BY ag.data_giornata DESC
    """)
    archivi = cur.fetchall()
    conn.close()

    return render_template('dashboard_admin.html',
                           autisti=autisti,
                           giri=giri,
                           data_filtro=data_filtro,
                           produttori=produttori,
                           archivi=archivi)



@app.route('/admin/elimina_giro', methods=['POST'])
@login_required
def elimina_giro():
    if current_user.ruolo != 'admin':
        return redirect('/')

    giro_id = request.form['giro_id']

    # Recupera ID utente a cui era assegnato PRIMA di eliminare
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT assegnato_a FROM giri_clienti WHERE id = %s", (giro_id,))
    result = cur.fetchone()

    if result:
        assegnato_a = result[0]

        # Elimina il giro
        cur.execute("DELETE FROM giri_clienti WHERE id = %s", (giro_id,))
        conn.commit()

        # Invia aggiornamento in tempo reale all'autista
        socketio.emit('elimina_giro', {'giro_id': giro_id}, to=f"user_{assegnato_a}")

    conn.close()
    return redirect('/admin')

@app.route('/autista')
@login_required
def autista_dashboard():
    if current_user.ruolo != 'autista':
        return redirect('/')

    oggi_str = request.args.get('data', date.today().isoformat())
    oggi = datetime.strptime(oggi_str, '%Y-%m-%d').date()

    giorno_prec = (oggi - timedelta(days=1)).isoformat()
    giorno_succ = (oggi + timedelta(days=1)).isoformat()

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        SELECT id, data, cliente, indirizzo, formulario_pdf
        FROM giri_clienti
        WHERE assegnato_a = %s AND data = %s
        ORDER BY data ASC
    """, (current_user.id, oggi))
    giri = cur.fetchall()
    conn.close()

    return render_template('dashboard_autista.html',
                           giri=giri,
                           data_corrente=oggi.isoformat(),
                           giorno_prec=giorno_prec,
                           giorno_succ=giorno_succ)

@app.route('/admin/aggiungi_autista', methods=['GET', 'POST'])
@login_required
def aggiungi_autista():
    if not current_user.ruolo == 'admin':
        return redirect('/')

    if request.method == 'POST':
        nome = request.form['nome']
        email = request.form['email']
        password = request.form['password']

        from werkzeug.security import generate_password_hash
        hashed_pw = generate_password_hash(password)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("INSERT INTO utenti (nome, email, password_hash, ruolo) VALUES (%s, %s, %s, 'autista')",
                    (nome, email, hashed_pw))
        conn.commit()
        conn.close()

        return redirect('/admin')

    return render_template('aggiungi_autista.html')

@app.route('/admin/aggiungi_produttore', methods=['GET', 'POST'])
@login_required
def aggiungi_produttore():
    if current_user.ruolo != 'admin':
        return redirect('/')

    if request.method == 'POST':
        denominazione = request.form['denominazione']
        indirizzo = request.form['indirizzo']
        sede_operativa = request.form['sede_operativa']
        partita_iva = request.form['partita_iva']
        email = request.form['email']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO produttori (denominazione, indirizzo, sede_operativa, partita_iva, email)
            VALUES (%s, %s, %s, %s, %s)
        """, (denominazione, indirizzo, sede_operativa, partita_iva, email))
        conn.commit()
        conn.close()

        return redirect('/admin')

    return render_template('aggiungi_produttore.html')

@app.route('/admin/aggiungi_destinatario', methods=['GET', 'POST'])
@login_required
def aggiungi_destinatario():
    if current_user.ruolo != 'admin':
        return redirect('/')

    if request.method == 'POST':
        denominazione = request.form['denominazione']
        indirizzo = request.form['indirizzo']
        partita_iva = request.form['partita_iva']
        autorizzazione = request.form['autorizzazione']
        tipo_aut = request.form['tipo_autorizzazione']
        rxx = request.form['rxx']
        dxx = request.form['dxx']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO destinatari (denominazione, indirizzo, partita_iva, autorizzazione, tipo_autorizzazione, codice_r, codice_d)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
        """, (denominazione, indirizzo, partita_iva, autorizzazione, tipo_aut, rxx, dxx))
        conn.commit()
        conn.close()

        return redirect('/admin')

    return render_template('aggiungi_destinatario.html')

@app.route('/admin/aggiungi_trasportatore', methods=['GET', 'POST'])
@login_required
def aggiungi_trasportatore():
    if current_user.ruolo != 'admin':
        return redirect('/')

    if request.method == 'POST':
        denominazione = request.form['denominazione']
        partita_iva = request.form['partita_iva']
        autorizzazione = request.form['autorizzazione']

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO trasportatori (denominazione, partita_iva, autorizzazione)
            VALUES (%s, %s, %s)
        """, (denominazione, partita_iva, autorizzazione))
        conn.commit()
        conn.close()

        return redirect('/admin')

    return render_template('aggiungi_trasportatore.html')





@app.route('/impostazioni', methods=['GET', 'POST'])
@login_required
def impostazioni_autista():
    if current_user.ruolo != 'autista':
        return redirect('/')

    conn = get_db_connection()
    cur = conn.cursor()

    if request.method == 'POST':
        targa = request.form['targa']
        nome = request.form['conducente']

        cur.execute("""
            UPDATE utenti SET targa = %s, conducente_nome = %s WHERE id = %s
        """, (targa, nome, current_user.id))
        conn.commit()
        conn.close()
        return redirect('/autista')


    # Precompila se già salvati
    cur.execute("SELECT targa, conducente_nome FROM utenti WHERE id = %s", (current_user.id,))
    dati = cur.fetchone()
    conn.close()

    return render_template('impostazioni_autista.html', dati=dati)

@app.route('/compila_formulario/<int:giro_id>', methods=['GET', 'POST'])
@login_required
def compila_formulario(giro_id):
    if current_user.ruolo != 'autista':
        return redirect('/')

    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("SELECT cliente, indirizzo, email_cliente FROM giri_clienti WHERE id = %s AND assegnato_a = %s", (giro_id, current_user.id))
    giro = cur.fetchone()

    # Recupero anagrafiche
    cur.execute("SELECT * FROM produttori ORDER BY denominazione")
    produttori = cur.fetchall()

    cur.execute("SELECT * FROM destinatari ORDER BY denominazione")
    destinatari = cur.fetchall()

    cur.execute("SELECT * FROM trasportatori ORDER BY denominazione")
    trasportatori = cur.fetchall()

    if not giro:
        conn.close()
        return "Giro non trovato o non assegnato a te.", 403

    if request.method == 'POST':
        # Recupero ID selezionati dal form
        id_produttore = request.form['produttore']
        id_destinatario = request.form['destinatario']
        id_trasportatore = request.form['trasportatore']

        # Recupero dati completi
        cur.execute("SELECT * FROM produttori WHERE id = %s", (id_produttore,))
        produttore = cur.fetchone()

        cur.execute("SELECT * FROM destinatari WHERE id = %s", (id_destinatario,))
        destinatario = cur.fetchone()

        cur.execute("SELECT * FROM trasportatori WHERE id = %s", (id_trasportatore,))
        trasportatore = cur.fetchone()

        cur.execute("SELECT targa, conducente_nome FROM utenti WHERE id = %s", (current_user.id,))
        dati_autista = cur.fetchone()

        conn.close()


        dati = {
            "cliente": giro[0],  # Per nome file

            # 💼 Produttore
            "Text-EiNF6149Sl": produttore[1],
            "Text-KC1l2xEp09": produttore[2],
            "Text-hXw-MZg2vc": produttore[3],
            "Text-vAc1UZusD3": produttore[4],

            # 🏭 Destinatario
            "Text-tL-nVbe2JF": destinatario[1],
            "Text-_zLFTFI5n_": destinatario[2],
            "Text-cAcqLq4ct8": destinatario[3],
            "Text-j2SCccuVQ7": destinatario[4],
            "Text-3sYHXoutcF": destinatario[5],
            "Text-bUcll4op52": destinatario[6],
            "Text-8qzbZ9JB6Y": destinatario[7],

            # 🚚 Trasportatore
            "Text-6c2uXRYZJk": trasportatore[1],
            "Text-KRlcOVuJoQ": trasportatore[2],
            "Text-ocAjz5D8Zj": trasportatore[3],

            # 📦 Altri dati
            "Text-dyAONWMSmO": request.form['quantita'],
            "Text-U0AYLqi4UQ": request.form['codice_eer'],
            "Text-yDutVdeFV6": dati_autista[0],  # targa
            "Text-jTfqXuYmHp": request.form['colli'],
            "Text-xIlZWzJiY6": dati_autista[1], # conducente
            "Date-ouDqqWbkwf": request.form['data_trasporto'],
            "Text-dULvUPKHVy": request.form['ora_trasporto'],
        }

        if request.form['unita'] == 'kg':
            dati["CheckBox-NQYcTVbIPW"] = "/Yes"

        from utils.pdf_utils import compila_pdf_con_acroform
        pdf_path = compila_pdf_con_acroform(dati, giro_id)

        conn = get_db_connection()
        cur = conn.cursor()
        cur.execute("""
                        UPDATE giri_clienti 
                        SET formulario_pdf = %s, orario_compilazione = %s 
                        WHERE id = %s
                    """, (pdf_path, datetime.now(), giro_id))
        conn.commit()
        conn.close()

        return '', 200


    cur = get_db_connection().cursor()
    cur.execute("SELECT targa, conducente_nome FROM utenti WHERE id = %s", (current_user.id,))
    dati_autista = cur.fetchone()

    return render_template(
        'compila_formulario.html',
        giro=giro,
        giro_id=giro_id,
        produttori=produttori,
        destinatari=destinatari,
        trasportatori=trasportatori,
        autista_targa=dati_autista[0],
        autista_nome=dati_autista[1]
    )

@app.route('/fine_giornata', methods=['POST'])
@login_required
def fine_giornata():
    if current_user.ruolo != 'autista':
        return redirect('/')

    oggi = date.today()
    conn = get_db_connection()
    cur = conn.cursor()

    # 1. Controlla se già esiste nel DB
    cur.execute("""
        SELECT id FROM archivi_giornate 
        WHERE autista_id = %s AND data_giornata = %s
    """, (current_user.id, oggi))
    esiste_archivio = cur.fetchone()

    if esiste_archivio:
        conn.close()
        return jsonify({'status': 'esistente'}), 200

    # 2. Recupera tutti i formulari
    cur.execute("""
        SELECT formulario_pdf FROM giri_clienti 
        WHERE assegnato_a = %s AND data = %s
    """, (current_user.id, oggi))
    risultati = cur.fetchall()
    conn.close()

    formulari_completati = [f[0] for f in risultati if f[0]]
    if len(formulari_completati) != len(risultati):
        return "Non tutti i formulari sono stati compilati.", 400

    # 3. Crea cartella e ZIP
    import zipfile, os
    zip_folder = 'static/archivi_giornate'
    os.makedirs(zip_folder, exist_ok=True)

    zip_filename = f"autista_{current_user.id}_{oggi.isoformat()}.zip"
    zip_path = os.path.join(zip_folder, zip_filename)

    with zipfile.ZipFile(zip_path, 'w') as zipf:
        for path in formulari_completati:
            full_path = os.path.join('static', path) if not path.startswith('static/') else path
            if os.path.exists(full_path):
                zipf.write(full_path, os.path.basename(full_path))

    # 4. Salva nel DB
    conn = get_db_connection()
    cur = conn.cursor()
    cur.execute("""
        INSERT INTO archivi_giornate (autista_id, data_giornata, zip_path)
        VALUES (%s, %s, %s)
    """, (current_user.id, oggi, zip_path))
    conn.commit()
    conn.close()

    return redirect('/autista')


@app.route('/download_archivio/<filename>')
@login_required
def download_archivio(filename):
    if current_user.ruolo != 'admin':
        return "Non autorizzato", 403
    return send_from_directory('static/archivi_giornate', filename, as_attachment=True)



@app.route('/logout')
def logout():
    logout_user()
    return redirect('/')

if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000)




