from flask import Flask, request, render_template, flash, redirect, url_for
from collections import Counter, defaultdict
from itertools import combinations
import openpyxl
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = 'gizli-anahtar-123'
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16MB limit

ALLOWED_EXTENSIONS = {'xlsx', 'xls'}

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def read_excel_file(file):
    """Excel dosyasını okur ve veri listesi döndürür"""
    try:
        workbook = openpyxl.load_workbook(file, data_only=True)
        sheet = workbook.active
        
        data = []
        headers = None
        
        for row_num, row in enumerate(sheet.iter_rows(values_only=True), 1):
            if row_num == 1:
                headers = row
                continue
            
            if any(cell is not None for cell in row):
                row_dict = {}
                for i, header in enumerate(headers):
                    if i < len(row):
                        row_dict[header] = row[i]
                data.append(row_dict)
        
        return data
    except Exception as e:
        raise Exception(f"Excel okuma hatası: {str(e)}")

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
        
        # Excel dosyasını oku
        try:
            data = read_excel_file(file)
        except Exception as e:
            flash(str(e), 'error')
            return redirect(url_for('index'))
        
        if not data:
            flash('Excel dosyasında veri bulunamadı!', 'error')
            return redirect(url_for('index'))
        
        # Gerekli sütunları kontrol et
        sample_row = data[0]
        required_columns = ['Numara', 'Ürün Grubu']
        
        # Analiz türüne göre ek sütun gereksinimleri
        if analysis_type in ['product_detail']:
            required_columns.append('Madde Açıklaması')
        elif analysis_type in ['sales_rep']:
            required_columns.append('Satış Sorumlusu Adı-Soyadı')
        
        missing_columns = [col for col in required_columns if col not in sample_row]
        if missing_columns:
            available_columns = list(sample_row.keys())
            flash(f'Excel dosyasında şu sütunlar bulunamadı: {", ".join(missing_columns)}! Mevcut sütunlar: {", ".join(available_columns)}', 'error')
            return redirect(url_for('index'))
        
        # Veriyi temizle
        clean_data = []
        for row in data:
            if (row.get('Numara') and row.get('Ürün Grubu') and 
                str(row.get('Numara')).strip() and str(row.get('Ürün Grubu')).strip()):
                clean_row = {
                    'Numara': str(row['Numara']).strip(),
                    'Ürün Grubu': str(row['Ürün Grubu']).upper().strip()
                }
                
                # Ürün adı (Madde Açıklaması)
                if 'Madde Açıklaması' in row and row['Madde Açıklaması']:
                    clean_row['Ürün Adı'] = str(row['Madde Açıklaması']).strip()
                
                # Satış sorumlusu
                if 'Satış Sorumlusu Adı-Soyadı' in row and row['Satış Sorumlusu Adı-Soyadı']:
                    clean_row['Satış Sorumlusu'] = str(row['Satış Sorumlusu Adı-Soyadı']).strip()
                
                # Tarih
                if 'Tarih' in row and row['Tarih']:
                    clean_row['Tarih'] = row['Tarih']
                
                # Müşteri
                if 'Perakende Müşteri Kodu' in row and row['Perakende Müşteri Kodu']:
                    clean_row['Müşteri'] = str(row['Perakende Müşteri Kodu']).strip()
                
                clean_data.append(clean_row)
        
        if not clean_data:
            flash('Temizlenebilir veri bulunamadı! Numara ve Ürün Grubu sütunlarını kontrol edin.', 'error')
            return redirect(url_for('index'))
        
        result_data = {}
        
        # Analiz türüne göre işlem
        if analysis_type == 'sales':
            product_counts = Counter(row['Ürün Grubu'] for row in clean_data)
            total_sales = sum(product_counts.values())
            
            result_data = {
                'type': 'sales',
                'title': 'Ürün Satış Analizi',
                'data': list(product_counts.most_common()),
                'total_products': len(product_counts),
                'total_sales': total_sales
            }
            
        elif analysis_type == 'product_detail':
            # Ürün adı bazında detaylı analiz
            product_name_counts = Counter(row['Ürün Adı'] for row in clean_data if 'Ürün Adı' in row)
            product_group_mapping = {}
            
            # Ürün adı ile grup eşleştirmesi
            for row in clean_data:
                if 'Ürün Adı' in row:
                    product_name = row['Ürün Adı']
                    product_group = row['Ürün Grubu']
                    if product_name not in product_group_mapping:
                        product_group_mapping[product_name] = product_group
            
            total_sales = sum(product_name_counts.values())
            top_products = product_name_counts.most_common(20)
            
            # Kategori bazında dağılım
            category_analysis = defaultdict(list)
            for product_name, count in top_products:
                group = product_group_mapping.get(product_name, 'Bilinmiyor')
                category_analysis[group].append({
                    'name': product_name,
                    'count': count,
                    'percentage': round((count / total_sales) * 100, 1)
                })
            
            result_data = {
                'type': 'product_detail',
                'title': 'Detaylı Ürün Performans Analizi',
                'top_products': top_products,
                'total_products': len(product_name_counts),
                'total_sales': total_sales,
                'category_analysis': dict(category_analysis),
                'product_group_mapping': product_group_mapping
            }
            
        elif analysis_type == 'sales_rep':
            # Satış sorumlusu performans analizi
            rep_performance = defaultdict(lambda: {
                'total_sales': 0,
                'unique_customers': set(),
                'unique_products': set(),
                'orders': set()
            })
            
            for row in clean_data:
                if 'Satış Sorumlusu' in row:
                    rep = row['Satış Sorumlusu']
                    rep_performance[rep]['total_sales'] += 1
                    rep_performance[rep]['orders'].add(row['Numara'])
                    rep_performance[rep]['unique_products'].add(row['Ürün Grubu'])
                    
                    if 'Müşteri' in row:
                        rep_performance[rep]['unique_customers'].add(row['Müşteri'])
            
            # Sonuçları hazırla
            rep_results = []
            for rep, stats in rep_performance.items():
                rep_results.append({
                    'name': rep,
                    'total_sales': stats['total_sales'],
                    'unique_customers': len(stats['unique_customers']),
                    'unique_products': len(stats['unique_products']),
                    'orders': len(stats['orders']),
                    'avg_products_per_order': round(stats['total_sales'] / len(stats['orders']), 1) if stats['orders'] else 0
                })
            
            # Performansa göre sırala
            rep_results.sort(key=lambda x: x['total_sales'], reverse=True)
            
            total_reps = len(rep_results)
            total_sales_all = sum(r['total_sales'] for r in rep_results)
            
            result_data = {
                'type': 'sales_rep',
                'title': 'Satış Sorumlusu Performans Analizi',
                'representatives': rep_results,
                'total_reps': total_reps,
                'total_sales': total_sales_all,
                'avg_sales_per_rep': round(total_sales_all / total_reps, 1) if total_reps > 0 else 0
            }
            
        elif analysis_type == 'lift':
            if not urun1 or not urun2:
                flash('Lift analizi için her iki ürün adını da giriniz!', 'error')
                return redirect(url_for('index'))
            
            urun1 = urun1.upper()
            urun2 = urun2.upper()
            
            # Ürün varlığını kontrol et
            all_products = set(row['Ürün Grubu'] for row in clean_data)
            if urun1 not in all_products:
                available_list = ', '.join(list(all_products)[:10])
                flash(f'"{urun1}" ürünü bulunamadı! Mevcut ürünler: {available_list}', 'error')
                return redirect(url_for('index'))
            
            if urun2 not in all_products:
                available_list = ', '.join(list(all_products)[:10])
                flash(f'"{urun2}" ürünü bulunamadı! Mevcut ürünler: {available_list}', 'error')
                return redirect(url_for('index'))
            
            # Sipariş bazında analiz
            order_products = defaultdict(set)
            for row in clean_data:
                order_products[row['Numara']].add(row['Ürün Grubu'])
            
            total_orders = len(order_products)
            orders_with_urun1 = sum(1 for products in order_products.values() if urun1 in products)
            orders_with_urun2 = sum(1 for products in order_products.values() if urun2 in products)
            orders_with_both = sum(1 for products in order_products.values() if urun1 in products and urun2 in products)
            
            if total_orders == 0:
                flash('Analiz için yeterli veri yok!', 'error')
                return redirect(url_for('index'))
            
            p_a = orders_with_urun1 / total_orders
            p_b = orders_with_urun2 / total_orders
            p_ab = orders_with_both / total_orders
            
            lift = round(p_ab / (p_a * p_b), 2) if p_a * p_b > 0 else 0
            confidence = round(p_ab / p_a, 2) if p_a > 0 else 0
            
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
                'together_sales': orders_with_both,
                'product1_sales': orders_with_urun1,
                'product2_sales': orders_with_urun2,
                'total_customers': total_orders,
                'interpretation': interpretation
            }
            
        elif analysis_type == 'pair':
            # Sipariş bazında ürün grupları
            order_products = defaultdict(set)
            for row in clean_data:
                order_products[row['Numara']].add(row['Ürün Grubu'])
            
            pair_counts = Counter()
            for products in order_products.values():
                if len(products) >= 2:
                    for pair in combinations(sorted(products), 2):
                        pair_counts[pair] += 1
            
            result_data = {
                'type': 'pair',
                'title': 'En Çok Birlikte Satılan Ürün Çiftleri',
                'pairs': [{'products': f"{p[0]} + {p[1]}", 'count': c} 
                         for (p, c) in pair_counts.most_common(15)],
                'total_pairs': len(pair_counts)
            }
            
        elif analysis_type == 'time':
            # Tarih sütunu kontrolü
            time_data = []
            for row in clean_data:
                if 'Tarih' in row and row['Tarih']:
                    try:
                        if isinstance(row['Tarih'], datetime):
                            month_year = row['Tarih'].strftime('%Y-%m')
                        else:
                            # String tarih parse et
                            date_obj = datetime.strptime(str(row['Tarih'])[:10], '%Y-%m-%d')
                            month_year = date_obj.strftime('%Y-%m')
                        time_data.append(month_year)
                    except:
                        continue
            
            if not time_data:
                flash('Zaman analizi için geçerli tarih verisi bulunamadı!', 'error')
                return redirect(url_for('index'))
            
            month_counts = Counter(time_data)
            
            result_data = {
                'type': 'time',
                'title': 'Aylık Satış Trendi',
                'data': list(month_counts.most_common()),
                'total_months': len(month_counts)
            }
            
        elif analysis_type == 'customer':
            # Müşteri analizi
            customer_col = 'Müşteri' if any('Müşteri' in row for row in clean_data) else 'Numara'
            
            customer_products = defaultdict(list)
            customer_variety = defaultdict(set)
            
            for row in clean_data:
                customer = row.get(customer_col, row['Numara'])
                customer_products[customer].append(row['Ürün Grubu'])
                customer_variety[customer].add(row['Ürün Grubu'])
            
            total_customers = len(customer_products)
            avg_products = sum(len(products) for products in customer_products.values()) / total_customers
            avg_variety = sum(len(variety) for variety in customer_variety.values()) / total_customers
            max_products = max(len(products) for products in customer_products.values())
            max_variety = max(len(variety) for variety in customer_variety.values())
            
            result_data = {
                'type': 'customer',
                'title': 'Müşteri Analizi',
                'avg_products_per_customer': round(avg_products, 2),
                'avg_variety_per_customer': round(avg_variety, 2),
                'total_customers': total_customers,
                'max_products': max_products,
                'max_variety': max_variety
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
