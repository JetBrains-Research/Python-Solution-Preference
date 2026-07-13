import sqlite3
from threading import Lock

DB_NAME = 'marketplace.db'
db_lock = Lock()

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with db_lock:
        with get_db() as conn:
            conn.execute('''
                CREATE TABLE IF NOT EXISTS products (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    title TEXT NOT NULL,
                    description TEXT NOT NULL,
                    price REAL NOT NULL,
                    category TEXT NOT NULL,
                    condition TEXT NOT NULL,
                    location TEXT NOT NULL,
                    image_path TEXT NOT NULL,
                    seller_name TEXT NOT NULL,
                    seller_email TEXT NOT NULL,
                    seller_token TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Available',
                    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            conn.execute('''
                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    product_id INTEGER NOT NULL,
                    buyer_name TEXT NOT NULL,
                    buyer_email TEXT NOT NULL,
                    buyer_phone TEXT NOT NULL,
                    buyer_token TEXT UNIQUE NOT NULL,
                    status TEXT NOT NULL DEFAULT 'Pending',
                    FOREIGN KEY (product_id) REFERENCES products (id)
                )
            ''')
            conn.commit()

def create_product(data, token):
    with db_lock:
        with get_db() as conn:
            cur = conn.execute('''
                INSERT INTO products (title, description, price, category, condition, location, image_path, seller_name, seller_email, seller_token)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ''', (data['title'], data['description'], data['price'], data['category'], data['condition'], data['location'], data['image_path'], data['seller_name'], data['seller_email'], token))
            conn.commit()
            return cur.lastrowid

def get_featured_products():
    with get_db() as conn:
        return conn.execute('SELECT * FROM products WHERE status = "Available" ORDER BY created_at DESC LIMIT 8').fetchall()

def get_products(category=None):
    with get_db() as conn:
        if category and category != 'All':
            return conn.execute('SELECT * FROM products WHERE status = "Available" AND category = ? ORDER BY created_at DESC', (category,)).fetchall()
        return conn.execute('SELECT * FROM products WHERE status = "Available" ORDER BY created_at DESC').fetchall()

def get_product(product_id):
    with get_db() as conn:
        return conn.execute('SELECT * FROM products WHERE id = ?', (product_id,)).fetchone()

def create_order(product_id, buyer_data, buyer_token):
    with db_lock:
        with get_db() as conn:
            # Atomic check and update
            cur = conn.execute('SELECT status FROM products WHERE id = ?', (product_id,))
            row = cur.fetchone()
            if not row or row['status'] != 'Available':
                return None
            
            conn.execute('UPDATE products SET status = "Pending" WHERE id = ?', (product_id,))
            cur = conn.execute('''
                INSERT INTO orders (product_id, buyer_name, buyer_email, buyer_phone, buyer_token)
                VALUES (?, ?, ?, ?, ?)
            ''', (product_id, buyer_data['name'], buyer_data['email'], buyer_data['phone'], buyer_token))
            conn.commit()
            return cur.lastrowid

def get_seller_status(token):
    with get_db() as conn:
        product = conn.execute('SELECT * FROM products WHERE seller_token = ?', (token,)).fetchone()
        if not product:
            return None
        
        order = None
        if product['status'] == 'Pending':
            order = conn.execute('SELECT * FROM orders WHERE product_id = ?', (product['id'],)).fetchone()
        elif product['status'] == 'Sold':
            order = conn.execute('SELECT * FROM orders WHERE product_id = ?', (product['id'],)).fetchone()
            
        return product, order

def update_product_status(product_id, new_status):
    with db_lock:
        with get_db() as conn:
            conn.execute('UPDATE products SET status = ? WHERE id = ?', (new_status, product_id))
            if new_status == 'Available':
                conn.execute('UPDATE orders SET status = "Cancelled" WHERE product_id = ?', (product_id,))
            elif new_status == 'Sold':
                conn.execute('UPDATE orders SET status = "Confirmed" WHERE product_id = ?', (product_id,))
            conn.commit()

def get_buyer_order(token):
    with get_db() as conn:
        order = conn.execute('SELECT * FROM orders WHERE buyer_token = ?', (token,)).fetchone()
        if not order:
            return None
        product = conn.execute('SELECT * FROM products WHERE id = ?', (order['product_id'],)).fetchone()
        return order, product
