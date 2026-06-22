import json
from typing import List, Dict, Any

class Vocabulary:
    """Manages the domain-specific vocabulary for the application."""

    def __init__(self, file_path: str = "vocabulary.json"):
        self.file_path = file_path
        self.vocabulary = self.load_vocabulary()

    def load_vocabulary(self) -> dict:
        """Loads the vocabulary from the specified JSON file."""
        try:
            with open(self.file_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            return {}

    def save_vocabulary(self) -> None:
        """Saves the current vocabulary to the JSON file."""
        with open(self.file_path, 'w') as f:
            json.dump(self.vocabulary, f, indent=2)

    def add_terms(self, terms: List[str], category: str) -> None:
        """Adds new terms to the vocabulary under a specific category."""
        if category not in self.vocabulary:
            self.vocabulary[category] = []
        for term in terms:
            if term not in self.vocabulary[category]:
                self.vocabulary[category].append(term)
        self.save_vocabulary()

    def get_terms(self, category: str) -> list:
        """Get all terms for a given category."""
        return self.vocabulary.get(category, [])

    def get_synonyms(self, term: str) -> List[str]:
        """Returns synonyms for a given term (placeholder for future enhancement)."""
        # This can be expanded later to include a more sophisticated synonym mapping
        return []

    def validate_entity(self, entity: str, entity_type: str) -> bool:
        """Validates if an entity exists in the vocabulary for a given type."""
        # This can be expanded later to include more sophisticated validation
        return entity in self.vocabulary.get(entity_type, [])