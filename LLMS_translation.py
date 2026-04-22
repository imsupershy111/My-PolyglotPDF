import asyncio
import yaml
import os
from dotenv import load_dotenv

from langchain_openai import ChatOpenAI
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

# Tự động nạp biến môi trường từ file .env
load_dotenv()

class OpenRouter_translation:
    def __init__(self):
        # 1. Đọc cấu hình từ config.yaml
        if not os.path.exists('config.yaml'):
            raise FileNotFoundError("Không tìm thấy file config.yaml!")
            
        with open('config.yaml', 'r', encoding='utf-8') as f:
            config = yaml.safe_load(f)
            
        router_cfg = config['translation_services']['OpenRouter']
        
        # 2. Lấy API Key từ .env
        self.api_key = os.getenv("OPENROUTER_API_KEY")
        if not self.api_key:
            raise ValueError("LỖI: Chưa cấu hình OPENROUTER_API_KEY trong file .env!")

        base_url = router_cfg['api_url']
        self.model_name = router_cfg['model_name']
        
        # 3. Khởi tạo mô hình LLM qua LangChain
        self.llm = ChatOpenAI(
            openai_api_key=self.api_key,
            openai_api_base=base_url,
            model_name=self.model_name,
            temperature=0.3,
            max_retries=2, # Tự động gọi lại nếu mạng rớt
        )
        
        # 4. Thiết lập Prompt Template
        system_prompt = config.get('translation_prompt', {}).get('system_prompt', 
            'You are a professional translator. Translate from {original_lang} to {target_lang}. Return only the translation without explanations or notes.')
        
        self.prompt = ChatPromptTemplate.from_messages([
            ("system", system_prompt),
            ("user", "{text}")
        ])
        
        # 5. Xây dựng Pipeline (Chain)
        # Flow: Đưa Text vào Prompt -> Nạp vào LLM -> Bóc tách lấy mỗi String kết quả
        self.chain = self.prompt | self.llm | StrOutputParser()

    async def translate(self, texts, original_lang, target_lang):
        """Chiến lược dịch siêu an toàn cho API Free"""
        print(f"🚀 Bắt đầu dịch {len(texts)} đoạn văn bản...")
        
        inputs = [{"text": t, "original_lang": original_lang, "target_lang": target_lang} for t in texts]
        results = []
        
        # Cấu hình siêu an toàn cho gói Free, bạn có thể tùy chỉnh nếu có gói trả phí với giới hạn cao hơn
        SAFE_BATCH_SIZE = 2
        SLEEP_TIME = 10 # Nghỉ 20 giây sau mỗi 5 đoạn (~ 15 đoạn/phút, dưới mức 20 RPM)

        for i in range(0, len(inputs), SAFE_BATCH_SIZE):
            batch_inputs = inputs[i : i + SAFE_BATCH_SIZE]
            print(f"📦 Đang xử lý khối: {i + 1} -> {min(i + SAFE_BATCH_SIZE, len(inputs))}")
            
            try:
                # Ép max_concurrency = 2 để không gửi quá nhiều cùng 1 giây
                batch_results = await self.chain.abatch(batch_inputs, config={"max_concurrency": 2})
                results.extend(batch_results)
            except Exception as e:
                print(f"⚠️ Lỗi tại khối này: {e}. Đang bỏ qua để tiếp tục...")
                results.extend(["[Lỗi dịch]"] * len(batch_inputs))
            
            # Chỉ nghỉ nếu còn đoạn chưa dịch
            if i + SAFE_BATCH_SIZE < len(inputs):
                print(f"⏳ Nghỉ {SLEEP_TIME}s để tránh bị API khóa...")
                await asyncio.sleep(SLEEP_TIME)
                
        print(f"✅ Hoàn thành! Đã dịch {len(results)}/{len(texts)} đoạn.")
        return results

# --- MÃ KIỂM THỬ (TEST) ---
async def main():
    texts = [
        "Hello, how are you?",
        "Large Language Models have revolutionized Natural Language Processing.",
        "We propose a novel architecture for document layout analysis.",
        "Equation 1 shows the attention mechanism."
    ]

    translator = OpenRouter_translation()
    
    # Gọi dịch từ Tiếng Anh sang Tiếng Việt
    translated_texts = await translator.translate(
        texts=texts,
        original_lang="English",
        target_lang="Vietnamese"
    )
    
    print("\n--- KẾT QUẢ DỊCH ---")
    for src, tgt in zip(texts, translated_texts):
        print(f"EN: {src}\nVN: {tgt}\n")

if __name__ == "__main__":
    asyncio.run(main())