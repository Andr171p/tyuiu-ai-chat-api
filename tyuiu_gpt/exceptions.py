class AppError(Exception):
    """Базовая ошибка приложения"""


class ReadingError(AppError):
    """Ошибка при чтении данных"""


class CreationError(AppError):
    """Ошибка при создании/записи данных"""


class DataConflictError(AppError):
    """Конфликт при создании данных"""
