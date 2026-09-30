from app.repositories.standards_repository import StandardsRepository
from app.services.search_service import SearchService


class StandardsController:

    @staticmethod
    def search_standards(db, standard_numbers: list[str]):
        repository = StandardsRepository(db)
        service = SearchService(repository)

        return service.search_standards(standard_numbers)