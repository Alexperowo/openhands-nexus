import re
import unittest
from concurrent.futures import ThreadPoolExecutor
from unittest.mock import patch

from pronunciation import for_silero


EXAMPLES = [
    ("Запущен OpenHands.", "Запущен Оупен Хэндс."),
    ("Код опубликован на GitHub.", "Код опубликован на Гитхаб."),
    ("Linux и Python готовы.", "Линукс и Пайтон готовы."),
    ("Прочитай README.md.", "Прочитай ридми точка эм-ди."),
    ("Создан PR через API на GPU.", "Создан пи-ар через эй-пи-ай на джи-пи-ю."),
    ("Ответ сохранён в JSON.", "Ответ сохранён в джейсон."),
    ("Функция camelCase и snake_case.", "Функция кэмэл кэйс и снэйк кэйс."),
    ("Вызови HTTPServer и getUserName.", "Вызови эйч-ти-ти-пи сервер и гэт юзер нэйм."),
    ("Выполни git status и uv run python service.py.",
     "Выполни гит стэтэс и ю-ви ран Пайтон сервис точка пай."),
    ("Зависимости: Docker, Ubuntu, FastAPI.", "Зависимости: докер, убунту, фаст эй-пи-ай."),
    ("Слова cache, queue, speech, hello, world.", "Слова кэш, кью, спич, хэлоу, уёрлд."),
    ("Неизвестное foobarquux.", "Неизвестное фубаркуэкс."),
    ("Открой https://github.com/OpenHands/OpenHands?tab=readme, затем продолжим.",
     "Открой ссылка, затем продолжим."),
    ("Адрес github.com.", "Адрес ссылка."),
    ("Файл /tmp/service.py.", "Файл сервис точка пай."),
    ("Путь /home/user/projects/nexus/ui/src/speech-events.ts.",
     "Путь путь к файлу."),
    ("Открой ./README.md и ~/project/src/service.py.", "Открой ридми точка эм-ди и путь к файлу."),
    ("Получен 0123456789abcdef0123456789abcdef.", "Получен хэш."),
    ("Коммит a1b2c3d готов.", "Коммит хэш готов."),
    ("UUID 550e8400-e29b-41d4-a716-446655440000.", "ю-ю-ай-ди хэш."),
    ("Версия v5_6_ru и HTTP2.", "Версия ви5 6 ру и эйч-ти-ти-пи2."),
    ("CPU RAM SSD CLI UI URL.", "си-пи-ю ар-эй-эм эс-эс-ди си-эл-ай ю-ай ю-ар-эл."),
    ("Кириллица, ёж и число 2026.", "Кириллица, ёж и число 2026."),
    ("Проверь src/one/two/three/four.py.", "Проверь путь к файлу."),
    ("Читай **OpenHands**\nAPI доступен.", "Читай **Оупен Хэндс**\nэй-пи-ай доступен."),
    ("Параметр max_tokens = 128.", "Параметр мэкс тоукэнз = 128."),
    ("HelloWorld и user_name.", "хэлоу уёрлд и юзер нэйм."),
    ("ID задачи: " + "x" * 80 + ".", "ай-ди задачи: идентификатор."),
    ("Версии Python3.12 и UTF8.", "Версии Пайтон3.12 и ю-ти-эф8."),
    ("Скачай ftp://example.org/file.zip!", "Скачай ссылка!"),
]


class PronunciationTests(unittest.TestCase):
    def test_agent_examples(self):
        for original, expected in EXAMPLES:
            with self.subTest(text=original):
                self.assertEqual(for_silero(original), expected)
                self.assertIsNone(re.search("[A-Za-z]", expected))

    def test_idempotent(self):
        for original, _ in EXAMPLES:
            normalized = for_silero(original)
            self.assertEqual(for_silero(normalized), normalized)

    def test_path_edges_and_long_uppercase(self):
        for text in ("/../", "/./", "./../"):
            with self.subTest(text=text):
                self.assertEqual(for_silero(text), "путь")
        self.assertEqual(for_silero("QWERTYUIOPASDFGHJKL"), "идентификатор")
        self.assertEqual(for_silero("WWW.example.org!"), "ссылка!")

    def test_concurrent_g2p(self):
        words = ["deployment", "feature", "request", "beautiful"] * 20
        with ThreadPoolExecutor(max_workers=8) as executor:
            results = list(executor.map(for_silero, words))
        for result in results:
            self.assertRegex(result, r"^[а-яё]+$")
        self.assertEqual(results[:4] * 20, results)

    def test_expansion_before_chunking(self):
        from service import TTS_CHUNK_CHARS, tts_chunks
        chunks = tts_chunks(("API GPU PR OpenHands.\n" * 100))
        self.assertGreater(len(chunks), 1)
        self.assertTrue(all(len(chunk) <= TTS_CHUNK_CHARS for chunk in chunks))
        self.assertNotRegex(" ".join(chunks), "[A-Za-z*]")
        self.assertEqual(" ".join(chunks).count("Оупен Хэндс"), 100)
        self.assertEqual(tts_chunks("**OpenHands**\nAPI доступен."),
                         ["Оупен Хэндс. эй-пи-ай доступен."])

    def test_speech_passes_normalized_text_to_model(self):
        import torch
        from service import SpeechRequest, speech
        with patch("service.get_tts_model") as load:
            load.return_value.apply_tts.return_value = torch.ones(4800) * 0.1
            response = speech(SpeechRequest(input="OpenHands и GitHub через API."))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(load.return_value.apply_tts.call_args.kwargs["text"],
                         "Оупен Хэндс и Гитхаб через эй-пи-ай.")


if __name__ == "__main__":
    unittest.main()
