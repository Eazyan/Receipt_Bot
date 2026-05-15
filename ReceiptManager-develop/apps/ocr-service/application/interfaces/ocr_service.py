from abc import ABC, abstractmethod
from application.dto.receipt_dto import ParsedReceiptDTO

class OCRService(ABC):

    @abstractmethod
    def process_receipt(self, image_path: str) -> ParsedReceiptDTO:
        """Принимает картинку (путь), возвращает объект передачи данных чека"""
        pass