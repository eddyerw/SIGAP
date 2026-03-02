import streamlit as st
import pandas as pd
import sqlite3
import requests
import io
import os
from datetime import datetime

# Library untuk Ekspor & PDF
import xlsxwriter
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table, TableStyle
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib import colors
import tempfile

def generate_pdf_laporan_analisis(
    jumlah_ruta, jumlah_keluarga, jumlah_jiwa,
    kerugian_tani, kerugian_rumah, total_kerugian
):
    tmp = tempfile.NamedTemporaryFile(delete=False, suffix=".pdf")
    doc = SimpleDocTemplate(tmp.name, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    elements.append(Paragraph(
        "<b>LAPORAN ANALISIS DAMPAK & KERUGIAN</b>",
        styles["Title"]
    ))
    elements.append(Paragraph(
        f"Tanggal Cetak: {datetime.now().strftime('%d-%m-%Y %H:%M')}",
        styles["Normal"]
    ))
    elements.append(Paragraph("<br/>", styles["Normal"]))

    data = [
        ["Indikator", "Nilai"],
        ["Ruta Terdampak", jumlah_ruta],
        ["Keluarga Terdampak", jumlah_keluarga],
        ["Total Jiwa", jumlah_jiwa],
        ["Kerugian Pertanian", f"Rp {kerugian_tani:,.0f}"],
        ["Kerugian Rumah", f"Rp {kerugian_rumah:,.0f}"],
        ["TOTAL KERUGIAN", f"Rp {total_kerugian:,.0f}"],
    ]

    table = Table(data, colWidths=[260, 200])
    table.setStyle(TableStyle([
        ("GRID", (0,0), (-1,-1), 1, colors.black),
        ("BACKGROUND", (0,0), (-1,0), colors.lightgrey),
        ("FONT", (0,0), (-1,0), "Helvetica-Bold"),
        ("FONT", (0,-1), (-1,-1), "Helvetica-Bold"),
        ("BACKGROUND", (0,-1), (-1,-1), colors.whitesmoke),
    ]))

    elements.append(table)
    doc.build(elements)
    return tmp.name


# --- 1. INISIALISASI DATABASE & MIGRASI ---
DB_NAME = "sigap_banjar.db"

def get_connection():
    return sqlite3.connect("sigap_banjar.db", check_same_thread=False)

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

def migrate_table_pertanian():
    conn = get_connection()
    c = conn.cursor()

    # Ambil kolom yang sudah ada
    c.execute("PRAGMA table_info(pertanian)")
    existing_columns = [col[1] for col in c.fetchall()]

    if "latitude" not in existing_columns:
        c.execute("ALTER TABLE pertanian ADD COLUMN latitude REAL")

    if "longitude" not in existing_columns:
        c.execute("ALTER TABLE pertanian ADD COLUMN longitude REAL")

    if "foto_lahan" not in existing_columns:
        c.execute("ALTER TABLE pertanian ADD COLUMN foto_lahan TEXT")

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
                   usia_padi INTEGER, estimasi_kerugian REAL, foto_lahan TEXT,
                   latitude REAL, longitude REAL, waktu_input DATETIME)''')
    # Tabel Inventori
    c.execute('CREATE TABLE IF NOT EXISTS stok_barang (nama_barang TEXT PRIMARY KEY, jumlah_stok REAL, satuan TEXT)')
    c.execute("INSERT OR IGNORE INTO stok_barang VALUES ('Beras', 0, 'Kg'), ('Mie Instan', 0, 'Dus'), ('Obat-obatan', 0, 'Paket')")
    # === TABEL KK (KEPALA KELUARGA) ===
    c.execute("""
    CREATE TABLE IF NOT EXISTS kk (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nik TEXT UNIQUE,
        nama_kk TEXT,
        kecamatan TEXT,
        jumlah_anggota INTEGER,
        status_rumah TEXT,
        kelompok_rentan TEXT,
        waktu_input DATETIME
    )
    """)
    # =========================
    # TABEL RUMAH
    # =========================
    c.execute("""
    CREATE TABLE IF NOT EXISTS rumah (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nik_pemilik TEXT,
        status_rumah TEXT,
        estimasi_kerugian REAL DEFAULT 0,
        waktu TIMESTAMP DEFAULT CURRENT_TIMESTAMP
    )
    """)

       
  # ===== AUTO MIGRASI KOLOM (AMAN) =====
    existing_columns = [
        col[1] for col in c.execute("PRAGMA table_info(pertanian)").fetchall()
    ]

    def add_column(name, tipe):
        if name not in existing_columns:
            c.execute(f"ALTER TABLE pertanian ADD COLUMN {name} {tipe}")

    add_column("foto_lahan", "TEXT")
    add_column("produksi", "REAL")
    add_column("catatan", "TEXT")

    conn.commit()
    conn.close()

init_db()
migrate_db()
migrate_table_pertanian()


# --- 2. FUNGSI HELPER (WA, WEATHER, DLL) ---
def kirim_wa_fonnte(kec, tinggi, keb):
    url = "https://api.fonnte.com/send"
    token = "Yh9CaJUmB74QdCnewn1z" 
    target = "08125064087" 
    pesan = f"🚨 *LAPORAN MASUK (PENDING)*\n📍 Kec: {kec}\n📏 Tinggi: {tinggi}cm\n🆘 Butuh: {keb}\n\nSegera verifikasi di Dashboard Admin."
    try: requests.post(url, headers={"Authorization": token}, data={"target": target, "message": pesan})
    except: pass

import requests

def get_weather():
    API_KEY = "a89f4bc4d2e3f0d0a3e204161b289c5c"
    CITY = "Martapura"
    URL = f"https://api.openweathermap.org/data/2.5/weather?q={CITY}&appid={"a89f4bc4d2e3f0d0a3e204161b289c5c"}&units=metric"

    try:
        response = requests.get(URL, timeout=5)
        data = response.json()

        if response.status_code != 200:
            return None

        weather = {
            "suhu": data["main"]["temp"],
            "cuaca": data["weather"][0]["description"],
            "kelembapan": data["main"]["humidity"]
        }
        return weather

    except Exception as e:
        print("Gagal ambil cuaca:", e)
        return None

# =============================
# === HITUNG KERUGIAN TANI ====
# =============================
def hitung_kerugian_tani(luas_lahan, usia_padi):
    """
    luas_lahan : luas sawah (hektar)
    usia_padi  : umur padi (hari)
    """

    # Estimasi biaya per hektar (rupiah)
    biaya_per_ha = 15000000  # 15 juta / ha (bibit, pupuk, tenaga)

    # Faktor kerugian berdasarkan usia padi
    if usia_padi < 30:
        faktor = 0.3
    elif usia_padi < 60:
        faktor = 0.6
    else:
        faktor = 1.0

    kerugian = luas_lahan * biaya_per_ha * faktor
    return int(kerugian)

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

    menu_list = ["📊 Dashboard", "📡 Lapor Kondisi", "✅ Verifikasi Laporan" ]
    if st.session_state.logged_in:
        menu_list += ["📝 Input Data KK", "🌾 Sektor Pertanian", "📦 Logistik & Stok", "✅ Verifikasi Laporan", "📉 Analisis Laporan Kerugian"]
    menu = st.radio("Navigasi", menu_list)

# --- 4. LOGIKA MENU ---

# =============================
# ===== MENU NAVIGASI =========
# =============================
#menu = st.sidebar.selectbox(
 #   "📌 Menu",
  #  [
   #     "📊 Dashboard",
    #    "📡 Lapor Kondisi",
    #]
#)

# =============================
# ===== DASHBOARD =============
# =============================
if menu == "📊 Dashboard":
    st.title("📊 Dashboard Situasi Terverifikasi")

    conn = get_connection()

    df_lap = pd.read_sql_query("""
        SELECT * FROM laporan 
        WHERE status_verifikasi = 'Terverifikasi'
        ORDER BY waktu DESC
    """, conn)

    df_kk = pd.read_sql_query("SELECT * FROM kk", conn)
    conn.close()

    # ===== NORMALISASI KOLOM =====
    df_kk.columns = df_kk.columns.str.strip().str.lower()

    # ===== METRIK UTAMA =====
    if not df_lap.empty:
        c1, c2 = st.columns(2)
        c1.metric("📍 Titik Banjir", len(df_lap))
        c2.metric("📏 Air Maksimum", f"{df_lap['tinggi_air'].max()} cm")

        st.dataframe(
            df_lap[['waktu', 'kecamatan', 'tinggi_air', 'kebutuhan']],
            use_container_width=True
        )
    else:
        st.info("Belum ada laporan terverifikasi.")

    total_kk = len(df_kk)
    total_jiwa = df_kk['jumlah_anggota'].sum() if not df_kk.empty else 0
    max_air = df_lap['tinggi_air'].max() if not df_lap.empty else 0

    status_wilayah = (
        "🔴 Bahaya" if max_air > 150 else
        "🟠 Waspada" if max_air > 50 else
        "🟢 Aman"
    )

    st.subheader("📌 Ringkasan Cepat")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("KK Terdampak", total_kk)
    m2.metric("Total Jiwa", total_jiwa)
    m3.metric("Level Air Tertinggi", f"{max_air} cm")
    m4.metric("Status Wilayah", status_wilayah)

    st.divider()

    # ===== VISUALISASI =====
    c1, c2 = st.columns(2)

    with c1:
        st.write("📍 **Sebaran Kecamatan**")
        if not df_kk.empty:
            st.bar_chart(df_kk['kecamatan'].value_counts())

    with c2:
        st.write("🏠 **Kondisi Rumah**")
        if not df_kk.empty:
            st.write(df_kk['status_rumah'].value_counts())

# =============================
# ===== LAPOR KONDISI ========
# =============================
elif menu == "📡 Lapor Kondisi":

    st.title("📡 Laporan Cepat Masyarakat")
    st.info("Laporan akan diverifikasi admin sebelum ditampilkan.")

    with st.form("lapor", clear_on_submit=True):
        kec = st.selectbox(
            "Kecamatan",
            ["Martapura", "Martapura Barat", "Martapura Timur", "Sungai Tabuk"]
        )
        tinggi = st.slider("Tinggi Air (cm)", 0, 300, 50)
        keb = st.multiselect("Kebutuhan", ["Evakuasi", "Logistik", "Medis"])
        foto = st.file_uploader("📸 Unggah Foto", ["jpg", "png", "jpeg"])
        submit = st.form_submit_button("Kirim Laporan")

    if submit:
        foto_path = None
        if foto:
            os.makedirs("uploads", exist_ok=True)
            foto_path = os.path.join(
                "uploads",
                f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{foto.name}"
            )
            with open(foto_path, "wb") as f:
                f.write(foto.getbuffer())

        conn = get_connection()
        conn.execute(
            """
            INSERT INTO laporan
            (kecamatan, tinggi_air, status, kebutuhan, foto_path, waktu, status_verifikasi)
            VALUES (?,?,?,?,?,?,?)
            """,
            (kec, tinggi, "Waspada", ", ".join(keb), foto_path, datetime.now(), "Pending"),
        )
        conn.commit()
        conn.close()

        kirim_wa_fonnte(kec, tinggi, ", ".join(keb))
        st.success("✅ Laporan terkirim (Pending).")


# =============================
# ===== VERIFIKASI ===========
# =============================
elif menu == "✅ Verifikasi Laporan":
    st.title("✅ Moderasi Laporan Masuk")

    conn = get_connection()
    df_all = pd.read_sql_query(
        "SELECT * FROM laporan WHERE status_verifikasi != 'Selesai' ORDER BY waktu DESC",
        conn,
    )

    if not df_all.empty:
        for _, row in df_all.iterrows():
            with st.expander(f"📍 {row['kecamatan']} | {row['status_verifikasi']}"):
                st.write(f"**Tinggi Air:** {row['tinggi_air']} cm")
                st.write(f"**Kebutuhan:** {row['kebutuhan']}")

                if row['foto_path'] and os.path.exists(row['foto_path']):
                    st.image(row['foto_path'], use_container_width=True)

                c1, c2, c3 = st.columns(3)

                if c1.button("✔️ Verifikasi", key=f"v{row['id']}"):
                    conn.execute(
                        "UPDATE laporan SET status_verifikasi='Terverifikasi' WHERE id=?",
                        (row['id'],)
                    )
                    conn.commit()
                    st.rerun()

                if c2.button("✅ Selesai", key=f"s{row['id']}"):
                    conn.execute(
                        "UPDATE laporan SET status_verifikasi='Selesai' WHERE id=?",
                        (row['id'],)
                    )
                    conn.commit()
                    st.rerun()

                if c3.button("🗑️ Hapus", key=f"h{row['id']}"):
                    conn.execute("DELETE FROM laporan WHERE id=?", (row['id'],))
                    conn.commit()
                    st.rerun()
    else:
        st.info("Tidak ada laporan masuk.")

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
                conn.execute("""INSERT INTO kk (nik, nama_kk, kecamatan,jumlah_anggota, status_rumah, kelompok_rentan, waktu_input) VALUES (?,?,?,?,?,?,?)""", (nik, nama, kec_w,jml_a, kondisi,", ".join(rentan), datetime.now()))
                conn.commit()
                st.success("✅ Data berhasil masuk ke Database SQL.")
            except: st.error("❌ NIK sudah terdaftar!")
            finally: conn.close()

# --- SEKTOR PERTANIAN (ADMIN) ---
elif menu == "🌾 Sektor Pertanian":
    st.title("🌾 Analisis Dampak Pertanian")

    with st.form("form_tani", clear_on_submit=True):
        nik_p = st.text_input("NIK Pemilik Lahan")

        kec_t = st.selectbox(
            "Lokasi Sawah",
            ["Martapura", "Martapura Barat", "Martapura Timur", "Sungai Tabuk"]
        )

        luas_l = st.number_input("Luas Lahan (Ha)", min_value=0.1)
        usia_p = st.number_input("Usia Padi (Hari)", min_value=1)

        st.markdown("### 📍 Lokasi GPS Sawah")
        col1, col2 = st.columns(2)
        with col1:
            lat = st.number_input(
                "Latitude",
                value=-3.320000,
                format="%.6f"
            )
        with col2:
            lon = st.number_input(
                "Longitude",
                value=114.590000,
                format="%.6f"
            )

        foto = st.file_uploader(
            "📷 Upload Foto Lahan Pertanian",
            type=["jpg", "jpeg", "png"]
        )

        submit = st.form_submit_button("💾 Simpan Data Pertanian")

    if submit:
        if not nik_p:
            st.warning("⚠️ NIK Pemilik Lahan wajib diisi")
        else:
            rugi = hitung_kerugian_tani(luas_l, usia_p)

            # === SIMPAN FOTO ===
            foto_path = None
            if foto:
                os.makedirs("foto_pertanian", exist_ok=True)
                foto_path = os.path.join(
                    "foto_pertanian",
                    f"{nik_p}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.jpg"
                )
                with open(foto_path, "wb") as f:
                    f.write(foto.getbuffer())

            # === SIMPAN DB ===
            conn = get_connection()
            conn.execute(
                """
                INSERT INTO pertanian
                (nik_pemilik, kecamatan, luas_lahan, usia_padi,
                 estimasi_kerugian, foto_lahan,
                 latitude, longitude, waktu_input)
                VALUES (?,?,?,?,?,?,?,?,?)
                """,
                (
                    nik_p, kec_t, luas_l, usia_p,
                    rugi, foto_path,
                    lat, lon, datetime.now()
                )
            )
            conn.commit()
            conn.close()

            st.success(f"✅ Data Tani + GPS tersimpan | Kerugian: Rp {rugi:,.0f}")

            # === TAMPILKAN PETA ===
            st.map(pd.DataFrame({"lat": [lat], "lon": [lon]}))

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


# ======================================================
# 📉 ANALISIS LAPORAN KERUGIAN (GABUNGAN)
# ======================================================
elif menu == "📉 Analisis Laporan Kerugian":
    st.title("📉 Analisis Laporan Kerugian")

    conn = get_connection()

    # ======================
    # AMBIL DATA (AMAN)
    # ======================
    try:
        df_tani = pd.read_sql_query("""
            SELECT nik_pemilik, kecamatan, luas_lahan,
                   estimasi_kerugian
            FROM pertanian
        """, conn)
    except Exception:
        df_tani = pd.DataFrame(
            columns=["nik_pemilik", "kecamatan", "luas_lahan", "estimasi_kerugian"]
        )

    try:
        df_rumah = pd.read_sql_query("""
            SELECT nik_pemilik, estimasi_kerugian
            FROM rumah
        """, conn)
    except Exception:
        df_rumah = pd.DataFrame(
            columns=["nik_pemilik", "estimasi_kerugian"]
        )

    try:
        df_kk = pd.read_sql_query("""
            SELECT nik_kk, jumlah_anggota
            FROM kk
        """, conn)
    except Exception:
        df_kk = pd.DataFrame(
            columns=["nik_kk", "jumlah_anggota"]
        )

    conn.close()

    # ======================
    # VALIDASI DATA
    # ======================
    if df_tani.empty and df_rumah.empty:
        st.info("📭 Belum ada data kerugian yang tercatat.")
    else:
        # ======================
        # HITUNG DAMPAK
        # ======================
        nik_terdampak = set()

        if not df_tani.empty:
            nik_terdampak.update(
                df_tani["nik_pemilik"].dropna().astype(str).unique()
            )

        if not df_rumah.empty:
            nik_terdampak.update(
                df_rumah["nik_pemilik"].dropna().astype(str).unique()
            )

        jumlah_ruta = len(nik_terdampak)

        if not df_kk.empty:
            df_kk_terdampak = df_kk[df_kk["nik_kk"].astype(str).isin(nik_terdampak)]
            jumlah_keluarga = len(df_kk_terdampak)
            jumlah_jiwa = int(df_kk_terdampak["jumlah_anggota"].sum())
        else:
            jumlah_keluarga = 0
            jumlah_jiwa = 0

        kerugian_tani = (
            df_tani["estimasi_kerugian"].sum()
            if not df_tani.empty else 0
        )

        kerugian_rumah = (
            df_rumah["estimasi_kerugian"].sum()
            if not df_rumah.empty else 0
        )

        total_kerugian = kerugian_tani + kerugian_rumah

        # ======================
        # RINGKASAN
        # ======================
        st.subheader("📌 Ringkasan Dampak")

        c1, c2, c3, c4 = st.columns(4)
        c1.metric("🏠 Ruta Terdampak", jumlah_ruta)
        c2.metric("👨‍👩‍👧 Keluarga", jumlah_keluarga)
        c3.metric("🧍 Total Jiwa", jumlah_jiwa)
        c4.metric("💰 Total Kerugian", f"Rp {total_kerugian:,.0f}")

        st.divider()

        # ======================
        # DETAIL KERUGIAN
        # ======================
        col1, col2 = st.columns(2)
        col1.metric("🌾 Kerugian Pertanian", f"Rp {kerugian_tani:,.0f}")
        col2.metric("🏚️ Kerugian Rumah", f"Rp {kerugian_rumah:,.0f}")

        st.divider()

        # ======================
        # TABEL & GRAFIK PERTANIAN
        # ======================
        if not df_tani.empty:
            st.subheader("🌾 Detail Kerugian Pertanian")
            st.dataframe(df_tani, use_container_width=True)

            chart = (
                df_tani
                .groupby("kecamatan")["estimasi_kerugian"]
                .sum()
                .sort_values(ascending=False)
            )
            st.bar_chart(chart)

        st.divider()

        # ======================
        # DOWNLOAD PDF
        # ======================
        if st.button("📥 Download Laporan PDF"):
            pdf_path = generate_pdf_laporan_analisis(
                jumlah_ruta,
                jumlah_keluarga,
                jumlah_jiwa,
                kerugian_tani,
                kerugian_rumah,
                total_kerugian
            )

            with open(pdf_path, "rb") as f:
                st.download_button(
                    "⬇️ Unduh PDF",
                    f,
                    file_name="laporan_analisis_kerugian.pdf",
                    mime="application/pdf"
                )

