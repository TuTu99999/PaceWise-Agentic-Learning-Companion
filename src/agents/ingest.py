"""
Script nạp học liệu mẫu (Course Materials) vào Qdrant Vector Store ngay trong module agents.
Chạy trực tiếp:
    python src/agents/ingest.py
"""

import sys
from pathlib import Path

if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8")
    except Exception:
        pass

# Đảm bảo import được module từ thư mục gốc
ROOT_DIR = Path(__file__).resolve().parent.parent.parent
if str(ROOT_DIR) not in sys.path:
    sys.path.insert(0, str(ROOT_DIR))

from src.agents.tools.qdrant_retriever import (  # noqa: E402
    DEFAULT_DOCS_DIR,
    DEFAULT_QDRANT_PATH,
    ingest_sample_documents,
)


def main():
    print("=" * 60)
    print("NẠP HỌC LIỆU MẪU VÀO QDRANT VECTOR STORE (LOCAL AGENTS DATA)")
    print("=" * 60)
    print(f"[*] Thư mục tài liệu: {DEFAULT_DOCS_DIR}")
    print(f"[*] Thư mục Qdrant: {DEFAULT_QDRANT_PATH}")

    try:
        result = ingest_sample_documents(
            docs_dir=DEFAULT_DOCS_DIR,
            storage_path=DEFAULT_QDRANT_PATH,
            force_recreate=True,
        )
        print(f"[+] Trạng thái: {result.get('status')}")
        print(f"[+] Bộ sưu tập: {result.get('collection_name')}")
        print(f"[+] Tổng số đoạn văn bản đã lập chỉ mục: {result.get('total_chunks')}")
        print(f"[+] Danh sách files đã xử lý: {', '.join(result.get('files_processed', []))}")
        print("=" * 60)
        print("[V] HOÀN TẤT NẠP HỌC LIỆU VÀO SRC/AGENTS/DATA THÀNH CÔNG!")
        print("=" * 60)
    except Exception as e:
        print(f"[!] Lỗi trong quá trình nạp tài liệu: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
