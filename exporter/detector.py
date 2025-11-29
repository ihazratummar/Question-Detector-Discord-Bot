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
    API_URL = "https://router.huggingface.co/hf-inference/models/facebook/bart-large-mnli"

    def __init__(self, api_key: str):
        self.api_key = api_key
        self.api_error_count = 0
        self.max_api_errors = 5 # Disable AI after this many errors

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

        if self.api_error_count >= self.max_api_errors:
            # Fallback to keywords if too many errors
            # logging.warning("HuggingFaceDetector disabled...") # Silenced
            return [False] * len(texts)

        headers = {"Authorization": f"Bearer {self.api_key}"}
        
        payload = {
            "inputs": texts,
            "parameters": {
                "candidate_labels": ["question", "statement"],
                "multi_label": False
            }
        }

        retries = 3
        for attempt in range(retries):
            try:
                async with aiohttp.ClientSession() as session:
                    async with session.post(self.API_URL, headers=headers, json=payload) as response:
                        if response.status == 200:
                            result = await response.json()
                            # Reset error count on success
                            self.api_error_count = 0
                            
                            is_questions = []
                            if isinstance(result, list):
                                for item in result:
                                    if isinstance(item, dict) and 'labels' in item and 'scores' in item:
                                        labels = item['labels']
                                        scores = item['scores']
                                        try:
                                            q_index = labels.index('question')
                                            q_score = scores[q_index]
                                            is_questions.append(q_score > 0.5)
                                        except ValueError:
                                            is_questions.append(False)
                                    else:
                                        is_questions.append(False)
                            else:
                                 return [False] * len(texts)
                            return is_questions
                        
                        elif response.status in [401, 403]:
                            # Auth error, disable permanently
                            error_text = await response.text()
                            logging.error(f"HF API Auth Error {response.status}: {error_text}. Disabling AI.")
                            self.api_error_count = self.max_api_errors
                            return [False] * len(texts)
                        
                        elif response.status in [429, 500, 502, 503, 504]:
                            # Transient error, retry
                            logging.warning(f"HF API Transient Error {response.status}. Retrying {attempt+1}/{retries}...")
                            await asyncio.sleep(2 * (attempt + 1)) # Backoff
                            continue
                        
                        else:
                            # Other error
                            logging.warning(f"HF API Error {response.status}: {await response.text()}")
                            break

            except Exception as e:
                logging.error(f"Error calling HF API: {e}")
                await asyncio.sleep(1)
        
        # If we get here, all retries failed
        self.api_error_count += 1
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
