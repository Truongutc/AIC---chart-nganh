"""
Client Google Drive tối giản cho pipeline tài chính ngành — chỉ quản lý file
trong ĐÚNG 1 folder cố định (không cần cây thư mục Ngành/Mã như dự án
Phan-tich-FA). Cơ chế xác thực (Service Account qua biến môi trường
GDRIVE_SERVICE_ACCOUNT_JSON, fallback file credentials.json cục bộ) sao chép
đúng từ D:\\Github\\Phan-tich-FA\\google_drive_uploader.py để dùng lại được
CHÍNH Service Account đã cấu hình cho dự án đó.
"""

import os
import json
import io

try:
    from google.oauth2 import service_account
    from googleapiclient.discovery import build
    from googleapiclient.http import MediaFileUpload, MediaIoBaseDownload
    _GOOGLE_LIBS_AVAILABLE = True
except ImportError:
    _GOOGLE_LIBS_AVAILABLE = False

# Folder Drive đích cho toàn bộ dữ liệu tài chính ngành (VCSH/LNST + CSV nạp ban đầu)
FOLDER_ID = "1R40I_9zlQIEoOUMOe7AdRr3vYUnQc4xw"

SCOPES = ["https://www.googleapis.com/auth/drive.file", "https://www.googleapis.com/auth/drive"]


def get_drive_service():
    """Khởi tạo Google Drive API service từ Service Account. Trả về None (không
    bao giờ raise) nếu thiếu thư viện hoặc thiếu credential — mọi hàm gọi
    service này phải tự chấp nhận None và bỏ qua thao tác Drive một cách êm."""
    if not _GOOGLE_LIBS_AVAILABLE:
        print("[GDrive] Thiếu thư viện google-api-python-client/google-auth — bỏ qua Drive.")
        return None

    creds_json = os.environ.get("GDRIVE_SERVICE_ACCOUNT_JSON")
    if creds_json:
        try:
            info = json.loads(creds_json)
            if isinstance(info, dict) and "client_email" in info:
                print(f"[GDrive] Xác thực bằng Service Account: {info['client_email']}")
            creds = service_account.Credentials.from_service_account_info(info, scopes=SCOPES)
            return build("drive", "v3", credentials=creds)
        except Exception as e:
            print(f"[GDrive] Lỗi parse GDRIVE_SERVICE_ACCOUNT_JSON: {e}")

    local_creds_path = os.path.join(os.path.dirname(__file__), "..", "credentials.json")
    if os.path.exists(local_creds_path):
        try:
            with open(local_creds_path, "r", encoding="utf-8") as f:
                info = json.load(f)
            if isinstance(info, dict) and "client_email" in info:
                print(f"[GDrive] Xác thực bằng credentials.json cục bộ: {info['client_email']}")
            creds = service_account.Credentials.from_service_account_file(local_creds_path, scopes=SCOPES)
            return build("drive", "v3", credentials=creds)
        except Exception as e:
            print(f"[GDrive] Lỗi đọc credentials.json cục bộ: {e}")

    print("[GDrive] Không có credential hợp lệ — bỏ qua thao tác Drive.")
    return None


def _mime_type_for(file_name):
    if file_name.endswith(".xlsx"):
        return "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
    if file_name.endswith(".csv"):
        return "text/csv"
    if file_name.endswith(".json"):
        return "application/json"
    return "application/octet-stream"


def upload_file(file_path, folder_id=FOLDER_ID):
    """Tải file lên đúng 1 folder cố định — nếu đã có file trùng tên trong
    folder thì UPDATE (ghi đè) thay vì tạo bản mới, giống đúng quy ước của
    Phan-tich-FA/google_drive_uploader.py. Trả về (file_id, webViewLink) hoặc
    (None, None) nếu không có service/lỗi (không bao giờ raise ra ngoài)."""
    if not os.path.exists(file_path):
        print(f"[GDrive] Không tìm thấy file: {file_path}")
        return None, None

    service = get_drive_service()
    if not service:
        return None, None

    file_name = os.path.basename(file_path)
    mime_type = _mime_type_for(file_name)
    media = MediaFileUpload(file_path, mimetype=mime_type, resumable=True)

    try:
        query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])

        if files:
            existing_file_id = files[0]["id"]
            print(f"[GDrive] Cập nhật file đã có (ID: {existing_file_id})...")
            file = service.files().update(fileId=existing_file_id, media_body=media, fields="id, webViewLink").execute()
        else:
            file_metadata = {"name": file_name, "parents": [folder_id]}
            print(f"[GDrive] Tạo file mới trong folder {folder_id}...")
            file = service.files().create(body=file_metadata, media_body=media, fields="id, webViewLink").execute()

        try:
            service.permissions().create(fileId=file.get("id"), body={"type": "anyone", "role": "reader"}).execute()
        except Exception as perm_err:
            print(f"[GDrive] Không đặt được quyền công khai (bỏ qua): {perm_err}")

        print(f"[GDrive] Tải lên thành công: {file_name} -> {file.get('webViewLink')}")
        return file.get("id"), file.get("webViewLink")
    except Exception as e:
        print(f"[GDrive] Tải lên thất bại {file_name}: {e}")
        return None, None


def download_file_by_name(file_name, folder_id=FOLDER_ID):
    """Tải nội dung (bytes) của file theo TÊN trong 1 folder cố định. Trả về
    None nếu không có service, không tìm thấy file, hoặc lỗi bất kỳ."""
    service = get_drive_service()
    if not service:
        return None
    try:
        query = f"name = '{file_name}' and '{folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, fields="files(id)").execute()
        files = results.get("files", [])
        if not files:
            print(f"[GDrive] Không tìm thấy file '{file_name}' trong folder {folder_id}.")
            return None

        file_id = files[0]["id"]
        request = service.files().get_media(fileId=file_id)
        buf = io.BytesIO()
        downloader = MediaIoBaseDownload(buf, request)
        done = False
        while not done:
            _, done = downloader.next_chunk()
        return buf.getvalue()
    except Exception as e:
        print(f"[GDrive] Lỗi tải file '{file_name}': {e}")
        return None


def list_files_in_folder(folder_id=FOLDER_ID):
    """Liệt kê {id, name, createdTime} của mọi file trong folder — dùng cho
    Import Finance để tìm CSV người dùng vừa đặt lên Drive (chọn file *.csv có
    createdTime mới nhất nếu có nhiều file)."""
    service = get_drive_service()
    if not service:
        return []
    try:
        query = f"'{folder_id}' in parents and trashed = false"
        results = service.files().list(q=query, fields="files(id, name, createdTime)").execute()
        return results.get("files", [])
    except Exception as e:
        print(f"[GDrive] Lỗi liệt kê folder {folder_id}: {e}")
        return []
