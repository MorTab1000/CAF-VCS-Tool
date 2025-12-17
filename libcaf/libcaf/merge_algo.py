from typing import Set, Optional
from libcaf.repository import Repository, load_commit

def get_commit_parents(repo: Repository, commit_hash: str) -> list[str]:
    """Helper to get parent(s) of a commit. 
    Currently handles single parent, but easy to expand for merge commits later."""
    if not commit_hash:
        return []
    
    try:
        commit = load_commit(repo.objects_dir(), commit_hash)
        # Assuming your Commit object has a .parent_hash or .parent attribute
        # Adjust 'parent' to match your actual Commit class attribute name
        if commit.parent: 
            return [commit.parent]
        return []
    except Exception:
        return []

def find_lca(repo: Repository, hash_a: str, hash_b: str) -> Optional[str]:
    """
    Finds the Lowest Common Ancestor (LCA) of two commits.
    """
    if not hash_a or not hash_b:
        return None
    
    if hash_a == hash_b:
        return hash_a

    # 1. Collect all ancestors of A
    ancestors_a: Set[str] = set()
    stack = [hash_a]
    
    while stack:
        current = stack.pop()
        if current in ancestors_a:
            continue
        
        # Add parents to stack
        parents = get_commit_parents(repo, current)
        stack.extend(parents)

    # 2. Walk up B's history and look for the first match in A's set
    # Using a BFS here ensures we find the "closest" ancestor first
    queue = [hash_b]
    visited_b: Set[str] = set()

    while queue:
        current = queue.pop(0) # FIFO for BFS (closest first)
        
        if current in ancestors_a:
            return current # Found it!
        
        if current in visited_b:
            continue
        visited_b.add(current)
        
        parents = get_commit_parents(repo, current)
        queue.extend(parents)

    return None # No common ancestor found (orphan branches)