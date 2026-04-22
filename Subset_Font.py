# NHIỆM VỤ: Tạo Subset Font. Quét các ký tự Unicode có trong phần dịch để tách riêng bộ font siêu nhẹ, giúp nhúng vào PDF không bị lỗi và giữ dung lượng file thấp.

import os
import datetime
from fontTools.subset import Subsetter, Options
from fontTools.ttLib import TTFont

def check_glyph_coverage(font, text):
    """
    Kiểm tra xem font chữ có hỗ trợ đầy đủ các ký tự trong văn bản không.
    Trả về danh sách các ký tự bị thiếu (ví dụ: các chữ cái có dấu ả, ế, ữ).
    """
    cmap = font.getBestCmap()
    missing_chars = []

    for char in text:
        if ord(char) not in cmap:
            missing_chars.append(char)

    return missing_chars

def subset_font(in_font_path, out_font_path, text, language="Vietnamese"):
    """
    Sử dụng fontTools để loại bỏ các ký tự không sử dụng.
    Chỉ giữ lại những ký tự có trong chuỗi `text` để giảm tối đa dung lượng PDF.
    """
    start_time = datetime.datetime.now()

    # 1. Kiểm tra tính hợp lệ của File Font Gốc
    if not os.path.exists(in_font_path):
        raise FileNotFoundError(
            f"\n[LỖI CHÍ MẠNG] Không tìm thấy file font gốc tại: {in_font_path}\n"
            f"Vui lòng tải một font chữ hỗ trợ Tiếng Việt (như Arial.ttf) "
            f"và đổi tên thành {os.path.basename(in_font_path)}, sau đó đặt vào thư mục temp/fonts/."
        )

    # 2. Đảm bảo thư mục đầu ra tồn tại
    output_dir = os.path.dirname(out_font_path)
    if output_dir:
        os.makedirs(output_dir, exist_ok=True)

    # 3. Lọc trùng lặp ký tự (Set) để tối ưu hóa việc phân tích
    # Biến "Xin chào" thành "Xinchào" -> giúp Subsetter chạy nhanh hơn
    unique_chars = "".join(sorted(set(text)))

    # 4. Đọc font gốc vào bộ nhớ
    font = TTFont(in_font_path)

    # 5. Cảnh báo nếu font không hỗ trợ tiếng Việt
    missing_chars = check_glyph_coverage(font, unique_chars)
    if missing_chars:
        print("\n[CẢNH BÁO] Font chữ hiện tại KHÔNG hỗ trợ các ký tự sau:")
        print("".join(missing_chars))
        print("=> Các ký tự này sẽ hiển thị thành ô vuông lỗi trên file PDF cuối cùng.\n")

        # Phải loại bỏ các ký tự này khỏi danh sách gọt, nếu không fontTools sẽ báo lỗi
        for char in missing_chars:
            unique_chars = unique_chars.replace(char, '')

    # 6. Thiết lập tham số gọt (Subset Options)
    options = Options()
    # Theo mặc định, fontTools đã loại bỏ rất nhiều bảng metadata không cần thiết.
    
    # 7. Kích hoạt bộ gọt
    subsetter = Subsetter(options=options)
    subsetter.populate(text=unique_chars)
    subsetter.subset(font)

    # 8. Lưu font mới đã được thu gọn
    font.save(out_font_path)
    
    elapsed_time = (datetime.datetime.now() - start_time).total_seconds()
    print(f"✅ Đã gọt font thành công: {os.path.basename(out_font_path)} (Tốn {elapsed_time:.2f} giây)")