from flask import Flask, request, render_template, flash, redirect, url_for
import pandas as pd
from itertools import combinations
import os
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'gizli-anahtar-123'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/analyze', methods=['POST'])
def analyze():
    try:
        # Dosya kontrolü
        if 'file' not in request.files:
            flash('Dosya seçilmedi!', 'error')
            return redirect(url_for('index'))
        
        file = request.files['file']
        if file.filename == '':
            flash('Dosya seçilmedi!', 'error')
            return redirect(url_for('index'))
        
        if not allowed_file(file.filename):
            flash('Sadece Excel dosyaları (.xlsx, .xls) desteklenir!', 'error')
            return redirect(url_for('index'))
        
        # Analiz parametreleri
        analysis_type = request.form.get('analysis')
        urun1 = request.form.get('urun1', '').strip()
        urun2 = request.form.get('urun2', '').strip()
        
        # Dosyayı oku
        try:
            df = pd.read_excel(file)
        except Exception as e:
            flash(f'Dosya okuma hatası: {str(e)}', 'error')
            return redirect(url_for('index'))
        
        # Gerekli sütunları kontrol et
        if 'Numara' not in df.columns or 'Ürün Grubu' not in df.columns:
            flash('Excel dosyasında "Numara" (D sütunu) ve "Ürün Grubu" (G sütunu) olmalı!', 'error')
            return redirect(url_for('index'))
        
        # Boş değerleri temizle
        df = df.dropna(subset=['Numara', 'Ürün Grubu'])
        df = df[df['Ürün Grubu'].astype(str).str.strip() != '']
        df = df[df['Numara'].astype(str).str.strip() != '']
        
        if df.empty:
            flash('Numara ve Ürün Grubu sütunlarında geçerli veri bulunamadı!', 'error')
            return redirect(url_for('index'))
        
        # Veri temizleme
        df['Ürün Grubu'] = df['Ürün Grubu'].astype(str).str.upper().str.strip()
        df['Numara'] = df['Numara'].astype(str).str.strip()
        
        result_data = {}
        
        # Analiz türüne göre işlem
        if analysis_type == 'sales':
            sales_data = df['Ürün Grubu'].value_counts()
            result_data = {
                'type': 'sales',
                'title': 'Ürün Satış Analizi',
                'data': [(product, count) for product, count in sales_data.items()],
                'total_products': len(sales_data),
                'total_sales': sales_data.sum()
            }
            
        elif analysis_type == 'lift':
            if not urun1 or not urun2:
                flash('Lift analizi için her iki ürün adını da giriniz!', 'error')
                return redirect(url_for('index'))
            
            # Ürün adlarını büyük harfe çevir
            urun1 = urun1.upper()
            urun2 = urun2.upper()
            
            # Ürün adlarının varlığını kontrol et
            available_products = df['Ürün Grubu'].unique()
            if urun1 not in available_products:
                available_list = ', '.join(available_products[:10])
                flash(f'"{urun1}" ürünü bulunamadı! Mevcut ürünler: {available_list}', 'error')
                return redirect(url_for('index'))
            
            if urun2 not in available_products:
                available_list = ', '.join(available_products[:10])
                flash(f'"{urun2}" ürünü bulunamadı! Mevcut ürünler: {available_list}', 'error')
                return redirect(url_for('index'))
            
            df['Urun1'] = df['Ürün Grubu'] == urun1
            df['Urun2'] = df['Ürün Grubu'] == urun2
            
            pivot = df.groupby('Numara').agg({'Urun1': 'max', 'Urun2': 'max'}).reset_index()
            total = pivot.shape[0]
            a = pivot['Urun1'].sum()
            b = pivot['Urun2'].sum()
            ab = pivot[(pivot['Urun1']) & (pivot['Urun2'])].shape[0]
            
            if total == 0:
                flash('Analiz için yeterli veri yok!', 'error')
                return redirect(url_for('index'))
            
            p_a = a / total
            p_b = b / total
            p_ab = ab / total
            
            lift = round(p_ab / (p_a * p_b), 2) if p_a * p_b > 0 else 0
            confidence = round(p_ab / p_a, 2) if p_a > 0 else 0
            
            # Lift yorumu
            if lift > 1.5:
                interpretation = "Çok güçlü pozitif korelasyon"
            elif lift > 1.2:
                interpretation = "Güçlü pozitif korelasyon"
            elif lift > 1.0:
                interpretation = "Zayıf pozitif korelasyon"
            elif lift == 1.0:
                interpretation = "Bağımsız ürünler"
            else:
                interpretation = "Negatif korelasyon"
            
            result_data = {
                'type': 'lift',
                'title': f'Lift Analizi: {urun1} & {urun2}',
                'lift': lift,
                'confidence': confidence,
                'together_sales': ab,
                'product1_sales': a,
                'product2_sales': b,
                'total_customers': total,
                'interpretation': interpretation
            }
            
        elif analysis_type == 'pair':
            basket = df.groupby('Numara')['Ürün Grubu'].apply(set)
            pair_counts = {}
            
            for urunler in basket:
                if len(urunler) >= 2:
                    for u1, u2 in combinations(sorted(urunler), 2):
                        pair = (u1, u2)
                        pair_counts[pair] = pair_counts.get(pair, 0) + 1
            
            sorted_pairs = sorted(pair_counts.items(), key=lambda x: x[1], reverse=True)[:15]
            
            result_data = {
                'type': 'pair',
                'title': 'En Çok Birlikte Satılan Ürün Çiftleri',
                'pairs': [{'products': f"{p[0]} + {p[1]}", 'count': c} 
                         for (p, c) in sorted_pairs],
                'total_pairs': len(pair_counts)
            }
            
        elif analysis_type == 'time':
            if 'Tarih' not in df.columns:
                flash('Zaman analizi için Tarih sütunu gerekli!', 'error')
                return redirect(url_for('index'))
            
            df['Tarih'] = pd.to_datetime(df['Tarih'], errors='coerce')
            df = df.dropna(subset=['Tarih'])
            df['Ay'] = df['Tarih'].dt.to_period("M")
            
            time_data = df.groupby('Ay').size()
            
            result_data = {
                'type': 'time',
                'title': 'Aylık Satış Trendi',
                'data': [(str(month), sales) for month, sales in time_data.items()],
                'total_months': len(time_data)
            }
            
        elif analysis_type == 'customer':
            # Müşteri analizi
            if 'Perakende Müşteri Kodu' in df.columns:
                customer_col = 'Perakende Müşteri Kodu'
            else:
                customer_col = 'Numara'
                
            urun_ade = df.groupby(customer_col).size()
            urun_tur = df.groupby(customer_col)['Ürün Grubu'].nunique()
            
            result_data = {
                'type': 'customer',
                'title': 'Müşteri Analizi',
                'avg_products_per_customer': round(urun_ade.mean(), 2),
                'avg_variety_per_customer': round(urun_tur.mean(), 2),
                'total_customers': len(urun_ade),
                'max_products': urun_ade.max(),
                'max_variety': urun_tur.max()
            }
            
        else:
            flash('Geçersiz analiz türü!', 'error')
            return redirect(url_for('index'))
        
        return render_template('results.html', result=result_data)
        
    except Exception as e:
        flash(f'Analiz sırasında hata oluştu: {str(e)}', 'error')
        return redirect(url_for('index'))

@app.errorhandler(413)
def too_large(e):
    flash('Dosya boyutu çok büyük! Maksimum 16MB', 'error')
    return redirect(url_for('index'))

if __name__ == '__main__':
    app.run(debug=True)