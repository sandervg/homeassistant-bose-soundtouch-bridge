import traceback

class ErrorHandler:
    @staticmethod
    def handle_exception(exc_type, exc_value, exc_traceback):
        print(f"[ERROR] Unhandled exception: {exc_type.__name__}: {exc_value}")
        traceback.print_exception(exc_type, exc_value, exc_traceback)
        return False
