from pypdf import PdfReader
import sys

try:
    reader = PdfReader("Final Assignment.pdf")
    text = ""
    for page in reader.pages:
        text += page.extract_text() + "\n"
    with open("requirements_parsed.txt", "w", encoding="utf-8") as f:
        f.write(text)
    print("Done writing to requirements_parsed.txt")
except Exception as e:
    print(f"Error reading PDF: {e}")
