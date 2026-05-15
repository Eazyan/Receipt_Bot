from application.interfaces.ocr_service import OCRService
from application.dto.receipt_dto import ParsedReceiptDTO
import lmstudio as lms

SYSTEM_PROMPT = """
                 Ты - полезный агент, специалист по распознаванию чеков.
                 Твоя основная задача заключается в извлечении из фотографии чека всех позиций в заказе с указанием их цены.
                 -Если при распознавании чека произошла ошибка,то ты ничего не придумываешь,
                  записывай ошибку ее в поле error, а позицию пропускай, если ошибок не было то оставляешь поле пустым.
                 """


SYSTEM_PROMPT_FOR_TEXT = """
                 Ты - полезный агент, специалист по распознаванию чеков.
                 Твоя основная задача заключается в извлечении из текста чека всех позиций в заказе с указанием их цены.
                 -Если при распознавании чека произошла ошибка,то ты ничего не придумываешь,
                  записывай ошибку ее в поле error, а позицию пропускай, если ошибок не было то оставляешь поле пустым.
                 """

class LMStudioModel(OCRService):
    """Адаптер для взаимодействия с локальной VL-моделью через LM Studio API

     Класс реализует интерфейс OCRService для обработки изображений чеков
     направляя запрос на локально запущенную в LMStudio модель (по дефолту qwen3-vl-4b)"""
    def __init__(self, model_name="qwen/qwen3-vl-4b"):

        self.model = lms.llm(
            model_name
        )

    def process_receipt(self, image_path: str) -> ParsedReceiptDTO:
        """Обрабатывает изображение чека, извлекая структурированные данные

        Использует LM Studio для отправки изображения и системного промпта
        модели, парсит ответ в Pydantic DTO."""
        image_handle = lms.prepare_image(image_path)
        chat = lms.Chat(initial_prompt=SYSTEM_PROMPT)
        prompt = """
        Распознай все позиции из этого чека с их ценами,
        определи дату заказа, сумму чаевых,
        сервисный сбор (он так же может называться платой за стол или за обслуживание)"""
        chat.add_user_message(prompt, images=[image_handle])
        try:
            prediction = self.model.respond(chat, response_format=ParsedReceiptDTO)
            return prediction.parsed
        except Exception as e:
            error_msg = str(e)
            return ParsedReceiptDTO(error=error_msg)

    def process_receipt_text(self, receipt_text: str) -> ParsedReceiptDTO:
        """Обрабатывает текст чека, извлекая структурированные данные

        Использует LM Studio для отправки изображения и системного промпта
        модели, парсит ответ в Pydantic DTO."""
        chat = lms.Chat(initial_prompt=SYSTEM_PROMPT_FOR_TEXT)
        prompt = f"""
        Распознай все позиции из этого чека с их ценами,
        определи дату заказа, сумму чаевых,
        сервисный сбор (он так же может называться платой за стол или за обслуживание)
        Текст чека:
        {receipt_text}"""
        chat.add_user_message(prompt)
        try:
            prediction = self.model.respond(chat, response_format=ParsedReceiptDTO)
            return prediction.parsed
        except Exception as e:
            error_msg = str(e)
            return ParsedReceiptDTO(error=error_msg)


