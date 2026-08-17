#!/usr/bin/env python3
"""
Script de gestión de la Biblioteca EPET N° 18
Uso:
  ./add_book.py <ISBN>
  ./add_book.py <ISBN> "Título del libro"
"""

import urllib.request
import urllib.parse
import json
import re
import sys
import os

CONFIG_PATH = "hugo.toml"
COVERS_DIR = "static/images/covers"

# Taxonomía única del catálogo. Google Books devuelve categorías libres y, a
# menudo, jerárquicas (por ejemplo: "Juvenile Fiction / Fantasy & Magic").
# Todos esos valores se reducen a uno de estos encabezados estables.
CATEGORY_RULES = (
    ("Literatura Infantil & Juvenil", ("juvenile", "children", "infantil", "juvenil", "young adult")),
    ("Cómics & Novela Gráfica", ("comics", "graphic novel", "manga")),
    ("Ciencia Ficción & Fantasía", ("science fiction", "fantasy", "ciencia ficción", "fantasía", "dystopian")),
    ("Poesía, Teatro & Clásicos", ("poetry", "poesía", "drama", "teatro", "classics", "clásicos")),
    ("Literatura & Ficción", ("fiction", "ficción", "literature", "literatura", "novel", "novela")),
    ("Informática & Tecnología", ("computers", "computer", "software", "programming", "informática", "technology")),
    ("Tecnología & Ingeniería", ("engineering", "ingeniería", "technology")),
    ("Ciencias Naturales & Física", ("science", "ciencia", "physics", "física", "biology", "biología")),
    ("Ciencias Sociales", ("social science", "sociology", "sociología", "politics", "política", "economics", "economía")),
    ("Historia & Crónicas", ("history", "historia", "biography", "biografía")),
    ("Filosofía, Ensayo & Pensamiento", ("philosophy", "filosofía", "essay", "ensayo", "religion", "religión")),
    ("Arte & Diseño", ("art", "arte", "design", "diseño", "music", "música")),
    ("Educación & Pedagogía", ("education", "educación", "teaching", "pedagogy", "pedagogía")),
)

def normalize_category(raw_category):
    """Convierte cualquier categoría de Google Books al estándar del catálogo."""
    value = re.sub(r"\s+", " ", str(raw_category or "")).strip().lower()
    for canonical, keywords in CATEGORY_RULES:
        if any(keyword in value for keyword in keywords):
            return canonical
    return "Otros"

def clean_isbn_str(raw):
    return re.sub(r'[^0-9X]', '', str(raw).strip().upper())

def has_value(value):
    return value not in (None, "", [], 0)

def merge_volume_info(volumes, isbn):
    """Combina ediciones/resultados: una portada no implica metadatos completos."""
    infos = [volume.get('volumeInfo', {}) for volume in volumes]
    if not infos:
        return None

    def first(field, default=""):
        return next((info.get(field) for info in infos if has_value(info.get(field))), default)

    categories = next((info.get('categories') for info in infos if info.get('categories')), [])
    image_links = next((info.get('imageLinks') for info in infos if info.get('imageLinks')), {})
    return {
        "isbn": isbn,
        "title": first('title', f"Libro {isbn}"),
        "authors": first('authors', ["Autor desconocido"]),
        "category": normalize_category(categories[0] if categories else ""),
        "publisher": first('publisher'),
        "year": str(first('publishedDate'))[:4],
        "pages": first('pageCount', 0),
        "description": first('description'),
        "cover_remote": (image_links.get('thumbnail') or image_links.get('smallThumbnail') or
                          f"https://books.google.com/books/content?vid=ISBN{isbn}&printsec=frontcover&img=1&zoom=1")
    }

def complete_from_openlibrary(book):
    """Completa campos que Google Books deja vacíos, sin reemplazar datos válidos."""
    missing = not all((book['publisher'], book['year'], book['pages'], book['description']))
    if not missing:
        return book
    try:
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{book['isbn']}&jscmd=data&format=json"
        req = urllib.request.Request(url, headers={'User-Agent': 'Biblioteca-EPETN18/1.0'})
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode('utf-8'))
        info = data.get(f"ISBN:{book['isbn']}", {})
        publishers = info.get('publishers') or []
        if not book['publisher'] and publishers:
            book['publisher'] = publishers[0].get('name', '')
        if not book['pages'] and info.get('number_of_pages'):
            book['pages'] = info['number_of_pages']
        if not book['year']:
            book['year'] = str(info.get('publish_date', ''))[-4:]
    except Exception as e:
        print(f"  [Aviso fuente alternativa]: {e}")
    return book

def fetch_openlibrary_info(isbn):
    """Obtiene una edición concreta cuando Google Books está limitado por cuota."""
    url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&jscmd=data&format=json"
    req = urllib.request.Request(url, headers={'User-Agent': 'Biblioteca-EPETN18/1.0'})
    with urllib.request.urlopen(req, timeout=6) as response:
        info = json.loads(response.read().decode('utf-8')).get(f"ISBN:{isbn}", {})
    if not info:
        return None

    authors = [a.get('name', '').strip() for a in info.get('authors', []) if a.get('name')]
    publishers = [p.get('name', '').strip() for p in info.get('publishers', []) if p.get('name')]
    subjects = [s.get('name', '') for s in info.get('subjects', [])]
    description = info.get('notes') or info.get('description') or ""
    if isinstance(description, dict):
        description = description.get('value', '')
    return {
        "isbn": isbn,
        "title": info.get('title') or f"Libro {isbn}",
        "authors": authors or ["Autor desconocido"],
        "category": normalize_category(subjects[0] if subjects else ""),
        "publisher": publishers[0] if publishers else "",
        "year": str(info.get('publish_date', ''))[-4:],
        "pages": info.get('number_of_pages') or 0,
        "description": description,
        "cover_remote": (info.get('cover', {}).get('medium') or
                          f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg")
    }

def fetch_book_info(isbn, custom_query=None):
    clean_isbn = clean_isbn_str(isbn)
    headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64)'}
    
    # 1. Intentar buscar en Google Books por ISBN exacto
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean_isbn}&maxResults=10"
    if custom_query:
        url = f"https://www.googleapis.com/books/v1/volumes?q={urllib.parse.quote(custom_query)}&maxResults=10"
        
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=6) as response:
            data = json.loads(response.read().decode('utf-8'))
            if data.get('items'):
                return complete_from_openlibrary(merge_volume_info(data['items'], clean_isbn))
    except Exception as e:
        print(f"  [Aviso API]: {e}")

    # Open Library suele seguir disponible aunque Google Books haya agotado la cuota.
    try:
        fallback = fetch_openlibrary_info(clean_isbn)
        if fallback:
            return fallback
    except Exception as e:
        print(f"  [Aviso Open Library]: {e}")

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
                "category": "Otros",
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
        "category": "Otros",
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
                print(f"  Portada guardada ({len(data)} bytes) en {local_path}")
                return f"images/covers/{isbn}.{ext}"
    except Exception as e:
        print(f"  [Aviso descarga portada]: {e}")

    return remote_url

def book_block(book, pdf=""):
    authors_json = json.dumps(book['authors'], ensure_ascii=False)
    desc_escaped = str(book['description'] or '').replace('"', '\\"').replace('\n', ' ')
    return f"""
    [[params.libros]]
    isbn = "{book['isbn']}"
    title = "{book['title']}"
    authors = {authors_json}
    category = "{book['category']}"
    publisher = "{book['publisher']}"
    year = "{book['year']}"
    pages = {book['pages'] or 0}
    description = "{desc_escaped}"
    cover = "{book['cover']}"
    pdf = "{pdf}"
"""

def save_to_hugo(book, refresh=False):
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    pattern = re.compile(rf'(?ms)^\s*\[\[params\.libros\]\].*?^\s*isbn\s*=\s*"{re.escape(book["isbn"])}".*?(?=^\s*\[\[params\.libros\]\]|\Z)')
    existing = pattern.search(content)
    if existing and refresh:
        pdf_match = re.search(r'(?m)^\s*pdf\s*=\s*"(.*)"\s*$', existing.group(0))
        pdf = pdf_match.group(1) if pdf_match else ""
        content = content[:existing.start()] + book_block(book, pdf) + content[existing.end():]
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            f.write(content)
        print(f"Metadatos del ISBN {book['isbn']} actualizados en {CONFIG_PATH}")
        return

    if existing:
        print(f"El libro con ISBN {book['isbn']} ya se encuentra registrado en {CONFIG_PATH}")
        return

    with open(CONFIG_PATH, 'a', encoding='utf-8') as f:
        f.write(book_block(book))
    print(f"Libro '{book['title']}' registrado con éxito en {CONFIG_PATH}")

def main():
    refresh = len(sys.argv) >= 2 and sys.argv[1] == '--refresh'
    isbn_arg = sys.argv[2] if refresh and len(sys.argv) >= 3 else (sys.argv[1] if len(sys.argv) >= 2 else None)
    query_index = 3 if refresh else 2
    if not isbn_arg:
        print("Uso: ./add_book.py <ISBN>")
        print("     ./add_book.py --refresh <ISBN> [\"Título del libro\"]")
        print("Ejemplo: ./add_book.py 9789500700764")
        sys.exit(1)

    isbn = isbn_arg
    query = sys.argv[query_index] if len(sys.argv) > query_index else None

    # No consultar APIs ni reemplazar datos al intentar agregar un ISBN existente.
    clean_isbn = clean_isbn_str(isbn)
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        if not refresh and f'isbn = "{clean_isbn}"' in f.read():
            print(f"El libro con ISBN {clean_isbn} ya se encuentra registrado en {CONFIG_PATH}")
            return
    
    print(f"Consultando metadatos para ISBN: {clean_isbn}...")
    book = fetch_book_info(isbn, query)
    
    print(f"Título: {book['title']}")
    print(f"Autores: {', '.join(book['authors'])}")
    print(f"Categoría: {book['category']}")
    print(f"Editorial: {book['publisher'] or 'No disponible'}")
    print(f"Año: {book['year'] or 'No disponible'}")
    print(f"Páginas: {book['pages'] or 'No disponibles'}")
    print(f"Descripción: {'disponible' if book['description'] else 'No disponible'}")
    
    cover_path = download_cover(book['isbn'], book['cover_remote'])
    book['cover'] = cover_path
    
    save_to_hugo(book, refresh=refresh)

if __name__ == '__main__':
    main()
