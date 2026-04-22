# NHIỆM VỤ: Trạm trung chuyển hàng đợi Dịch thuật. Hỗ trợ gom nhóm (batch), đảm bảo gửi dữ liệu đồng bộ và chia nhỏ lượng văn bản trước khi gửi đến API.

import asyncio
import LLMS_translation as lt

class Online_translation:
    def __init__(self, original_language, target_language, translation_type=None, texts_to_process=None):
        if texts_to_process is None:
            texts_to_process = []
            
        self.original_text = texts_to_process
        self.target_language = target_language
        self.original_lang = original_language
        

    def translation(self):
        """
        Hàm này đóng vai trò Trạm trung chuyển (Bridge):
        Nhận lệnh từ file main.py (chạy đồng bộ) và kích hoạt LangChain (chạy bất đồng bộ)
        """
        print(f"\n[Trạm Trung Chuyển] Bắt đầu điều phối {len(self.original_text)} khối văn bản...")
        
        if not self.original_text:
            return []

        # Khởi tạo LangChain
        translator = lt.OpenRouter_translation()
        
        # Dùng asyncio.run để chạy luồng bất đồng bộ một cách an toàn và dọn dẹp sạch sẽ sau khi xong
        translated_texts = asyncio.run(translator.translate(
            texts=self.original_text,
            original_lang=self.original_lang,
            target_lang=self.target_language
        ))
        
        return translated_texts


# =====================================================================
# CÁC HÀM XỬ LÝ CHIA NHỎ VĂN BẢN (CHUNK / TOKEN LIMIT) - GIỮ NGUYÊN BẢN GỐC
# =====================================================================

def split_text_to_fit_token_limit(text, encoder, index_text, max_length=280):
    tokens = encoder.encode(text)
    if len(tokens) <= max_length:
        return [(text, len(tokens), index_text)]

    split_points = [i for i, token in enumerate(tokens) if encoder.decode([token]).strip() in [' ', '.', '?', '!','！','？','。']]
    parts = []
    last_split = 0
    for i, point in enumerate(split_points + [len(tokens)]):
        if point - last_split > max_length:
            part_tokens = tokens[last_split:split_points[i - 1]]
            parts.append((encoder.decode(part_tokens), len(part_tokens), index_text))
            last_split = split_points[i - 1]
        elif i == len(split_points):
            part_tokens = tokens[last_split:]
            parts.append((encoder.decode(part_tokens), len(part_tokens), index_text))

    return parts

def process_texts(texts, encoder):
    processed_texts = []
    for i, text in enumerate(texts):
        sub_texts = split_text_to_fit_token_limit(text, encoder, i)
        processed_texts.extend(sub_texts)
    return processed_texts

def calculate_split_points(processed_texts, max_tokens=425):
    split_points = []
    current_tokens = 0

    for i in range(len(processed_texts) - 1):
        current_tokens = processed_texts[i][1]
        next_tokens = processed_texts[i + 1][1]

        if current_tokens + next_tokens > max_tokens:
            split_points.append(i)

    split_points.append(len(processed_texts) - 1)

    return split_points