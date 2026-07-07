import os
import zipfile
import shutil
from typing import List, Tuple
import fitz  # PyMuPDF
from pypdf import PdfReader
from docx import Document

RESUME_EXTENSIONS = ('.pdf', '.docx', '.doc')

def is_resume_file(filename: str) -> bool:
    return filename.lower().endswith(RESUME_EXTENSIONS)

def extract_zip(zip_path: str, extract_to: str) -> List[str]:
    """
    Extracts a ZIP file and returns a list of paths to all files inside.
    Sanitizes names to avoid issues with trailing spaces on Windows.
    """
    if not os.path.exists(extract_to):
        os.makedirs(extract_to)
    
    with zipfile.ZipFile(zip_path, 'r') as zip_ref:
        for info in zip_ref.infolist():
            # Sanitize path components (remove trailing spaces which are illegal on Windows)
            sanitized_path_components = [p.strip() for p in info.filename.split('/')]
            sanitized_path = os.path.join(*sanitized_path_components)
            
            # Ensure it's inside extract_to
            target_path = os.path.abspath(os.path.join(extract_to, sanitized_path))
            if not target_path.startswith(os.path.abspath(extract_to)):
                continue # Path traversal protection
            
            if info.is_dir():
                os.makedirs(target_path, exist_ok=True)
            else:
                os.makedirs(os.path.dirname(target_path), exist_ok=True)
                with zip_ref.open(info.filename) as source, open(target_path, "wb") as dest:
                    shutil.copyfileobj(source, dest)
    
    extracted_files = []
    for root, _, filenames in os.walk(extract_to):
        for filename in filenames:
            extracted_files.append(os.path.abspath(os.path.join(root, filename)))
    return extracted_files

def extract_text_from_pdf(pdf_path: str) -> str:
    """
    Extracts text from a PDF file using PyMuPDF (fitz) - the fastest & most accurate method.
    """
    text = ""
    try:
        with fitz.open(pdf_path) as doc:
            for page in doc:
                text += page.get_text("text") + "\n"
    except Exception as e:
        print(f"Error extracting PDF text from {pdf_path}: {e}") # Changed from logger.error to print for consistency
    return text.strip()

def extract_text_from_docx(docx_path: str) -> str:
    """Extracts text from a DOCX file."""
    try:
        doc = Document(docx_path)
        text = "\n".join([para.text for para in doc.paragraphs])
        return text.strip()
    except Exception as e:
        print(f"Error extracting DOCX {docx_path}: {e}")
        return ""

def get_resume_content(file_path: str) -> Tuple[str, str]:
    """Returns (filename, content) from a file."""
    filename = os.path.basename(file_path)
    ext = filename.split('.')[-1].lower()
    
    if ext == 'pdf':
        return filename, extract_text_from_pdf(file_path)
    elif ext in ['doc', 'docx']:
        return filename, extract_text_from_docx(file_path)
    else:
        # Try reading as plain text if it's not a known binary format
        try:
            with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
                return filename, f.read()
        except:
            return filename, ""
