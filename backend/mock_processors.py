import os
import tempfile
import time 
from fastapi import Depends, FastAPI, UploadFile
from models.users import User
from parsers.audio import process_audio
from parsers.common import file_already_exists
from parsers.csv import process_csv
from parsers.docx import process_docx
from parsers.epub import process_epub
from parsers.html import process_html
from parsers.markdown import process_markdown
from parsers.notebook import process_ipnyb
from parsers.odt import process_odt
from parsers.pdf import process_pdf
from parsers.powerpoint import process_powerpoint
from parsers.txt import process_txt
from supabase import Client
from langchain.document_loaders import UnstructuredMarkdownLoader, TextLoader, PyPDFLoader, UnstructuredHTMLLoader, UnstructuredPowerPointLoader, Docx2txtLoader, UnstructuredODTLoader, UnstructuredEPubLoader, NotebookLoader
from langchain.document_loaders.csv_loader import CSVLoader
from langchain.text_splitter import RecursiveCharacterTextSplitter
from langchain.schema import Document
from utils.file import compute_sha1_from_file

file_analyzers = {
    ".txt": TextLoader,
    ".csv": CSVLoader,
    ".md": UnstructuredMarkdownLoader,
    ".mdx": UnstructuredMarkdownLoader,
    ".markdown": UnstructuredMarkdownLoader,
    ".pdf": PyPDFLoader,
    ".html": UnstructuredHTMLLoader,
    ".pptx": UnstructuredPowerPointLoader,
    ".docx": Docx2txtLoader,
    ".odt": UnstructuredODTLoader,
    ".epub": UnstructuredEPubLoader,
    ".ipynb": NotebookLoader,
}


async def analyze_file(file: UploadFile, loader_class):
    documents = []
    file_name = file.filename
    file_size = file.file._file.tell()  # Getting the size of the file
    dateshort = time.strftime("%Y%m%d")

    # Here, we're writing the uploaded file to a temporary file, so we can use it with your existing code.
    with tempfile.NamedTemporaryFile(delete=False, suffix=file.filename) as tmp_file:
        await file.seek(0)
        content = await file.read()
        tmp_file.write(content)
        tmp_file.flush()

        loader = loader_class(tmp_file.name)
        documents = loader.load()
        # Ensure this function works with FastAPI
        file_sha1 = compute_sha1_from_file(tmp_file.name)

    os.remove(tmp_file.name)
    chunk_size = 500
    chunk_overlap = 0

    text_splitter = RecursiveCharacterTextSplitter.from_tiktoken_encoder(
        chunk_size=chunk_size, chunk_overlap=chunk_overlap)

    documents = text_splitter.split_documents(documents)

    metadata = {
        "file_sha1": file_sha1,
        "file_size": file_size,
        "file_name": file_name,
        "chunk_size": chunk_size,
        "chunk_overlap": chunk_overlap,
        "date": dateshort,
    }
    doc_with_metadata = {'metadata': metadata, 'documents': documents}
    return doc_with_metadata


async def mock_filter_file(file: UploadFile):
    file_extension = os.path.splitext(file.filename)[-1].lower()  # Convert file extension to lowercase
    if file_extension in file_analyzers:
        return await analyze_file(file, file_analyzers[file_extension])
    else:
        return {"message": f"❌ {file.filename} is not supported.", "type": "error"}

