#!/usr/bin/env python3

from typing import List, Optional
from pydantic import BaseModel, Field
from functools import total_ordering
from dataclasses import dataclass, field


class PersonDetails(BaseModel):
    """Model for person details"""
    id: str
    name: str
    birth_date: Optional[str] = None
    birth_place: Optional[str] = None
    death_date: Optional[str] = None
    death_place: Optional[str] = None
    gender: Optional[str] = None
    occupation: Optional[str] = None
    parents: List[str] = Field(default_factory=list)
    spouses: List[str] = Field(default_factory=list)
    children: List[str] = Field(default_factory=list)


class PersonRelationships(BaseModel):
    """Model for person relationships, optimized for graph traversal"""
    id: str
    gender: Optional[str] = None
    parents: List[str] = Field(default_factory=list)
    spouses: List[str] = Field(default_factory=list)
    children: List[str] = Field(default_factory=list)


# --- Constants for Heuristics ---
# These improve readability and make the logic easier to tune.
BIRTH_YEAR_PROXIMITY_THRESHOLD = 500  # How close a birth year must be to be considered "relevant" for the heuristic.
BIRTH_YEAR_HEURISTIC_FACTOR = 25.0   # The factor to scale the birth year distance by.
NO_BIRTH_YEAR_PENALTY = 9999         # A large value to deprioritize nodes without a birth year.
HAS_BIRTH_YEAR_BONUS = 5000          # A value to prioritize nodes with a birth year over those without, even if the target year is unknown.


@total_ordering
@dataclass
class NodePriority:
    """
    Represents the priority of a node in the search queue.

    This class is designed for a bidirectional A* search. The priority is a composite
    value that ensures the search is both efficient and deterministic.

    Improvements over the original version:
    1.  Clarity: Uses a dataclass and named constants for magic numbers.
    2.  Simplicity: The complex comparison logic in __lt__ is replaced with a
        more readable and Pythonic tuple comparison.
    3.  Encapsulation: Heuristic calculations are done once in __post_init__.
    """
    distance: int
    person_id: str
    path: List[str]
    target_birth_year: Optional[int]

    # These fields are computed once and used for comparison.
    # They are excluded from the default __repr__ for brevity.
    _adjusted_distance: float = field(init=False, repr=False)
    _birth_year_distance: int = field(init=False, repr=False)

    def __post_init__(self):
        """
        Initialize with default values. Call init_heuristics() with gedcom_ctx to calculate proper values.
        """
        self._birth_year_distance = NO_BIRTH_YEAR_PENALTY
        self._adjusted_distance = float(self.distance)
    
    def init_heuristics(self, gedcom_ctx):
        """
        Calculates the heuristic values using the provided GEDCOM context.
        """
        from .gedcom_utils import extract_birth_year
        
        birth_year = extract_birth_year(self.person_id, gedcom_ctx)

        # Calculate the birth year distance heuristic (h_cost)
        if birth_year is not None and self.target_birth_year is not None:
            self._birth_year_distance = abs(birth_year - self.target_birth_year)
        elif birth_year is not None:
            self._birth_year_distance = HAS_BIRTH_YEAR_BONUS
        else:
            self._birth_year_distance = NO_BIRTH_YEAR_PENALTY

        # Calculate the adjusted total distance (f_cost = g_cost + h_cost)
        # g_cost is self.distance.
        self._adjusted_distance = float(self.distance)
        if self._birth_year_distance < BIRTH_YEAR_PROXIMITY_THRESHOLD:
            self._adjusted_distance += self._birth_year_distance / BIRTH_YEAR_HEURISTIC_FACTOR

        # Calculate the birth year distance heuristic (h_cost)
        if birth_year is not None and self.target_birth_year is not None:
            self._birth_year_distance = abs(birth_year - self.target_birth_year)
        elif birth_year is not None:
            self._birth_year_distance = HAS_BIRTH_YEAR_BONUS
        else:
            self._birth_year_distance = NO_BIRTH_YEAR_PENALTY

        # Calculate the adjusted total distance (f_cost = g_cost + h_cost)
        # g_cost is self.distance.
        self._adjusted_distance = float(self.distance)
        if self._birth_year_distance < BIRTH_YEAR_PROXIMITY_THRESHOLD:
            self._adjusted_distance += self._birth_year_distance / BIRTH_YEAR_HEURISTIC_FACTOR

    def __eq__(self, other):
        if not isinstance(other, NodePriority):
            return NotImplemented
        # Two nodes are equal if their sort keys are identical.
        return (self._adjusted_distance, self._birth_year_distance, self.person_id) == \
               (other._adjusted_distance, other._birth_year_distance, other.person_id)

    def __lt__(self, other):
        """
        Compares two nodes for priority queue ordering.
        The comparison is done via a tuple, which is efficient and readable.
        """
        if not isinstance(other, NodePriority):
            return NotImplemented
        
        # The sort order is determined by this tuple:
        # 1. Adjusted Distance (f_cost): The primary factor, combining real distance and heuristic.
        # 2. Birth Year Distance (h_cost): A secondary heuristic to guide the search.
        # 3. Person ID: A final, deterministic tie-breaker.
        return (self._adjusted_distance, self._birth_year_distance, self.person_id) < \
               (other._adjusted_distance, other._birth_year_distance, other.person_id)

    def __repr__(self):
        return (
            f"NodePriority(f_cost={self._adjusted_distance:.2f}, "
            f"dist={self.distance}, birth_dist={self._birth_year_distance}, "
            f"id='{self.person_id}')"
        )


class LoadGedcomParams(BaseModel):
    """Parameters for loading a GEDCOM file"""
    file_path: str


class GetPersonParams(BaseModel):
    """Parameters for getting person details"""
    person_id: str


class FindPersonParams(BaseModel):
    """Parameters for finding a person by name"""
    name: str


class GetRelationshipsParams(BaseModel):
    """Parameters for getting relationships"""
    person_id: str


class GetEventsParams(BaseModel):
    """Parameters for getting events for a person"""
    person_id: str


class GetPlacesParams(BaseModel):
    """Parameters for getting places information"""
    query: Optional[str] = None


class GetTimelineParams(BaseModel):
    """Parameters for getting a timeline of events for a person"""
    person_id: str


class SearchParams(BaseModel):
    """Parameters for searching across the GEDCOM file"""
    query: str
    search_type: Optional[str] = "all"  # all, people, places, events


class GetNotesParams(BaseModel):
    """Parameters for getting notes for a person or family"""
    entity_id: str


class GetSourcesParams(BaseModel):
    """Parameters for getting sources for a person or family"""
    entity_id: str


class GetStatisticsParams(BaseModel):
    """Parameters for getting GEDCOM file statistics"""
    pass


class GetCommonAncestorsParams(BaseModel):
    """Parameters for finding common ancestors of multiple people"""
    person_ids: List[str] = Field(description="List of person IDs to find common ancestors for")
    max_level: int = Field(default=20, description="Maximum ancestor level to search (default: 20)")