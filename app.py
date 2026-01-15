from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from typing import List
import os
import requests
import time
import re
from urllib.parse import urlparse
import hashlib
import tempfile

from dotenv import load_dotenv
import uuid

try:
    import psycopg2
except Exception:
    psycopg2 = None

try:
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.common.by import By
    from selenium.webdriver.support.ui import WebDriverWait
    from selenium.webdriver.support import expected_conditions as EC
except Exception:
    webdriver = None

try:
    from bs4 import BeautifulSoup
except Exception:
    BeautifulSoup = None

try:
    from reportlab.lib.pagesizes import letter, A4
    from reportlab.platypus import SimpleDocTemplate, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import inch
except Exception:
    SimpleDocTemplate = None

try:
    from PyPDF2 import PdfReader
except Exception:
    PdfReader = None

from starlette.responses import JSONResponse
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

# Load environment variables from .env if present
load_dotenv()
SUPABASE_KEY = os.getenv('SUPABASE_KEY')
SUPABASE_BUCKET = os.getenv('SUPABASE_BUCKET')
SUPABASE_URL = os.getenv('SUPABASE_URL')
DATABASE_URL = os.getenv('DATABASE_URL')


class ScrapeRequest(BaseModel):
    urls: List[str]
    project_id: str


class ProcessDocumentRequest(BaseModel):
    document_id: str


def extract_clean_text(html_content, url):
    """Extract comprehensive text content from HTML, including:
    - Paragraphs (<p>)
    - All div elements (<div>)
    - Section content (<section>)
    - Article content (<article>)
    - Main content (<main>)
    - All headings (<h1> to <h6>)
    - Table content (<table>, <th>, <td>)
    - List items (<li>, <ul>, <ol>)
    - Quotes and code (<blockquote>, <pre>, <code>)
    
    Filters out navigation, ads, images, scripts, and other non-content elements.
    """
    if not BeautifulSoup:
        return "BeautifulSoup not available for text extraction"
    
    soup = BeautifulSoup(html_content, 'html.parser')
    
    # Remove unwanted elements that shouldn't contribute to content
    unwanted_tags = [
        'script', 'style', 'nav', 'header', 'footer', 
        'aside', 'iframe', 'img', 'video', 'audio',
        'form', 'button', 'input', 'select', 'textarea',
        'noscript', 'meta', 'link', 'title'
    ]
    
    # Remove by tag
    for tag in unwanted_tags:
        for element in soup.find_all(tag):
            element.decompose()
    
    # Remove elements with unwanted classes/IDs (ads, navigation, etc.)
    unwanted_selectors = [
        '[class*="ad"]', '[class*="advertisement"]', '[class*="banner"]',
        '[class*="popup"]', '[class*="modal"]', '[class*="sidebar"]',
        '[class*="menu"]', '[class*="navigation"]', '[class*="nav"]',
        '[class*="header"]', '[class*="footer"]', '[class*="social"]',
        '[class*="share"]', '[class*="comment"]', '[class*="related"]',
        '[id*="ad"]', '[id*="advertisement"]', '[id*="banner"]',
        '[id*="popup"]', '[id*="modal"]', '[id*="sidebar"]',
        '[id*="menu"]', '[id*="navigation"]', '[id*="nav"]',
        '[id*="header"]', '[id*="footer"]'
    ]
    
    for selector in unwanted_selectors:
        for element in soup.select(selector):
            element.decompose()
    
    # Extract text from all important content elements including tables
    content_elements = soup.find_all([
        'p', 'div', 'section', 'article', 'main',
        'h1', 'h2', 'h3', 'h4', 'h5', 'h6',
        'table', 'thead', 'tbody', 'tr', 'th', 'td',
        'li', 'ul', 'ol', 'blockquote', 'pre', 'code'
    ])
    text_content = []
    
    for element in content_elements:
        # Get text from the element, excluding any nested unwanted content
        text = element.get_text(separator=' ', strip=True)
        
        # More lenient filtering - include headings and table cells that might be shorter
        if (text and 
            len(text.strip()) > 2 and  # Very minimal length filter
            not re.match(r'^[\s\W]*$', text) and  # Not just whitespace/punctuation
            'cookie' not in text.lower() and  # Skip cookie notices
            'subscribe' not in text.lower()[:30]):  # Skip subscription prompts
            
            # For headings, always include them regardless of length
            if element.name in ['h1', 'h2', 'h3', 'h4', 'h5', 'h6']:
                text_content.append(f"[HEADING] {text}")
            # For table cells, include them with lower word requirement
            elif element.name in ['th', 'td']:
                if len(text.split()) >= 1:  # At least 1 word for table cells
                    text_content.append(f"[TABLE] {text}")
            # For other elements, use moderate filtering
            elif len(text.split()) >= 2:  # At least 2 words for other content
                text_content.append(text)
    
    # If no content found in main elements, try to get any meaningful text from other elements
    if not text_content:
        # Fallback to other content elements
        body = soup.find('body') or soup
        for element in body.find_all(['span', 'a', 'strong', 'em', 'b', 'i']):
            text = element.get_text(strip=True)
            if text and len(text) > 5 and len(text.split()) >= 1:
                text_content.append(text)
    
    # Remove duplicates while preserving order and clean up content
    seen = set()
    unique_content = []
    for text in text_content:
        # Clean up text and remove extra whitespace
        clean_text = ' '.join(text.split())
        if clean_text not in seen and len(clean_text.strip()) > 2:
            seen.add(clean_text)
            unique_content.append(clean_text)
    
    return '\n\n'.join(unique_content)


def create_pdf_from_text(text_content, pdf_path, url, project_id):
    """Create a PDF file from extracted text content"""
    if not SimpleDocTemplate:
        # Fallback to text file if reportlab not available
        # write to a temporary file, then upload to Supabase if configured
        with tempfile.NamedTemporaryFile('w', delete=False, encoding='utf-8', suffix='.txt') as tf:
            tf.write(text_content)
            temp_path = tf.name

        if SUPABASE_URL and SUPABASE_KEY and SUPABASE_BUCKET:
            dest_name = os.path.basename(pdf_path).replace('.pdf', '.txt')
            uploaded = upload_to_supabase(temp_path, SUPABASE_BUCKET, dest_name)
            try:
                os.remove(temp_path)
            except:
                pass
            return uploaded
        return temp_path
    
    # Create PDF in a temporary file then upload to Supabase
    with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tf:
        temp_pdf_path = tf.name
    doc = SimpleDocTemplate(temp_pdf_path, pagesize=A4)
    styles = getSampleStyleSheet()
    story = []
    
    # Title style
    title_style = ParagraphStyle(
        'CustomTitle',
        parent=styles['Heading1'],
        fontSize=16,
        spaceAfter=30,
    )
    
    # Add title
    story.append(Paragraph(f"Web Content Extraction", title_style))
    story.append(Paragraph(f"URL: {url}", styles['Normal']))
    story.append(Paragraph(f"Project: {project_id}", styles['Normal']))
    story.append(Paragraph(f"Extracted: {time.strftime('%Y-%m-%d %H:%M:%S')}", styles['Normal']))
    story.append(Spacer(1, 20))
    
    # Split content into paragraphs and add to PDF
    paragraphs = text_content.split('\\n\\n')
    
    for para in paragraphs:
        if para.strip():
            # Clean text for PDF (remove problematic characters)
            clean_para = para.replace('\\n', ' ').strip()
            if len(clean_para) > 10:  # Only add substantial content
                story.append(Paragraph(clean_para, styles['Normal']))
                story.append(Spacer(1, 12))
    
    # Build PDF
    doc.build(story)

    # If Supabase configured, upload and remove temp file
    if SUPABASE_URL and SUPABASE_KEY and SUPABASE_BUCKET:
        dest_name = os.path.basename(pdf_path)
        uploaded_url = upload_to_supabase(temp_pdf_path, SUPABASE_BUCKET, dest_name)
        try:
            os.remove(temp_pdf_path)
        except:
            pass
        return uploaded_url

    # Otherwise, save to the provided path locally
    try:
        os.makedirs(os.path.dirname(pdf_path), exist_ok=True)
        os.replace(temp_pdf_path, pdf_path)
    except Exception:
        # If replace fails, leave temp file and return its path
        return temp_pdf_path

    return pdf_path


def upload_to_supabase(file_path, bucket, dest_path):
    """Upload a file to Supabase Storage using the REST endpoint.
    Requires SUPABASE_URL and SUPABASE_KEY environment variables.
    Returns the public URL (assumes the bucket or object is public),
    or the storage API response text on failure.
    """
    if not (SUPABASE_URL and SUPABASE_KEY and bucket):
        raise RuntimeError('Supabase configuration missing (SUPABASE_URL, SUPABASE_KEY, SUPABASE_BUCKET)')

    # Ensure dest_path has no leading slash
    dest_path = dest_path.lstrip('/')
    url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/{bucket}/{dest_path}"

    headers = {
        'Authorization': f'Bearer {SUPABASE_KEY}',
        'apiKey': SUPABASE_KEY
    }

    with open(file_path, 'rb') as f:
        data = f.read()

    resp = requests.put(url, data=data, headers=headers, timeout=60)
    if resp.status_code in (200, 201, 204):
        # Return the public object URL (common Supabase pattern)
        public_url = f"{SUPABASE_URL.rstrip('/')}/storage/v1/object/public/{bucket}/{dest_path}"
        return public_url
    else:
        # Return raw response text on failure to help debugging
        return f"upload_failed: {resp.status_code} {resp.text}"


def insert_document_record(project_id, filename, file_path, source='scrape', status='pending', document_content=None):
    """Insert a document record into the documents table. Creates the table if it does not exist."""
    if not psycopg2:
        print("[DB INSERT] psycopg2 not available")
        return None
    
    if not DATABASE_URL:
        print("[DB INSERT] DATABASE_URL not configured")
        return None

    try:
        print(f"[DB INSERT] Connecting to database...")
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        print(f"[DB INSERT] Creating table if not exists...")
        cur.execute("""
        CREATE TABLE IF NOT EXISTS documents (
            id UUID PRIMARY KEY,
            project_id TEXT,
            filename TEXT,
            file_path TEXT,
            source TEXT,
            status TEXT DEFAULT 'pending',
            document_content TEXT
        )
        """)

        doc_id = uuid.uuid4()
        print(f"[DB INSERT] Inserting document record with id={doc_id}")
        cur.execute(
            "INSERT INTO documents (id, project_id, filename, file_path, source, status, document_content) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (str(doc_id), project_id if project_id else None, filename, file_path, source, status, document_content)
        )
        conn.commit()
        cur.close()
        conn.close()
        print(f"[DB INSERT] Successfully inserted document with id={doc_id}")
        return str(doc_id)
    except Exception as e:
        print(f"[DB INSERT] Error during insert: {type(e).__name__}: {str(e)}")
        try:
            conn.close()
        except:
            pass
        return None


def download_pdf_from_url(url):
    """Download a PDF file from a URL and return the file path."""
    try:
        response = requests.get(url, timeout=60)
        response.raise_for_status()
        
        # Save to temporary file
        with tempfile.NamedTemporaryFile(delete=False, suffix='.pdf') as tmp_file:
            tmp_file.write(response.content)
            return tmp_file.name
    except Exception as e:
        print(f"[DOWNLOAD PDF] Error: {str(e)}")
        return None


def extract_text_from_pdf(pdf_path):
    """Extract text content from a PDF file."""
    if not PdfReader:
        return None
    
    try:
        reader = PdfReader(pdf_path)
        text_content = []
        
        for page in reader.pages:
            text = page.extract_text()
            if text:
                text_content.append(text)
        
        return '\n\n'.join(text_content)
    except Exception as e:
        print(f"[PDF EXTRACT] Error: {str(e)}")
        return None


def update_document_content(document_id, content):
    """Update the document_content column for a given document_id."""
    if not (psycopg2 and DATABASE_URL):
        return False
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute(
            "UPDATE documents SET document_content = %s, status = %s WHERE id = %s",
            (content, 'processed', document_id)
        )
        conn.commit()
        rows_updated = cur.rowcount
        cur.close()
        conn.close()
        
        return rows_updated > 0
    except Exception as e:
        print(f"[UPDATE CONTENT] Error: {str(e)}")
        try:
            conn.close()
        except:
            pass
        return False


def get_document_by_id(document_id):
    """Retrieve a document record by its ID."""
    if not (psycopg2 and DATABASE_URL):
        return None
    
    try:
        conn = psycopg2.connect(DATABASE_URL)
        cur = conn.cursor()
        
        cur.execute(
            "SELECT id, project_id, filename, file_path, source, status, document_content FROM documents WHERE id = %s",
            (document_id,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        
        if row:
            return {
                'id': row[0],
                'project_id': row[1],
                'filename': row[2],
                'file_path': row[3],
                'source': row[4],
                'status': row[5],
                'document_content': row[6]
            }
        return None
    except Exception as e:
        print(f"[GET DOCUMENT] Error: {str(e)}")
        try:
            conn.close()
        except:
            pass
        return None


@app.post("/process_document")
async def process_document(body: ProcessDocumentRequest):
    """Process a document by downloading its PDF from Supabase, extracting text, and updating the database."""
    if not PdfReader:
        raise HTTPException(status_code=500, detail="PyPDF2 not available. Install PyPDF2 for PDF text extraction.")
    
    # Get document record from database
    document = get_document_by_id(body.document_id)
    if not document:
        raise HTTPException(status_code=404, detail=f"Document with id {body.document_id} not found")
    
    file_path = document.get('file_path')
    if not file_path:
        raise HTTPException(status_code=400, detail="Document has no file_path")
    
    # Download PDF from Supabase
    print(f"[PROCESS] Downloading PDF from {file_path}")
    local_pdf_path = download_pdf_from_url(file_path)
    if not local_pdf_path:
        raise HTTPException(status_code=500, detail="Failed to download PDF from Supabase")
    
    try:
        # Extract text from PDF
        print(f"[PROCESS] Extracting text from PDF")
        extracted_text = extract_text_from_pdf(local_pdf_path)
        
        if not extracted_text:
            raise HTTPException(status_code=500, detail="Failed to extract text from PDF")
        
        # Update database with extracted content
        print(f"[PROCESS] Updating document_content in database")
        success = update_document_content(body.document_id, extracted_text)
        
        if not success:
            raise HTTPException(status_code=500, detail="Failed to update document_content in database")
        
        return JSONResponse({
            "document_id": body.document_id,
            "status": "processed",
            "content_length": len(extracted_text),
            "message": "Document processed successfully"
        })
    
    finally:
        # Clean up temporary file
        try:
            os.remove(local_pdf_path)
        except:
            pass


@app.post("/scrape")
async def scrape(body: ScrapeRequest):
    if webdriver is None:
        raise HTTPException(status_code=500, detail="Selenium not available. Install selenium and ensure ChromeDriver is available.")

    results = []

    # Setup Chrome options for headless browsing with WAF bypass
    chrome_options = Options()
    chrome_options.add_argument("--headless")
    chrome_options.add_argument("--no-sandbox")
    chrome_options.add_argument("--disable-dev-shm-usage")
    chrome_options.add_argument("--disable-gpu")
    chrome_options.add_argument("--disable-images")
    chrome_options.add_argument("--disable-blink-features=AutomationControlled")
    chrome_options.add_argument("--disable-extensions")
    chrome_options.add_argument("--window-size=1920,1080")
    
    # Add realistic user agent to bypass WAF detection
    chrome_options.add_argument("--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36")
    
    # Remove automation indicators
    chrome_options.add_experimental_option("excludeSwitches", ["enable-automation"])
    chrome_options.add_experimental_option('useAutomationExtension', False)
    
    # Remove --disable-javascript to allow dynamic content loading
    
    driver = None
    
    try:
        driver = webdriver.Chrome(options=chrome_options)
        driver.set_page_load_timeout(30)
        
        # Hide automation indicators
        driver.execute_script("Object.defineProperty(navigator, 'webdriver', {get: () => undefined})")
        
        for idx, url in enumerate(body.urls, start=1):
            # Create meaningful filename from URL
            parsed_url = urlparse(url)
            domain = parsed_url.netloc.replace('www.', '').replace('.', '_')
            path = parsed_url.path.replace('/', '_').replace('.', '_')
            
            # Create a short hash for uniqueness if path is empty or too long
            url_hash = hashlib.md5(url.encode()).hexdigest()[:8]
            
            if path and len(path) > 5:
                filename_base = f"{domain}{path}"[:50]  # Limit length
            else:
                filename_base = f"{domain}_{url_hash}"
            
            # Clean filename and add project prefix
            clean_filename = re.sub(r'[^a-zA-Z0-9_-]', '_', filename_base)
            pdf_name = f"{body.project_id}_{clean_filename}.pdf"
            pdf_path = pdf_name  # Just the filename, no local directory needed
            
            try:
                # Navigate to the page with retry mechanism
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        driver.get(url)
                        
                        # Add realistic delay and user behavior simulation
                        time.sleep(2)
                        
                        # Scroll to simulate user behavior
                        driver.execute_script("window.scrollTo(0, document.body.scrollHeight/2);")
                        time.sleep(1)
                        driver.execute_script("window.scrollTo(0, 0);")
                        time.sleep(1)
                        
                        # Check if we're blocked
                        page_title = driver.title.lower()
                        if 'blocked' in page_title or 'forbidden' in page_title:
                            if attempt < max_retries - 1:
                                print(f"[SCRAPE] Detected blocking on attempt {attempt + 1}, retrying...")
                                time.sleep(5)  # Wait before retry
                                continue
                        
                        break  # Success, exit retry loop
                        
                    except Exception as retry_error:
                        if attempt < max_retries - 1:
                            print(f"[SCRAPE] Attempt {attempt + 1} failed: {retry_error}, retrying...")
                            time.sleep(5)
                        else:
                            raise retry_error
                
                # Get page source after JavaScript execution
                html_content = driver.page_source
                
                # Extract clean text content
                clean_text = extract_clean_text(html_content, url)
                
                # Create PDF from extracted text
                created_file = create_pdf_from_text(clean_text, pdf_path, url, body.project_id)

                # If uploaded to Supabase (public URL returned), insert DB record
                document_id = None
                if SUPABASE_URL and created_file and isinstance(created_file, str) and created_file.startswith(SUPABASE_URL.rstrip('/')):
                    try:
                        document_id = insert_document_record(body.project_id, pdf_name, created_file, source='scrape', status='pending', document_content=None)
                    except Exception:
                        document_id = None

                results.append({
                    "url": url,
                    "pdf_file": created_file,
                    "method": "selenium",
                    "content_length": len(clean_text),
                    "document_id": document_id
                })
                
            except Exception as e:
                # Fallback to requests for static content
                try:
                    response = requests.get(url, timeout=30)
                    response.raise_for_status()
                    clean_text = extract_clean_text(response.text, url)
                    
                    # Create PDF from extracted text
                    created_file = create_pdf_from_text(clean_text, pdf_path, url, body.project_id)

                    document_id = None
                    if SUPABASE_URL and created_file and isinstance(created_file, str) and created_file.startswith(SUPABASE_URL.rstrip('/')):
                        try:
                            document_id = insert_document_record(body.project_id, pdf_name, created_file, source='scrape', status='pending', document_content=None)
                        except Exception:
                            document_id = None

                    results.append({
                        "url": url,
                        "pdf_file": created_file,
                        "method": "requests_fallback",
                        "content_length": len(clean_text),
                        "document_id": document_id
                    })
                except Exception as fallback_error:
                    # If both methods fail, create a simple error PDF
                    try:
                        error_content = f"Failed to scrape URL: {url} - Selenium Error: {str(e)} - Fallback Error: {str(fallback_error)}"
                        error_pdf = create_pdf_from_text(error_content, pdf_path, url, body.project_id)
                        results.append({"url": url, "pdf_file": error_pdf, "method": "error_pdf", "error": "Both methods failed, created error PDF"})
                    except:
                        results.append({"url": url, "error": f"Selenium failed: {str(e)}, Fallback failed: {str(fallback_error)}"})
    
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Driver initialization failed: {str(e)}")
    
    finally:
        if driver:
            driver.quit()
    
    return JSONResponse({"results": results})

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
