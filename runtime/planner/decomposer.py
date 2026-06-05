"""
Task Decomposer for OpenSarthi.
Computes groups of independent plan steps that can be executed in parallel.
"""
from typing import List
from planner.schemas import PlanStep

def get_parallel_groups(steps: List[PlanStep]) -> List[List[int]]:
    """
    Computes parallel execution groups using topological sorting/leveling.
    Returns a list of lists, where each sublist contains the indices of steps
    that can be executed concurrently in that round.
    If a cycle or invalid dependency is detected, falls back to sequential groups
    (each step in its own group).
    """
    n = len(steps)
    if n == 0:
        return []

    # 1. Validate dependencies
    for i, step in enumerate(steps):
        deps = getattr(step, "depends_on", []) or []
        for dep in deps:
            if not isinstance(dep, int) or dep < 0 or dep >= n or dep == i:
                # Invalid dependency, fallback to sequential
                return [[j] for j in range(n)]

    # 2. Build graph and in-degrees
    adj = {i: [] for i in range(n)}
    in_degree = {i: 0 for i in range(n)}
    
    for i, step in enumerate(steps):
        deps = getattr(step, "depends_on", []) or []
        for dep in deps:
            adj[dep].append(i)
            in_degree[i] += 1

    # 3. BFS to group by level (topological sorting levels)
    current_level = [i for i in range(n) if in_degree[i] == 0]
    
    # If no step has in_degree 0, but there are steps, we have a cycle or invalid state.
    if not current_level and n > 0:
        return [[j] for j in range(n)]

    groups = []
    visited_count = 0
    
    while current_level:
        groups.append(current_level)
        visited_count += len(current_level)
        
        next_level = []
        for u in current_level:
            for v in adj[u]:
                in_degree[v] -= 1
                if in_degree[v] == 0:
                    next_level.append(v)
        current_level = next_level

    if visited_count < n:
        # Cycle detected! Fall back to sequential execution.
        return [[j] for j in range(n)]

    return groups
