# NHIỆM VỤ: Tiện ích xuất file PDF song ngữ. Chịu trách nhiệm gộp trang của PDF gốc và PDF bản dịch nằm cạnh nhau theo chiều ngang.

import fitz
import os

def merge_pdfs_horizontally(pdf1_path, pdf2_path, output_path, spacing=0):
    """
    Gộp hai file PDF theo chiều ngang (trái - phải) thành một file duy nhất.
    
    :param pdf1_path: Đường dẫn tới file PDF gốc (hiển thị bên trái).
    :param pdf2_path: Đường dẫn tới file PDF bản dịch (hiển thị bên phải).
    :param output_path: Đường dẫn lưu file PDF sau khi gộp.
    :param spacing: Khoảng cách (pixel/point) giữa 2 trang (mặc định = 0).
    """
    # 1. Kiểm tra sự tồn tại của file đầu vào
    if not os.path.exists(pdf1_path):
        raise FileNotFoundError(f"Không tìm thấy file PDF gốc: {pdf1_path}")
    if not os.path.exists(pdf2_path):
        raise FileNotFoundError(f"Không tìm thấy file PDF bản dịch: {pdf2_path}")

    # 2. Mở 2 tài liệu PDF
    doc1 = fitz.open(pdf1_path)
    doc2 = fitz.open(pdf2_path)

    # 3. Khởi tạo tài liệu PDF mới để chứa kết quả gộp
    result_doc = fitz.open()

    # 4. Kiểm tra tính hợp lệ của số trang
    if doc1.page_count == 0 or doc2.page_count == 0:
        raise ValueError("Cả hai file PDF phải có ít nhất 1 trang.")

    if doc1.page_count != doc2.page_count:
        raise ValueError(f"Số trang không khớp: File gốc có {doc1.page_count} trang, file dịch có {doc2.page_count} trang.")

    # 5. Xử lý gộp từng trang
    for page_num in range(doc1.page_count):
        page1 = doc1[page_num]
        page2 = doc2[page_num]

        # Lấy kích thước (Bounding Box) của từng trang
        rect1 = page1.rect
        rect2 = page2.rect

        # Tính toán kích thước cho canvas mới (Rộng = Rộng 1 + Rộng 2 + Khoảng cách)
        new_width = rect1.width + rect2.width + spacing
        new_height = max(rect1.height, rect2.height)

        # Tạo trang mới với kích thước vừa tính
        new_page = result_doc.new_page(width=new_width, height=new_height)

        # Trục ma trận cho trang 1 (Giữ nguyên vị trí x=0, y=0)
        matrix1 = fitz.Matrix(1, 1)

        # Trục ma trận cho trang 2 (Dịch chuyển sang phải một đoạn = Rộng 1 + Khoảng cách)
        matrix2 = fitz.Matrix(1, 1)
        x_shift = rect1.width + spacing
        matrix2.pretranslate(x_shift, 0)

        # Vẽ (Render) nội dung của 2 trang cũ lên trang mới
        new_page.show_pdf_page(rect1, doc1, page_num, matrix1)
        
        # Xác định vùng giới hạn vẽ cho trang 2
        target_rect2 = fitz.Rect(x_shift, 0, x_shift + rect2.width, new_height)
        new_page.show_pdf_page(target_rect2, doc2, page_num, matrix2)

    # 6. Đảm bảo thư mục đầu ra tồn tại trước khi lưu
    output_dir = os.path.dirname(output_path)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir, exist_ok=True)

    # 7. Lưu file kết quả với tùy chọn nén (deflate=True) để giảm dung lượng
    result_doc.save(output_path, garbage=4, deflate=True)

    # 8. Giải phóng bộ nhớ
    doc1.close()
    doc2.close()
    result_doc.close()

# Dành cho việc test riêng lẻ module này
if __name__ == "__main__":
    # Giả lập đường dẫn dựa theo kiến trúc của PolyglotPDF
    pdf1_path = r"./static/original/sample.pdf"
    pdf2_path = r"./static/target/sample_Vietnamese.pdf"
    output_path = r"./static/merged_pdf/sample_Song_Ngu.pdf"

    try:
        print("Đang tiến hành gộp PDF...")
        merge_pdfs_horizontally(pdf1_path, pdf2_path, output_path)
        print(f"✅ Gộp PDF thành công! File được lưu tại: {output_path}")
    except Exception as e:
        print(f"Lỗi trong quá trình gộp: {str(e)}")