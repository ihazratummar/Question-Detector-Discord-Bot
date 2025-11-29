import asyncio
import os
import logging
from dotenv import load_dotenv
from exporter.detector import QuestionDetector

# Setup logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')

async def main():
    # Load env
    load_dotenv()
    api_key = os.getenv("HUGGINGFACE_API_KEY")
    
    if not api_key:
        print("❌ Error: HUGGINGFACE_API_KEY not found in .env")
        return

    print(f"🔑 Found API Key: {api_key[:4]}...{api_key[-4:]}")
    
    # Initialize Detector
    detector = QuestionDetector(
        language="sv", 
        hf_api_key=api_key, 
        use_ai=True
    )
    
    # Test Cases
    test_sentences = [
        "Vad heter du?",            # Question (Swedish)
        "Jag heter Anna.",          # Statement
        "Kan du hjälpa mig?",       # Question
        "Det är fint väder idag.",  # Statement
        "Who are you?",             # Question (English)
        "I am a bot.",              # Statement
        "Varför fungerar det inte?", # Question
        "Systemet är nere."         # Statement
    ]
    
    print("\n🧪 Starting AI Detection Test...\n")
    
    results = await detector.detect_batch(test_sentences)
    
    correct_count = 0
    expected_results = [True, False, True, False, True, False, True, False]
    
    for text, is_q, expected in zip(test_sentences, results, expected_results):
        status = "✅" if is_q == expected else "❌"
        type_str = "Question" if is_q else "Statement"
        print(f"{status} [{type_str}] '{text}'")
        if is_q == expected:
            correct_count += 1
            
    print(f"\n📊 Accuracy: {correct_count}/{len(test_sentences)} ({correct_count/len(test_sentences)*100:.1f}%)")
    
    if detector.hf_detector and detector.hf_detector.api_error_count > 0:
        print(f"\n⚠️ API Errors encountered: {detector.hf_detector.api_error_count}")
        print("👉 If you see 403 errors, check your HuggingFace Token permissions!")

if __name__ == "__main__":
    asyncio.run(main())
