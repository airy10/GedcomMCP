#!/usr/bin/env python3

import heapq
import time
import logging
import collections
from typing import List, Set, Dict, Any, Tuple, Optional

from .gedcom_models import NodePriority
from .gedcom_utils import extract_birth_year
from .gedcom_data_access import get_person_details_internal, _get_person_relationships_internal

def _dijkstra_bidirectional_search(start, end, allowed_relationships: Set[str], gedcom_ctx, max_distance=100, exclude_initial_spouse_children=False, min_distance=0, strict_min_distance=False):
    """Optimized bidirectional Dijkstra search with better data structures and pruning"""
    import time
    
    if not gedcom_ctx.gedcom_parser:
        return None, -1
    
    # We'll need to import logger when this function is used
    # logger.info(f"PERF: Starting bidirectional Dijkstra search from {start} to {end}")
    
    # Use the larger of the user-provided max_distance and our calculated reasonable distance
    # This prevents overly restrictive limits while still providing some optimization
    # But don't go beyond a reasonable limit to prevent infinite searches
    effective_max_distance = min(max_distance, 100)
    
    # OPTIMIZATION 2: Component connectivity check for disconnected pairs
    # First do a very quick check with small max_depth
    connectivity_start = time.time()
    connectivity_result = check_component_connectivity(start, end, allowed_relationships, gedcom_ctx, max_depth=50)
    connectivity_time = time.time() - connectivity_start
    
    if connectivity_result is False:
        # We'll need to import logger when this function is used
        # logger.info(f"PERF: Quick connectivity check - people are in different components (took {connectivity_time:.3f}s)")
        return None, -1
    elif connectivity_result is True:
        # We'll need to import logger when this function is used
        # logger.info(f"PERF: Quick connectivity check - found direct connection (took {connectivity_time:.3f}s)")
        pass
    else:
        # We'll need to import logger when this function is used
        # logger.info(f"PERF: Quick connectivity check inconclusive - proceeding with full search (took {connectivity_time:.3f}s)")
        pass
    
    # Keep track of original start and end for path reconstruction
    original_start, original_end = start, end
    
    # OPTIMIZATION: Pre-compute the relationships cache key to avoid repeated tuple(sorted()) calls
    relationships_cache_key = tuple(sorted(allowed_relationships))
    
    # Verify both people exist and have some connections
    start_neighbors = _get_person_neighbors_lazy(start, allowed_relationships, gedcom_ctx, exclude_spouse_children=exclude_initial_spouse_children, relationships_cache_key=relationships_cache_key)
    end_neighbors = _get_person_neighbors_lazy(end, allowed_relationships, gedcom_ctx, exclude_spouse_children=exclude_initial_spouse_children, relationships_cache_key=relationships_cache_key)
    # We'll need to import logger when this function is used
    # logger.info(f"PERF: Start person {start} has {len(start_neighbors)} neighbors")
    # logger.info(f"PERF: End person {end} has {len(end_neighbors)} neighbors")
    
    # Optimization: Start the search from the person with fewer connections
    # This reduces the search space significantly for disconnected components
    swapped = False
    if len(end_neighbors) < len(start_neighbors):
        # We'll need to import logger when this function is used
        # logger.info(f"PERF: Swapping search direction - starting from person with fewer connections ({len(end_neighbors)} vs {len(start_neighbors)})")
        start, end = end, start
        start_neighbors, end_neighbors = end_neighbors, start_neighbors
        swapped = True
    
    # Get target birth years for heuristic ordering
    target_birth_year = extract_birth_year(end, gedcom_ctx)
    start_birth_year = extract_birth_year(start, gedcom_ctx)
    
    # Forward search (from start) - using deterministic NodePriority
    class InfinityDict(dict):
        def __missing__(self, key):
            return float('infinity')
    
    forward_distances = InfinityDict()
    forward_distances[start] = 0
    forward_previous = {}
    forward_visited = set()
    forward_pq = [NodePriority(0, start, [start], target_birth_year)]
    
    # Backward search (from end) - using deterministic NodePriority  
    backward_distances = InfinityDict()
    backward_distances[end] = 0
    backward_previous = {}
    backward_visited = set()
    backward_pq = [NodePriority(0, end, [end], start_birth_year)]
    nodes_processed = 0
    edges_examined = 0
    search_start = time.time()
    last_log_time = time.time()
    
    # Time limit for disconnected component detection
    time_limit = 120.0  # 120 seconds max for distant relationships
    
    # Best meeting point found so far
    best_distance = float('infinity')
    meeting_node = None
    
    # Track shortest path as fallback if no path meets min_distance
    shortest_distance = float('infinity')
    shortest_meeting_node = None
    
    while forward_pq or backward_pq:
        # Check if both searches have exceeded reasonable distance
        min_forward_dist = forward_pq[0].distance if forward_pq else float('infinity')
        min_backward_dist = backward_pq[0].distance if backward_pq else float('infinity')
        
        # Only stop if BOTH queues have real distances that exceed the limit
        # Don't stop if one queue is empty (infinity) unless both are empty
        # For distant relationships, be more lenient with the distance check
        if (forward_pq and backward_pq and 
            min_forward_dist + min_backward_dist > effective_max_distance * 1.2):  # Allow 20% overage for distant relationships
            # We'll need to import logger when this function is used
            # logger.info(f"PERF: Bidirectional: Stopping search - combined distance {min_forward_dist + min_backward_dist:.1f} exceeds max {effective_max_distance}")
            break
        
        # Stop if both queues are empty (no more nodes to explore)
        if not forward_pq and not backward_pq:
            # We'll need to import logger when this function is used
            # logger.info(f"PERF: Bidirectional: No more nodes to explore")
            break
        
        # EARLY TERMINATION: If one side has exhausted all reachable nodes without finding target
        # This is crucial for disconnected components
        if not forward_pq and best_distance == float('infinity'):
            # We'll need to import logger when this function is used
            # logger.info(f"PERF: Bidirectional: Forward search exhausted all reachable nodes ({len(forward_visited)} nodes) - no connection exists")
            break
        if not backward_pq and best_distance == float('infinity'):
            # We'll need to import logger when this function is used
            # logger.info(f"PERF: Bidirectional: Backward search exhausted all reachable nodes ({len(backward_visited)} nodes) - no connection exists")
            break
        
        # OPTIMIZATION: Stop if current search paths are longer than best known complete path
        if best_distance != float('infinity'):
            if min_forward_dist + min_backward_dist >= best_distance:
                # We'll need to import logger when this function is used
                # logger.info(f"PERF: Bidirectional: Stopping search - current paths ({min_forward_dist + min_backward_dist:.1f}) >= best path ({best_distance})")
                break
        
        # Alternate between forward and backward search - ensure balanced exploration
        # Use simple alternation based on which side has processed fewer nodes
        if forward_pq and (not backward_pq or len(forward_visited) <= len(backward_visited)):
            # Forward step
            current_priority = heapq.heappop(forward_pq)
            current_distance, current_node = current_priority.distance, current_priority.person_id
            
            # Skip if already visited (better path already found)
            if current_node in forward_visited:
                continue
            
            # Skip if we've already found a better path to this node
            if current_distance > forward_distances[current_node]:
                continue
                
            forward_visited.add(current_node)
            nodes_processed += 1
            
            # Check if we've met the backward search
            if current_node in backward_visited:
                total_distance = forward_distances[current_node] + backward_distances[current_node]
                
                # Always track the shortest path as fallback
                if total_distance < shortest_distance:
                    shortest_distance = total_distance
                    shortest_meeting_node = current_node
                
                # Check if this path meets our minimum distance requirement
                if total_distance >= min_distance and total_distance < best_distance:
                    # Accept the meeting point - trust Dijkstra won't create cycles
                    best_distance = total_distance
                    meeting_node = current_node
                    # We'll need to import logger when this function is used
                    # logger.info(f"PERF: Bidirectional: Found valid meeting point {current_node} with distance {best_distance} (meets min_distance {min_distance})")
                    break
                elif min_distance == 0 and total_distance < best_distance:
                    # If no minimum distance required, accept any shortest path
                    best_distance = total_distance
                    meeting_node = current_node
                    # We'll need to import logger when this function is used
                    # logger.info(f"PERF: Bidirectional: Found meeting point {current_node} with distance {best_distance} - pruning optimization now active")
                    break
            
            # Stop if we've exceeded half the max distance (since we're searching from both ends)
            if current_distance >= effective_max_distance // 2:
                continue  # Skip expanding this node
            
            # OPTIMIZATION: Skip if this path is already longer than best known complete path
            if best_distance != float('infinity') and current_distance >= best_distance:
                # We'll need to import logger when this function is used
                # logger.info(f"PERF: Bidirectional: Skipping forward node {current_node} (distance {current_distance}) >= best path ({best_distance})")
                continue  # Skip expanding this node
            
            # Expand forward
            # Only exclude spouse/children for the initial start node
            exclude_for_this_node = exclude_initial_spouse_children and current_node == start
            neighbors = _get_person_neighbors_lazy(current_node, allowed_relationships, gedcom_ctx, exclude_spouse_children=exclude_for_this_node, relationships_cache_key=relationships_cache_key)
            for neighbor, weight, relationship_type in neighbors:
                edges_examined += 1
                if neighbor in forward_visited:
                    continue
                
                distance = current_distance + weight
                if distance < forward_distances[neighbor]:
                    forward_distances[neighbor] = distance
                    forward_previous[neighbor] = (current_node, relationship_type)
                    new_path = current_priority.path + [neighbor]
                    heapq.heappush(forward_pq, NodePriority(distance, neighbor, new_path, target_birth_year))
        
        elif backward_pq:
            # Backward step
            current_priority = heapq.heappop(backward_pq)
            current_distance, current_node = current_priority.distance, current_priority.person_id
            
            # Skip if already visited (better path already found)
            if current_node in backward_visited:
                continue
            
            # Skip if we've already found a better path to this node
            if current_distance > backward_distances[current_node]:
                continue
                
            backward_visited.add(current_node)
            nodes_processed += 1
            
            # Check if we've met the forward search
            if current_node in forward_visited:
                total_distance = forward_distances[current_node] + backward_distances[current_node]
                
                # Always track the shortest path as fallback
                if total_distance < shortest_distance:
                    shortest_distance = total_distance
                    shortest_meeting_node = current_node
                
                # Check if this path meets our minimum distance requirement
                if total_distance >= min_distance and total_distance < best_distance:
                    # Accept the meeting point - trust Dijkstra won't create cycles
                    best_distance = total_distance
                    meeting_node = current_node
                    # We'll need to import logger when this function is used
                    # logger.info(f"PERF: Bidirectional: Found valid meeting point {current_node} with distance {best_distance} (meets min_distance {min_distance})")
                    break
                elif min_distance == 0 and total_distance < best_distance:
                    # If no minimum distance required, accept any shortest path
                    best_distance = total_distance
                    meeting_node = current_node
                    # We'll need to import logger when this function is used
                    # logger.info(f"PERF: Bidirectional: Found meeting point {current_node} with distance {best_distance}")
                    break
            
            # Stop if we've exceeded half the max distance (since we're searching from both ends)
            if current_distance >= effective_max_distance // 2:
                continue  # Skip expanding this node
            
            # OPTIMIZATION: Skip if this path is already longer than best known complete path
            if best_distance != float('infinity') and current_distance >= best_distance:
                # We'll need to import logger when this function is used
                # logger.info(f"PERF: Bidirectional: Skipping backward node {current_node} (distance {current_distance}) >= best path ({best_distance})")
                continue  # Skip expanding this node
            
            # Expand backward (reverse relationships)
            # Only exclude spouse/children for the initial end node
            exclude_for_this_node = exclude_initial_spouse_children and current_node == end
            neighbors = _get_person_neighbors_lazy_reverse(current_node, allowed_relationships, gedcom_ctx, exclude_spouse_children=exclude_for_this_node, relationships_cache_key=relationships_cache_key)
            for neighbor, weight, relationship_type in neighbors:
                edges_examined += 1
                if neighbor in backward_visited:
                    continue
                
                distance = current_distance + weight
                if distance < backward_distances[neighbor]:
                    backward_distances[neighbor] = distance
                    backward_previous[neighbor] = (current_node, relationship_type)
                    new_path = current_priority.path + [neighbor]
                    heapq.heappush(backward_pq, NodePriority(distance, neighbor, new_path, start_birth_year))
        
        # Progress logging with queue status
        current_time = time.time()
        if nodes_processed % 200 == 0 or (current_time - last_log_time) > 10.0:
            elapsed = current_time - search_start
            rate = nodes_processed / elapsed if elapsed > 0 else 0
            # We'll need to import logger when this function is used
            # logger.info(f"PERF: Bidirectional search processed {nodes_processed} nodes, examined {edges_examined} edges - {rate:.1f} nodes/sec")
            # logger.info(f"PERF: Queue status - Forward: {len(forward_pq)} items, Backward: {len(backward_pq)} items")
            # logger.info(f"PERF: Visited - Forward: {len(forward_visited)} nodes, Backward: {len(backward_visited)} nodes")
            last_log_time = current_time
            
            # TIME LIMIT: Stop if taking too long (likely disconnected)
            if elapsed > time_limit:
                # We'll need to import logger when this function is used
                # logger.info(f"PERF: TIME LIMIT - stopping search after {elapsed:.1f}s - likely disconnected components")
                break
    
    # Handle minimum distance requirements
    if meeting_node is None:
        # No path found that meets minimum distance requirement
        if min_distance > 0 and shortest_meeting_node is not None:
            if strict_min_distance:
                # Strict mode: return no path if min_distance cannot be met
                # We'll need to import logger when this function is used
                # logger.info(f"PERF: Bidirectional: No path found meeting min_distance {min_distance} (strict mode)")
                return None, -1
            else:
                # Fallback mode: use shortest path with warning
                # We'll need to import logger when this function is used
                # logger.info(f"PERF: Bidirectional: No path found meeting min_distance {min_distance}, using shortest path (distance {shortest_distance})")
                meeting_node = shortest_meeting_node
                best_distance = shortest_distance
        else:
            # We'll need to import logger when this function is used
            # logger.info(f"PERF: Bidirectional: No path found after processing {nodes_processed} nodes")
            return None, -1
    
    # Reconstruct path from both sides
    # Forward path: from start to meeting_node
    forward_path = []
    current = meeting_node
    while current is not None:
        forward_path.append(current)
        if current in forward_previous:
            current, _ = forward_previous[current]
        else:
            current = None
    forward_path.reverse()  # Now: [start, ..., meeting_node]
    
    # Backward path: from end to meeting_node  
    backward_path = []
    current = meeting_node
    while current is not None:
        if current in backward_previous:
            current, _ = backward_previous[current]
            if current is not None:
                backward_path.append(current)
        else:
            current = None
    # backward_path is now: [node_before_meeting, ..., end]
    # We want: [meeting_node, ..., end] but excluding meeting_node since it's in forward_path
    
    # Combine: [start, ..., meeting_node] + [node_after_meeting, ..., end]
    full_path = forward_path + backward_path
    
    # If we swapped start and end, we need to reverse the path to get the correct direction
    if swapped:
        full_path.reverse()
    
    # Validate path for cycles - this should NEVER happen in a correct shortest path
    if len(full_path) != len(set(full_path)):
        duplicates = len(full_path) - len(set(full_path))
        # We'll need to import logger when this function is used
        # logger.error(f"PERF: CRITICAL BUG - Path has {duplicates} duplicate nodes")
        return None, -1
    
    # We'll need to import logger when this function is used
    # logger.info(f"PERF: Bidirectional completed: {nodes_processed} nodes processed, path length {len(full_path)}")
    return full_path, best_distance


def check_component_connectivity(person1_id, person2_id, allowed_relationships: Set[str], gedcom_ctx, max_depth=1000):
    """
    Quick BFS-based connectivity checker to identify disconnected components before expensive search.
    Returns True if connected, False if disconnected, None if inconclusive (hit max_depth).
    """
    
    # Quick check - if they're the same person
    if person1_id == person2_id:
        return True
    
    visited = set()
    queue = collections.deque([person1_id])
    visited.add(person1_id)
    nodes_visited = 0
    
    search_start = time.time()
    
    while queue and nodes_visited < max_depth:
        current = queue.popleft()
        nodes_visited += 1
        
        # Early termination - found target
        if current == person2_id:
            # We'll need to import logger when this function is used
            # logger.info(f"PERF: Quick connectivity check - found target after visiting {nodes_visited} nodes")
            return True
            
        # Explore neighbors
        neighbors = _get_person_neighbors_lazy(current, allowed_relationships, gedcom_ctx)
        for neighbor_id, weight, rel_type in neighbors:
            if neighbor_id not in visited:
                visited.add(neighbor_id)
                queue.append(neighbor_id)
                
    # Check if we can reach person2 from our explored component
    is_connected = person2_id in visited
    
    # Log performance info
    search_time = time.time() - search_start
    # We'll need to import logger when this function is used
    # logger.info(f"PERF: Quick connectivity check - visited {nodes_visited} nodes in {search_time:.3f}s, connected: {is_connected}")
    
    # If we hit the max_depth, we're inconclusive
    if nodes_visited >= max_depth:
        # We'll need to import logger when this function is used
        # logger.info(f"PERF: Quick connectivity check - hit max_depth {max_depth}, inconclusive")
        return None
        
    return is_connected


def _get_person_neighbors_lazy(person_id, allowed_relationships: Set[str], gedcom_ctx, exclude_spouse_children=False, relationships_cache_key=None):
    """
    Lazily gets neighbors (parents, spouses, children) of a person.
    This function is optimized for graph traversal algorithms like A*
    by only fetching necessary relationship data using _get_person_relationships_internal.
    """
    if not gedcom_ctx.gedcom_parser:
        return []

    # Use a combined cache for neighbors based on person_id and allowed_relationships
    # This prevents re-calculating neighbors for the same person and relationship type
    if relationships_cache_key is None:
        relationships_cache_key = tuple(sorted(allowed_relationships))
    cache_key = (person_id, relationships_cache_key, exclude_spouse_children)
    
    if cache_key in gedcom_ctx.neighbor_cache:
        return gedcom_ctx.neighbor_cache[cache_key]

    neighbors = []
    
    # PERFORMANCE OPTIMIZATION: Use the new _get_person_relationships_internal
    person_relationships = _get_person_relationships_internal(person_id, gedcom_ctx)
    
    if not person_relationships:
        gedcom_ctx.neighbor_cache[cache_key] = []
        return []
    
    # Handle parent relationships (including mother/father specific)
    if "parent" in allowed_relationships or "mother" in allowed_relationships or "father" in allowed_relationships:
        for parent_id in person_relationships.parents:  # Already sorted during creation
            parent_relationships = _get_person_relationships_internal(parent_id, gedcom_ctx)
            if parent_relationships:
                # Check if we should include this parent based on gender restrictions
                include_parent = False
                relationship_type = "parent"
                
                if "parent" in allowed_relationships:
                    include_parent = True
                elif "mother" in allowed_relationships and parent_relationships.gender == "F":
                    include_parent = True
                    relationship_type = "mother"
                elif "father" in allowed_relationships and parent_relationships.gender == "M":
                    include_parent = True
                    relationship_type = "father"
                
                if include_parent:
                    neighbors.append((parent_id, 1, relationship_type))
    
    # Handle child relationships
    if "child" in allowed_relationships and not exclude_spouse_children:
        neighbors.extend([(child_id, 1, "child") for child_id in person_relationships.children])  # Already sorted during creation
    
    # Add spouse relationships (exclude if requested)
    if "spouse" in allowed_relationships and not exclude_spouse_children:
        neighbors.extend([(spouse_id, 1, "spouse") for spouse_id in person_relationships.spouses])  # Already sorted during creation
    
    # Add sibling relationships (optimized)
    if "sibling" in allowed_relationships:
        siblings = set()
        for parent_id in person_relationships.parents:
            # Use cached parent relationships if available
            parent_relationships = _get_person_relationships_internal(parent_id, gedcom_ctx)
            
            if parent_relationships:
                # OPTIMIZATION: Use set operations for efficiency
                parent_children = set(parent_relationships.children) - {person_id}
                siblings.update(parent_children)
        
        # DETERMINISM FIX: Sort siblings to ensure consistent ordering between process runs
        neighbors.extend([(sibling_id, 1, "sibling") for sibling_id in sorted(siblings)])
    
    # Cache the result
    gedcom_ctx.neighbor_cache[cache_key] = neighbors
    return neighbors


def _get_person_neighbors_lazy_reverse(person_id, allowed_relationships: Set[str], gedcom_ctx, exclude_spouse_children=False, relationships_cache_key=None):
    """Get reverse neighbors (for backward search)"""
    # For family relationships, most are bidirectional, so we can reuse the same function
    return _get_person_neighbors_lazy(person_id, allowed_relationships, gedcom_ctx, exclude_spouse_children=exclude_spouse_children, relationships_cache_key=relationships_cache_key)


def _generate_relationship_chain_lazy(path, allowed_relationships, gedcom_ctx):
    """Generate relationship chain for lazy search with correct directionality"""
    
    if len(path) < 2:
        return []
    
    chain = []
    for i in range(len(path) - 1):
        current = path[i]
        next_person = path[i + 1]
        
        # Get the relationship between current and next
        # First try forward direction
        neighbors = _get_person_neighbors_lazy(current, allowed_relationships, gedcom_ctx)
        found = False
        for neighbor_id, weight, rel_type in neighbors:
            if neighbor_id == next_person:
                # Fix the relationship direction based on the path direction
                corrected_rel = _correct_relationship_direction(rel_type, current, next_person, gedcom_ctx)
                chain.append(corrected_rel)
                found = True
                break
        
        # If not found in forward direction, try reverse direction
        if not found:
            reverse_neighbors = _get_person_neighbors_lazy(next_person, allowed_relationships, gedcom_ctx)
            for neighbor_id, weight, rel_type in reverse_neighbors:
                if neighbor_id == current:
                    # This is the reverse relationship, so we need to invert it
                    if rel_type == "parent":
                        corrected_rel = _correct_relationship_direction("child", current, next_person, gedcom_ctx)
                    elif rel_type == "child":
                        corrected_rel = _correct_relationship_direction("parent", current, next_person, gedcom_ctx)
                    else:
                        # For bidirectional relationships like spouse/sibling
                        corrected_rel = _correct_relationship_direction(rel_type, current, next_person, gedcom_ctx)
                    chain.append(corrected_rel)
                    found = True
                    break
        
        # If still not found, add a fallback
        if not found:
            # We'll need to import logger when this function is used
            # logger.warning(f"Could not find relationship between {current} and {next_person} with allowed relationships {allowed_relationships}")
            chain.append("unknown")
    
    return chain


def _correct_relationship_direction(rel_type, from_person, to_person, gedcom_ctx):
    """Correct the relationship direction to show the path from from_person's perspective"""
    
    if rel_type == "spouse":
        # Check gender of to_person to use wife/husband
        to_person_details = get_person_details_internal(to_person, gedcom_ctx)
        if to_person_details and to_person_details.gender:
            if to_person_details.gender == "F":
                return "wife_of"
            elif to_person_details.gender == "M":
                return "husband_of"
        return "spouse_of"  # fallback if gender unknown
    elif rel_type == "sibling":
        # Check gender of to_person to use brother/sister
        to_person_details = get_person_details_internal(to_person, gedcom_ctx)
        if to_person_details and to_person_details.gender:
            if to_person_details.gender == "F":
                return "sister_of"
            elif to_person_details.gender == "M":
                return "brother_of"
        return "sibling_of"  # fallback if gender unknown
    elif rel_type == "parent":
        # Graph edge "parent" means from_person -> to_person where to_person is from_person's parent
        # So from_person is the child of to_person
        # Check gender of to_person to use mother/father
        to_person_details = get_person_details_internal(to_person, gedcom_ctx)
        if to_person_details and to_person_details.gender:
            if to_person_details.gender == "F":
                return "child_of_mother"
            elif to_person_details.gender == "M":
                return "child_of_father"
        return "child_of"   # fallback if gender unknown
    elif rel_type == "child":
        # Graph edge "child" means from_person -> to_person where to_person is from_person's child
        # So from_person is the parent of to_person
        # Check gender of from_person to use mother/father
        from_person_details = get_person_details_internal(from_person, gedcom_ctx)
        if from_person_details and from_person_details.gender:
            if from_person_details.gender == "F":
                return "mother_of"
            elif from_person_details.gender == "M":
                return "father_of"
        return "parent_of"  # fallback if gender unknown
    else:
        return rel_type


def _generate_relationship_description(path, relationship_chain, gedcom_ctx):
    """Generate a human-readable description of the relationship"""
    
    if len(path) == 1:
        return "Same person"
    
    # Get person names for the description
    person_names = []
    for person_id in path:
        person = get_person_details_internal(person_id, gedcom_ctx)
        person_names.append(person.name if person else "Unknown")
    
    if len(path) == 2:
        rel_desc = _format_relationship_with_gender(relationship_chain[0], path[0], path[1], gedcom_ctx)
        return f"{person_names[0]} is the {rel_desc} {person_names[1]}"
    
    # For longer paths, describe the chain step by step
    description_parts = [person_names[0]]
    
    for i, rel in enumerate(relationship_chain):
        rel_desc = _format_relationship_with_gender(rel, path[i], path[i + 1], gedcom_ctx)
        description_parts.append(f"is the {rel_desc}")
        description_parts.append(person_names[i + 1])
        
        # Add connector for next relationship
        if i < len(relationship_chain) - 1:
            description_parts.append(", who")
    
    return " ".join(description_parts)


def _format_relationship_with_gender(rel_type, from_person_id, to_person_id, gedcom_ctx):
    """Format relationship type with gender-specific terms"""
    
    if rel_type in ["child_of_mother", "child_of_father", "child_of"]:
        # Check gender of the child (from_person)
        from_person = get_person_details_internal(from_person_id, gedcom_ctx)
        if from_person and from_person.gender:
            if from_person.gender == "M":
                return "son of"
            elif from_person.gender == "F":
                return "daughter of"
        return "child of"  # fallback if gender unknown
    elif rel_type == "mother_of":
        return "mother of"
    elif rel_type == "father_of":
        return "father of"
    elif rel_type == "parent_of":
        return "parent of"
    elif rel_type in ["spouse", "spouse_of"]:
        # Check gender of the spouse (from_person) to determine if they are husband or wife
        from_person = get_person_details_internal(from_person_id, gedcom_ctx)
        if from_person and from_person.gender:
            if from_person.gender == "M":
                return "husband of"
            elif from_person.gender == "F":
                return "wife of"
        return "spouse of"  # fallback if gender unknown
    elif rel_type == "wife_of":
        return "wife of"
    elif rel_type == "husband_of":
        return "husband of"
    elif rel_type in ["sibling", "sibling_of"]:
        # Could also be "brother of" or "sister of"
        from_person = get_person_details_internal(from_person_id, gedcom_ctx)
        if from_person and from_person.gender:
            if from_person.gender == "M":
                return "brother of"
            elif from_person.gender == "F":
                return "sister of"
        return "sibling_of"  # fallback if gender unknown
    elif rel_type == "sister_of":
        return "sister of"
    elif rel_type == "brother_of":
        return "brother of"
    else:
        return rel_type


def _format_relationship_description(rel_type):
    """Format relationship type into readable description"""
    if rel_type == "child_of":
        return "child of"
    elif rel_type == "child_of_mother":
        return "child of"  # The gender info is in the person name context
    elif rel_type == "child_of_father":
        return "child of"  # The gender info is in the person name context
    elif rel_type == "parent_of":
        return "parent of"
    elif rel_type == "mother_of":
        return "mother of"
    elif rel_type == "father_of":
        return "father of"
    elif rel_type in ["spouse", "spouse_of"]:
        return "spouse of"
    elif rel_type == "wife_of":
        return "wife of"
    elif rel_type == "husband_of":
        return "husband of"
    elif rel_type in ["sibling", "sibling_of"]:
        return "sibling of"
    elif rel_type == "sister_of":
        return "sister of"
    elif rel_type == "brother_of":
        return "brother of"
    else:
        return rel_type

def _find_shortest_relationship_path_internal(person1_id: str, person2_id: str, allowed_relationships: str, gedcom_ctx, max_distance: int = 30, exclude_initial_spouse_children: bool = False, min_distance: int = 0) -> str:
    """Find the shortest relationship path between two people
    
    Args:
        person1_id: First person's ID
        person2_id: Second person's ID  
        allowed_relationships: Comma-separated list of allowed relationship types:
                              - "spouse" (marriage relationships)
                              - "mother" (mother-child relationships only)
                              - "father" (father-child relationships only)  
                              - "parents" (both mother and father relationships)
                              - "children" (parent-child relationships, person -> children)
                              - "blood" (both parents and children, no spouse)
                              - "sibling" (siblings through common parents)
                              - "all" (all relationship types)
                              - "default" (spouse, parents, children - typical family relationships)
                              Examples: "parents", "blood", "parents,sibling", "all"
        max_distance: Maximum relationship distance to search (default: 30)
                     Stops searching if no path found within this distance
                     If path exists but exceeds max_distance, returns "path too long" result
        exclude_initial_spouse_children: If True, excludes spouse and children links for the two initial people
                                       This allows finding relationships like cousins without considering direct marriage/children
                                       (default: False)
        min_distance: Minimum relationship distance required (default: 0)
                     If > 0, will find the shortest path that is at least this distance long
                     Useful for finding distant relationships while avoiding immediate family
    
    Returns:
        JSON with shortest path, relationship chain, and distance
        If path exceeds max_distance, returns result with "path_too_long": true
    """
    logger = logging.getLogger(__name__)
    
    # Validate that both people exist
    from gedcom_data_access import get_person_details_internal
    person1 = get_person_details_internal(person1_id, gedcom_ctx)
    person2 = get_person_details_internal(person2_id, gedcom_ctx)
    
    if not person1:
        return f"Person not found: {person1_id}"
    if not person2:
        return f"Person not found: {person2_id}"
    
    if person1_id == person2_id:
        return f'{{"path": ["{person1_id}"], "distance": 0, "relationship_chain": ["self"], "description": "Same person"}}'
    
    # Validate max_distance
    if max_distance < 1:
        max_distance = 30
        
    try:
        import time
        start_time = time.time()
        
        # Parse allowed relationships
        parse_start = time.time()
        allowed = set()
        allowed_relationships_lower = allowed_relationships.lower()
        
        if allowed_relationships_lower == "all":
            allowed = {"parent", "spouse", "sibling"}
        elif allowed_relationships_lower == "default":
            allowed = {"parent", "spouse", "child"}  # Default: spouse, parents, children
        elif allowed_relationships_lower == "blood":
            allowed = {"parent", "child"}  # Blood relationships only
        elif allowed_relationships_lower == "parents":
            allowed = {"parent"}  # Parents only (both mother and father)
        elif allowed_relationships_lower == "children":
            allowed = {"child"}  # Children only
        else:
            # Parse comma-separated list and expand special types
            raw_relationships = {rel.strip().lower() for rel in allowed_relationships.split(",")}
            allowed = set()
            
            for rel in raw_relationships:
                if rel == "spouse":
                    allowed.add("spouse")
                elif rel == "mother":
                    allowed.add("mother")  # Will be handled specially in neighbor function
                elif rel == "father":
                    allowed.add("father")  # Will be handled specially in neighbor function
                elif rel == "parents":
                    allowed.add("parent")  # Both mother and father
                elif rel == "children":
                    allowed.add("child")
                elif rel == "blood":
                    allowed.update({"parent", "child"})
                elif rel == "sibling":
                    allowed.add("sibling")
                elif rel == "parent":
                    allowed.add("parent")
                elif rel == "child":
                    allowed.add("child")
                elif rel == "all":
                    allowed.update({"parent", "spouse", "sibling", "child"})
                else:
                    logger.warning(f"Unknown relationship type: {rel}")
        
        parse_time = time.time() - parse_start
        logger.info(f"PERF: Relationship parsing took {parse_time:.3f}s, allowed: {allowed}")
        
        # Use optimized lazy bidirectional search
        search_start = time.time()
        logger.info(f"PERF: Starting bidirectional search (max distance: {max_distance}, min distance: {min_distance})")
        path, distance = _dijkstra_bidirectional_search(person1_id, person2_id, allowed, gedcom_ctx, max_distance, exclude_initial_spouse_children, min_distance)
        
        search_time = time.time() - search_start
        logger.info(f"PERF: Bidirectional search took {search_time:.3f}s")

        
        if path is None:
            total_time = time.time() - start_time
            logger.info(f"PERF: Total time (no path found): {total_time:.3f}s")
            if min_distance > 0:
                return f'{{"path": null, "distance": -1, "relationship_chain": [], "description": "No relationship path found with minimum distance {min_distance} using allowed relationship types: {allowed_relationships}. Try reducing min_distance or using different relationship types."}}'
            else:
                return f'{{"path": null, "distance": -1, "relationship_chain": [], "description": "No relationship path found with allowed relationship types: {allowed_relationships}"}}'
        
        # Generate relationship chain description
        chain_start = time.time()
        relationship_chain = _generate_relationship_chain_lazy(path, allowed, gedcom_ctx)
        description = _generate_relationship_description(path, relationship_chain, gedcom_ctx)
        chain_time = time.time() - chain_start
        logger.info(f"PERF: Relationship chain generation took {chain_time:.3f}s")
        
        # Get person names for the path and create detailed description
        names_start = time.time()
        path_with_names = []
        detailed_path_description = []
        
        for i, person_id in enumerate(path):
            person = get_person_details_internal(person_id, gedcom_ctx)
            person_name = person.name if person else "Unknown"
            path_with_names.append({
                "id": person_id,
                "name": person_name
            })
            
            # Create step-by-step description
            if i < len(path) - 1:  # Not the last person
                rel_type = relationship_chain[i]
                next_person = get_person_details_internal(path[i + 1], gedcom_ctx)
                next_name = next_person.name if next_person else "Unknown"
                
                if rel_type in ["child_of", "child_of_mother", "child_of_father"]:
                    detailed_path_description.append(f"{person_name} -> {rel_type} -> {next_name}")
                elif rel_type in ["parent_of", "mother_of", "father_of"]:
                    detailed_path_description.append(f"{person_name} -> {rel_type} -> {next_name}")
                elif rel_type in ["spouse", "spouse_of", "wife_of", "husband_of"]:
                    detailed_path_description.append(f"{person_name} -> {rel_type} -> {next_name}")
                elif rel_type in ["sibling", "sibling_of", "sister_of", "brother_of"]:
                    detailed_path_description.append(f"{person_name} -> {rel_type} -> {next_name}")
                else:
                    detailed_path_description.append(f"{person_name} -> {rel_type} -> {next_name}")
        
        names_time = time.time() - names_start
        logger.info(f"PERF: Name lookup took {names_time:.3f}s for {len(path)} people")
        
        # Build performance info
        performance_info = {
            "total_time": time.time() - start_time,
            "search_time": search_time,
            "chain_generation_time": chain_time,
            "name_lookup_time": names_time,
            "algorithm_used": "bidirectional_lazy"
        }
        
        result = {
            "person1": {"id": person1_id, "name": person1.name},
            "person2": {"id": person2_id, "name": person2.name},
            "distance": distance,
            "path": path_with_names,
            "relationship_chain": relationship_chain,
            "description": description,
            "detailed_path": detailed_path_description,
            "allowed_relationships": list(allowed),
            "performance": performance_info
        }
        
        total_time = time.time() - start_time
        logger.info(f"PERF: Total shortest path operation took {total_time:.3f}s")
        
        return json.dumps(result, indent=2)
    
    except Exception as e:
        return f"Error finding relationship path: {e}\n{traceback.format_exc()}"


def _find_all_relationship_paths_internal(person1_id: str, person2_id: str, allowed_relationships: str, gedcom_ctx, max_distance: int = 15, max_paths: int = 10) -> str:
    """Find all relationship paths between two people, sorted by distance
    
    Args:
        person1_id: First person's ID
        person2_id: Second person's ID  
        allowed_relationships: Comma-separated list of allowed relationship types:
                              - \"parent\" (parent-child relationships)
                              - \"spouse\" (marriage relationships)
                              - \"sibling\" (siblings through common parents)
                              - \"all\" (default: all relationship types)
        max_distance: Maximum relationship distance to search (default: 15)
        max_paths: Maximum number of paths to return (default: 10)
    
    Returns:
        JSON with all paths found, sorted from shortest to longest
    """
    logger = logging.getLogger(__name__)
    
    # Validate that both people exist
    person1 = get_person_details_internal(person1_id, gedcom_ctx)
    person2 = get_person_details_internal(person2_id, gedcom_ctx)
    
    if not person1:
        return f"Person not found: {person1_id}"
    if not person2:
        return f"Person not found: {person2_id}"
    
    if person1_id == person2_id:
        return f'{"paths": [{"path": ["{person1_id}"], "distance": 0, "relationship_chain": ["self"], "description": "Same person"}], "total_paths": 1}'
    
    # Validate parameters
    if max_distance < 1:
        max_distance = 15
    if max_paths < 1:
        max_paths = 10
    
    try:
        start_time = time.time()
        
        # Parse allowed relationships
        allowed = set()
        if allowed_relationships.lower() == "all":
            allowed = {"parent", "spouse", "sibling"}
        else:
            allowed = {rel.strip().lower() for rel in allowed_relationships.split(",")}
        
        logger.info(f"PERF: Finding all paths from {person1_id} to {person2_id} (max distance: {max_distance}, max paths: {max_paths})")
        
        # Find all paths using modified DFS
        all_paths = _find_all_paths_dfs(person1_id, person2_id, allowed, gedcom_ctx, max_distance, max_paths)
        
        if not all_paths:
            total_time = time.time() - start_time
            logger.info(f"PERF: No paths found in {total_time:.3f}s")
            return f'{"paths": [], "total_paths": 0, "search_time": {total_time:.3f}}'
        
        # Sort paths by distance (shortest first)
        all_paths.sort(key=lambda p: p["distance"])
        
        # Filter out redundant/silly paths
        all_paths = _filter_redundant_paths(all_paths, gedcom_ctx)
        
        # Limit to max_paths
        all_paths = all_paths[:max_paths]
        
        # Generate relationship chains and descriptions for each path
        for path_info in all_paths:
            path = path_info["path"]
            relationship_chain = _generate_relationship_chain_lazy(path, allowed, gedcom_ctx)
            description = _generate_relationship_description(path, relationship_chain, gedcom_ctx)
            
            path_info["relationship_chain"] = relationship_chain
            path_info["description"] = description
            
            # Add person names to path
            path_with_names = []
            for person_id in path:
                person = get_person_details_internal(person_id, gedcom_ctx)
                person_name = person.name if person else "Unknown"
                path_with_names.append({"id": person_id, "name": person_name})
            path_info["path"] = path_with_names
        
        total_time = time.time() - start_time
        
        result = {
            "person1": {"id": person1_id, "name": person1.name},
            "person2": {"id": person2_id, "name": person2.name},
            "paths": all_paths,
            "total_paths": len(all_paths),
            "search_time": total_time
        }
        
        return json.dumps(result, indent=2)
    
    except Exception as e:
        return f"Error finding all relationship paths: {e}\n{traceback.format_exc()}"

def _find_all_paths_dfs(start_node, end_node, allowed_relationships, gedcom_ctx, max_depth, max_paths):
    """Internal DFS function to find all paths"""
    all_paths = []
    
    # We'll use a stack for DFS, storing tuples of (current_node, path_list)
    stack = [(start_node, [start_node])]
    
    while stack:
        current_node, path = stack.pop()
        
        # If we found the end node, add this path to our results
        if current_node == end_node:
            all_paths.append({
                "path": path,
                "distance": len(path) - 1
            })
            # Stop if we've found enough paths
            if len(all_paths) >= max_paths:
                break
            continue # Don't explore further from the end node
        
        # If the path is too long, stop exploring this branch
        if len(path) > max_depth:
            continue
            
        # Get neighbors and add them to the stack
        neighbors = _get_person_neighbors_lazy(current_node, allowed_relationships, gedcom_ctx)
        
        for neighbor_id, weight, rel_type in neighbors:
            # Avoid cycles by not revisiting nodes in the current path
            if neighbor_id not in path:
                new_path = path + [neighbor_id]
                stack.append((neighbor_id, new_path))
                
    return all_paths

def _filter_redundant_paths(paths, gedcom_ctx):
    """Filter out paths that are simply longer versions of shorter paths.
    
    For example, if we have a path A -> B -> C, and another path A -> D -> B -> C,
    the second path is redundant because it just adds an extra step to get to B.
    """
    if not paths:
        return []
    
    # Sort paths by length (shortest first)
    paths.sort(key=lambda p: len(p["path"]))
    
    unique_paths = []
    
    for i, p1 in enumerate(paths):
        is_redundant = False
        for j, p2 in enumerate(paths):
            if i == j:
                continue
            
            # If p1's path is a sub-path of p2's path, then p2 is redundant
            # This is a simple check - more complex redundancy could exist
            if len(p1["path"]) < len(p2["path"]):
                # Check if p1 is a subsequence of p2
                # This is not perfect, but a good heuristic
                if all(item in p2["path"] for item in p1["path"]):
                    # This is a weak check, let's do a stronger one
                    # Check if p1 is a contiguous sublist of p2
                    is_sublist = False
                    for k in range(len(p2["path"]) - len(p1["path"]) + 1):
                        if p2["path"][k:k+len(p1["path"])] == p1["path"]:
                            is_sublist = True
                            break
                    
                    if is_sublist:
                        # p1 is a sublist of p2, so p2 is redundant if we already have p1
                        # But we are iterating from shortest to longest, so we just need to check
                        # if p1 makes p2 redundant
                        pass
            
            # A better check: if p2 contains all nodes of p1, and is longer, it's likely redundant
            if set(p1["path"]).issubset(set(p2["path"])) and len(p1["path"]) < len(p2["path"]):
                # This is a good sign of redundancy, especially if they share start/end nodes
                if p1["path"][0] == p2["path"][0] and p1["path"][-1] == p2["path"][-1]:
                    is_redundant = True
                    # We can't break here, because p1 might be redundant with another path
                    # But we can mark p1 as redundant if it's a superset of a shorter path
    
    # This is still not quite right. A simpler filter:
    # For each path, check if any other path is "better".
    # A path is "better" if it's shorter and connects the same two people.
    # But we already sorted by length, so we just need to remove longer paths
    # that are supersets of shorter paths.
    
    final_paths = []
    for i in range(len(paths)):
        is_redundant = False
        for j in range(i):
            # If path i is a superset of a shorter path j
            if set(paths[j]["path"]).issubset(set(paths[i]["path"])):
                is_redundant = True
                break
        if not is_redundant:
            final_paths.append(paths[i])
            
    return final_paths


def _find_all_paths_to_ancestor_internal(start_person_id: str, ancestor_id: str, gedcom_ctx, max_paths: int = 10) -> List[List[str]]:
    """
    Find all paths from a person to a specific ancestor, following only parent relationships.
    
    Args:
        start_person_id: The ID of the person to start from
        ancestor_id: The ID of the ancestor to search for
        gedcom_ctx: The GEDCOM context
        max_paths: Maximum number of paths to return (default: 10)
        
    Returns:
        List of paths, where each path is a list of person IDs from start_person_id to ancestor_id
    """
    if not gedcom_ctx.gedcom_parser:
        return []
    
    # Check if both people exist
    start_person = get_person_details_internal(start_person_id, gedcom_ctx)
    ancestor = get_person_details_internal(ancestor_id, gedcom_ctx)
    
    if not start_person:
        raise ValueError(f"Start person not found: {start_person_id}")
    if not ancestor:
        raise ValueError(f"Ancestor not found: {ancestor_id}")
    
    # If they're the same person, return a single path with just that person
    if start_person_id == ancestor_id:
        return [[start_person_id]]
    
    all_paths = []
    
    def dfs_find_ancestor_paths(current_id: str, current_path: List[str], visited: Set[str]):
        # Limit the number of paths we return
        if len(all_paths) >= max_paths:
            return
        
        # If we've found the ancestor, add this path to our results
        if current_id == ancestor_id:
            all_paths.append(current_path.copy())
            return
        
        # Get the current person's details
        person = get_person_details_internal(current_id, gedcom_ctx)
        if not person or not person.parents:
            return
        
        # Explore each parent
        for parent_id in person.parents:
            # Avoid cycles
            if parent_id not in visited:
                visited.add(parent_id)
                current_path.append(parent_id)
                dfs_find_ancestor_paths(parent_id, current_path, visited)
                current_path.pop()
                visited.remove(parent_id)
    
    # Start the search
    visited = {start_person_id}
    path = [start_person_id]
    dfs_find_ancestor_paths(start_person_id, path, visited)
    
    return all_paths

