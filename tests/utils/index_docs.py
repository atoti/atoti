from langchain_community.document_loaders import RecursiveUrlLoader
from langchain_chroma import Chroma
from langchain_ollama import OllamaEmbeddings
from langchain.text_splitter import RecursiveCharacterTextSplitter
from bs4 import BeautifulSoup
import os
import shutil
import ollama
import re

loader = RecursiveUrlLoader(
    "https://docs.activeviam.com/products/atoti/python-sdk/0.9.next/",  # Start from API index
    max_depth=4,  # Increase depth to ensure it crawls
    prevent_outside=True,  # Allow crawling outside to capture all API links
    use_async=False,
    timeout=60,  # Increase timeout
    check_response_status=True,
    continue_on_failure=True,
    link_regex=r'<a\s+(?:[^>]*?\s+)?href="([^"]*(?=.html)[^"]*)"',
    # base_url="https://docs.activeviam.com/products/atoti/python-sdk/0.9.7/",
    # ...
)

print("Loading documents...")
documents = loader.load()

print(f"\nFound {len(documents)} documents:")
print("=" * 50)

# Clean HTML content from documents
print("\n🧹 Cleaning HTML content...")
cleaned_documents = []
for doc in documents:
    # Skip CSS, JS, and other non-documentation files
    url = doc.metadata.get("source", "")
    if any(ext in url for ext in [".css", ".js", ".png", ".jpg", ".ico", ".gif"]):
        continue

    # Parse HTML and extract clean text
    soup = BeautifulSoup(doc.page_content, "html.parser")

    # Remove script, style, nav, footer, header elements
    for element in soup(
        ["script", "style", "nav", "footer", "header", "aside", "noscript"]
    ):
        element.decompose()

    # Remove elements with common navigation/UI classes
    for element in soup.find_all(
        attrs={"class": ["navbar", "sidebar", "breadcrumb", "toc"]}
    ):
        element.decompose()

    # Focus on main content areas
    main_content = (
        soup.find("main")
        or soup.find("article")
        or soup.find(attrs={"class": ["content", "main"]})
    )
    if main_content:
        text = main_content.get_text()
    else:
        text = soup.get_text()

    # Clean up whitespace and normalize
    text = re.sub(r"\s+", " ", text).strip()

    # More selective filtering for quality content
    if (
        len(text) > 500  # Substantial content
        and (
            "atoti" in text.lower()
            or "session" in text.lower()
            or "api" in text.lower()
        )
        and not url.endswith("genindex.html")  # Skip index pages
        and "tutorial" in url.lower()
        or "guide" in url.lower()
        or "api" in url.lower()
        or "changelog" in url.lower()
    ):
        doc.page_content = text
        cleaned_documents.append(doc)

documents = cleaned_documents
print(f"Cleaned to {len(documents)} quality documents")

# Extract and display all URLs with content sizes
urls = set()
url_content_sizes = {}
for doc in documents:
    url = doc.metadata.get("source", "Unknown URL")
    content_size = len(doc.page_content)
    urls.add(url)
    url_content_sizes[url] = content_size

# Sort URLs alphabetically and print with content sizes
sorted_urls = sorted(urls)
for i, url in enumerate(sorted_urls, 1):
    content_size = url_content_sizes[url]
    print(f"{i:2d}. {url}")
    print(f"     Content size: {content_size:,} characters")

print(f"\nTotal unique URLs found: {len(urls)}")

# Initialize text splitter for chunking documents with better parameters
text_splitter = RecursiveCharacterTextSplitter(
    chunk_size=1500,  # Increased from 1000 for better context
    chunk_overlap=300,  # Increased from 200 for better continuity
    length_function=len,
    separators=["\n\n", "\n", ". ", " ", ""],  # Better separators for clean breaks
)

# Split documents into chunks
print("\nSplitting documents into chunks...")
split_docs = text_splitter.split_documents(documents)
print(f"Created {len(split_docs)} chunks from {len(documents)} documents")

# Initialize embeddings using Ollama (no API key required)
# Make sure you have Ollama installed and pull the model first:
# ollama pull nomic-embed-text
print("Attempting to use Ollama embeddings...")
try:
    embeddings = OllamaEmbeddings(model="nomic-embed-text")
    print("Using Ollama embeddings with nomic-embed-text model")

except Exception as e:
    print(f"Ollama embeddings failed ({e})")

# Create Chroma vector database
print("\nCreating Chroma vector database...")
persist_directory = "./atoti_docs_vectordb"

# Remove existing database if it exists
if os.path.exists(persist_directory):
    shutil.rmtree(persist_directory)
    print(f"Removed existing database at {persist_directory}")

# Create new vector database
vectordb = Chroma.from_documents(
    documents=split_docs, embedding=embeddings, persist_directory=persist_directory
)

print(f"Successfully created vector database with {len(split_docs)} chunks")
print(f"Database persisted to: {persist_directory}")
