"""Install pinned English/Tamil Tesseract data locally; does not install Tesseract itself."""
from pathlib import Path
from urllib.request import urlopen
import hashlib

ROOT = Path(__file__).resolve().parents[1]
DATA = ROOT / ".localdev/tessdata"
FILES = {"eng": "7d4322bd2a7749724879683fc3912cb542f19906c83bcc1a52132556427170b2", "tam": "d02fbec24be4b07e32e80d0ccfc3b6b67a3c5d61c9d0a7c8532677990912c6ec"}

if __name__ == "__main__":
    DATA.mkdir(parents=True, exist_ok=True)
    for language, expected in FILES.items():
        path = DATA / (language + ".traineddata")
        if path.exists() and hashlib.sha256(path.read_bytes()).hexdigest() == expected:
            print(language + ": already verified")
            continue
        with urlopen("https://raw.githubusercontent.com/tesseract-ocr/tessdata_fast/main/" + path.name, timeout=60) as response:
            data = response.read()
        if hashlib.sha256(data).hexdigest() != expected:
            raise RuntimeError("OCR data checksum changed; review upstream before updating.")
        path.write_bytes(data)
        print(language + ": downloaded and verified")
