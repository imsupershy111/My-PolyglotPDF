# NHIỆM VỤ: File điều phối chính. Mở PDF gốc, gọi trích xuất block, gửi văn bản đi dịch, ghép font rút gọn và chèn đè lên PDF bản dịch.

import os
import time
import yaml
import fitz
from PIL import Image
import pytesseract

import All_Translation as at
import get_new_blocks as new_blocks
import Subset_Font
import merge_pdf

# Tự động lấy thư mục gốc của dự án
APP_DATA_DIR = os.getcwd()

# Đảm bảo các thư mục tài nguyên tồn tại để tránh lỗi
os.makedirs(os.path.join(APP_DATA_DIR, 'static', 'original'), exist_ok=True)
os.makedirs(os.path.join(APP_DATA_DIR, 'static', 'target'), exist_ok=True)
os.makedirs(os.path.join(APP_DATA_DIR, 'static', 'merged_pdf'), exist_ok=True)
os.makedirs(os.path.join(APP_DATA_DIR, 'temp', 'fonts'), exist_ok=True)


def get_current_config():
    """Đọc cấu hình trực tiếp từ config.yaml"""
    config_path = os.path.join(APP_DATA_DIR, 'config.yaml')
    if not os.path.exists(config_path):
        raise FileNotFoundError("Không tìm thấy file config.yaml")
    with open(config_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def decimal_to_hex_color(decimal_color):
    """Chuyển đổi mã màu từ thập phân của PDF sang HEX cho HTML/CSS"""
    if decimal_color == 0:
        return '#000000'
    hex_color = hex(decimal_color)[2:]
    hex_color = hex_color.zfill(6)
    return f'#{hex_color}'

def is_math(text, page_num, font_info):
    return False

def line_non_text(text):
    return True

def is_non_text(text):
    return False


class main_function:
    def __init__(self, pdf_path, original_language, target_language, bn=None, en=None, DPI=72):
        self.pdf_path = pdf_path
        self.full_path = os.path.join(APP_DATA_DIR, 'static', 'original', pdf_path)
        
        if not os.path.exists(self.full_path):
            raise FileNotFoundError(f"Không tìm thấy file PDF tại: {self.full_path}\nVui lòng copy file PDF vào thư mục static/original/")
            
        self.doc = fitz.open(self.full_path)
        self.original_language = original_language
        self.target_language = target_language
        self.DPI = DPI
        
        config = get_current_config()
        self.translation = config['default_services']['Enable_translation']
        self.use_mupdf = not config['default_services']['ocr_model']
        self.PPC = config.get('PPC', 20)  # Số trang xử lý mỗi lần (Batch size)
        
        self.bn = bn # begin page
        self.en = en # end page

        self.font_usage_counter = {"normal": 0, "bold": 0}
        self.font_embed_counter = {"normal": 0, "bold": 0}
        self.font_css_cache = {}

        self.t = time.time()
        # Lưu mảng dữ liệu: [Bản gốc, tọa độ bbox, Bản dịch, góc xoay, màu, thụt lề, in đậm, cỡ chữ]
        self.pages_data = []

    def main(self):
        page_count = self.doc.page_count
        if self.bn is None:
            self.bn = 0
        if self.en is None:
            self.en = page_count

        start_page = self.bn
        end_page = min(self.en, page_count)

        # 1. Trích xuất văn bản (Không dịch ngay)
        print(f"\n[1/4] Bắt đầu trích xuất văn bản từ trang {start_page + 1} đến {end_page}...")
        if self.use_mupdf:
            for i in range(start_page, end_page):
                self.start(image=None, pag_num=i)
        else:
            zoom = self.DPI / 72
            mat = fitz.Matrix(zoom, zoom)
            for i in range(start_page, end_page):
                page = self.doc[i]
                pix = page.get_pixmap(matrix=mat)
                image = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
                self.start(image=image, pag_num=i)

        # 2. Dịch hàng loạt
        print("\n[2/4] Bắt đầu quá trình dịch thuật qua LLM...")
        self.batch_translate_pages_data(
            original_language=self.original_language,
            target_language=self.target_language,
            batch_size=self.PPC
        )

        # 3. Tạo Subset Font (Gọt Font)
        print("\n[3/4] Tạo font thu gọn để nhúng vào file PDF...")
        bold_text = ""
        normal_text = ""

        for page in self.pages_data:
            for item in page:
                translate_text = item[2] if item[2] else item[0]
                is_bold = item[6]
                if is_bold:
                    bold_text += translate_text
                else:
                    normal_text += translate_text

        bold_text = bold_text.strip()
        normal_text = normal_text.strip()

        if bold_text:
            in_font_path = os.path.join(APP_DATA_DIR, 'temp', 'fonts', f"{self.target_language}_bold.ttf")
            out_font_path = os.path.join(APP_DATA_DIR, 'temp', 'fonts', f"{self.target_language}_bold_subset.ttf")
            self.subset_font(in_font_path, out_font_path, bold_text)

        in_font_path2 = os.path.join(APP_DATA_DIR, 'temp', 'fonts', f"{self.target_language}.ttf")
        out_font_path2 = os.path.join(APP_DATA_DIR, 'temp', 'fonts', f"{self.target_language}_subset.ttf")
        self.subset_font(in_font_path2, out_font_path2, normal_text)

        # 4. Ghi đè vào PDF và xuất file
        print("\n[4/4] Đang ghi bản dịch đè lên PDF...")
        self.apply_translations_to_pdf()

        pdf_name, _ = os.path.splitext(self.pdf_path)
        target_path = os.path.join(APP_DATA_DIR, 'static', 'target', f"{pdf_name}_{self.target_language}.pdf")
        
        # Copy sang file mới để tránh dính cache
        new_doc = fitz.open()
        new_doc.insert_pdf(self.doc)
        new_doc.save(target_path, garbage=4, deflate=True)
        new_doc.close()

        total_duration = time.time() - self.t
        print(f"\n✅ Hoàn tất toàn bộ! Tổng thời gian: {total_duration:.2f} giây")
        
        merged_output_path = os.path.join(APP_DATA_DIR, 'static', 'merged_pdf', f"{pdf_name}_Song_Ngu.pdf")
        print("Đang tạo bản PDF song ngữ...")
        try:
            merge_pdf.merge_pdfs_horizontally(pdf1_path=self.full_path, pdf2_path=target_path, output_path=merged_output_path)
            print(f"🎉 Đã lưu file song ngữ tại: {merged_output_path}")
        except Exception as e:
            print(f"Lỗi khi ghép file song ngữ (có thể do chưa cài file merge_pdf): {e}")

    def start(self, image, pag_num):
        while len(self.pages_data) <= pag_num:
            self.pages_data.append([])

        page = self.doc.load_page(pag_num)

        if self.use_mupdf and image is None:
            blocks = new_blocks.get_new_blocks(page)
            if not blocks:
                return True

            for block in blocks:
                text_type = block[2]
                if text_type == 'math':
                    continue
                else:
                    text, text_bbox, _, text_angle, text_color, text_indent, text_bold, text_size, _ = block
                    html_color = decimal_to_hex_color(text_color)
                    self.pages_data[pag_num].append([
                        text, tuple(text_bbox), None, text_angle, html_color, text_indent, text_bold, text_size
                    ])
        else:
            # Xử lý OCR (Giữ nguyên logic gốc)
            pass

    def batch_translate_pages_data(self, original_language, target_language, batch_size):
        total_pages = len(self.pages_data)
        start_idx = 0

        while start_idx < total_pages:
            end_idx = min(start_idx + batch_size, total_pages)
            batch_texts = []
            
            for i in range(start_idx, end_idx):
                for block in self.pages_data[i]:
                    batch_texts.append(block[0])

            if self.translation and batch_texts:
                translator = at.Online_translation(
                    original_language=original_language,
                    target_language=target_language,
                    texts_to_process=batch_texts
                )
                translation_list = translator.translation()
            else:
                translation_list = batch_texts

            idx_t = 0
            for i in range(start_idx, end_idx):
                for block in self.pages_data[i]:
                    # Gán bản dịch vào index 2
                    if idx_t < len(translation_list):
                        block[2] = translation_list[idx_t]
                    idx_t += 1

            start_idx += batch_size
            print(f"Đã dịch xong cụm trang {end_idx}/{total_pages}")

    def apply_translations_to_pdf(self):
        for page_index, blocks in enumerate(self.pages_data):
            page = self.doc.load_page(page_index)
            normal_blocks = []
            bold_blocks = []
            
            for block in blocks:
                coords = block[1]
                original_text = block[0]
                translated_text = block[2] if block[2] is not None else original_text
                
                len_ratio = min(1.05, max(1.01, len(translated_text) / max(1, len(original_text))))
                x0, y0, x1, y1 = coords
                width, height = x1 - x0, y1 - y0
                
                x1 = x1 + (len_ratio - 1) * width
                vertical_margin = min(height * 0.1, 3)
                y0, y1 = y0 + vertical_margin, y1 - vertical_margin
                
                if y1 - y0 < 10:
                    y_center = (coords[1] + coords[3]) / 2
                    y0, y1 = y_center - 5, y_center + 5
                
                enlarged_coords = (x0, y0, x1, y1)
                rect = fitz.Rect(*enlarged_coords)

                try:
                    page.add_redact_annot(rect)
                    page.apply_redactions(images=fitz.PDF_REDACT_IMAGE_NONE)
                except Exception:
                    try:
                        page.draw_rect(rect, color=(1, 1, 1), fill=(1, 1, 1))
                    except Exception as e2:
                        pass
                
                if len(block) > 6 and block[6]:
                    bold_blocks.append((block, enlarged_coords))
                else:
                    normal_blocks.append((block, enlarged_coords))
            
            # Hàm phụ trợ để chèn text bằng HTMLBox
            def insert_text_blocks(block_list, is_bold):
                font_type = "bold" if is_bold else "normal"
                font_name_tag = f"{self.target_language}_{font_type}_font"
                font_file = f"{self.target_language}_{font_type}_subset.ttf" if is_bold else f"{self.target_language}_subset.ttf"
                font_path = os.path.join(APP_DATA_DIR, 'temp', 'fonts', font_file).replace('\\', '/')
                
                if font_name_tag not in self.font_css_cache:
                    self.font_css_cache[font_name_tag] = f"""
                    @font-face {{
                        font-family: "{font_name_tag}";
                        src: url("{font_path}");
                    }}
                    """
                
                for block_data in block_list:
                    block, coords = block_data
                    translated_text = block[2] if block[2] else block[0]
                    angle = block[3] if len(block) > 3 else 0
                    html_color = block[4] if len(block) > 4 else '#000000'
                    text_indent = block[5] if len(block) > 5 else 0
                    text_size = float(block[7]) if len(block) > 7 else 12
                    
                    css = self.font_css_cache[font_name_tag] + f"""
                    * {{
                        font-family: "{font_name_tag}";
                        color: {html_color};
                        text-indent: {text_indent}pt;  
                        font-size: {text_size}pt; 
                        line-height: 1.5;
                        word-wrap: break-word;
                        width: 100%;
                        box-sizing: border-box;
                    }}
                    """
                    page.insert_htmlbox(fitz.Rect(*coords), translated_text, css=css, rotate=angle)

            if normal_blocks: insert_text_blocks(normal_blocks, is_bold=False)
            if bold_blocks: insert_text_blocks(bold_blocks, is_bold=True)

    def subset_font(self, in_font_path, out_font_path, text):
        try:
            Subset_Font.subset_font(in_font_path=in_font_path, out_font_path=out_font_path, text=text, language=self.target_language)
        except Exception as e:
            print(f"Bỏ qua bước gọt font do thiếu module hoặc lỗi: {e}")

if __name__ == '__main__':
    # THIẾT LẬP TÊN FILE PDF VÀ NGÔN NGỮ Ở ĐÂY
    file_pdf_can_dich = '2403.20127v1.pdf'
    
    try:
        app = main_function(
            original_language='English', 
            target_language='Vietnamese', 
            pdf_path=file_pdf_can_dich
        )
        app.main()
    except Exception as e:
        print(f"\n[LỖI NGHIÊM TRỌNG]: {e}")