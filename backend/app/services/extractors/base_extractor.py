from abc import ABC, abstractmethod


class BaseExtractor(ABC):

    @abstractmethod
    def extract(self, file):
        """
        Extract standard-related information from a file.

        Returns:
            list[dict]: extracted rows containing:
                - sdo_name
                - displaystdno
        """
        pass