from collections import deque
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Union, Tuple, Callable
from . import TreeRecordType, Tree, TreeRecord
from libcaf.plumbing import load_tree, load_commit


def find_lca(repo_objects_dir: Path, hash_a: str, hash_b: str) -> Optional[str]:
    """
    Finds the Lowest Common Ancestor (LCA) of two commits.
    """
    if not hash_a or not hash_b:
        return None
    
    if hash_a == hash_b:
        return hash_a

    # 1. Collect all ancestors of A
    ancestors_a: set[str] = set()
    stack = [hash_a]
    
    while stack:
        current = stack.pop()
        if current in ancestors_a:
            continue
        
        ancestors_a.add(current)
        commit = load_commit(repo_objects_dir, current)
        stack.extend(commit.parents)

    # 2. Walk up B's history and look for the first match in A's set
    # Using a BFS here ensures we find the "closest" ancestor first
    queue = deque([hash_b])
    visited_b: set[str] = set()

    while queue:
        current = queue.popleft() # FIFO for BFS (closest first)
        
        if current in ancestors_a:
            return current
        
        if current in visited_b:
            continue
        visited_b.add(current)
        commit = load_commit(repo_objects_dir, current)
        parents = commit.parents
        queue.extend(parents) # Add from the right

    return None # No common ancestor found (orphan branches)


@dataclass(frozen=True)
class MergeConflict:
    """An immutable record of a conflict to be resolved by the execution engine."""
    base_hash: Optional[str]
    ours_hash: Optional[str]
    theirs_hash: Optional[str]
    conflict_type: str  # "content", "modify/delete", or "type"

MergeResult = Dict[str, Union[TreeRecord, MergeConflict, dict]]


def merge_trees(base_hash: Optional[str], ours_hash: Optional[str], theirs_hash: Optional[str], fetch_tree: Callable[[str], Tree]) -> MergeResult:
    """
    Compares three trees and returns the NEW directory structure.
    Recursively handles sub-directories.
    """
    # 1. Load the three tree dictionaries (Path -> Hash)
    # (Helper function 'load_tree_dict' returns {} if hash is None)
    result = {}
    base_records = fetch_tree(base_hash).records if base_hash else {}
    ours_records = fetch_tree(ours_hash).records if ours_hash else {}
    theirs_records = fetch_tree(theirs_hash).records if theirs_hash else {}

    all_paths = sorted(set(base_records) | set(ours_records) | set(theirs_records))

    for path in all_paths:
        b_rec, o_rec, t_rec = base_records.get(path), ours_records.get(path), theirs_records.get(path)
        b_hash = b_rec.hash if b_rec else None
        o_hash, o_type = (o_rec.hash, o_rec.type) if o_rec else (None, None)
        t_hash, t_type = (t_rec.hash, t_rec.type) if t_rec else (None, None)         

         #case 1: fast forward or identical     
        if o_hash == t_hash:
            if o_hash:
                result[path] = o_rec
        
        elif b_hash == o_hash:
            if t_hash:
                result[path] = t_rec
        
        elif b_hash == t_hash:
            if o_hash:
                result[path] = o_rec

        #case 2: both dirs, need to recurse
        elif o_type == t_type == TreeRecordType.TREE:            
            result[path] = merge_trees(b_hash, o_hash, t_hash, fetch_tree)
       
        #case 3: content conflict
        else:
            # categorize the conflict type
            if o_hash is None or t_hash is None:
                conflict_type = "modify/delete"
            elif o_type != t_type:
                conflict_type = "type"
            else:
                conflict_type = "content"
            result[path] = MergeConflict(b_hash, o_hash, t_hash, conflict_type)

    return result
    
def load_tree_dict(repo_dir: Path, tree_hash: Optional[str]) -> Dict[str, tuple[str, TreeRecordType]]:
    """Helper to load a tree and return a dict of name -> hash. Returns {} if tree_hash is None."""
    if tree_hash is None:
        return {}
    tree = load_tree(repo_dir, tree_hash)
    return {rec.name: (rec.hash, rec.type) for rec in tree.records.values()}