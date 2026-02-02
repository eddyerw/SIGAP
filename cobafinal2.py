import streamlit as st
import pandas as pd
import sqlite3
import requests
import io
import os
from datetime import datetime

# Library untuk Ekspor & PDF
import xlsxwriter
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors

# --- 1. INISIALISASI DATABASE & MIGRASI ---
DB_NAME = "sigap_banjar.db"

def get_connection():
    return sqlite3.connect(DB_NAME, check_same_thread=False)

def column_exists(conn, table_name, column_name):
    cur = conn.execute(f"PRAGMA table_info({table_name})")
    columns = [row[1] for row in cur.fetchall()]
    return column_name in columns

def migrate_db():
    conn = get_connection()
    # Migrasi Kolom Foto
    if not column_exists(conn, "laporan", "foto_path"):
        conn.execute("ALTER TABLE laporan ADD COLUMN foto_path TEXT")
    # Migrasi Kolom Verifikasi
    if not column_exists(conn, "laporan", "status_verifikasi"):
        conn.execute("ALTER TABLE laporan ADD COLUMN status_verifikasi TEXT DEFAULT 'Pending'")
    conn.commit()
    conn.close()

def init_db():
    conn = get_connection()
    c = conn.cursor()
    # Tabel Warga
    c.execute('''CREATE TABLE IF NOT EXISTS warga (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nik TEXT UNIQUE, nama_kk TEXT, kecamatan TEXT, 
                    jml_anggota INTEGER, status_rumah TEXT, 
                    kelompok_rentan TEXT, waktu_input DATETIME)''')
    # Tabel Laporan (Dengan Status Verifikasi)
    c.execute('''CREATE TABLE IF NOT EXISTS laporan (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    kecamatan TEXT, tinggi_air INTEGER, status TEXT, 
                    kebutuhan TEXT, foto_path TEXT, waktu DATETIME,
                    status_verifikasi TEXT DEFAULT 'Pending')''')
    # Tabel Pertanian
    c.execute('''CREATE TABLE IF NOT EXISTS pertanian (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    nik_pemilik TEXT, kecamatan TEXT, luas_lahan REAL, 
                    usia_padi INTEGER, estimasi_kerugian REAL, waktu_input DATETIME)''')
    # Tabel Inventori
    c.execute('CREATE TABLE IF NOT EXISTS stok_barang (nama_barang TEXT PRIMARY KEY, jumlah_stok REAL, satuan TEXT)')
    c.execute("INSERT OR IGNORE INTO stok_barang VALUES ('Beras', 0, 'Kg'), ('Mie Instan', 0, 'Dus'), ('Obat-obatan', 0, 'Paket')")
    
    conn.commit()
    conn.close()

init_db()
migrate_db()

# --- 2. FUNGSI HELPER (WA, WEATHER, DLL) ---
def kirim_wa_fonnte(kec, tinggi, keb):
    url = "https://api.fonnte.com/send"
    token = "Yh9CaJUmB74QdCnewn1z" 
    target = "08125064087" 
    pesan = f"🚨 *LAPORAN MASUK (PENDING)*\n📍 Kec: {kec}\n📏 Tinggi: {tinggi}cm\n🆘 Butuh: {keb}\n\nSegera verifikasi di Dashboard Admin."
    try: requests.post(url, headers={"Authorization": token}, data={"target": target, "message": pesan})
    except: pass

def get_weather_data(city_name="Martapura"):
    api_key = "a89f4bc4d2e3f0d0a3e204161b289c5c" 
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={api_key}&units=metric&lang=id"
    try:
        res = requests.get(url).json()
        return {"temp": res['main']['temp'], "desc": res['weather'][0]['description']}
    except: return None

# --- 3. UI CONFIG & LOGIN ---
st.set_page_config(page_title="SIGAP BANJAR", page_icon="🌊", layout="wide")

if "logged_in" not in st.session_state: st.session_state.logged_in = False

with st.sidebar:
    st.title("🌊 SIGAP BANJAR")
    if not st.session_state.logged_in:
        user = st.text_input("Admin User")
        pw = st.text_input("Password", type="password")
        if st.button("Login"):
            if user == "admin" and pw == "banjar2026": 
                st.session_state.logged_in = True
                st.rerun()
    else:
        st.success("🔓 Admin Aktif")
        if st.button("Logout"): 
            st.session_state.logged_in = False
            st.rerun()

    menu_list = ["📊 Dashboard", "📡 Lapor Kondisi"]
    if st.session_state.logged_in:
        menu_list += ["📝 Input Data KK", "🌾 Sektor Pertanian", "📦 Logistik & Stok", "✅ Verifikasi Laporan", "📈 Analisis"]
    menu = st.radio("Navigasi", menu_list)

# --- 4. LOGIKA MENU ---

# --- DASHBOARD (HANYA DATA TERVERIFIKASI) ---
if menu == "📊 Dashboard":
    st.title("📊 Dashboard Situasi Terverifikasi")
    conn = get_connection()
    # Hanya menampilkan yang sudah diverifikasi admin
    df_lap = pd.read_sql_query("SELECT * FROM laporan WHERE status_verifikasi = 'Terverifikasi' ORDER BY waktu DESC", conn)
    conn.close()
    
    if not df_lap.empty:
        c1, c2 = st.columns(2)
        c1.metric("Titik Banjir Terverifikasi", len(df_lap))
        c2.metric("Ketinggian Maksimal", f"{df_lap['tinggi_air'].max()} cm")
        st.dataframe(df_lap[['waktu', 'kecamatan', 'tinggi_air', 'kebutuhan']], use_container_width=True)
    else:
        st.info("Belum ada laporan warga yang terverifikasi untuk ditampilkan.")

# --- LAPOR KONDISI (STATUS DEFAULT: PENDING) ---
elif menu == "📡 Lapor Kondisi":
    st.title("📡 Laporan Cepat Masyarakat")
    st.info("Laporan Anda akan melalui proses verifikasi admin sebelum dipublikasikan.")
    with st.form("lapor", clear_on_submit=True):
        kec = st.selectbox("Kecamatan", ["Martapura", "Martapura Barat", "Martapura Timur", "Sungai Tabuk"])
        tinggi = st.slider("Tinggi Air (cm)", 0, 300, 50)
        keb = st.multiselect("Kebutuhan", ["Evakuasi", "Logistik", "Medis"])
        foto = st.file_uploader("📸 Unggah Foto Lokasi", type=["jpg", "png", "jpeg"])
        
        if st.form_submit_button("Kirim Laporan"):
            foto_path = None
            if foto:
                os.makedirs("uploads", exist_ok=True)
                foto_path = f"uploads/{datetime.now().strftime('%Y%m%d_%H%M%S')}_{foto.name}"
                with open(foto_path, "wb") as f: f.write(foto.getbuffer())

            conn = get_connection()
            conn.execute("""INSERT INTO laporan (kecamatan, tinggi_air, status, kebutuhan, foto_path, waktu, status_verifikasi) 
                            VALUES (?,?,?,?,?,?,?)""", 
                         (kec, tinggi, "Waspada", ", ".join(keb), foto_path, datetime.now(), 'Pending'))
            conn.commit(); conn.close()
            kirim_wa_fonnte(kec, tinggi, ", ".join(keb))
            st.success("✅ Laporan terkirim! Status: Pending (Menunggu Verifikasi Admin).")

# --- VERIFIKASI LAPORAN (KHUSUS ADMIN) ---
elif menu == "✅ Verifikasi Laporan":
    st.title("✅ Moderasi Laporan Masuk")
    conn = get_connection()
    # Ambil semua kecuali yang sudah selesai/dihapus
    df_all = pd.read_sql_query("SELECT * FROM laporan WHERE status_verifikasi != 'Selesai' ORDER BY waktu DESC", conn)
    
    if not df_all.empty:
        for _, row in df_all.iterrows():
            with st.expander(f"📍 {row['kecamatan']} | Status: {row['status_verifikasi']} | {row['waktu']}"):
                col_text, col_img = st.columns([2, 1])
                with col_text:
                    st.write(f"**Tinggi Air:** {row['tinggi_air']} cm")
                    st.write(f"**Kebutuhan:** {row['kebutuhan']}")
                with col_img:
                    if row['foto_path'] and os.path.exists(row['foto_path']):
                        st.image(row['foto_path'], use_container_width=True)
                    else: st.caption("Tidak ada foto.")
                
                # Tombol Moderasi
                b1, b2, b3 = st.columns(3)
                if b1.button(f"Verifikasi #{row['id']}"):
                    conn.execute("UPDATE laporan SET status_verifikasi = 'Terverifikasi' WHERE id = ?", (row['id'],))
                    conn.commit(); st.rerun()
                if b2.button(f"Selesaikan #{row['id']}"):
                    conn.execute("UPDATE laporan SET status_verifikasi = 'Selesai' WHERE id = ?", (row['id'],))
                    conn.commit(); st.rerun()
                if b3.button(f"Hapus Fiktif #{row['id']}", help="Hapus laporan palsu"):
                    conn.execute("DELETE FROM laporan WHERE id = ?", (row['id'],))
                    conn.commit(); st.rerun()
    else:
        st.info("Tidak ada laporan baru untuk diverifikasi.")
    conn.close()
    
# --- INPUT DATA KK (ADMIN) ---
elif menu == "📝 Input Data KK":
    st.title("📝 Registrasi Data Keluarga")
    with st.form("form_kk", clear_on_submit=True):
        nama = st.text_input("Nama Kepala Keluarga")
        nik = st.text_input("NIK (16 Digit)")
        kec_w = st.selectbox("Kecamatan", ["Martapura", "Martapura Barat", "Martapura Timur", "Sungai Tabuk"])
        jml_a = st.number_input("Jumlah Anggota", min_value=1)
        kondisi = st.radio("Status Rumah", ["Terendam (Bisa Ditempati)", "Terendam (Mengungsi)", "Rusak Berat"])
        rentan = st.multiselect("Kelompok Rentan", ["Balita", "Lansia", "Ibu Hamil", "Disabilitas"])

        if st.form_submit_button("Simpan Data"):
            conn = get_connection()
            try:
                conn.execute("INSERT INTO warga (nik, nama_kk, kecamatan, jml_anggota, status_rumah, kelompok_rentan, waktu_input) VALUES (?,?,?,?,?,?,?)",
                             (nik, nama, kec_w, jml_a, kondisi, rentan, datetime.now()))
                conn.commit()
                st.success("✅ Data berhasil masuk ke Database SQL.")
            except: st.error("❌ NIK sudah terdaftar!")
            finally: conn.close()

# --- SEKTOR PERTANIAN (ADMIN) ---
elif menu == "🌾 Sektor Pertanian":
    st.title("🌾 Analisis Dampak Pertanian")
    with st.form("form_tani", clear_on_submit=True):
        nik_p = st.text_input("NIK Pemilik Lahan")
        kec_t = st.selectbox("Lokasi Sawah", ["Martapura", "Martapura Barat", "Martapura Timur", "Sungai Tabuk"])
        luas_l = st.number_input("Luas Lahan (Ha)", min_value=0.1)
        usia_p = st.number_input("Usia Padi (Hari)", min_value=1)
        
        if st.form_submit_button("Simpan Data Pertanian"):
            rugi = hitung_kerugian_tani(luas_l, usia_p)
            conn = get_connection()
            conn.execute("INSERT INTO pertanian (nik_pemilik, kecamatan, luas_lahan, usia_padi, estimasi_kerugian, waktu_input) VALUES (?,?,?,?,?,?)",
                         (nik_p, kec_t, luas_l, usia_p, rugi, datetime.now()))
            conn.commit()
            conn.close()
            st.success(f"✅ Data Tani Tersimpan. Estimasi Kerugian: Rp {rugi:,.0f}")

# --- MANAJEMEN LOGISTIK (STOK IN/OUT) ---
elif menu == "📦 Logistik & Stok":
    st.title("📦 Sistem Manajemen Inventori")
    t1, t2 = st.tabs(["📥 Stok Masuk", "📤 Penyaluran Bantuan"])
    
    with t1:
        with st.form("in"):
            item = st.selectbox("Barang", ["Beras", "Mie Instan", "Obat-obatan"])
            qty = st.number_input("Jumlah", min_value=1.0)
            asal = st.text_input("Sumber")
            if st.form_submit_button("Simpan"):
                conn = get_connection()
                conn.execute("UPDATE stok_barang SET jumlah_stok = jumlah_stok + ? WHERE nama_barang = ?", (qty, item))
                conn.execute("INSERT INTO logistik_transaksi (tipe, item, jumlah, tujuan_asal, waktu) VALUES (?,?,?,?,?)", ('MASUK', item, qty, asal, datetime.now()))
                conn.commit(); conn.close()
                st.success("Stok Bertambah.")

    with t2:
        with st.form("out"):
            item_k = st.selectbox("Barang", ["Beras", "Mie Instan", "Obat-obatan"])
            qty_k = st.number_input("Jumlah", min_value=1.0)
            tujuan = st.selectbox("Tujuan", ["Martapura Barat", "Bengkalis (Transit Melaka)", "Sungai Tabuk"])
            if st.form_submit_button("Kirim"):
                conn = get_connection()
                stok = pd.read_sql_query("SELECT jumlah_stok FROM stok_barang WHERE nama_barang = ?", conn, params=(item_k,))['jumlah_stok'][0]
                if stok >= qty_k:
                    conn.execute("UPDATE stok_barang SET jumlah_stok = jumlah_stok - ? WHERE nama_barang = ?", (qty_k, item_k))
                    conn.execute("INSERT INTO logistik_transaksi (tipe, item, jumlah, tujuan_asal, waktu) VALUES (?,?,?,?,?)", ('KELUAR', item_k, qty_k, tujuan, datetime.now()))
                    conn.commit(); st.success("Logistik dikirim.")
                else: st.error("Stok Kurang!")
                conn.close()


# --- MENU ANALISIS & EKSPOR ---
elif menu == "📈 Analisis":
    st.title("📈 Laporan Akhir & Ekspor Data")
    conn = get_connection()
    df_t = pd.read_sql_query("SELECT * FROM pertanian", conn)
    conn.close()
    
    if not df_t.empty:
        st.subheader("Data Kerugian Sektor Pertanian")
        st.dataframe(df_t)
        
        # Ekspor Excel
        output = io.BytesIO()
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_t.to_excel(writer, index=False, sheet_name='Laporan_Tani')
        st.download_button("📥 Ekspor ke Excel (.xlsx)", output.getvalue(), "Laporan_Tani_Banjar.xlsx")
    else:
        st.info("Belum ada data untuk dianalisis.")
