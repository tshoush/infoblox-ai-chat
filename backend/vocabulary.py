"""
Domain vocabulary management for Infoblox terminology and network concepts.
Handles entity recognition, synonym mapping, and term validation.
"""

import json
import re
import logging
from typing import Dict, List, Set, Optional, Tuple, Any
from pathlib import Path
from dataclasses import dataclass
import ipaddress

from config import config_manager
from cache import cache_manager

logger = logging.getLogger(__name__)


@dataclass
class VocabularyTerm:
    """Represents a vocabulary term with metadata."""
    term: str
    category: str
    synonyms: List[str]
    definition: str
    examples: List[str]
    regex_pattern: Optional[str] = None


@dataclass
class EntityMatch:
    """Represents a matched entity in text."""
    text: str
    entity_type: str
    start_pos: int
    end_pos: int
    confidence: float
    normalized_value: Optional[str] = None


class NetworkEntityRecognizer:
    """Recognizes network-related entities in text."""
    
    def __init__(self):
        self.patterns = {
            'ipv4_address': r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\b',
            'ipv6_address': r'\b(?:[0-9a-fA-F]{1,4}:){7}[0-9a-fA-F]{1,4}\b|\b::1\b|\b::\b',
            'cidr_network': r'\b(?:(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\.){3}(?:25[0-5]|2[0-4][0-9]|[01]?[0-9][0-9]?)\/(?:[0-9]|[1-2][0-9]|3[0-2])\b',
            'mac_address': r'\b(?:[0-9a-fA-F]{2}[:-]){5}[0-9a-fA-F]{2}\b',
            'hostname': r'\b[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*\b',
            'domain_name': r'\b[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z]{2,})+\b',
            'port_number': r'\b(?:6553[0-5]|655[0-2][0-9]|65[0-4][0-9]{2}|6[0-4][0-9]{3}|[1-5][0-9]{4}|[1-9][0-9]{0,3})\b'
        }
        
        # Compile patterns for performance
        self.compiled_patterns = {
            name: re.compile(pattern, re.IGNORECASE)
            for name, pattern in self.patterns.items()
        }
    
    def extract_entities(self, text: str) -> List[EntityMatch]:
        """Extract network entities from text."""
        entities = []
        
        for entity_type, pattern in self.compiled_patterns.items():
            for match in pattern.finditer(text):
                entity_text = match.group()
                confidence = self._calculate_confidence(entity_text, entity_type)
                
                if confidence > 0.5:  # Only include high-confidence matches
                    normalized = self._normalize_entity(entity_text, entity_type)
                    
                    entities.append(EntityMatch(
                        text=entity_text,
                        entity_type=entity_type,
                        start_pos=match.start(),
                        end_pos=match.end(),
                        confidence=confidence,
                        normalized_value=normalized
                    ))
        
        # Remove overlapping entities (keep highest confidence)
        entities = self._remove_overlaps(entities)
        
        return sorted(entities, key=lambda x: x.start_pos)
    
    def _calculate_confidence(self, text: str, entity_type: str) -> float:
        """Calculate confidence score for entity match."""
        if entity_type in ['ipv4_address', 'cidr_network']:
            try:
                if entity_type == 'ipv4_address':
                    ipaddress.IPv4Address(text)
                else:
                    ipaddress.IPv4Network(text, strict=False)
                return 0.95
            except ValueError:
                return 0.3
        
        elif entity_type == 'ipv6_address':
            try:
                ipaddress.IPv6Address(text)
                return 0.95
            except ValueError:
                return 0.3
        
        elif entity_type == 'mac_address':
            # Validate MAC address format
            clean_mac = re.sub(r'[:-]', '', text)
            if len(clean_mac) == 12 and all(c in '0123456789abcdefABCDEF' for c in clean_mac):
                return 0.9
            return 0.3
        
        elif entity_type == 'port_number':
            try:
                port = int(text)
                if 1 <= port <= 65535:
                    return 0.8
            except ValueError:
                pass
            return 0.3
        
        elif entity_type in ['hostname', 'domain_name']:
            # Basic validation for hostnames/domains
            if '.' in text and len(text) > 3:
                return 0.7
            return 0.4
        
        return 0.5
    
    def _normalize_entity(self, text: str, entity_type: str) -> Optional[str]:
        """Normalize entity value."""
        try:
            if entity_type == 'ipv4_address':
                return str(ipaddress.IPv4Address(text))
            elif entity_type == 'ipv6_address':
                return str(ipaddress.IPv6Address(text))
            elif entity_type == 'cidr_network':
                return str(ipaddress.IPv4Network(text, strict=False))
            elif entity_type == 'mac_address':
                # Normalize to colon-separated format
                clean_mac = re.sub(r'[:-]', '', text.lower())
                return ':'.join(clean_mac[i:i+2] for i in range(0, 12, 2))
            elif entity_type in ['hostname', 'domain_name']:
                return text.lower()
            elif entity_type == 'port_number':
                return text
        except Exception:
            pass
        
        return text
    
    def _remove_overlaps(self, entities: List[EntityMatch]) -> List[EntityMatch]:
        """Remove overlapping entities, keeping highest confidence."""
        if not entities:
            return entities
        
        # Sort by start position
        sorted_entities = sorted(entities, key=lambda x: x.start_pos)
        
        filtered = [sorted_entities[0]]
        
        for entity in sorted_entities[1:]:
            last_entity = filtered[-1]
            
            # Check for overlap
            if entity.start_pos < last_entity.end_pos:
                # Keep the one with higher confidence
                if entity.confidence > last_entity.confidence:
                    filtered[-1] = entity
            else:
                filtered.append(entity)
        
        return filtered


class VocabularyManager:
    """Manages Infoblox and networking terminology vocabulary."""
    
    def __init__(self, vocab_file: str = "vocabulary.json"):
        self.vocab_file = Path(vocab_file)
        self.terms: Dict[str, VocabularyTerm] = {}
        self.synonyms_map: Dict[str, str] = {}  # synonym -> canonical term
        self.categories: Dict[str, List[str]] = {}
        self.entity_recognizer = NetworkEntityRecognizer()
        
        self._load_vocabulary()
    
    def _load_vocabulary(self):
        """Load vocabulary from file and build default terms."""
        # Load from file if exists
        if self.vocab_file.exists():
            try:
                with open(self.vocab_file, 'r') as f:
                    vocab_data = json.load(f)
                    
                for term_data in vocab_data.get('terms', []):
                    term = VocabularyTerm(**term_data)
                    self.add_term(term)
                    
                logger.info(f"Loaded {len(self.terms)} terms from vocabulary file")
            except Exception as e:
                logger.error(f"Failed to load vocabulary file: {e}")
        
        # Add default Infoblox terms
        self._add_default_terms()
        
        # Save updated vocabulary
        self._save_vocabulary()
    
    def _add_default_terms(self):
        """Add default Infoblox and networking terms."""
        default_terms = [
            # WAPI Objects
            VocabularyTerm(
                term="record:a",
                category="wapi_object",
                synonyms=["a record", "a records", "address record", "host record"],
                definition="DNS A record mapping hostname to IPv4 address",
                examples=["Create an A record for server.example.com", "Show all A records"]
            ),
            VocabularyTerm(
                term="record:aaaa",
                category="wapi_object", 
                synonyms=["aaaa record", "aaaa records", "ipv6 record"],
                definition="DNS AAAA record mapping hostname to IPv6 address",
                examples=["Create AAAA record for IPv6", "List AAAA records"]
            ),
            VocabularyTerm(
                term="record:cname",
                category="wapi_object",
                synonyms=["cname record", "cname records", "canonical name", "alias record"],
                definition="DNS CNAME record creating alias for another hostname",
                examples=["Create CNAME alias", "Show CNAME records"]
            ),
            VocabularyTerm(
                term="record:mx",
                category="wapi_object",
                synonyms=["mx record", "mx records", "mail exchange", "mail record"],
                definition="DNS MX record specifying mail server for domain",
                examples=["Configure MX record", "List mail servers"]
            ),
            VocabularyTerm(
                term="record:ptr",
                category="wapi_object",
                synonyms=["ptr record", "ptr records", "reverse dns", "reverse lookup"],
                definition="DNS PTR record for reverse DNS lookup",
                examples=["Create PTR record", "Reverse DNS lookup"]
            ),
            VocabularyTerm(
                term="network",
                category="wapi_object",
                synonyms=["subnet", "network range", "ip network", "network segment"],
                definition="IP network or subnet configuration",
                examples=["Create network 192.168.1.0/24", "List all networks"]
            ),
            VocabularyTerm(
                term="host",
                category="wapi_object",
                synonyms=["host record", "host entry", "device", "endpoint"],
                definition="Host record combining A/AAAA and PTR records",
                examples=["Create host record", "Find host by IP"]
            ),
            VocabularyTerm(
                term="zone_auth",
                category="wapi_object",
                synonyms=["authoritative zone", "dns zone", "zone", "domain zone"],
                definition="Authoritative DNS zone configuration",
                examples=["Create DNS zone", "List zones"]
            ),
            VocabularyTerm(
                term="range",
                category="wapi_object",
                synonyms=["dhcp range", "ip range", "address range", "dhcp pool"],
                definition="DHCP address range for dynamic allocation",
                examples=["Create DHCP range", "Configure IP pool"]
            ),
            
            # Network Operations
            VocabularyTerm(
                term="search",
                category="operation",
                synonyms=["find", "lookup", "query", "get", "show", "list", "display"],
                definition="Search or retrieve network objects",
                examples=["Search for records", "Find by IP address"]
            ),
            VocabularyTerm(
                term="create",
                category="operation",
                synonyms=["add", "new", "make", "configure", "set up", "establish"],
                definition="Create new network objects",
                examples=["Create new record", "Add network"]
            ),
            VocabularyTerm(
                term="update",
                category="operation",
                synonyms=["modify", "change", "edit", "alter", "revise"],
                definition="Update existing network objects",
                examples=["Update record", "Modify network"]
            ),
            VocabularyTerm(
                term="delete",
                category="operation",
                synonyms=["remove", "drop", "destroy", "eliminate"],
                definition="Delete network objects",
                examples=["Delete record", "Remove network"]
            ),
            
            # Network Concepts
            VocabularyTerm(
                term="dns",
                category="network_concept",
                synonyms=["domain name system", "name resolution", "dns server"],
                definition="Domain Name System for hostname resolution",
                examples=["DNS configuration", "Name resolution"]
            ),
            VocabularyTerm(
                term="dhcp",
                category="network_concept",
                synonyms=["dynamic host configuration", "dhcp server", "ip assignment"],
                definition="Dynamic Host Configuration Protocol for IP assignment",
                examples=["DHCP configuration", "IP allocation"]
            ),
            VocabularyTerm(
                term="ipam",
                category="network_concept",
                synonyms=["ip address management", "address management"],
                definition="IP Address Management system",
                examples=["IPAM configuration", "Address tracking"]
            )
        ]
        
        for term in default_terms:
            if term.term not in self.terms:
                self.add_term(term)
    
    def add_term(self, term: VocabularyTerm):
        """Add a term to the vocabulary."""
        self.terms[term.term] = term
        
        # Update synonyms map
        for synonym in term.synonyms:
            self.synonyms_map[synonym.lower()] = term.term
        
        # Update categories
        if term.category not in self.categories:
            self.categories[term.category] = []
        if term.term not in self.categories[term.category]:
            self.categories[term.category].append(term.term)
    
    def get_canonical_term(self, text: str) -> Optional[str]:
        """Get canonical term for text (handling synonyms)."""
        text_lower = text.lower()
        
        # Direct match
        if text_lower in self.terms:
            return text_lower
        
        # Synonym match
        if text_lower in self.synonyms_map:
            return self.synonyms_map[text_lower]
        
        return None
    
    def find_terms_in_text(self, text: str) -> List[Tuple[str, str, int, int]]:
        """Find vocabulary terms in text."""
        matches = []
        text_lower = text.lower()
        
        # Check for direct term matches
        for term in self.terms:
            pattern = re.compile(r'\b' + re.escape(term) + r'\b', re.IGNORECASE)
            for match in pattern.finditer(text):
                matches.append((match.group(), term, match.start(), match.end()))
        
        # Check for synonym matches
        for synonym, canonical in self.synonyms_map.items():
            pattern = re.compile(r'\b' + re.escape(synonym) + r'\b', re.IGNORECASE)
            for match in pattern.finditer(text):
                matches.append((match.group(), canonical, match.start(), match.end()))
        
        # Remove overlaps and sort by position
        matches = self._remove_term_overlaps(matches)
        return sorted(matches, key=lambda x: x[2])
    
    def _remove_term_overlaps(self, matches: List[Tuple[str, str, int, int]]) -> List[Tuple[str, str, int, int]]:
        """Remove overlapping term matches."""
        if not matches:
            return matches
        
        sorted_matches = sorted(matches, key=lambda x: (x[2], -(x[3] - x[2])))  # Sort by start, then by length desc
        
        filtered = [sorted_matches[0]]
        
        for match in sorted_matches[1:]:
            last_match = filtered[-1]
            
            # Check for overlap
            if match[2] < last_match[3]:
                # Skip overlapping match (keep the first/longer one)
                continue
            else:
                filtered.append(match)
        
        return filtered
    
    def get_terms_by_category(self, category: str) -> List[VocabularyTerm]:
        """Get all terms in a category."""
        if category not in self.categories:
            return []
        
        return [self.terms[term] for term in self.categories[category]]
    
    def suggest_completions(self, partial_text: str, max_suggestions: int = 10) -> List[str]:
        """Suggest term completions for partial text."""
        partial_lower = partial_text.lower()
        suggestions = []
        
        # Check terms
        for term in self.terms:
            if term.startswith(partial_lower):
                suggestions.append(term)
        
        # Check synonyms
        for synonym in self.synonyms_map:
            if synonym.startswith(partial_lower):
                suggestions.append(synonym)
        
        return sorted(set(suggestions))[:max_suggestions]
    
    def validate_entity(self, entity: str, entity_type: str) -> bool:
        """Validate network entity format."""
        try:
            if entity_type == 'ipv4_address':
                ipaddress.IPv4Address(entity)
                return True
            elif entity_type == 'ipv6_address':
                ipaddress.IPv6Address(entity)
                return True
            elif entity_type == 'cidr_network':
                ipaddress.IPv4Network(entity, strict=False)
                return True
            elif entity_type == 'mac_address':
                clean_mac = re.sub(r'[:-]', '', entity)
                return len(clean_mac) == 12 and all(c in '0123456789abcdefABCDEF' for c in clean_mac)
            elif entity_type == 'port_number':
                port = int(entity)
                return 1 <= port <= 65535
            elif entity_type in ['hostname', 'domain_name']:
                return bool(re.match(r'^[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?(?:\.[a-zA-Z0-9](?:[a-zA-Z0-9-]{0,61}[a-zA-Z0-9])?)*$', entity))
        except Exception:
            pass
        
        return False
    
    def analyze_query(self, query: str) -> Dict[str, Any]:
        """Analyze query for terms and entities."""
        # Find vocabulary terms
        term_matches = self.find_terms_in_text(query)
        
        # Extract network entities
        entity_matches = self.entity_recognizer.extract_entities(query)
        
        # Categorize found terms
        operations = []
        objects = []
        concepts = []
        
        for _, canonical_term, _, _ in term_matches:
            term_obj = self.terms.get(canonical_term)
            if term_obj:
                if term_obj.category == 'operation':
                    operations.append(canonical_term)
                elif term_obj.category == 'wapi_object':
                    objects.append(canonical_term)
                elif term_obj.category == 'network_concept':
                    concepts.append(canonical_term)
        
        return {
            'query': query,
            'term_matches': term_matches,
            'entity_matches': [
                {
                    'text': e.text,
                    'type': e.entity_type,
                    'confidence': e.confidence,
                    'normalized': e.normalized_value
                }
                for e in entity_matches
            ],
            'operations': list(set(operations)),
            'objects': list(set(objects)),
            'concepts': list(set(concepts))
        }
    
    def _save_vocabulary(self):
        """Save vocabulary to file."""
        try:
            vocab_data = {
                'terms': [
                    {
                        'term': term.term,
                        'category': term.category,
                        'synonyms': term.synonyms,
                        'definition': term.definition,
                        'examples': term.examples,
                        'regex_pattern': term.regex_pattern
                    }
                    for term in self.terms.values()
                ],
                'version': '1.0',
                'last_updated': str(Path(__file__).stat().st_mtime)
            }
            
            with open(self.vocab_file, 'w') as f:
                json.dump(vocab_data, f, indent=2)
                
        except Exception as e:
            logger.error(f"Failed to save vocabulary: {e}")
    
    def get_statistics(self) -> Dict[str, Any]:
        """Get vocabulary statistics."""
        return {
            'total_terms': len(self.terms),
            'total_synonyms': len(self.synonyms_map),
            'categories': {cat: len(terms) for cat, terms in self.categories.items()},
            'entity_types': list(self.entity_recognizer.patterns.keys())
        }


# Global vocabulary manager instance
vocabulary_manager = VocabularyManager()


def analyze_user_query(query: str) -> Dict[str, Any]:
    """Analyze user query for terms and entities."""
    return vocabulary_manager.analyze_query(query)


def get_term_suggestions(partial_text: str, max_suggestions: int = 10) -> List[str]:
    """Get term completion suggestions."""
    return vocabulary_manager.suggest_completions(partial_text, max_suggestions)