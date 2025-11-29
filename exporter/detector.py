import re
from typing import List, Optional

SWEDISH_STRONG_KEYWORDS = [
    "varför", "hur", "vad", "när", "vem", "vilken", "vilket", "vilka",
    "var", "vart", "hurdan", "hur mycket"
]

SWEDISH_WEAK_KEYWORDS = [
    "kan", "ska", "finns", "är", "gör"
]

import aiohttp
import asyncio
import logging

class HuggingFaceDetector:
    def __init__(self, api_key: str, model: str = "KBLab/bert-base-swedish-cased"):
        self.api_key = api_key
        self.api_url = f"https://api-inference.huggingface.co/models/{model}"
        self.headers = {"Authorization": f"Bearer {api_key}"}

    async def is_question(self, text: str) -> bool:
        """
        Single text check (wraps batch check).
        """
        results = await self.is_question_batch([text])
        return results[0]

    async def is_question_batch(self, texts: List[str]) -> List[bool]:
        """
        Uses Hugging Face Inference API to determine if a list of texts are questions.
        """
        if not texts:
            return []

        # Using a multilingual zero-shot classifier
        model = "joeddav/xlm-roberta-large-xnli" 
        api_url = f"https://api-inference.huggingface.co/models/{model}"
        
        # HF Inference API supports batch inputs for zero-shot
        payload = {
            "inputs": texts,
            "parameters": {"candidate_labels": ["fråga", "påstående"]}
        }

        try:
            async with aiohttp.ClientSession() as session:
                async with session.post(api_url, headers=self.headers, json=payload) as response:
                    if response.status != 200:
                        logging.warning(f"HF API Error {response.status}: {await response.text()}")
                        return [False] * len(texts)
                    
                    results = await response.json()
                    # Result format for batch: List of dicts
                    # [{'sequence': '...', 'labels': [...], 'scores': [...]}, ...]
                    
                    if isinstance(results, dict): # Single result returned if batch size 1 sometimes
                        results = [results]
                        
                    final_results = []
                    for result in results:
                        if 'labels' in result and 'scores' in result:
                            labels = result['labels']
                            scores = result['scores']
                            try:
                                idx = labels.index("fråga")
                                score = scores[idx]
                                final_results.append(score > 0.5)
                            except ValueError:
                                final_results.append(False)
                        else:
                            final_results.append(False)
                    return final_results

        except Exception as e:
            logging.error(f"HF API Exception: {e}")
            return [False] * len(texts)

class QuestionDetector:
    def __init__(self, language: str = "sv", extra_keywords: Optional[List[str]] = None, 
                 hf_api_key: Optional[str] = None, use_ai: bool = False):
        self.language = language
        self.strong_keywords = set(SWEDISH_STRONG_KEYWORDS)
        self.weak_keywords = set(SWEDISH_WEAK_KEYWORDS)
        if extra_keywords:
            self.strong_keywords.update(k.lower() for k in extra_keywords)
            
        self.use_ai = use_ai
        self.hf_detector = None
        if use_ai and hf_api_key:
            self.hf_detector = HuggingFaceDetector(hf_api_key)

    async def is_question(self, content: str) -> bool:
        """
        Determines if a message content is a question.
        """
        return (await self.detect_batch([content]))[0]

    async def detect_batch(self, contents: List[str]) -> List[bool]:
        """
        Batch detection logic.
        1. Run regex rules first (free).
        2. If undecided and AI enabled, batch send to AI.
        """
        results = [False] * len(contents)
        ai_candidates_indices = []
        ai_candidates_texts = []

        for i, content in enumerate(contents):
            if not content:
                results[i] = False
                continue

            content = content.strip()
            if len(content) < 3:
                results[i] = False
                continue

            content_without_urls = re.sub(r'https?://\S+', '', content)

            # 1. Obvious Question (Has ?)
            if "?" in content_without_urls:
                results[i] = True
                continue
            
            # 2. Strong Keyword Start
            lower_content = content_without_urls.lower()
            words = re.findall(r'\w+', lower_content)
            if words and words[0] in self.strong_keywords:
                results[i] = True
                continue

            # 3. If AI enabled, mark for AI check
            if self.use_ai and self.hf_detector:
                if len(content.split()) > 2: # Heuristic
                    ai_candidates_indices.append(i)
                    ai_candidates_texts.append(content)
            
        # Batch call AI
        if ai_candidates_texts:
            ai_results = await self.hf_detector.is_question_batch(ai_candidates_texts)
            for idx, is_q in zip(ai_candidates_indices, ai_results):
                results[idx] = is_q
                
        return results

    def normalize(self, content: str) -> str:
        """
        Normalizes text for deduplication (not for export).
        """
        content = content.strip().lower()
        content = re.sub(r'\s+', ' ', content)
        return content
