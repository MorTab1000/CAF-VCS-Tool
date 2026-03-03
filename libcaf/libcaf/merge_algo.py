from collections import deque
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, Dict, Union, Tuple
from . import TreeRecordType, TreeRecord
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

MergeResult = Dict[str, Union[Tuple[str, TreeRecordType], MergeConflict, dict]]


def merge_trees(repo_dir: Path, base_hash: Optional[str], ours_hash: Optional[str], theirs_hash: Optional[str]) -> MergeResult:
    """
    Compares three trees and returns the NEW directory structure.
    Recursively handles sub-directories.
    """
    # 1. Load the three tree dictionaries (Path -> Hash)
    # (Helper function 'load_tree_dict' returns {} if hash is None)
    result = {}
    base_tree = load_tree_dict(repo_dir, base_hash)
    ours_tree = load_tree_dict(repo_dir, ours_hash)
    theirs_tree = load_tree_dict(repo_dir, theirs_hash)

    all_paths = sorted(set(base_tree) | set(ours_tree) | set(theirs_tree))

    for path in all_paths:
        b_hash, _ = base_tree.get(path, (None, None))
        o_hash, o_type = ours_tree.get(path, (None, None))
        t_hash, t_type = theirs_tree.get(path, (None, None))

         #case 1: fast forward or identical     
        if o_hash == t_hash:
            if o_hash:
                result[path] = (o_hash, o_type)
        
        elif b_hash == o_hash:
            if t_hash:
                result[path] = (t_hash, t_type)
        
        elif b_hash == t_hash:
            if o_hash:
                result[path] = (o_hash, o_type)

        #case 2: both dirs, need to recurse
        elif o_type == t_type == TreeRecordType.TREE:            
            sub_result = merge_trees(repo_dir, b_hash, o_hash, t_hash)
            result[path] = sub_result
       
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