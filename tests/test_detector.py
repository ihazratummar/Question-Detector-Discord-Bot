import pytest
from exporter.detector import QuestionDetector

@pytest.mark.asyncio
async def test_swedish_keyword_detection():
    detector = QuestionDetector(language="sv")
    
    # Positive cases
    assert await detector.is_question("Hur installerar jag detta?") is True
    assert await detector.is_question("Vad är meningen med livet?") is True
    assert await detector.is_question("Kan någon hjälpa mig?") is True
    assert await detector.is_question("Varför fungerar det inte?") is True
    
    # Negative cases
    assert await detector.is_question("Detta är ett påstående.") is False
    assert await detector.is_question("Hej alla") is False
    assert await detector.is_question("ok") is False # Too short
    
    # Question mark check
    assert await detector.is_question("Det fungerar inte?") is True

    # URL exclusion tests
    assert await detector.is_question("https://discord.com/oauth2/authorize?client_id=123") is False
    assert await detector.is_question("Kolla här: https://example.com?q=1") is False
    assert await detector.is_question("Vad är detta? https://example.com") is True
    assert await detector.is_question("https://example.com?q=1 Varför?") is True

    # False positive checks (Strict mode)
    assert await detector.is_question("Sen får vi se vad som händer.") is False
    assert await detector.is_question("Jag vet inte vad jag ska göra.") is False
    assert await detector.is_question("Vad ska vi göra?") is True # Starts with strong keyword
    
    # Weak keyword false positives (should be False without ?)
    assert await detector.is_question("Ska geo tracka dig via han gubben") is False
    assert await detector.is_question("Gör inte Ian arg han behöver vara klartänkt") is False
    assert await detector.is_question("Kan vara så att det regnar") is False
    
    # Weak keyword with ? (should be True)
    assert await detector.is_question("Ska vi gå?") is True
    assert await detector.is_question("Kan du hjälpa mig?") is True

@pytest.mark.asyncio
async def test_short_message_ignore():
    detector = QuestionDetector()
    assert await detector.is_question("?") is False # < 3 chars
    assert await detector.is_question("a?") is False # < 3 chars
    assert await detector.is_question("ab?") is True # >= 3 chars

@pytest.mark.asyncio
async def test_normalization():
    detector = QuestionDetector()
    raw = "  HUR   mår  DU?  "
    normalized = detector.normalize(raw)
    assert normalized == "hur mår du?"
