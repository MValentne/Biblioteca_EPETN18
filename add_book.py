#!/usr/bin/env python3
"""
Script de gestión de la Biblioteca EPET N° 18
Uso:
  ./add_book.py <ISBN>
  ./add_book.py <ISBN> "Título del libro"
"""

import urllib.request
import json
import re
import sys
import os

CONFIG_PATH = "hugo.toml"
COVERS_DIR = "static/images/covers"

# Mapeo de categorías en inglés a español
CATEGORY_MAP = {
    "fiction": "Ficción / Novela",
    "juvenile fiction": "Literatura Juvenil / Infantil",
    "computers": "Informática & Tecnología",
    "science": "Ciencias Naturales & Física",
    "history": "Historia & Crónicas",
    "philosophy": "Filosofía & Pensamiento",
    "poetry": "Poesía & Clásicos",
    "education": "Educación & Pedagogía",
    "technology & engineering": "Tecnología & Ingeniería",
    "art": "Arte & Diseño",
    "drama": "Teatro & Dramaturgia",
    "comics & graphic novels": "Cómics & Novela Gráfica",
    "social science": "Ciencias Sociales"
}

def clean_isbn_str(raw):
    return re.sub(r'[^0-9X]', '', str(raw).strip().upper())

def fetch_book_info(isbn, custom_query=None):
    clean_isbn = clean_isbn_str(isbn)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    # 1. Intentar buscar en Google Books por ISBN exacto
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean_isbn}&maxResults=1"
    if custom_query:
        url = f"https://www.googleapis.com/books/v1/volumes?q={urllib.parse.quote(custom_query)}&maxResults=1"
        
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('items'):
                item = data['items'][0]
                v = item.get('volumeInfo', {})
                raw_cat = (v.get('categories') or ['General'])[0].split('/')[0].strip()
                cat_friendly = CATEGORY_MAP.get(raw_cat.lower(), raw_cat)
                
                # Obtener enlace a la mejor portada
                img_links = v.get('imageLinks', {})
                cover_remote = (img_links.get('thumbnail') or 
                                img_links.get('smallThumbnail') or 
                                f"https://books.google.com/books/content?vid=ISBN{clean_isbn}&printsec=frontcover&img=1&zoom=1")
                cover_remote = cover_remote.replace('http://', 'https://')
                
                return {
                    "isbn": clean_isbn,
                    "title": v.get('title', f"Libro {clean_isbn}"),
                    "authors": v.get('authors', ["Autor desconocido"]),
                    "category": cat_friendly,
                    "publisher": v.get('publisher', ""),
                    "year": (v.get('publishedDate') or "")[:4],
                    "pages": v.get('pageCount', 0),
                    "description": v.get('description', ""),
                    "cover_remote": cover_remote
                }
    except Exception as e:
        print(f"  [Aviso API]: {e}")

    # Fallback por scraping web de Google Books si la API tiene cuota agotada
    try:
        gb_web = f"https://books.google.com/books?vid=ISBN{clean_isbn}"
        req = urllib.request.Request(gb_web, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as r:
            html = r.read().decode('utf-8', errors='ignore')
            title_m = re.search(r'<meta property=\"og:title\" content=\"([^\"]+)\"', html)
            title = title_m.group(1).replace(' - Google Libros', '').replace(' - Google Books', '') if title_m else f"Libro {clean_isbn}"
            img_m = re.search(r'src=\"([^\"]+books/content\?id=[a-zA-Z0-9_\-]+[^\"]+img=1[^\"]*)\"', html)
            cover_remote = img_m.group(1).replace('&amp;', '&') if img_m else f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-L.jpg"
            return {
                "isbn": clean_isbn,
                "title": title,
                "authors": ["Biblioteca EPET N° 18"],
                "category": "General",
                "publisher": "",
                "year": "",
                "pages": 0,
                "description": "Ejemplar catalogado en la Biblioteca EPET N° 18.",
                "cover_remote": cover_remote
            }
    except Exception:
        pass

    return {
        "isbn": clean_isbn,
        "title": f"Libro {clean_isbn}",
        "authors": ["Biblioteca EPET N° 18"],
        "category": "General",
        "publisher": "",
        "year": "",
        "pages": 0,
        "description": "Ejemplar catalogado en la Biblioteca EPET N° 18.",
        "cover_remote": f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-L.jpg"
    }

def download_cover(isbn, remote_url):
    os.makedirs(COVERS_DIR, exist_ok=True)
    ext = "jpg"
    local_path = os.path.join(COVERS_DIR, f"{isbn}.{ext}")
    
    if os.path.exists(local_path) and os.path.getsize(local_path) > 1000:
        return f"images/covers/{isbn}.{ext}"

    try:
        req = urllib.request.Request(remote_url, headers={'User-Agent': 'Mozilla/5.0'})
        with urllib.request.urlopen(req, timeout=8) as resp:
            data = resp.read()
            if len(data) > 500:
                with open(local_path, 'wb') as f:
                    f.write(data)
                print(f"  📥 Portada descargada ({len(data)} bytes) en {local_path}")
                return f"images/covers/{isbn}.{ext}"
    except Exception as e:
        print(f"  [Aviso descarga portada]: {e}")

    return remote_url

def save_to_hugo(book):
    authors_json = json.dumps(book['authors'], ensure_ascii=False)
    desc_escaped = book['description'].replace('"', '\\"').replace('\n', ' ')
    
    # Verificar si el ISBN ya existe en hugo.toml
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    if f'isbn = "{book["isbn"]}"' in content:
        print(f"ℹ️ El libro con ISBN {book['isbn']} ya se encuentra registrado en {CONFIG_PATH}")
        return

    block = f"""
    [[params.libros]]
    isbn = "{book['isbn']}"
    title = "{book['title']}"
    authors = {authors_json}
    category = "{book['category']}"
    publisher = "{book['publisher']}"
    year = "{book['year']}"
    pages = {book['pages']}
    description = "{desc_escaped}"
    cover = "{book['cover']}"
"""
    with open(CONFIG_PATH, 'a', encoding='utf-8') as f:
        f.write(block)
    print(f"✅ Libro '{book['title']}' registrado con éxito en {CONFIG_PATH}")

def main():
    if len(sys.argv) < 2:
        print("Uso: ./add_book.py <ISBN>")
        print("Ejemplo: ./add_book.py 9789500700764")
        sys.exit(1)

    isbn = sys.argv[1]
    query = sys.argv[2] if len(sys.argv) > 2 else None
    
    print(f"🔍 Consultando metadatos para ISBN: {isbn}...")
    book = fetch_book_info(isbn, query)
    
    print(f"📖 Título: {book['title']}")
    print(f"✍️  Autores: {', '.join(book['authors'])}")
    print(f"📂 Categoría: {book['category']}")
    
    cover_path = download_cover(book['isbn'], book['cover_remote'])
    book['cover'] = cover_path
    
    save_to_hugo(book)

if __name__ == '__main__':
    main()
