import hashlib, os, json
from functools import wraps
from datetime import datetime, date
from flask import (Flask, render_template, request, session, redirect,
                   url_for, flash, send_file, jsonify)
from reportlab.pdfgen import canvas
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.units import mm
import pymysql

# ─── Flask config ───────────────────────────────────────────────
app = Flask(__name__, template_folder='template')
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'akhlak360-secret-key-pti-2026')

# Folder downloads (kalau di Vercel, hanya /tmp yang writable)
if os.environ.get('VERCEL'):
    DOWNLOAD_FOLDER = '/tmp/downloads'
else:
    DOWNLOAD_FOLDER = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'downloads')
os.makedirs(DOWNLOAD_FOLDER, exist_ok=True)

# ─── Database helpers ───────────────────────────────────────────
class MySQLWrapper:
    def __init__(self, **kwargs):
        self.conn = pymysql.connect(**kwargs)

    def execute(self, query, params=()):
        # Convert SQLite placeholders to MySQL placeholders
        mysql_query = query.replace('?', '%s')
        cursor = self.conn.cursor()
        cursor.execute(mysql_query, params)
        return cursor

    def commit(self):
        self.conn.commit()

    def close(self):
        self.conn.close()

def get_db():
    return MySQLWrapper(
        host=os.environ.get('MYSQLHOST', 'localhost'),
        port=int(os.environ.get('MYSQLPORT', 3306)),
        user=os.environ.get('MYSQLUSER', 'root'),
        password=os.environ.get('MYSQLPASSWORD', ''),
        database=os.environ.get('MYSQLDATABASE', 'akhlak360_db'),
        cursorclass=pymysql.cursors.DictCursor
    )

# ─── Auth decorators ───────────────────────────────────────────
def login_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if 'user_id' not in session:
            flash('Silakan login terlebih dahulu.', 'warning')
            return redirect(url_for('login'))
        return f(*a, **kw)
    return wrapper

def hc_required(f):
    @wraps(f)
    def wrapper(*a, **kw):
        if 'user_id' not in session:
            return redirect(url_for('login'))
        if session.get('role') != 'hc':
            flash('Akses ditolak — hanya HC.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*a, **kw)
    return wrapper

# ═══════════════════════════════════════════════════════════════
#  ROUTES — AUTH
# ═══════════════════════════════════════════════════════════════
@app.route('/')
def index():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET','POST'])
def login():
    if 'user_id' in session:
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        uname = request.form.get('username','').strip()
        pwd = request.form.get('password','')
        hashed = hashlib.md5(pwd.encode()).hexdigest()
        db = get_db()
        user = db.execute("SELECT * FROM user WHERE username=?", (uname,)).fetchone()
        db.close()
        if user and (user['password_hash'] == hashed or user['password_hash'] == pwd):
            session['user_id'] = user['id_user']
            session['username'] = user['username']
            session['role'] = user['role']
            session['id_karyawan'] = user['id_karyawan']
            # Get display name
            if user['id_karyawan']:
                db2 = get_db()
                k = db2.execute("SELECT nama FROM karyawan WHERE id_karyawan=?", (user['id_karyawan'],)).fetchone()
                session['user_name'] = k['nama'] if k else user['username']
                db2.close()
            else:
                session['user_name'] = 'Administrator HC'

            session['has_seen_reminder'] = False
            return redirect(url_for('dashboard'))
        flash('Username atau password salah!', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

# ═══════════════════════════════════════════════════════════════
#  ROUTES — DASHBOARD
# ═══════════════════════════════════════════════════════════════
@app.route('/dashboard')
@login_required
def dashboard():
    db = get_db()
    role = session.get('role')
    if role == 'hc':
        total_k = db.execute("SELECT COUNT(*) c FROM karyawan").fetchone()['c']
        total_q = db.execute("SELECT COUNT(*) c FROM kuesioner WHERE status='active'").fetchone()['c']
        total_penilai = db.execute("SELECT COUNT(*) c FROM penilai WHERE id_kuesioner=1").fetchone()['c']
        total_selesai = db.execute("SELECT COUNT(*) c FROM penilai WHERE id_kuesioner=1 AND status_pengisian='selesai'").fetchone()['c']
        total_belum = total_penilai - total_selesai
        persen = round(total_selesai / total_penilai * 100) if total_penilai > 0 else 0

        # --- Chart Data Fetching ---
        dept_data_raw = db.execute("SELECT departemen, COUNT(*) as c FROM karyawan GROUP BY departemen").fetchall()
        karyawan_dept_chart = [{'name': d['departemen'], 'y': d['c']} for d in dept_data_raw]

        karyawan_all = db.execute("SELECT nama, departemen, jabatan FROM karyawan ORDER BY departemen, nama").fetchall()
        karyawan_list = [dict(row) for row in karyawan_all]

        penilai_data_raw = db.execute('''
            SELECT kategori, status_pengisian, COUNT(*) as c
            FROM penilai
            WHERE id_kuesioner=1
            GROUP BY kategori, status_pengisian
        ''').fetchall()

        categories = ['Atasan', 'Bawahan', 'Rekan', 'Diri Sendiri']
        kat_map = {'atasan': 0, 'bawahan': 1, 'rekan': 2, 'diri_sendiri': 3}
        selesai_data = [0, 0, 0, 0]
        belum_data = [0, 0, 0, 0]

        for row in penilai_data_raw:
            kat_idx = kat_map.get(row['kategori'])
            if kat_idx is not None:
                if row['status_pengisian'] == 'selesai':
                    selesai_data[kat_idx] = row['c']
                else:
                    belum_data[kat_idx] = row['c']

        penilai_chart = {
            'categories': categories,
            'selesai': selesai_data,
            'belum': belum_data
        }

        # Recent completion
        recent = db.execute('''
            SELECT k.nama, p.kategori, k2.nama as dinilai_nama
            FROM penilai p
            JOIN karyawan k ON p.id_karyawan_penilai=k.id_karyawan
            JOIN karyawan k2 ON p.id_karyawan_dinilai=k2.id_karyawan
            WHERE p.status_pengisian='selesai'
            ORDER BY p.id_penilai DESC LIMIT 5
        ''').fetchall()
        db.close()
        return render_template('dashboard_hc.html', total_karyawan=total_k,
                               total_q=total_q, total_penilai=total_penilai,
                               total_selesai=total_selesai, total_belum=total_belum,
                               persen=persen, karyawan_dept_chart=karyawan_dept_chart,
                               penilai_chart=penilai_chart, recent=recent,
                               karyawan_list=karyawan_list)
    else:
        kid = session.get('id_karyawan')
        tugas = db.execute('''
            SELECT p.id_penilai, p.kategori, p.status_pengisian, k.nama as dinilai_nama
            FROM penilai p JOIN karyawan k ON p.id_karyawan_dinilai=k.id_karyawan
            WHERE p.id_karyawan_penilai=? AND p.id_kuesioner=1
        ''', (kid,)).fetchall()
        hasil = db.execute('''
            SELECT dimensi, skor_atasan, skor_rekan, skor_bawahan, skor_diri, skor_akhir
            FROM hasil_penilaian
            WHERE id_karyawan=? AND id_kuesioner=1
        ''', (kid,)).fetchall()
        db.close()

        # Selalu tampilkan chart, default 0 untuk semua kategori
        chart_data = {
            'Amanah': {'atasan':0, 'rekan':0, 'bawahan':0, 'diri':0, 'akhir':0},
            'Kompeten': {'atasan':0, 'rekan':0, 'bawahan':0, 'diri':0, 'akhir':0},
            'Harmonis': {'atasan':0, 'rekan':0, 'bawahan':0, 'diri':0, 'akhir':0},
            'Loyal': {'atasan':0, 'rekan':0, 'bawahan':0, 'diri':0, 'akhir':0},
            'Adaptif': {'atasan':0, 'rekan':0, 'bawahan':0, 'diri':0, 'akhir':0},
            'Kolaboratif': {'atasan':0, 'rekan':0, 'bawahan':0, 'diri':0, 'akhir':0}
        }

        if hasil:
            for r in hasil:
                chart_data[r['dimensi']] = {
                    'atasan': r['skor_atasan'] or 0,
                    'rekan': r['skor_rekan'] or 0,
                    'bawahan': r['skor_bawahan'] or 0,
                    'diri': r['skor_diri'] or 0,
                    'akhir': r['skor_akhir'] or 0
                }

        pending_count = sum(1 for t in tugas if t['status_pengisian'] != 'selesai')
        show_reminder = False
        if pending_count > 0 and not session.get('has_seen_reminder'):
            show_reminder = True
            session['has_seen_reminder'] = True

        return render_template('dashboard_karyawan.html', tugas=tugas, chart_data=chart_data,
                               show_reminder=show_reminder, pending_count=pending_count)

@app.route('/profile', methods=['GET', 'POST'])
@login_required
def profile():
    db = get_db()
    id_user = session.get('user_id')
    id_karyawan = session.get('id_karyawan')

    # Ambil data karyawan jika ada
    karyawan = None
    atasan = None
    if id_karyawan:
        karyawan = db.execute("SELECT * FROM karyawan WHERE id_karyawan=?", (id_karyawan,)).fetchone()
        if karyawan and karyawan['id_atasan']:
            atasan = db.execute("SELECT nama FROM karyawan WHERE id_karyawan=?", (karyawan['id_atasan'],)).fetchone()

    if request.method == 'POST':
        old_pw = request.form.get('old_password')
        new_pw = request.form.get('new_password')
        confirm_pw = request.form.get('confirm_password')

        # Validasi
        user = db.execute("SELECT password_hash FROM user WHERE id_user=?", (id_user,)).fetchone()
        old_hash = hashlib.md5(old_pw.encode()).hexdigest()

        if old_hash != user['password_hash']:
            flash('Password Lama yang Anda masukkan salah.', 'danger')
        elif new_pw != confirm_pw:
            flash('Konfirmasi Password Baru tidak cocok.', 'danger')
        elif len(new_pw) < 6:
            flash('Password Baru minimal 6 karakter.', 'warning')
        else:
            new_hash = hashlib.md5(new_pw.encode()).hexdigest()
            db.execute("UPDATE user SET password_hash=? WHERE id_user=?", (new_hash, id_user))
            db.commit()
            flash('Password Anda berhasil diubah! Silakan gunakan password baru pada saat login berikutnya.', 'success')

    db.close()
    return render_template('profile.html', karyawan=karyawan, atasan=atasan)

# ═══════════════════════════════════════════════════════════════
#  ROUTES — KARYAWAN CRUD (HC only)
# ═══════════════════════════════════════════════════════════════
@app.route('/karyawan')
@hc_required
def karyawan_list():
    db = get_db()
    data = db.execute('''
        SELECT k.*, a.nama as atasan_nama FROM karyawan k
        LEFT JOIN karyawan a ON k.id_atasan=a.id_karyawan
        ORDER BY k.id_karyawan
    ''').fetchall()
    db.close()
    return render_template('karyawan.html', karyawan_list=data)

@app.route('/karyawan/tambah', methods=['GET','POST'])
@hc_required
def tambah_karyawan():
    db = get_db()
    if request.method == 'POST':
        nip = request.form['nip'].strip()
        nama = request.form['nama'].strip()
        jabatan = request.form['jabatan'].strip()
        departemen = request.form['departemen'].strip()
        id_atasan = request.form.get('id_atasan') or None
        try:
            c = db.execute("INSERT INTO karyawan (nip,nama,jabatan,departemen,id_atasan) VALUES (?,?,?,?,?)",
                       (nip, nama, jabatan, departemen, id_atasan))
            kid = c.lastrowid

            # Buat akun otomatis (username = NIP, password = NIP123)
            pw_hash = hashlib.md5((nip + "123").encode()).hexdigest()
            db.execute("INSERT INTO user (username,password_hash,role,id_karyawan) VALUES (?,?,'karyawan',?)",
                       (nip, pw_hash, kid))
            db.commit()
            flash('Karyawan berhasil ditambahkan!', 'success')
        except Exception as e:
            flash(f'Gagal menambahkan karyawan: {e}', 'danger')
        db.close()
        return redirect(url_for('karyawan_list'))
    atasan = db.execute("SELECT id_karyawan, nama, jabatan FROM karyawan ORDER BY nama").fetchall()
    db.close()
    return render_template('tambah_karyawan.html', atasan_list=atasan)

@app.route('/karyawan/edit/<int:id>', methods=['GET','POST'])
@hc_required
def edit_karyawan(id):
    db = get_db()
    if request.method == 'POST':
        db.execute("UPDATE karyawan SET nip=?,nama=?,jabatan=?,departemen=?,id_atasan=? WHERE id_karyawan=?",
                   (request.form['nip'], request.form['nama'], request.form['jabatan'],
                    request.form['departemen'], request.form.get('id_atasan') or None, id))
        db.commit(); db.close()
        flash('Data karyawan berhasil diperbarui!', 'success')
        return redirect(url_for('karyawan_list'))
    k = db.execute("SELECT * FROM karyawan WHERE id_karyawan=?", (id,)).fetchone()
    atasan = db.execute("SELECT id_karyawan, nama, jabatan FROM karyawan WHERE id_karyawan!=? ORDER BY nama", (id,)).fetchall()
    db.close()
    if not k:
        flash('Karyawan tidak ditemukan!', 'danger')
        return redirect(url_for('karyawan_list'))
    return render_template('edit_karyawan.html', karyawan=k, atasan_list=atasan)

@app.route('/karyawan/hapus/<int:id>')
@hc_required
def hapus_karyawan(id):
    db = get_db()
    try:
        db.execute("DELETE FROM karyawan WHERE id_karyawan=?", (id,))
        db.commit()
        flash('Karyawan berhasil dihapus!', 'success')
    except:
        flash('Gagal menghapus. Karyawan mungkin masih terhubung dengan data lain.', 'danger')
    db.close()
    return redirect(url_for('karyawan_list'))

@app.route('/karyawan/import', methods=['POST'])
@hc_required
def import_karyawan():
    if 'file' not in request.files:
        flash('Tidak ada file yang diunggah.', 'danger')
        return redirect(url_for('karyawan_list'))

    file = request.files['file']
    if file.filename == '':
        flash('File tidak valid.', 'danger')
        return redirect(url_for('karyawan_list'))

    try:
        import pandas as pd
        if file.filename.endswith('.csv'):
            df = pd.read_csv(file)
        else:
            df = pd.read_excel(file)

        required_cols = ['NIP', 'Nama', 'Jabatan', 'Departemen']
        for col in required_cols:
            if col not in df.columns:
                flash(f'Kolom wajib {col} tidak ditemukan dalam file!', 'danger')
                return redirect(url_for('karyawan_list'))

        db = get_db()
        success = 0

        # Pass 1: Insert karyawan baru
        for _, row in df.iterrows():
            # Hapus .0 jika terbaca sebagai float oleh pandas
            nip = str(row['NIP']).strip().replace('.0', '')
            nama = str(row['Nama']).strip()
            jabatan = str(row['Jabatan']).strip()
            departemen = str(row['Departemen']).strip()

            exist = db.execute("SELECT id_karyawan FROM karyawan WHERE nip=?", (nip,)).fetchone()
            if not exist:
                c = db.execute("INSERT INTO karyawan (nip,nama,jabatan,departemen,id_atasan) VALUES (?,?,?,?,NULL)",
                          (nip, nama, jabatan, departemen))
                kid = c.lastrowid
                pw_hash = hashlib.md5((nip + "123").encode()).hexdigest()
                db.execute("INSERT INTO user (username,password_hash,role,id_karyawan) VALUES (?,?,'karyawan',?)",
                          (nip, pw_hash, kid))
                success += 1

        # Pass 2: Update id_atasan
        if 'NIP_Atasan' in df.columns:
            for _, row in df.iterrows():
                nip = str(row['NIP']).strip().replace('.0', '')
                nip_atasan = str(row['NIP_Atasan']).strip().replace('.0', '') if pd.notna(row['NIP_Atasan']) else None

                if nip_atasan and nip_atasan != 'nan' and nip_atasan != 'None' and nip_atasan != '':
                    # Cari id_atasan berdasarkan nip_atasan
                    atasan = db.execute("SELECT id_karyawan FROM karyawan WHERE nip=?", (nip_atasan,)).fetchone()
                    if atasan:
                        # Update karyawan yang bersangkutan
                        db.execute("UPDATE karyawan SET id_atasan=? WHERE nip=?", (atasan['id_karyawan'], nip))

        db.commit()
        db.close()
        flash(f'Berhasil mengimpor {success} karyawan baru.', 'success')
    except Exception as e:
        flash(f'Gagal mengimpor file: {str(e)}', 'danger')

    return redirect(url_for('karyawan_list'))

# ═══════════════════════════════════════════════════════════════
#  ROUTES — KUESIONER
# ═══════════════════════════════════════════════════════════════
@app.route('/kuesioner')
@login_required
def kuesioner():
    db = get_db()
    role = session.get('role')
    if role == 'hc':
        kuesioner_list = db.execute("SELECT * FROM kuesioner ORDER BY id_kuesioner DESC").fetchall()
        # Count stats per kuesioner
        stats = {}
        for q in kuesioner_list:
            total = db.execute("SELECT COUNT(*) c FROM penilai WHERE id_kuesioner=?", (q['id_kuesioner'],)).fetchone()['c']
            done = db.execute("SELECT COUNT(*) c FROM penilai WHERE id_kuesioner=? AND status_pengisian='selesai'", (q['id_kuesioner'],)).fetchone()['c']
            stats[q['id_kuesioner']] = {'total': total, 'done': done}
        db.close()
        return render_template('kuesioner_list.html', kuesioner_list=kuesioner_list, stats=stats)
    else:
        kid = session.get('id_karyawan')
        tugas = db.execute('''
            SELECT p.id_penilai, p.kategori, p.status_pengisian, k.nama as dinilai_nama,
                   q.nama_kuesioner, q.periode
            FROM penilai p
            JOIN karyawan k ON p.id_karyawan_dinilai=k.id_karyawan
            JOIN kuesioner q ON p.id_kuesioner=q.id_kuesioner
            WHERE p.id_karyawan_penilai=? ORDER BY p.status_pengisian ASC
        ''', (kid,)).fetchall()
        db.close()
        return render_template('kuesioner_list.html', tugas=tugas)

@app.route('/kuesioner/kelola', methods=['GET','POST'])
@app.route('/kuesioner/kelola/<int:id>', methods=['GET','POST'])
@hc_required
def kuesioner_kelola(id=None):
    db = get_db()
    if request.method == 'POST':
        nama = request.form['nama_kuesioner']
        periode = request.form['periode']
        tgl_mulai = request.form['tanggal_mulai']
        tgl_selesai = request.form['tanggal_selesai']
        status = request.form.get('status', 'draft')
        if id:
            db.execute("UPDATE kuesioner SET nama_kuesioner=?,periode=?,tanggal_mulai=?,tanggal_selesai=?,status=? WHERE id_kuesioner=?",
                       (nama, periode, tgl_mulai, tgl_selesai, status, id))
        else:
            c = db.execute("INSERT INTO kuesioner (nama_kuesioner,periode,tanggal_mulai,tanggal_selesai,status) VALUES (?,?,?,?,?)",
                       (nama, periode, tgl_mulai, tgl_selesai, status))
            id_q = c.lastrowid

            # Auto-seed standard AKHLAK questions
            questions = [
                ('Amanah', 1, 'Memenuhi janji dan komitmen.'),
                ('Amanah', 2, 'Bertanggung jawab atas tugas, keputusan, dan tindakan yang dilakukan.'),
                ('Amanah', 3, 'Berpegang teguh kepada nilai moral dan etika.'),
                ('Kompeten', 1, 'Meningkatkan kompetensi diri untuk menjawab tantangan yang selalu berubah.'),
                ('Kompeten', 2, 'Membantu orang lain belajar.'),
                ('Kompeten', 3, 'Menyelesaikan tugas dengan kualitas terbaik.'),
                ('Harmonis', 1, 'Menghargai setiap orang apapun latar belakangnya.'),
                ('Harmonis', 2, 'Suka menolong orang lain.'),
                ('Harmonis', 3, 'Membangun lingkungan kerja yang kondusif.'),
                ('Loyal', 1, 'Menjaga nama baik sesama karyawan, pimpinan, BUMN, dan Negara.'),
                ('Loyal', 2, 'Rela berkorban untuk mencapai tujuan yang lebih besar.'),
                ('Loyal', 3, 'Patuh kepada pimpinan sepanjang tidak bertentangan dengan hukum dan etika.'),
                ('Adaptif', 1, 'Cepat menyesuaikan diri untuk menjadi lebih baik.'),
                ('Adaptif', 2, 'Terus-menerus melakukan perbaikan mengikuti perkembangan teknologi.'),
                ('Adaptif', 3, 'Bertindak proaktif.'),
                ('Kolaboratif', 1, 'Memberi kesempatan kepada berbagai pihak untuk berkontribusi.'),
                ('Kolaboratif', 2, 'Terbuka dalam bekerja sama untuk menghasilkan nilai tambah.'),
                ('Kolaboratif', 3, 'Menggerakkan pemanfaatan berbagai sumber daya untuk tujuan bersama.')
            ]
            for q_dim, q_urut, q_teks in questions:
                db.execute("INSERT INTO pertanyaan (id_kuesioner, dimensi_akhlak, urutan, teks_pertanyaan) VALUES (?, ?, ?, ?)",
                           (id_q, q_dim, q_urut, q_teks))

        db.commit()
        flash('Kuesioner berhasil disimpan!', 'success')
        db.close()
        return redirect(url_for('kuesioner'))
    q = None
    if id:
        q = db.execute("SELECT * FROM kuesioner WHERE id_kuesioner=?", (id,)).fetchone()
    db.close()
    return render_template('kuesioner_kelola.html', kuesioner=q)

# ═══════════════════════════════════════════════════════════════
#  ROUTES — KONFIGURASI PENILAI
# ═══════════════════════════════════════════════════════════════
@app.route('/penilai_config', methods=['GET'])
@hc_required
def penilai_config():
    db = get_db()
    kuesioner = db.execute("SELECT * FROM kuesioner ORDER BY id_kuesioner DESC").fetchall()
    karyawan = db.execute("SELECT id_karyawan, nip, nama, jabatan FROM karyawan ORDER BY nama").fetchall()

    id_kuesioner = request.args.get('id_kuesioner', type=int)
    penilai_list = []
    if id_kuesioner:
        penilai_list = db.execute('''
            SELECT p.id_penilai, p.kategori, k_penilai.nama as penilai_nama, k_dinilai.nama as dinilai_nama, k_dinilai.id_karyawan as dinilai_id
            FROM penilai p
            JOIN karyawan k_penilai ON p.id_karyawan_penilai = k_penilai.id_karyawan
            JOIN karyawan k_dinilai ON p.id_karyawan_dinilai = k_dinilai.id_karyawan
            WHERE p.id_kuesioner = ?
            ORDER BY k_dinilai.nama, p.kategori
        ''', (id_kuesioner,)).fetchall()

    db.close()
    return render_template('penilai_config.html', kuesioner=kuesioner, karyawan=karyawan,
                           id_kuesioner=id_kuesioner, penilai_list=penilai_list)

@app.route('/penilai_config/add', methods=['POST'])
@hc_required
def penilai_config_add():
    db = get_db()
    id_kuesioner = request.form['id_kuesioner']
    id_dinilai = request.form['id_dinilai']
    id_penilai = request.form['id_penilai']
    kategori = request.form['kategori']

    # Check exists
    exists = db.execute("SELECT id_penilai FROM penilai WHERE id_kuesioner=? AND id_karyawan_dinilai=? AND id_karyawan_penilai=?",
                        (id_kuesioner, id_dinilai, id_penilai)).fetchone()
    if exists:
        flash('Penilai tersebut sudah ditugaskan untuk karyawan ini!', 'warning')
    else:
        db.execute("INSERT INTO penilai (id_kuesioner, id_karyawan_penilai, id_karyawan_dinilai, kategori) VALUES (?,?,?,?)",
                   (id_kuesioner, id_penilai, id_dinilai, kategori))
        db.commit()
        flash('Berhasil menambahkan penilai.', 'success')

    db.close()
    return redirect(url_for('penilai_config', id_kuesioner=id_kuesioner))

@app.route('/penilai_config/delete/<int:id_penilai>')
@hc_required
def penilai_config_delete(id_penilai):
    db = get_db()
    p = db.execute("SELECT id_kuesioner FROM penilai WHERE id_penilai=?", (id_penilai,)).fetchone()
    if p:
        db.execute("DELETE FROM penilai WHERE id_penilai=?", (id_penilai,))
        db.commit()
        flash('Berhasil menghapus penilai.', 'success')
        id_kuesioner = p['id_kuesioner']
    else:
        id_kuesioner = None
    db.close()
    return redirect(url_for('penilai_config', id_kuesioner=id_kuesioner))

@app.route('/kuesioner/isi/<int:id_penilai>', methods=['GET','POST'])
@login_required
def kuesioner_isi(id_penilai):
    db = get_db()
    pnl = db.execute('''
        SELECT p.*, k.nama as dinilai_nama, q.nama_kuesioner
        FROM penilai p
        JOIN karyawan k ON p.id_karyawan_dinilai=k.id_karyawan
        JOIN kuesioner q ON p.id_kuesioner=q.id_kuesioner
        WHERE p.id_penilai=?
    ''', (id_penilai,)).fetchone()
    if not pnl or pnl['id_karyawan_penilai'] != session.get('id_karyawan'):
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('kuesioner'))

    pertanyaan = db.execute('''
        SELECT * FROM pertanyaan WHERE id_kuesioner=? ORDER BY dimensi_akhlak, urutan
    ''', (pnl['id_kuesioner'],)).fetchall()

    # Group by dimensi
    grouped = {}
    for p in pertanyaan:
        dim = p['dimensi_akhlak']
        if dim not in grouped:
            grouped[dim] = []
        grouped[dim].append(dict(p))

    # Existing answers
    existing = {}
    for j in db.execute("SELECT id_pertanyaan, skor FROM jawaban WHERE id_penilai=?", (id_penilai,)).fetchall():
        existing[j['id_pertanyaan']] = j['skor']

    if request.method == 'POST':
        # Save all answers
        db.execute("DELETE FROM jawaban WHERE id_penilai=?", (id_penilai,))
        is_draft = 1 if request.form.get('action') == 'draft' else 0
        for p in pertanyaan:
            skor = request.form.get(f'q_{p["id_pertanyaan"]}')
            if skor:
                db.execute("INSERT INTO jawaban (id_penilai,id_pertanyaan,skor,is_draft) VALUES (?,?,?,?)",
                           (id_penilai, p['id_pertanyaan'], int(skor), is_draft))
        status = 'draft' if is_draft else 'selesai'
        db.execute("UPDATE penilai SET status_pengisian=? WHERE id_penilai=?", (status, id_penilai))
        db.commit()
        db.close()
        if is_draft:
            flash('Draft berhasil disimpan!', 'info')
        else:
            flash('Kuesioner berhasil disubmit!', 'success')
        return redirect(url_for('kuesioner'))

    total = len(pertanyaan)
    answered = len(existing)
    progress = round(answered / total * 100) if total > 0 else 0
    db.close()
    dimensi_order = ['Amanah','Kompeten','Harmonis','Loyal','Adaptif','Kolaboratif']
    return render_template('kuesioner_isi.html', penilai=pnl, grouped=grouped,
                           existing=existing, progress=progress, dimensi_order=dimensi_order)

@app.route('/kuesioner/status')
@hc_required
def kuesioner_status():
    db = get_db()
    data = db.execute('''
        SELECT k.nama as karyawan_nama, k.departemen, k.jabatan,
               k2.nama as dinilai_nama, p.kategori, p.status_pengisian, p.id_penilai
        FROM penilai p
        JOIN karyawan k ON p.id_karyawan_penilai=k.id_karyawan
        JOIN karyawan k2 ON p.id_karyawan_dinilai=k2.id_karyawan
        WHERE p.id_kuesioner=1
        ORDER BY k.nama
    ''').fetchall()
    # Summary
    total = len(data)
    selesai = sum(1 for d in data if d['status_pengisian'] == 'selesai')
    draft = sum(1 for d in data if d['status_pengisian'] == 'draft')
    belum = sum(1 for d in data if d['status_pengisian'] == 'belum')
    db.close()
    return render_template('kuesioner_status.html', status_list=data,
                           total=total, selesai=selesai, draft=draft, belum=belum)

# ═══════════════════════════════════════════════════════════════
#  ROUTES — HASIL PENILAIAN
# ═══════════════════════════════════════════════════════════════
@app.route('/hasil')
@login_required
def hasil():
    db = get_db()
    role = session.get('role')
    if role == 'hc':
        # Get all karyawan with their average scores
        data = db.execute('''
            SELECT k.id_karyawan, k.nip, k.nama, k.jabatan, k.departemen,
                   ROUND(AVG(h.skor_akhir),2) as rata_rata
            FROM karyawan k
            LEFT JOIN hasil_penilaian h ON k.id_karyawan=h.id_karyawan
            GROUP BY k.id_karyawan
            ORDER BY rata_rata DESC
        ''').fetchall()
    else:
        kid = session.get('id_karyawan')
        data = db.execute('''
            SELECT k.id_karyawan, k.nip, k.nama, k.jabatan, k.departemen,
                   ROUND(AVG(h.skor_akhir),2) as rata_rata
            FROM karyawan k
            LEFT JOIN hasil_penilaian h ON k.id_karyawan=h.id_karyawan
            WHERE k.id_karyawan=?
            GROUP BY k.id_karyawan
        ''', (kid,)).fetchall()
    db.close()
    return render_template('hasil_penilaian.html', hasil_list=data)

@app.route('/hasil/detail/<int:id_karyawan>')
@login_required
def hasil_detail(id_karyawan):
    db = get_db()
    role = session.get('role')
    kid = session.get('id_karyawan')
    if role != 'hc' and kid != id_karyawan:
        flash('Akses ditolak.', 'danger')
        return redirect(url_for('hasil'))
    k = db.execute("SELECT * FROM karyawan WHERE id_karyawan=?", (id_karyawan,)).fetchone()
    skor = db.execute("SELECT * FROM hasil_penilaian WHERE id_karyawan=? AND id_kuesioner=1 ORDER BY dimensi", (id_karyawan,)).fetchall()
    db.close()
    if not k:
        flash('Karyawan tidak ditemukan.', 'danger')
        return redirect(url_for('hasil'))
    chart_data = {}
    for s in skor:
        chart_data[s['dimensi']] = {
            'atasan': s['skor_atasan'], 'rekan': s['skor_rekan'],
            'bawahan': s['skor_bawahan'], 'diri': s['skor_diri'],
            'akhir': s['skor_akhir']
        }
    return render_template('hasil_detail.html', karyawan=k, skor_list=skor,
                           chart_data=json.dumps(chart_data))

# ═══════════════════════════════════════════════════════════════
#  API ROUTES
# ═══════════════════════════════════════════════════════════════
@app.route('/api/autosave', methods=['POST'])
@login_required
def api_autosave():
    data = request.get_json()
    id_penilai = data.get('id_penilai')
    answers = data.get('answers', {})
    db = get_db()
    for pid_str, skor in answers.items():
        pid = int(pid_str)
        existing = db.execute("SELECT id_jawaban FROM jawaban WHERE id_penilai=? AND id_pertanyaan=?",
                              (id_penilai, pid)).fetchone()
        if existing:
            db.execute("UPDATE jawaban SET skor=?,is_draft=1 WHERE id_jawaban=?",
                       (int(skor), existing['id_jawaban']))
        else:
            db.execute("INSERT INTO jawaban (id_penilai,id_pertanyaan,skor,is_draft) VALUES (?,?,?,1)",
                       (id_penilai, pid, int(skor)))
    db.execute("UPDATE penilai SET status_pengisian='draft' WHERE id_penilai=?", (id_penilai,))
    db.commit()
    db.close()
    return jsonify({'status': 'ok', 'message': 'Draft tersimpan'})

@app.route('/api/hitung-skor/<int:id_kuesioner>', methods=['POST'])
@hc_required
def api_hitung_skor(id_kuesioner):
    db = get_db()
    dimensi_list = ['Amanah','Kompeten','Harmonis','Loyal','Adaptif','Kolaboratif']
    karyawan_ids = [r['id_karyawan'] for r in db.execute("SELECT DISTINCT id_karyawan_dinilai as id_karyawan FROM penilai WHERE id_kuesioner=?", (id_kuesioner,)).fetchall()]
    db.execute("DELETE FROM hasil_penilaian WHERE id_kuesioner=?", (id_kuesioner,))
    count = 0
    for kid in karyawan_ids:
        for dim in dimensi_list:
            scores = {}
            for kat, bobot in [('atasan',0.4),('rekan',0.2),('bawahan',0.3),('diri_sendiri',0.1)]:
                row = db.execute('''
                    SELECT AVG(j.skor) as avg_skor FROM jawaban j
                    JOIN penilai p ON j.id_penilai=p.id_penilai
                    JOIN pertanyaan pt ON j.id_pertanyaan=pt.id_pertanyaan
                    WHERE p.id_karyawan_dinilai=? AND p.id_kuesioner=?
                    AND p.kategori=? AND pt.dimensi_akhlak=? AND p.status_pengisian='selesai'
                ''', (kid, id_kuesioner, kat, dim)).fetchone()
                scores[kat] = float(row['avg_skor']) if (row and row['avg_skor'] is not None) else 0
            akhir = scores['atasan']*0.4 + scores['rekan']*0.2 + scores['bawahan']*0.3 + scores['diri_sendiri']*0.1
            if any(v > 0 for v in scores.values()):
                db.execute("""INSERT INTO hasil_penilaian (id_kuesioner,id_karyawan,dimensi,
                    skor_atasan,skor_rekan,skor_bawahan,skor_diri,skor_akhir) VALUES (?,?,?,?,?,?,?,?)""",
                    (id_kuesioner, kid, dim, round(scores['atasan'],2), round(scores['rekan'],2),
                     round(scores['bawahan'],2), round(scores['diri_sendiri'],2), round(akhir,2)))
                count += 1
    db.commit()
    db.close()
    flash(f'Skor berhasil dihitung! {count} hasil penilaian diperbarui.', 'success')
    return redirect(url_for('hasil'))

@app.route('/api/chart-data/<int:id_karyawan>')
@login_required
def api_chart_data(id_karyawan):
    db = get_db()
    skor = db.execute("SELECT * FROM hasil_penilaian WHERE id_karyawan=? AND id_kuesioner=1", (id_karyawan,)).fetchall()
    db.close()
    result = {}
    for s in skor:
        result[s['dimensi']] = {
            'atasan': s['skor_atasan'], 'rekan': s['skor_rekan'],
            'bawahan': s['skor_bawahan'], 'diri': s['skor_diri'], 'akhir': s['skor_akhir']
        }
    return jsonify(result)

# ═══════════════════════════════════════════════════════════════
if __name__ == '__main__':
    app.run(debug=True, port=5001)