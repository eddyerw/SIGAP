import streamlit as st
import pandas as pd
from datetime import datetime
import os
from reportlab.lib.pagesizes import A4
from reportlab.platypus import SimpleDocTemplate, Paragraph, Table
from reportlab.lib.styles import getSampleStyleSheet
import io
import requests

def get_weather_data(city_name="Martapura"):
    api_key = "a89f4bc4d2e3f0d0a3e204161b289c5c" 
    url = f"http://api.openweathermap.org/data/2.5/weather?q={city_name}&appid={api_key}&units=metric&lang=id"
    
    try:
        response = requests.get(url).json()
        data = {
            "temp": response['main']['temp'],
            "desc": response['weather'][0]['description'],
            "rain": response.get('rain', {}).get('1h', 0) # Curah hujan dalam mm
        }
        return data
    except Exception:
        return None

# --- FUNGSI KIRIM WHATSAPP (Fonnte API) ---
def kirim_notifikasi_wa(kecamatan, tinggi, kebutuhan):
    url = "https://api.fonnte.com/send"
    token = "Yh9CaJUmB74QdCnewn1z"  # Ganti dengan Token dari Fonnte
    target = "08125064087" # Ganti dengan nomor WhatsApp Koordinator/Grup

    pesan = (
        f"🚨 *LAPORAN BANJIR BARU*\n\n"
        f"📍 *Lokasi:* Kec. {kecamatan}\n"
        f"📏 *Ketinggian Air:* {tinggi} cm\n"
        f"🆘 *Kebutuhan:* {keb}\n\n"
        f"Mohon segera tindak lanjuti melalui Dashboard Waspada Banjar."
    )

    data = {
        'target': target,
        'message': pesan,
    }
    headers = {
        'Authorization': token
    }
    
    try:
        response = requests.post(url, headers=headers, data=data)
        return response.status_code == 200
    except:
        return False


# --- 1. KONFIGURASI HALAMAN & THEME ---
st.set_page_config(
    page_title="SIGAP BANJAR | Disaster Management",
    page_icon="🌊",
    layout="wide"
)

# Custom CSS untuk tampilan premium
st.markdown("""
    <style>
    /* Gradient Sidebar */
    [data-testid="stSidebar"] {
        background: linear-gradient(180deg, #1e3a8a 0%, #1e40af 100%);
    }
    [data-testid="stSidebar"] .stMarkdown h1 {
        color: white;
    }
    /* Metric Card Styling */
    div[data-testid="metric-container"] {
        background-color: #f8fafc;
        border: 1px solid #e2e8f0;
        padding: 15px;
        border-radius: 12px;
        box-shadow: 0 2px 4px rgba(0,0,0,0.05);
    }
    /* Status Labels */
    .status-badge {
        padding: 5px 12px;
        border-radius: 20px;
        font-weight: bold;
        color: white;
    }
    </style>
    """, unsafe_allow_html=True)

# --- 2. KONFIGURASI DATABASE LOKAL ---
NAMA_FILE_LOKAL = "database_banjar.csv"
NAMA_FILE_LAPORAN = "database_laporan.csv"
FILE_DTSEN = "dtsen.csv"

# --- 3. FUNGSI LOAD DATA ---
def load_data():
    if os.path.exists(NAMA_FILE_LOKAL):
        return pd.read_csv(NAMA_FILE_LOKAL, dtype={'NIK': str})
    return pd.DataFrame(columns=['Waktu Input', 'Nama Kepala Keluarga', 'NIK', 'Kecamatan', 'Desa/Kelurahan', 'Jumlah Anggota', 'Balita/Lansia', 'Status Rumah', 'Kebutuhan Utama', 'Jenis Aset'])

def load_laporan():
    if os.path.exists(NAMA_FILE_LAPORAN):
        return pd.read_csv(NAMA_FILE_LAPORAN)
    return pd.DataFrame(columns=['Waktu', 'Kecamatan', 'Level Air (cm)', 'Status', 'Kebutuhan'])

def load_dtsen():
    if os.path.exists(FILE_DTSEN):
        try:
            df = pd.read_csv(FILE_DTSEN, dtype={'NIK': str})
            return df['NIK'].astype(str).unique().tolist()
        except: return None
    return None

def kirim_wa(kec, tinggi, keb):
    # Logika Fonnte dari coba2.py
    url = "https://api.fonnte.com/send"
    token = "Yh9CaJUmB74QdCnewn1z" # Ganti jika perlu
    target = "08125064087"
    pesan = (
        f"🚨 *LAPORAN BANJIR BARU*\n\n"
        f"📍 *Lokasi:* Kec. {kec}\n"
        f"📏 *Ketinggian Air:* {tinggi} cm\n"
        f"🆘 *Kebutuhan:* {keb}\n\n"
        f"Mohon segera tindak lanjuti melalui Dashboard Waspada Banjar."
    )

    data = {
        'target': target,
        'message': pesan,
    }
    headers = {
        'Authorization': token
    }
    
    try:
        response = requests.post(url, headers=headers, data=data)
        return response.status_code == 200
    except:
        return False

def generate_pdf_laporan(df, total_kerugian, total_jiwa):
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4)
    styles = getSampleStyleSheet()
    elements = []

    # Judul Laporan
    elements.append(Paragraph("LAPORAN RINGKASAN DAMPAK BANJIR", styles['Title']))
    elements.append(Paragraph(f"Tanggal Cetak: {datetime.now().strftime('%d %M %Y %H:%M')}", styles['Normal']))
    elements.append(Paragraph("<br/><br/>", styles['Normal']))

    # Ringkasan Statistik
    ringkasan_data = [
        ["Total KK Terdata", f"{len(df)}"],
        ["Total Jiwa Terdampak", f"{int(total_jiwa)} Orang"],
        ["Estimasi Total Kerugian", f"Rp {total_kerugian:,.0f}"]
    ]
    t_ringkasan = Table(ringkasan_data)
    elements.append(t_ringkasan)
    elements.append(Paragraph("<br/><br/>", styles['Normal']))

    # Tabel Detail (Ambil 5 kolom saja agar muat di A4)
    data_tabel = [["Nama KK", "Kecamatan", "Status Rumah", "Anggota"]]
    for _, row in df.iterrows():
        data_tabel.append([
            row['Nama Kepala Keluarga'], 
            row['Kecamatan'], 
            row['Status Rumah'], 
            row['Jumlah Anggota']
        ])
    
    t_detail = Table(data_tabel)
    elements.append(t_detail)

    doc.build(elements)
    buffer.seek(0)
    return buffer

# --- 4. SIDEBAR NAVIGASI ---
with st.sidebar:
    st.markdown("# 🌊 SIGAP BANJAR")
    st.markdown("---")
    menu = st.radio(
        "Navigasi Utama",
        ["📊 Dashboard", "📝 Input Data KK", "📡 Lapor Kondisi", "📦 Logistik", "📈 Analisis"]
    )
    st.markdown("---")
    st.info("Penyimpanan: **Lokal (CSV)** Aktif")

# --- MENU 1: DASHBOARD ---
if menu == "📊 Dashboard":
    st.title("📊 Dashboard Situasi Banjir Kabupaten Banjar")
    
    # Memuat Data
    df_kk = load_data()
    df_lap = load_laporan()
    
    # ===== PERHITUNGAN DATA UTAMA =====
    total_kk = len(df_kk)
    total_jiwa = df_kk['Jumlah Anggota'].sum() if not df_kk.empty else 0
    max_air = df_lap['Level Air (cm)'].max() if not df_lap.empty else 0

    # Logika Status Wilayah (Dinamis)
    status_wilayah = (
        "🔴 Bahaya" if max_air > 150 else 
        "🟠 Waspada" if max_air > 50 else 
        "🟢 Aman"
    )

    # ===== 1. RINGKASAN METRIK UTAMA =====
    st.subheader("📌 Ringkasan Cepat")
    m1, m2, m3, m4 = st.columns(4)
    m1.metric("KK Terdampak", f"{total_kk}", "Keluarga")
    m2.metric("Total Jiwa", int(total_jiwa), "Orang")
    m3.metric("Level Air Tertinggi", f"{max_air} cm")
    m4.metric("Status Wilayah", status_wilayah)

    st.divider()

    # ===== 2. KONDISI CUACA TERKINI =====
    st.subheader("🌦️ Kondisi Cuaca Terkini")
    weather = get_weather_data()

    if weather:
        w1, w2, w3 = st.columns(3)
        w1.metric("🌡️ Suhu", f"{weather['temp']} °C")
        w2.metric("☁️ Cuaca", weather['desc'].capitalize())
        w3.metric("🌧️ Hujan", f"{weather['rain']} mm/jam")
    else:
        st.info("Data cuaca tidak tersedia saat ini.")

    # ===== 3. AUTO WARNING SYSTEM (EWS) =====
    st.subheader("🚨 Peringatan Dini Otomatis")
    warning_list = []

    if max_air > 150:
        warning_list.append("🔴 Tinggi air kritis (>150 cm)")
    
    if weather and weather['rain'] > 10:
        warning_list.append("🌧️ Curah hujan tinggi (>10 mm/jam)")

    if weather and weather['rain'] > 10 and max_air > 100:
        warning_list.append("⚠️ Risiko banjir meluas dalam beberapa jam ke depan")

    if warning_list:
        for w in warning_list:
            st.error(w)
    else:
        st.success("🟢 Tidak ada peringatan kritis saat ini")

    st.divider()

    # ===== 4. VISUALISASI DATA LAPANGAN =====
    st.subheader("📊 Analisis Distribusi")
    c1, c2 = st.columns(2)

    with c1:
        st.write("📍 **Sebaran Kecamatan**")
        if not df_kk.empty:
            # Menggunakan bar chart untuk visualisasi yang lebih intuitif
            st.bar_chart(df_kk['Kecamatan'].value_counts())
        else:
            st.write("Belum ada data kecamatan.")

    with c2:
        st.write("🏠 **Kondisi Rumah**")
        if not df_kk.empty:
            # Menampilkan data status rumah dalam bentuk tabel/list
            st.write(df_kk['Status Rumah'].value_counts())
        else:
            st.write("Belum ada data kondisi rumah.")

# --- MENU 2: INPUT DATA KK ---
elif menu == "📝 Input Data KK":
    st.title("📝 Pendataan Keluarga")
    list_nik = load_dtsen()
    
    if list_nik is None:
        st.warning("⚠️ Database DTSEN tidak ditemukan. Verifikasi NIK dilewati.")

    with st.form("form_kk", clear_on_submit=True):
        col1, col2 = st.columns(2)
        with col1:
            nama = st.text_input("Nama Kepala Keluarga")
            nik = st.text_input("NIK (16 Digit)")
            kec = st.selectbox("Kecamatan", ["Martapura", "Martapura Barat", "Martapura Timur", "Sungai Tabuk", "Karang Intan", "Astambul", "Simpang Empat", "Pengaron"])
        with col2:
            jml = st.number_input("Jumlah Anggota", min_value=1)
            status = st.radio("Kondisi Rumah", ["Terendam (Bisa Ditempati)", "Terendam (Mengungsi)", "Rusak Berat"])
            rentan = st.multiselect("Kelompok Rentan", ["Balita", "Lansia", "Ibu Hamil", "Disabilitas"])
        
        if st.form_submit_button("Simpan Data"):
            if not nama or not nik:
                st.error("Nama dan NIK wajib diisi!")
            elif list_nik and nik not in list_nik:
                st.error(f"❌ NIK {nik} tidak terdaftar di DTSEN!")
            else:
                df_lama = load_data()
                new_data = pd.DataFrame([{
                    'Waktu Input': datetime.now().strftime("%Y-%m-%d %H:%M"),
                    'Nama Kepala Keluarga': nama, 'NIK': str(nik), 'Kecamatan': kec,
                    'Jumlah Anggota': int(jml), 'Status Rumah': status, 'Balita/Lansia': ", ".join(rentan)
                }])
                pd.concat([df_lama, new_data], ignore_index=True).to_csv(NAMA_FILE_LOKAL, index=False)
                st.success("✅ Data tersimpan!")
                st.rerun()

# --- MENU 3: LAPOR KONDISI ---
elif menu == "📡 Lapor Kondisi":
    st.title("📡 Laporan Lapangan")

    tab1, tab2 = st.tabs(["📝 Input Laporan", "📊 Riwayat"])

    # ================= TAB INPUT =================
    with tab1:
        with st.form("form_lap", clear_on_submit=True):

            kec = st.selectbox("Lokasi", ["Martapura", "Martapura Barat"])
            tinggi = st.slider("Tinggi Air (cm)", 0, 300, 50)
            keb = st.multiselect("Kebutuhan Mendesak", ["Evakuasi", "Logistik", "Medis"])

            if st.form_submit_button("Kirim Laporan & Notifikasi WA"):
                df_l = load_laporan()
                stat = "Bahaya" if tinggi > 150 else "Waspada"
                new_l = pd.DataFrame([{'Waktu': datetime.now().strftime("%H:%M"), 'Kecamatan': kec, 'Level Air (cm)': tinggi, 'Status': stat, 'Kebutuhan': ", ".join(keb)}])
                pd.concat([df_l, new_l], ignore_index=True).to_csv(NAMA_FILE_LAPORAN, index=False)
            
                kirim_wa(kec, tinggi, ", ".join(keb))
                st.success("✅ Laporan Terkirim & Notifikasi WA Terkirim!")

            # ✅ UPLOAD FOTO — INDENT HARUS SEJAJAR INPUT LAIN
            foto_path = None
            foto = st.file_uploader(
                "📸 Unggah Foto Lokasi (Opsional)",
                type=["jpg", "jpeg", "png"]
            )

            if foto:
                os.makedirs("uploads", exist_ok=True)
                foto_path = os.path.join(
                    "uploads",
                    f"{datetime.now().strftime('%Y%m%d_%H%M%S')}_{foto.name}"
                )
                with open(foto_path, "wb") as f:
                    f.write(foto.getbuffer())

                st.image(
                    foto,
                    caption="Preview Foto Lokasi",
                    use_container_width=True
                )
  # ✅ TOMBOL SUBMIT PALING BAWAH
            if st.form_submit_button("Kirim Laporan"):
                st.success("Form terkirim")
# --- MENU 4: LOGISTIK (PASTIKAN STRUKTUR INI BENAR) ---
elif menu == "📦 Logistik":
    st.title("📦 Manajemen Bantuan")
    df_l = load_laporan()
    
    if not df_l.empty:
        st.dataframe(df_l, use_container_width=True)
        
        # Fitur filter harus sejajar di dalam blok "if not df_l.empty"
        st.subheader("Filter Prioritas Bantuan")
        pilihan_kec = st.multiselect("Filter Kecamatan", df_l['Kecamatan'].unique())
        if pilihan_kec:
            filtered_df = df_l[df_l['Kecamatan'].isin(pilihan_kec)]
            st.write(filtered_df)
    else:
        st.info("Belum ada laporan masuk.")

# --- MENU 5: ANALISIS DAMPAK ---
elif menu == "📈 Analisis":
    st.title("📈 Analisis & Estimasi Kerugian")
    
    # Ambil data dari database warga
    df_keluarga = load_data()
    
    if not df_keluarga.empty:
        # PEMBERSIH DATA: Menghapus spasi di awal/akhir teks agar cocok dengan mapping
        df_keluarga['Status Rumah'] = df_keluarga['Status Rumah'].astype(str).str.strip()
        
        # 1. Tabel Biaya (Pastikan teks di kiri SAMA PERSIS dengan di menu Input Data)
        biaya_kerusakan = {
            "Terendam (Bisa Ditempati)": 1500000, 
            "Terendam (Mengungsi)": 5000000, 
            "Rusak Berat": 25000000
        }
        
        # 2. Perhitungan dengan Mapping
        df_keluarga['Estimasi Kerugian (Rp)'] = df_keluarga['Status Rumah'].map(biaya_kerusakan).fillna(0)
        
        # Pastikan jumlah anggota adalah angka (numeric)
        df_keluarga['Jumlah Anggota'] = pd.to_numeric(df_keluarga['Jumlah Anggota'], errors='coerce').fillna(0)
        
        total_kerugian = df_keluarga['Estimasi Kerugian (Rp)'].sum()
        total_jiwa = df_keluarga['Jumlah Anggota'].sum()

        # 3. Tampilan Metrik Utama
        st.markdown("### 📊 Statistik Dampak")
        c1, c2, c3 = st.columns(3)
        with c1:
            st.metric("Total Kerugian", f"Rp {total_kerugian:,.0f}".replace(",", "."))
        with c2:
            st.metric("Jiwa Terdampak", f"{int(total_jiwa)} Orang")
        with c3:
            st.metric("Total Data KK", f"{len(df_keluarga)} KK")
        
        st.divider()

        # 4. Grafik Sebaran
        col_grafik1, col_grafik2 = st.columns(2)
        with col_grafik1:
            st.subheader("📍 Kerugian per Kecamatan")
            # Agregasi data untuk grafik
            chart_kec = df_keluarga.groupby('Kecamatan')['Estimasi Kerugian (Rp)'].sum()
            st.bar_chart(chart_kec)
            
        with col_grafik2:
            st.subheader("🏠 Kondisi Rumah")
            st.bar_chart(df_keluarga['Status Rumah'].value_counts())

        # 5. Tombol Cetak PDF
        st.write("---")
        try:
            pdf_data = generate_pdf_laporan(df_keluarga, total_kerugian, total_jiwa)
            st.download_button(
                label="📥 Download Laporan PDF",
                data=pdf_data,
                file_name=f"Laporan_Banjar_{datetime.now().strftime('%d%m%Y')}.pdf",
                mime="application/pdf"
            )
        except Exception as e:
            st.info("Pencetakan PDF siap digunakan setelah fungsi PDF dikonfigurasi.")

    else:
        # Tampilan jika file CSV kosong atau tidak ditemukan
        st.warning("⚠️ Database warga masih kosong. Silakan isi data di menu 'Input Data KK' terlebih dahulu.")

