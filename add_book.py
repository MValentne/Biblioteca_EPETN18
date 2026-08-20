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
import time

CONFIG_PATH = "hugo.toml"
COVERS_DIR = "static/images/covers"
USER_AGENT = "Biblioteca-EPETN18/1.1 (catalogo escolar)"

class MetadataUnavailable(RuntimeError):
    """Ninguna fuente pudo devolver metadatos confiables."""

def fetch_json(url, timeout=8, attempts=3):
    """Consulta una API con backoff y respeta los límites temporales."""
    for attempt in range(attempts):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT, "Accept": "application/json"})
            with urllib.request.urlopen(req, timeout=timeout) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            if error.code not in (429, 500, 502, 503, 504) or attempt == attempts - 1:
                raise
            retry_after = error.headers.get("Retry-After", "")
            try:
                delay = min(max(float(retry_after), 1), 30)
            except ValueError:
                delay = 2 ** attempt
            print(f"  [Aviso API]: HTTP {error.code}; reintentando en {delay:g}s...")
            time.sleep(delay)
        except (urllib.error.URLError, TimeoutError, json.JSONDecodeError) as error:
            if attempt == attempts - 1:
                raise
            delay = 2 ** attempt
            print(f"  [Aviso API]: {error}; reintentando en {delay}s...")
            time.sleep(delay)

# Taxonomía del catálogo. Google Books devuelve categorías libres y jerárquicas
# (ej: "Juvenile Fiction / Fantasy & Magic"). Open Library devuelve subjects
# como strings libres (ej: "Combinatorial analysis"). Todos se reducen aquí.
CATEGORY_RULES = (
    ("Literatura Infantil & Juvenil", (
        "juvenile", "children", "infantil", "juvenil", "young adult",
        "kid", "picture book", "children's fiction", "children's literature",
    )),
    ("Cómics & Novela Gráfica", (
        "comics", "graphic novel", "manga", "comic",
    )),
    ("Ciencia Ficción & Fantasía", (
        "science fiction", "fantasy", "ciencia ficción", "fantasía",
        "dystopian", "speculative", "supernatural", "sci-fi",
        "utopian", "alternate history",
    )),
    ("Poesía, Teatro & Clásicos", (
        "poetry", "poesía", "drama", "teatro", "classics", "clásicos",
        "verse", "play", "epic", "tragedy", "gaucho",
    )),
    ("Literatura & Ficción", (
        "fiction", "ficción", "literature", "literatura", "novel", "novela",
        "short stories", "cuentos", "adventure", "thriller", "mystery",
        "romance", "suspense", "crime", "horror", "detective", "narrative",
        "narración", "literary", "literaria",
    )),
    ("Informática & Tecnología", (
        "computers", "computer science", "software", "programming",
        "informática", "algorithms", "data structures", "machine learning",
        "artificial intelligence", "internet", "networks", "operating system",
        "database", "cybersecurity", "python", "java", "javascript",
        "web development", "sistemas", "computación",
    )),
    ("Tecnología & Ingeniería", (
        "engineering", "ingeniería", "electronics", "electrónica",
        "mechanical", "mecánica", "civil", "electrical", "eléctrica",
        "systems", "automation", "automatización", "industrial",
    )),
    ("Matemáticas", (
        "mathematics", "matemáticas", "math", "algebra", "calculus",
        "geometry", "geometría", "statistics", "estadística", "probability",
        "combinatorial", "combinatorics", "number theory", "topology",
        "analysis", "discrete", "discreta", "trigonometry", "trigonometría",
    )),
    ("Ciencias Naturales & Física", (
        "science", "ciencia", "physics", "física", "biology", "biología",
        "chemistry", "química", "astronomy", "astronomía", "ecology",
        "ecología", "geology", "geología", "natural history",
    )),
    ("Ciencias Sociales", (
        "social science", "sociology", "sociología", "politics", "política",
        "economics", "economía", "anthropology", "antropología",
        "psychology", "psicología", "communication", "comunicación",
        "political science", "ciencias sociales",
    )),
    ("Historia & Crónicas", (
        "history", "historia", "biography", "biografía", "autobiography",
        "autobiografía", "chronicle", "crónica", "memoir", "war", "guerra",
        "ancient", "medieval", "colonial", "historical",
    )),
    ("Filosofía, Ensayo & Pensamiento", (
        "philosophy", "filosofía", "essay", "ensayo", "religion", "religión",
        "ethics", "ética", "logic", "lógica", "spirituality", "espiritualidad",
        "theology", "teología", "pensamiento",
    )),
    ("Arte & Diseño", (
        "art", "arte", "design", "diseño", "music", "música",
        "architecture", "arquitectura", "photography", "fotografía",
        "film", "cinema", "painting", "drawing",
    )),
    ("Educación & Pedagogía", (
        "education", "educación", "teaching", "pedagogy", "pedagogía",
        "learning", "aprendizaje", "school", "escuela", "curriculum",
    )),
    ("Salud & Medicina", (
        "medicine", "medicina", "health", "salud", "nutrition", "nutrición",
        "anatomy", "anatomía", "clinical", "clínica", "nursing", "enfermería",
    )),
    ("Derecho", (
        "law", "derecho", "legal", "jurisprudence", "jurisprudencia",
        "constitution", "constitución", "criminal", "penal", "civil law",
    )),
    ("Administración & Negocios", (
        "business", "negocios", "management", "administración", "marketing",
        "finance", "finanzas", "entrepreneurship", "emprendimiento",
        "leadership", "liderazgo", "accounting", "contabilidad",
    )),
)

def normalize_category(raw_categories):
    """Mapea categorías/subjects de cualquier API al estándar del catálogo.

    Acepta un string o una lista de strings (como devuelven Google Books y
    Open Library). Prueba CADA entrada en orden hasta encontrar el primer match.
    Si ninguno hace match retorna el primer valor recibido en Title Case
    (más legible y dinámico que siempre poner 'Otros').
    """
    if isinstance(raw_categories, str):
        candidates = [raw_categories] if raw_categories.strip() else []
    elif isinstance(raw_categories, (list, tuple)):
        candidates = [str(c).strip() for c in raw_categories if c and str(c).strip()]
    else:
        candidates = []

    for raw in candidates:
        value = re.sub(r"\s+", " ", raw).strip().lower()
        for canonical, keywords in CATEGORY_RULES:
            if any(keyword in value for keyword in keywords):
                return canonical

    # Sin match en las reglas: usar la primera categoría recibida tal cual
    if candidates:
        return candidates[0].strip().title()
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

    # Recolectar TODAS las categorías de todos los volúmenes para maximizar el match
    all_categories = []
    for info in infos:
        all_categories.extend(info.get('categories') or [])

    image_links = next((info.get('imageLinks') for info in infos if info.get('imageLinks')), {})
    return {
        "isbn": isbn,
        "title": first('title', f"Libro {isbn}"),
        "authors": first('authors', ["Autor desconocido"]),
        "category": normalize_category(all_categories),
        "publisher": first('publisher'),
        "year": str(first('publishedDate'))[:4],
        "pages": first('pageCount', 0),
        "description": first('description'),
        "cover_remote": (image_links.get('thumbnail') or image_links.get('smallThumbnail') or
                          f"https://books.google.com/books/content?vid=ISBN{isbn}&printsec=frontcover&img=1&zoom=1")
    }

def _fetch_openlibrary_subjects(isbn):
    """Obtiene subjects desde la API de ediciones y, si son escasos, también desde Works.

    Retorna (subjects: list[str], edition_info: dict).
    """
    subjects = []
    info = {}

    # 1. API de ediciones (jscmd=data) — subjects con nombre legible
    try:
        url = f"https://openlibrary.org/api/books?bibkeys=ISBN:{isbn}&jscmd=data&format=json"
        data = fetch_json(url)
        info = data.get(f"ISBN:{isbn}", {})
        subjects += [s.get('name', '') for s in info.get('subjects', []) if s.get('name')]
    except Exception:
        pass

    # 2. Si hay pocos subjects, enriquecer desde la API de Works
    if len(subjects) < 3:
        works = info.get('works', [])
        if works:
            work_key = works[0].get('key', '')  # ej: "/works/OL1234W"
            if work_key:
                try:
                    work_data = fetch_json(f"https://openlibrary.org{work_key}.json")
                    for s in work_data.get('subjects', []):
                        if isinstance(s, str):
                            subjects.append(s)
                        elif isinstance(s, dict):
                            subjects.append(s.get('name', ''))
                except Exception:
                    pass

    return [s for s in subjects if s], info

def complete_from_openlibrary(book):
    """Completa campos que Google Books deja vacíos; también mejora 'Otros'."""
    needs_meta = not all((book['publisher'], book['year'], book['pages'], book['description']))
    needs_category = book['category'] == "Otros"
    if not needs_meta and not needs_category:
        return book
    try:
        subjects, info = _fetch_openlibrary_subjects(book['isbn'])
        publishers = info.get('publishers') or []
        if not book['publisher'] and publishers:
            book['publisher'] = publishers[0].get('name', '')
        if not book['pages'] and info.get('number_of_pages'):
            book['pages'] = info['number_of_pages']
        if not book['year']:
            book['year'] = str(info.get('publish_date', ''))[-4:]
        # Mejorar categoría si sigue siendo 'Otros' y tenemos subjects de OL
        if needs_category and subjects:
            candidate = normalize_category(subjects)
            if candidate != "Otros":
                book['category'] = candidate
                print(f"  Categoría mejorada desde Open Library: {candidate}")
    except Exception as e:
        print(f"  [Aviso fuente alternativa]: {e}")
    return book

def fetch_openlibrary_info(isbn):
    """Obtiene una edición concreta cuando Google Books está limitado por cuota."""
    subjects, info = _fetch_openlibrary_subjects(isbn)
    if not info:
        return None

    authors = [a.get('name', '').strip() for a in info.get('authors', []) if a.get('name')]
    publishers = [p.get('name', '').strip() for p in info.get('publishers', []) if p.get('name')]
    description = info.get('notes') or info.get('description') or ""
    if isinstance(description, dict):
        description = description.get('value', '')

    return {
        "isbn": isbn,
        "title": info.get('title') or f"Libro {isbn}",
        "authors": authors or ["Autor desconocido"],
        "category": normalize_category(subjects),
        "publisher": publishers[0] if publishers else "",
        "year": str(info.get('publish_date', ''))[-4:],
        "pages": info.get('number_of_pages') or 0,
        "description": description,
        "cover_remote": (info.get('cover', {}).get('medium') or
                          f"https://covers.openlibrary.org/b/isbn/{isbn}-L.jpg")
    }

def fetch_book_info(isbn, custom_query=None):
    clean_isbn = clean_isbn_str(isbn)
    # 1. Intentar buscar en Google Books por ISBN exacto
    url = f"https://www.googleapis.com/books/v1/volumes?q=isbn:{clean_isbn}&maxResults=10"
    if custom_query:
        url = f"https://www.googleapis.com/books/v1/volumes?q={urllib.parse.quote(custom_query)}&maxResults=10"
        
    try:
        data = fetch_json(url)
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

    raise MetadataUnavailable(
        f"No se encontraron metadatos para ISBN {clean_isbn}; no se modificó hugo.toml."
    )

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
    toml_string = lambda value: json.dumps(str(value or ""), ensure_ascii=False)
    return f"""
    [[params.libros]]
    isbn = "{book['isbn']}"
    title = {toml_string(book['title'])}
    authors = {authors_json}
    category = {toml_string(book['category'])}
    publisher = {toml_string(book['publisher'])}
    year = {toml_string(book['year'])}
    pages = {book['pages'] or 0}
    description = {toml_string(book['description'])}
    cover = {toml_string(book['cover'])}
    pdf = {toml_string(pdf)}
"""

def _find_book_block(content, isbn):
    """Devuelve (start, end) del bloque [[params.libros]] que contiene el ISBN.

    Estrategia: busca la línea `isbn = "ISBN"`, luego localiza el
    [[params.libros]] inmediatamente anterior y el [[params.libros]] siguiente
    (o el final del archivo). Esto evita que el regex retroceda y capture
    bloques de libros anteriores.
    """
    isbn_pattern = re.compile(rf'(?m)^\s*isbn\s*=\s*"{re.escape(isbn)}"')
    isbn_match = isbn_pattern.search(content)
    if not isbn_match:
        return None, None

    header_pattern = re.compile(r'(?m)^\s*\[\[params\.libros\]\]')

    # Buscar el [[params.libros]] que viene JUSTO ANTES del ISBN
    block_start = None
    for m in header_pattern.finditer(content, 0, isbn_match.start()):
        block_start = m.start()  # el último header antes del ISBN

    if block_start is None:
        return None, None  # ISBN encontrado pero sin header (no debería pasar)

    # El bloque termina donde empieza el SIGUIENTE [[params.libros]] o el EOF
    next_header = header_pattern.search(content, isbn_match.end())
    block_end = next_header.start() if next_header else len(content)

    return block_start, block_end

def save_to_hugo(book, refresh=False):
    with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
        content = f.read()

    block_start, block_end = _find_book_block(content, book['isbn'])
    existing = block_start is not None

    if existing and refresh:
        existing_block = content[block_start:block_end]
        pdf_match = re.search(r'(?m)^\s*pdf\s*=\s*"(.*)"\s*$', existing_block)
        pdf = pdf_match.group(1) if pdf_match else ""
        content = content[:block_start] + book_block(book, pdf) + content[block_end:]
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
    try:
        book = fetch_book_info(isbn, query)
    except MetadataUnavailable as error:
        print(f"[ERROR] {error}")
        print("Podés reintentar más tarde o pasar el título como segundo argumento.")
        sys.exit(2)
    
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
