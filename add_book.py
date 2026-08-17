#!/usr/bin/env python3
import urllib.request
import json
import re
import sys
import os

CONFIG_PATH = "hugo.toml"

def get_book_metadata(isbn):
    clean_isbn = re.sub(r'[^0-9X]', '', isbn)
    headers = {'User-Agent': 'Mozilla/5.0'}
    
    # 1. Google Books API
    try:
        url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean_isbn}&maxResults=1"
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.loads(response.read().decode())
            if data.get('items'):
                v = data['items'][0].get('volumeInfo', {})
                cover = ""
                if v.get('imageLinks'):
                    cover = v['imageLinks'].get('thumbnail') or v['imageLinks'].get('smallThumbnail') or ""
                    cover = cover.replace("http://", "https://")
                return {
                    "isbn": clean_isbn,
                    "title": v.get('title', f"Libro {clean_isbn}"),
                    "authors": v.get('authors', ["Autor desconocido"]),
                    "category": v.get('categories', ["General"])[0].split('/')[0].strip(),
                    "publisher": v.get('publisher', ""),
                    "year": (v.get('publishedDate') or "")[:4],
                    "pages": v.get('pageCount', 0),
                    "description": v.get('description', ""),
                    "cover": cover or f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-L.jpg"
                }
    except Exception:
        pass

    # Fallback básico
    return {
        "isbn": clean_isbn,
        "title": f"Libro {clean_isbn}",
        "authors": ["Biblioteca EPET N° 18"],
        "category": "General",
        "publisher": "",
        "year": "",
        "pages": 0,
        "description": "Ejemplar disponible en la biblioteca.",
        "cover": f"https://covers.openlibrary.org/b/isbn/{clean_isbn}-L.jpg"
    }

def append_to_toml(book):
    authors_str = json.dumps(book['authors'], ensure_ascii=False)
    desc_escaped = book['description'].replace('"', '\\"').replace('\n', ' ')
    block = f"""
    [[params.libros]]
    isbn = "{book['isbn']}"
    title = "{book['title']}"
    authors = {authors_str}
    category = "{book['category']}"
    publisher = "{book['publisher']}"
    year = "{book['year']}"
    pages = {book['pages']}
    description = "{desc_escaped}"
    cover = "{book['cover']}"
"""
    with open(CONFIG_PATH, 'a', encoding='utf-8') as f:
        f.write(block)
    print(f"✅ Libro '{book['title']}' agregado con éxito a {CONFIG_PATH}")

if __name__ == '__main__':
    if len(sys.argv) < 2:
        print("Uso: ./add_book.py <ISBN>")
        sys.exit(1)
    
    isbn_arg = sys.argv[1]
    print(f"Buscando metadatos para ISBN: {isbn_arg}...")
    book = get_book_metadata(isbn_arg)
    append_to_toml(book)
